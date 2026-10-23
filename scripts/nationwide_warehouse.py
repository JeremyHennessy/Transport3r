"""Build a provenance-preserving nationwide DuckDB from verified full source cuts.

Every CSV row and column is retained as text. Unresolved identities remain in the
raw tables and mapping audit; they are never silently dropped or assigned.
"""
import argparse,json,pathlib,re,sys,os
from verify_snapshot import verify
from source_contract import source_contracts
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'outputs/nationwide-runtime'))

def ident(value):
    return '"'+value.replace('"','""')+'"'
def literal(value):
    return "'"+str(value).replace("'","''")+"'"
def table(source):
    if not re.fullmatch('[a-z0-9]{4}-[a-z0-9]{4}',source):raise ValueError('Invalid source identity')
    return 'raw_'+source.replace('-','_')
def canonical(column):
    value=f'trim(cast({column} AS VARCHAR))';digits=f"regexp_replace({value}, '[.]0+$', '')"
    return f"CASE WHEN regexp_full_match({value}, '[0-9]+([.]0+)?') AND ltrim({digits}, '0') <> '' THEN ltrim({digits}, '0') END"
def text(column):
    return f"nullif(trim(cast({column} AS VARCHAR)),'')"
def docket_key(column):
    return f'upper({text(column)})'
def parsed_date(column):
    value=text(column)
    return (f"coalesce(try_strptime({value},'%Y%m%d')::DATE,try_strptime({value},'%m%d%Y')::DATE,"
            f"try_strptime({value},'%Y%m%d %H%M')::DATE,try_strptime({value},'%Y%m%d %H%M%S')::DATE,"
            f"try_strptime({value},'%m%d%Y %H%M')::DATE,try_strptime({value},'%Y%m%d%H%M')::DATE,"
            f"try_strptime({value},'%m/%d/%Y')::DATE,try_strptime({value},'%d-%b-%y')::DATE,"
            f"try_strptime({value},'%d-%b-%Y')::DATE,try_strptime({value},'%Y-%m-%dT%H:%M:%S.%f')::DATE,"
            f"try_strptime({value},'%Y-%m-%dT%H:%M:%S')::DATE,try_cast({value} AS DATE))")

def verified_sources(folder):
    folder=pathlib.Path(folder).resolve()
    collection=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    catalog=json.loads((ROOT/'data/fmcsa_sources.json').read_text(encoding='utf-8'))
    if collection.get('schema_version')!=7 or collection.get('status')!='COMPLETE':raise ValueError('Nationwide collection is not complete')
    entries=collection['sources']
    if len(entries)!=len(catalog) or {e['id'] for e in entries}!={e['id'] for e in catalog}:raise ValueError('Nationwide source coverage mismatch')
    for entry in entries:
        cut=(folder/entry['cut']).resolve()
        if not cut.is_relative_to(folder):raise ValueError('Source cut escaped collection')
        result=verify(cut)
        manifest=json.loads((cut/'manifest.json').read_text(encoding='utf-8'))
        if result['source_count']!=1 or manifest['datasets'][0]['id']!=entry['id']:raise ValueError('Wrong source cut')
        item=manifest['datasets'][0]
        if item['row_count']!=entry['rows'] or item['bytes']!=entry['bytes']:raise ValueError('Collection totals disagree')
        yield cut,item

def load_source(db,cut,item):
    metadata=json.loads((cut/item['metadata_after']).read_text(encoding='utf-8'))
    columns=[c['fieldName'] for c in metadata['metadata']['columns'] if not c.get('fieldName','').startswith(':')]
    if len(set(columns))!=len(columns) or '_warehouse_row_id' in columns:raise ValueError('Ambiguous source columns')
    name=table(item['id'])
    # Explicit text columns avoid losing leading zeros or interpreting source dates.
    schema='{'+','.join(literal(c)+":'VARCHAR'" for c in columns)+'}'
    db.execute(f"CREATE TABLE {name} AS SELECT row_number() OVER () AS _warehouse_row_id,* FROM read_csv({literal(cut/item['path'])}, header=true, auto_detect=false, columns={schema}, delim=',', quote='\"', escape='\"', parallel=false, strict_mode=true, nullstr='')")
    count=db.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
    published=int(metadata['row_count']);acquired=item['row_count']
    if published!=acquired or acquired!=count:raise ValueError('Published, acquired and warehouse source counts differ')
    db.execute('INSERT INTO source_lineage VALUES (?,?,?,?,?,?,?,?)',
               [item['id'],str(cut),item['sha256'],item['available_at'],item['rows_updated_at'],published,acquired,count])
    return columns

