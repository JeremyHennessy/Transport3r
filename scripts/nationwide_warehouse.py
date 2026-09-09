"""Build a provenance-preserving nationwide DuckDB from verified full source cuts.

Every CSV row and column is retained as text. Unresolved identities remain in the
raw tables and mapping audit; they are never silently dropped or assigned.
"""
import argparse,json,pathlib,re,sys,os
from verify_snapshot import verify
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
    return f"CASE WHEN regexp_full_match({column}, '[0-9]+') AND ltrim({column}, '0') <> '' THEN ltrim({column}, '0') END"

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
    if count!=item['row_count']:raise ValueError('Warehouse import count differs from verified CSV')
    db.execute('INSERT INTO source_lineage VALUES (?,?,?,?,?,?)',[item['id'],str(cut),item['sha256'],item['available_at'],item['rows_updated_at'],count])
    return columns

def map_sources(db,schemas):
    inspections=table('fx4q-ay7w');legacy=table('6eyk-hxee')
    db.execute(f'CREATE TABLE inspection_identity AS SELECT inspection_id,count(*) AS parent_rows,min({canonical("dot_number")}) AS dot FROM {inspections} GROUP BY inspection_id')
    db.execute(f'CREATE TABLE docket_identity AS SELECT docket_number,count(DISTINCT {canonical("dot_number")}) AS owners,count(*) FILTER(WHERE {canonical("dot_number")} IS NULL) AS unknown_owners,min({canonical("dot_number")}) AS dot FROM {legacy} GROUP BY docket_number')
    children={'wt8s-2hbx','876r-jsdb','qbt8-7vic','5qik-smay'}
    audit=[]
    for source,columns in schemas.items():
        raw=table(source);mapped=raw.replace('raw_','carrier_')
        field=next((f for f in ['dot_number','usdot_number'] if f in columns),None)
        if source in children:
            mismatch=f' OR (r.{ident(field)} IS NOT NULL AND ({canonical("r."+ident(field))} IS NULL OR {canonical("r."+ident(field))} <> p.dot))' if field else ''
            valid=f'p.parent_rows=1 AND p.dot IS NOT NULL AND NOT (false{mismatch})'
            sql=f"SELECT r.*,CASE WHEN {valid} THEN p.dot END AS _dot_number,CASE WHEN {valid} THEN 'MAPPED' ELSE 'UNRESOLVED_PARENT' END AS _mapping_status FROM {raw} r LEFT JOIN inspection_identity p ON r.inspection_id=p.inspection_id"
        elif source=='ypjt-5ydn':
            valid='p.owners=1 AND p.unknown_owners=0 AND p.dot IS NOT NULL'
            sql=f"SELECT r.*,CASE WHEN {valid} THEN p.dot END AS _dot_number,CASE WHEN {valid} THEN 'MAPPED' ELSE 'UNRESOLVED_DOCKET' END AS _mapping_status FROM {raw} r LEFT JOIN docket_identity p ON r.prefix_docket_number=p.docket_number"
        elif field:
            dot=canonical(ident(field));sql=f"SELECT *,{dot} AS _dot_number,CASE WHEN {dot} IS NULL THEN 'UNRESOLVED_DOT' ELSE 'MAPPED' END AS _mapping_status FROM {raw}"
        else:raise ValueError('No registered identity mapping for '+source)
        db.execute(f'CREATE VIEW {mapped} AS {sql}')
        counts=db.execute(f'SELECT _mapping_status,count(*) FROM {mapped} GROUP BY 1').fetchall()
        if sum(n for _,n in counts)!=db.execute(f'SELECT count(*) FROM {raw}').fetchone()[0]:raise ValueError('Mapping multiplied or dropped source rows')
        audit.append({'source':source,'counts':dict(counts)})
    return audit

def build(folder,output):
    import duckdb
    output=pathlib.Path(output).resolve()
    if output.exists():raise FileExistsError('Use a new warehouse filename; existing warehouse is retained')
    output.parent.mkdir(parents=True,exist_ok=True)
    pending=output.with_suffix('.partial.duckdb')
    if pending.exists():raise FileExistsError('An earlier unpromoted build is retained; use a new output filename')
    db=duckdb.connect(str(pending));db.execute("SET memory_limit='2GB'");db.execute('SET threads=4')
    try:
        db.execute('CREATE TABLE source_lineage(source_id VARCHAR,cut VARCHAR,sha256 VARCHAR,available_at VARCHAR,rows_updated_at BIGINT,row_count BIGINT)')
        schemas={}
        for cut,item in verified_sources(folder):
            schemas[item['id']]=load_source(db,cut,item);print(f"Imported {item['id']}: {item['row_count']:,} rows",flush=True)
        audit=map_sources(db,schemas)
        rows=db.execute('SELECT sum(row_count) FROM source_lineage').fetchone()[0]
        carriers=db.execute('SELECT count(DISTINCT _dot_number) FROM carrier_az4n_8mr2').fetchone()[0]
        result={'status':'VERIFIED','scope':'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES','sources':len(schemas),'rows':rows,'census_carriers':carriers,'mapping_audit':audit,'historical_feature_validity':'NOT_CERTIFIED'}
        db.execute('CREATE TABLE warehouse_acceptance AS SELECT ? AS acceptance_json',[json.dumps(result)])
        db.execute('CHECKPOINT');db.close()
        os.link(pending,output)
        with output.with_suffix('.acceptance.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
        return result
    finally:db.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('collection');p.add_argument('output');a=p.parse_args();print(json.dumps(build(a.collection,a.output),indent=2))
