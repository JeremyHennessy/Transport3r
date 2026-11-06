"""Fail-closed Transport3r warehouse count, join-cardinality and provenance audit.

Usage: python scripts/audit_warehouse_integrity.py warehouse.duckdb --output audit.json
Requires duckdb. Read-only: never changes source data or an immutable cut.
"""
import argparse
import hashlib
import json
import pathlib
import sys

def audit(path, deep=False):
    import duckdb
    path=pathlib.Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    db=duckdb.connect(str(path), read_only=True)
    failures=[]
    sources=[]
    try:
        tables={row[0] for row in db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
        if 'source_lineage' not in tables or 'warehouse_acceptance' not in tables:
            raise ValueError('Missing warehouse acceptance or source lineage')
        receipt=json.loads(db.execute('SELECT acceptance_json FROM warehouse_acceptance').fetchone()[0])
        expected={x['source']:x for x in receipt.get('source_acceptance',[])}
        lineage=db.execute('SELECT source_id,sha256,published_rows,acquired_rows,warehouse_rows FROM source_lineage ORDER BY source_id').fetchall()
        if len(lineage)!=receipt.get('sources') or len(expected)!=len(lineage):
            failures.append('Source coverage differs from acceptance receipt')
        for source,sha,published,acquired,warehouse in lineage:
            raw='raw_'+source.replace('-','_')
            mapping='mapping_'+source.replace('-','_')
            carrier='carrier_'+source.replace('-','_')
            entry=expected.get(source,{})
            if any(name not in tables for name in (raw,mapping)):
                failures.append(source+': raw or mapping table missing')
                continue
            raw_rows=db.execute('SELECT count(*) FROM "'+raw+'"').fetchone()[0]
            map_rows=db.execute('SELECT count(*) FROM "'+mapping+'"').fetchone()[0]
            unique_map=db.execute('SELECT count(DISTINCT _warehouse_row_id) FROM "'+mapping+'"').fetchone()[0]
            missing=db.execute('SELECT count(*) FROM "'+raw+'" r LEFT JOIN "'+mapping+'" m USING (_warehouse_row_id) WHERE m._warehouse_row_id IS NULL').fetchone()[0]
            status_rows=dict(db.execute('SELECT _mapping_status,count(*) FROM "'+mapping+'" GROUP BY 1').fetchall())
            reason_rows=dict(db.execute('SELECT _mapping_reason,count(*) FROM "'+mapping+'" GROUP BY 1').fetchall())
            null_reasons=db.execute('SELECT count(*) FROM "'+mapping+'" WHERE _mapping_reason IS NULL OR _mapping_status IS NULL').fetchone()[0]
            expected_counts=entry.get('mapping_status',{})
            checks={'source_counts':raw_rows==published==acquired==warehouse==entry.get('warehouse_rows'),
                    'mapping_cardinality':raw_rows==map_rows==unique_map and missing==0,
                    'mapping_status':status_rows==expected_counts and sum(status_rows.values())==raw_rows,
                    'mapping_reasons':reason_rows==entry.get('mapping_reasons') and null_reasons==0,
                    'provenance':sha==entry.get('sha256')}
            if deep:
                # Exact duplicate rows count only ORIGINAL columns; exclude synthetic row id.
                cols=[r[1] for r in db.execute("PRAGMA table_info('"+raw+"')").fetchall() if r[1]!='_warehouse_row_id']
                if not cols:
                    checks['exact_duplicates']=False
                else:
                    names=','.join('"'+c.replace('"','""')+'"' for c in cols)
                    duplicates=db.execute('SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM "'+raw+'" GROUP BY '+names+' HAVING count(*)>1)').fetchone()[0]
                    checks['exact_duplicates']=duplicates==entry.get('exact_duplicate_rows')
            for name,passed in checks.items():
                if not passed: failures.append(source+': '+name)
            sources.append({'source':source,'sha256':sha,'published':published,'acquired':acquired,
                            'warehouse':warehouse,'actual_raw':raw_rows,'actual_mapping':map_rows,
                            'distinct_mapping_rows':unique_map,'missing_mapping_rows':missing,
                            'mapping_status':status_rows,'checks':checks})
        actual_total=sum(x['actual_raw'] for x in sources)
        if actual_total!=receipt.get('rows'): failures.append('Aggregate warehouse row count mismatch')
        if len(sources)!=receipt.get('sources'): failures.append('Audited source count mismatch')
        return {'status':'PASS' if not failures else 'FAIL','warehouse':str(path),
                'warehouse_sha256':sha256(path),'cut_id':receipt.get('cut_id'),
                'source_count':len(sources),'raw_rows':actual_total,
                'receipt_rows':receipt.get('rows'),'deep_exact_duplicates_checked':deep,
                'sources':sources,'failures':failures,
                'limits':['Does not prove current GitHub Pages totals equal warehouse/API totals.',
                          'Does not certify actuarial scores, routes or geographic hazard attribution.',
                          'Exact duplicate recount requires --deep and may be expensive.']}
    finally:
        db.close()

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('warehouse')
    p.add_argument('--output',help='JSON result path; never overwrite an existing audit')
    p.add_argument('--deep',action='store_true',help='Recount exact source duplicates (expensive)')
    args=p.parse_args()
    try:
        result=audit(args.warehouse,args.deep)
    except Exception as exc:
        result={'status':'ERROR','failures':[str(exc)]}
    raw=json.dumps(result,indent=2)+'\n'
    if args.output:
        with open(args.output,'x',encoding='utf-8') as f:f.write(raw)
    else: print(raw)
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':sys.exit(main())