def mapping_sql(source,columns,contract):
    raw=table(source);identity=contract['identity'];strategy=identity['strategy']
    if strategy in ('direct_usdot','direct_usdot_legacy'):
        field=identity['field'];candidate=canonical('r.'+ident(field))
        if field not in columns:raise ValueError('Contracted USDOT field unavailable: '+source)
        reason=("CASE WHEN q._candidate_dot IS NULL THEN 'INVALID_DOT' "
                +("WHEN c.census_rows=1 THEN 'CENSUS_SELF_RESOLVED' " if source=='az4n-8mr2' else "")+
                "WHEN c.dot IS NULL THEN 'DIRECT_ID_NO_CENSUS_RECORD' WHEN c.census_rows<>1 THEN 'DIRECT_ID_AMBIGUOUS_CENSUS' "
                "ELSE 'DIRECT_ID_CENSUS_RESOLVED' END")
        status="CASE WHEN q._candidate_dot IS NULL THEN 'UNRESOLVED' WHEN c.dot IS NULL OR c.census_rows<>1 THEN 'IDENTIFIED_ONLY' ELSE 'RESOLVED' END"
        return f"SELECT q.* EXCLUDE (_candidate_dot),q._candidate_dot AS _dot_number,{status} AS _mapping_status,{reason} AS _mapping_reason FROM (SELECT r.*,{candidate} AS _candidate_dot FROM {raw} r) q LEFT JOIN census_identity c ON c.dot=q._candidate_dot"
    if strategy=='inspection_parent':
        field=identity['field'];key=text('r.'+ident(field))
        if field not in columns:raise ValueError('Contracted inspection field unavailable: '+source)
        assertion=next((f for f in ('dot_number','usdot_number') if f in columns),None)
        asserted=canonical('r.'+ident(assertion)) if assertion else 'NULL'
        asserted_present=text('r.'+ident(assertion))+' IS NOT NULL' if assertion else 'false'
        parent_valid='p.parent_rows=1 AND p.parent_dots=1 AND p.invalid_parent_dots=0 AND p.dot IS NOT NULL'
        assertion_valid=f'NOT ({asserted_present}) OR ({asserted} IS NOT NULL AND {asserted}=p.dot)'
        candidate=f'CASE WHEN {parent_valid} AND {assertion_valid} THEN p.dot END'
        reason=(f"CASE WHEN {key} IS NULL THEN 'INVALID_PARENT_KEY' WHEN p.inspection_id IS NULL THEN 'MISSING_PARENT' "
                "WHEN p.parent_rows<>1 THEN 'DUPLICATE_PARENT' WHEN p.parent_dots<>1 THEN 'PARENT_DOT_CONFLICT' "
                f"WHEN p.invalid_parent_dots<>0 OR p.dot IS NULL THEN 'PARENT_INVALID_DOT' WHEN {asserted_present} AND {asserted} IS NULL THEN 'CHILD_DOT_INVALID' "
                f"WHEN {asserted_present} AND {asserted}<>p.dot THEN 'CHILD_DOT_CONFLICT' WHEN c.dot IS NULL THEN 'PARENT_DOT_NO_CENSUS_RECORD' "
                "WHEN c.census_rows<>1 THEN 'PARENT_DOT_AMBIGUOUS_CENSUS' ELSE 'INSPECTION_PARENT_CENSUS_RESOLVED' END")
        status=(f"CASE WHEN NOT ({parent_valid}) OR NOT ({assertion_valid}) THEN 'UNRESOLVED' "
                "WHEN c.dot IS NULL OR c.census_rows<>1 THEN 'IDENTIFIED_ONLY' ELSE 'RESOLVED' END")
        return f"SELECT r.*,{candidate} AS _dot_number,{status} AS _mapping_status,{reason} AS _mapping_reason FROM {raw} r LEFT JOIN inspection_identity p ON {key}=p.inspection_id LEFT JOIN census_identity c ON c.dot=p.dot"
    if strategy=='legacy_docket':
        field=identity['field'];key=docket_key('r.'+ident(field))
        if field not in columns:raise ValueError('Contracted docket field unavailable: '+source)
        valid='p.owners=1 AND p.unknown_owners=0 AND p.dot IS NOT NULL'
        candidate=f'CASE WHEN {valid} THEN p.dot END'
        reason=(f"CASE WHEN {key} IS NULL OR NOT regexp_full_match({key},'[A-Z]{{1,3}}[0-9]+') THEN 'INVALID_DOCKET' "
                "WHEN p.docket_number IS NULL THEN 'DOCKET_NOT_FOUND' WHEN p.owners>1 THEN 'DOCKET_MULTIPLE_OWNERS' "
                "WHEN p.unknown_owners>0 OR p.dot IS NULL THEN 'DOCKET_UNKNOWN_OWNER' WHEN c.dot IS NULL THEN 'DOCKET_DOT_NO_CENSUS_RECORD' "
                "WHEN c.census_rows<>1 THEN 'DOCKET_DOT_AMBIGUOUS_CENSUS' ELSE 'DOCKET_CENSUS_RESOLVED' END")
        status=f"CASE WHEN NOT ({valid}) THEN 'UNRESOLVED' WHEN c.dot IS NULL OR c.census_rows<>1 THEN 'IDENTIFIED_ONLY' ELSE 'RESOLVED' END"
        return f"SELECT r.*,{candidate} AS _dot_number,{status} AS _mapping_status,{reason} AS _mapping_reason FROM {raw} r LEFT JOIN docket_identity p ON {key}=p.docket_number LEFT JOIN census_identity c ON c.dot=p.dot"
    raise ValueError('No registered identity mapping for '+source)

