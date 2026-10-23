"""Read verified, Census-resolved carrier evidence from a nationwide DuckDB cut."""
import argparse,json,pathlib,re

from source_contract import catalog_sources,source_contracts
from nationwide_warehouse import table
from verify_snapshot import timestamp


def connect(path):
    import duckdb
    path=pathlib.Path(path).resolve()
    if not path.is_file():raise FileNotFoundError(path)
    return duckdb.connect(str(path),read_only=True)


def acceptance(db):
    rows=db.execute("SELECT acceptance_json FROM warehouse_acceptance").fetchall()
    if len(rows)!=1:raise ValueError('Verified warehouse acceptance receipt unavailable')
    receipt=json.loads(rows[0][0])
    if receipt.get('status')!='VERIFIED' or receipt.get('identity_contract')!='FMCSA_CARRIER_IDENTITY_1':
        raise ValueError('Warehouse is not accepted under the current identity contract')
    if not isinstance(receipt.get('cut_id'),str) or not receipt['cut_id'] or timestamp(receipt.get('cut_available_at','')).utcoffset() is None:
        raise ValueError('Warehouse common-cut availability is invalid')
    expected_gates={'source_coverage','published_acquired_warehouse_counts','row_mapping_accounting',
                    'unresolved_reason_accounting','arbitrary_assignment_prevention'}
    gates=receipt.get('acceptance_gates',{})
    if set(gates)!=expected_gates or any(value!='PASS' for value in gates.values()):raise ValueError('Warehouse acceptance gates are incomplete')
    expected_sources={source['id'] for source in catalog_sources()}
    lineage=receipt.get('source_lineage',[]);source_acceptance=receipt.get('source_acceptance',[])
    if receipt.get('sources')!=len(expected_sources) or len(lineage)!=len(expected_sources) or len(source_acceptance)!=len(expected_sources) or {item.get('source') for item in lineage}!=expected_sources or {item.get('source') for item in source_acceptance}!=expected_sources:
        raise ValueError('Warehouse source acceptance coverage is incomplete')
    lineage_by_source={item['source']:item for item in lineage};mapping_totals={'resolved':0,'identified_only':0,'unresolved':0};warehouse_total=0
    for item in source_acceptance:
        counts=[item.get(key) for key in ('published_rows','acquired_rows','warehouse_rows')]
        lineage_item=lineage_by_source[item['source']]
        lineage_counts=[lineage_item.get(key) for key in ('published_rows','acquired_rows','warehouse_rows')]
        statuses=item.get('mapping_status');reasons=item.get('mapping_reasons')
        if (not re.fullmatch(r'[0-9a-f]{64}',str(lineage_item.get('sha256',''))) or not isinstance(lineage_item.get('rows_updated_at'),int)
                or timestamp(lineage_item.get('available_at','')).utcoffset() is None or item.get('sha256')!=lineage_item['sha256'] or item.get('rows_updated_at')!=lineage_item['rows_updated_at']
                or not all(isinstance(value,int) and value>=0 for value in counts) or len(set(counts))!=1 or counts!=lineage_counts
                or not isinstance(statuses,dict) or set(statuses)-{'RESOLVED','IDENTIFIED_ONLY','UNRESOLVED'}
                or not all(isinstance(value,int) and value>=0 for value in statuses.values()) or sum(statuses.values())!=counts[2]
                or not isinstance(reasons,dict) or not all(isinstance(key,str) and key and isinstance(value,int) and value>=0 for key,value in reasons.items()) or sum(reasons.values())!=counts[2]
                or item.get('count_gate')!='PASS' or item.get('reason_gate')!='PASS'):
            raise ValueError('Warehouse source count acceptance is invalid')
        for key in mapping_totals:mapping_totals[key]+=statuses.get(key.upper(),0)
        warehouse_total+=counts[2]
    totals=receipt.get('mapping_totals',{})
    if set(totals)!={'resolved','identified_only','unresolved'} or not all(isinstance(value,int) and value>=0 for value in totals.values()) or totals!=mapping_totals or sum(totals.values())!=receipt.get('rows') or warehouse_total!=receipt.get('rows'):
        raise ValueError('Warehouse mapping totals are invalid')
    return receipt


def resolved_carrier(db,dot,include_records=True):
    if not isinstance(dot,str) or not re.fullmatch(r'[1-9][0-9]*',dot):raise ValueError('Positive USDOT identifier required')
    receipt=acceptance(db)
    census=db.execute("SELECT count(*) FROM mapping_az4n_8mr2 WHERE _dot_number=? AND _mapping_status='RESOLVED'",[dot]).fetchone()[0]
    if census!=1:raise ValueError('USDOT is not uniquely resolved to one Company Census row in this cut')
    sources=[];total=0
    contracts=source_contracts()
    for source in catalog_sources():
        sid=source['id'];raw=table(sid);mapping=raw.replace('raw_','mapping_')
        count=db.execute(f"SELECT count(*) FROM {mapping} WHERE _dot_number=? AND _mapping_status='RESOLVED'",[dot]).fetchone()[0]
        rows=[]
        if include_records and count:
            cursor=db.execute(f"SELECT r.* EXCLUDE (_warehouse_row_id) FROM {raw} r JOIN {mapping} m USING (_warehouse_row_id) WHERE m._dot_number=? AND m._mapping_status='RESOLVED' ORDER BY r._warehouse_row_id",[dot])
            names=[column[0] for column in cursor.description]
            rows=[dict(zip(names,row)) for row in cursor.fetchall()]
            if len(rows)!=count:raise ValueError('Carrier export count differs from resolved mapping count')
        lineage=next(item for item in receipt['source_lineage'] if item['source']==sid)
        sources.append({'source_id':sid,'grain':contracts[sid]['grain'],'release_group':contracts[sid]['release_group'],
                        'carrier_rows':count,'status':'ROWS_RETURNED' if count else 'NO_ROWS_RETURNED',
                        'scope':'ALL_RESOLVED_ROWS_FOR_USDOT_IN_VERIFIED_NATIONWIDE_CUT','browser_cap_applied':False,
                        'source_available_at':lineage['available_at'],'source_rows_updated_at':lineage['rows_updated_at'],
                        'source_sha256':lineage['sha256'],'rows':rows if include_records else None})
        total+=count
    return {'version':1,'dot_number':dot,'cut_id':receipt.get('cut_id') or pathlib.Path(receipt['source_lineage'][0]['cut']).parents[1].name,
            'cut_available_at':receipt['cut_available_at'],
            'identity_contract':receipt['identity_contract'],'source_count':len(sources),'carrier_rows':total,
            'sources':sources,'completeness_receipt':{
                'status':'VERIFIED','scope':receipt['scope'],'sources_expected':receipt['sources'],
                'sources_returned':len(sources),'published_acquired_warehouse_counts':'PASS',
                'row_mapping_accounting':'PASS','unresolved_rows_excluded_from_carrier_assignment':True,
                'mapping_totals':receipt['mapping_totals'],
                'sms_release_binding':receipt['sms_release_binding'],
                'historical_feature_validity':receipt['historical_feature_validity'],
                'risk_score':None,'forecast':None}}


def read(path,dot,include_records=True):
    db=connect(path)
    try:return resolved_carrier(db,dot,include_records)
    finally:db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('warehouse');parser.add_argument('--dot',required=True);parser.add_argument('--counts-only',action='store_true');args=parser.parse_args()
    print(json.dumps(read(args.warehouse,args.dot,not args.counts_only),indent=2))
