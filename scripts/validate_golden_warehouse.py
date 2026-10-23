"""Reconcile frozen golden live observations to the same-publication nationwide warehouse/API."""
import argparse,json,pathlib

from nationwide_evidence import acceptance,connect,resolved_carrier

SOURCE_KEYS={'census':'az4n-8mr2','inspections':'fx4q-ay7w','crash':'aayw-vxb3','smsInspection':'rbkj-cgst','smsCensus':'kjg3-diqy'}


def validate(warehouse,reconciliation,output=None):
    root=pathlib.Path(reconciliation);summary=json.loads((root/'summary.json').read_text(encoding='utf-8'));observations=json.loads((root/'observations.json').read_text(encoding='utf-8'))
    if summary.get('status')!='PASS' or summary.get('selection')!='FROZEN_GOLDEN_V1' or summary.get('changedSources'):
        raise ValueError('Frozen golden live reconciliation did not pass one stable publication window')
    db=connect(warehouse)
    try:
        receipt=acceptance(db);lineage={item['source']:item for item in receipt['source_lineage']}
        publication=[]
        for sid in SOURCE_KEYS.values():
            expected=summary['before'][sid].get('rowsUpdatedAt');actual=lineage[sid]['rows_updated_at']
            publication.append({'source':sid,'golden_rows_updated_at':expected,'warehouse_rows_updated_at':actual,'match':expected==actual})
        if not all(item['match'] for item in publication):raise ValueError('Golden and warehouse observations are not the same source publications')
        checks=[]
        for carrier in observations['carriers']:
            dot=carrier['dot']
            census=db.execute("SELECT count(*) FROM mapping_az4n_8mr2 WHERE _dot_number=? AND _mapping_status='RESOLVED'",[dot]).fetchone()[0]
            checks.append({'dot':dot,'source':'az4n-8mr2','live_rows':1,'warehouse_rows':census,'api_rows':None,'match':census==1})
            if not carrier.get('detailed'):continue
            api=resolved_carrier(db,dot,False);api_counts={source['source_id']:source['carrier_rows'] for source in api['sources']}
            for key,sid in SOURCE_KEYS.items():
                if key=='census':continue
                live=carrier['slices'][key]['total'];warehouse_rows=db.execute(f"SELECT count(*) FROM mapping_{sid.replace('-','_')} WHERE _dot_number=? AND _mapping_status='RESOLVED'",[dot]).fetchone()[0]
                api_rows=api_counts[sid];checks.append({'dot':dot,'source':sid,'live_rows':live,'warehouse_rows':warehouse_rows,'api_rows':api_rows,'match':live==warehouse_rows==api_rows})
        failures=[item for item in checks if not item['match']]
        result={'version':1,'status':'PASS' if not failures else 'FAIL','same_publication_sources':publication,'census_carriers':summary['censusCarriers'],'detailed_carriers':summary['detailedCarriers'],'checks':len(checks),'failures':failures,'identity_contract':receipt['identity_contract'],'warehouse_scope':receipt['scope']}
    finally:db.close()
    if output:pathlib.Path(output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('warehouse');parser.add_argument('reconciliation');parser.add_argument('--output');args=parser.parse_args();result=validate(args.warehouse,args.reconciliation,args.output);print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='PASS' else 1)