def duplicate_rows(db,raw):
    return db.execute(f'SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM (SELECT * EXCLUDE (_warehouse_row_id) FROM {raw}) GROUP BY ALL HAVING count(*)>1)').fetchone()[0]

def date_quality(db,raw,columns,fields):
    if not fields:return []
    expressions=[]
    for field in fields:
        if field not in columns:raise ValueError('Contracted date field unavailable: '+field)
        value=text(ident(field));parsed=parsed_date(ident(field))
        expressions.extend([f'count(*)',f'count(*) FILTER(WHERE {value} IS NULL)',f'count(*) FILTER(WHERE {parsed} IS NOT NULL)',f'min({parsed})',f'max({parsed})'])
    values=db.execute(f"SELECT {','.join(expressions)} FROM {raw}").fetchone();result=[]
    for index,field in enumerate(fields):
        total,missing,valid,earliest,latest=values[index*5:index*5+5]
        result.append({'field':field,'rows':total,'missing':missing,'valid':valid,'invalid':total-missing-valid,
                       'earliest':str(earliest) if earliest else None,'latest':str(latest) if latest else None})
    return result

def map_sources(db,schemas,contracts=None):
    contracts=contracts or source_contracts();inspections=table('fx4q-ay7w');legacy=table('6eyk-hxee');census=table('az4n-8mr2')
    census_dot=canonical('dot_number')
    db.execute(f'CREATE TABLE census_identity AS SELECT {census_dot} AS dot,count(*) AS census_rows FROM {census} WHERE {census_dot} IS NOT NULL GROUP BY 1')
    parent_dot=canonical('dot_number')
    db.execute(f"CREATE TABLE inspection_identity AS SELECT {text('inspection_id')} AS inspection_id,count(*) AS parent_rows,count(DISTINCT {parent_dot}) AS parent_dots,count(*) FILTER(WHERE {parent_dot} IS NULL) AS invalid_parent_dots,min({parent_dot}) AS dot FROM {inspections} GROUP BY 1")
    docket_dot=canonical('dot_number')
    db.execute(f"CREATE TABLE docket_identity AS SELECT {docket_key('docket_number')} AS docket_number,count(DISTINCT {docket_dot}) AS owners,count(*) FILTER(WHERE {docket_dot} IS NULL) AS unknown_owners,min({docket_dot}) AS dot FROM {legacy} GROUP BY 1")
    audit=[]
    for source,columns in schemas.items():
        if source not in contracts:raise ValueError('Missing source contract: '+source)
        raw=table(source);mapped=raw.replace('raw_','carrier_');mapping=raw.replace('raw_','mapping_')
        sql=mapping_sql(source,columns,contracts[source])
        db.execute(f'CREATE TABLE {mapping} AS SELECT _warehouse_row_id,_dot_number,_mapping_status,_mapping_reason FROM ({sql})')
        db.execute(f'CREATE INDEX {mapping}_dot_status ON {mapping}(_dot_number,_mapping_status)')
        db.execute(f'CREATE VIEW {mapped} AS SELECT r.*,m.* EXCLUDE (_warehouse_row_id) FROM {raw} r JOIN {mapping} m USING (_warehouse_row_id)')
        statuses=dict(db.execute(f'SELECT _mapping_status,count(*) FROM {mapping} GROUP BY 1').fetchall())
        reasons=dict(db.execute(f'SELECT _mapping_reason,count(*) FROM {mapping} GROUP BY 1').fetchall())
        raw_count=db.execute(f'SELECT count(*) FROM {raw}').fetchone()[0]
        if sum(statuses.values())!=raw_count or sum(reasons.values())!=raw_count:raise ValueError('Mapping multiplied or dropped source rows')
        distinct=db.execute(f'SELECT count(DISTINCT _dot_number) FROM {mapping} WHERE _dot_number IS NOT NULL').fetchone()[0]
        audit.append({'source':source,'rows':raw_count,'mapping_status':statuses,'mapping_reasons':reasons,
                      'distinct_identified_carriers':distinct,'exact_duplicate_rows':duplicate_rows(db,raw),
                      'date_quality':date_quality(db,raw,columns,contracts[source]['event_date_fields'])})
    return audit

def build(folder,output):
    import duckdb
    folder=pathlib.Path(folder).resolve()
    collection=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    output=pathlib.Path(output).resolve()
    acceptance_path=output.with_suffix('.acceptance.json')
    if output.exists() or acceptance_path.exists():raise FileExistsError('Use a new warehouse filename; existing warehouse artifacts are retained')
    output.parent.mkdir(parents=True,exist_ok=True)
    pending=output.with_suffix('.partial.duckdb')
    if pending.exists():raise FileExistsError('An earlier unpromoted build is retained; use a new output filename')
    db=duckdb.connect(str(pending));db.execute("SET memory_limit='2GB'");db.execute('SET threads=4')
    try:
        db.execute('CREATE TABLE source_lineage(source_id VARCHAR,cut VARCHAR,sha256 VARCHAR,available_at VARCHAR,rows_updated_at BIGINT,published_rows BIGINT,acquired_rows BIGINT,warehouse_rows BIGINT)')
        schemas={}
        for cut,item in verified_sources(folder):
            schemas[item['id']]=load_source(db,cut,item);print(f"Imported {item['id']}: {item['row_count']:,} rows",flush=True)
        contracts=source_contracts()
        if set(contracts)!=set(schemas):raise ValueError('Source contract coverage mismatch')
        audit=map_sources(db,schemas,contracts)
        rows=db.execute('SELECT sum(warehouse_rows) FROM source_lineage').fetchone()[0]
        carriers=db.execute("SELECT count(DISTINCT _dot_number) FROM mapping_az4n_8mr2 WHERE _mapping_status='RESOLVED'").fetchone()[0]
        lineage=[dict(zip(('source','cut','sha256','available_at','rows_updated_at','published_rows','acquired_rows','warehouse_rows'),row))
                 for row in db.execute('SELECT * FROM source_lineage ORDER BY source_id').fetchall()]
        by_source={item['source']:item for item in audit}
        acceptance=[]
        for item in lineage:
            mapping=by_source[item['source']]
            mapped=sum(mapping['mapping_status'].values())
            reasoned=sum(mapping['mapping_reasons'].values())
            if not item['published_rows']==item['acquired_rows']==item['warehouse_rows']==mapped or reasoned!=mapped or any(reason is None for reason in mapping['mapping_reasons']):
                raise ValueError('Every acquired row must have exactly one mapping status and reason')
            acceptance.append({
                'source':item['source'],'sha256':item['sha256'],'rows_updated_at':item['rows_updated_at'],
                'published_rows':item['published_rows'],'acquired_rows':item['acquired_rows'],'warehouse_rows':item['warehouse_rows'],
                'mapping_status':mapping['mapping_status'],'mapping_reasons':mapping['mapping_reasons'],
                'distinct_identified_carriers':mapping['distinct_identified_carriers'],
                'exact_duplicate_rows':mapping['exact_duplicate_rows'],'date_quality':mapping['date_quality'],
                'count_gate':'PASS' if item['published_rows']==item['acquired_rows']==item['warehouse_rows']==mapping['rows'] else 'FAIL',
                'reason_gate':'PASS' if reasoned==mapping['rows'] else 'FAIL',
            })
        unresolved=sum(item['mapping_status'].get('UNRESOLVED',0) for item in audit)
        identified_only=sum(item['mapping_status'].get('IDENTIFIED_ONLY',0) for item in audit)
        resolved=sum(item['mapping_status'].get('RESOLVED',0) for item in audit)
        if resolved+identified_only+unresolved!=rows:
            raise ValueError('Aggregate mapping status totals differ from warehouse rows')
        result={'status':'VERIFIED','cut_id':folder.name,'cut_available_at':collection['completed_at'],'scope':'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES','identity_contract':'FMCSA_CARRIER_IDENTITY_1',
                'sources':len(schemas),'rows':rows,'census_carriers':carriers,
                'mapping_totals':{'resolved':resolved,'identified_only':identified_only,'unresolved':unresolved},
                'acceptance_gates':{'source_coverage':'PASS','published_acquired_warehouse_counts':'PASS',
                                    'row_mapping_accounting':'PASS','unresolved_reason_accounting':'PASS',
                                    'arbitrary_assignment_prevention':'PASS'},
                'source_lineage':lineage,'source_acceptance':acceptance,'mapping_audit':audit,
                'historical_feature_validity':'NOT_CERTIFIED','sms_release_binding':'UNVERIFIED'}
        db.execute('CREATE TABLE warehouse_acceptance AS SELECT ? AS acceptance_json',[json.dumps(result)])
        db.execute('CHECKPOINT');db.close()
        os.link(pending,output)
        pending.unlink()
        with acceptance_path.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
        return result
    finally:db.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('collection');p.add_argument('output');a=p.parse_args();print(json.dumps(build(a.collection,a.output),indent=2))
