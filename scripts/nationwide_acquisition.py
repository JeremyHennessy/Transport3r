"""Complete nationwide source files, independently verified and preserved per source."""
import argparse,json,pathlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from snapshot_store import acquire,now,write_once,create_cut
from verify_snapshot import verify
ROOT=pathlib.Path(__file__).resolve().parents[1]

def accepted(folder,source):
    results=[]
    for cut in sorted((folder/source['id']).glob('*')) if (folder/source['id']).is_dir() else []:
        manifest=cut/'manifest.json'
        if not manifest.is_file():continue
        value=json.loads(manifest.read_text(encoding='utf-8'))
        if value.get('status')=='COMPLETE':
            verify(cut)
            if len(value.get('datasets',[]))!=1 or value['datasets'][0].get('id')!=source['id']:raise ValueError('Completed source cut identity differs from collection path')
            item=value['datasets'][0]
            results.append({'id':source['id'],'status':'COMPLETE','cut':str(cut.relative_to(folder)),'rows':item['row_count'],'bytes':item['bytes'],'attempts':[{'cut':str(cut.relative_to(folder)),'status':'COMPLETE','reused':True}]})
    return results[-1] if results else None

def run(output_root,workers=3,build_warehouse=False,collection=None):
    if not 1<=workers<=4:raise ValueError('Use 1..4 download workers')
    sources=json.loads((ROOT/'data/fmcsa_sources.json').read_text(encoding='utf-8'))
    if collection:
        folder=pathlib.Path(collection).resolve();requested=json.loads((folder/'requested-sources.json').read_text(encoding='utf-8'))
        if requested!=sources:raise ValueError('Resumed collection source catalog differs')
        if (folder/'manifest.json').exists():raise ValueError('Collection already has an immutable complete manifest')
        run_record=json.loads((folder/'run.json').read_text(encoding='utf-8'))
        record={**run_record,'scope':'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES','source_count':len(sources),'sources':[]}
    else:
        folder,record=create_cut(pathlib.Path(output_root),schema_version=7,acquisition_kind='NATIONWIDE_SOURCE_COLLECTION')
        record.update(scope='ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES',source_count=len(sources),sources=[])
        write_once(folder/'requested-sources.json',sources)
    print('Nationwide collection: '+str(folder),flush=True)
    completed={source['id']:accepted(folder,source) for source in sources};completed={sid:item for sid,item in completed.items() if item}
    record['sources'].extend(completed.values())
    def collect(source):
        attempts=[]
        for attempt in range(1,4):
            cut,m=acquire([source],folder/source['id'],compression='gzip')
            attempts.append({'cut':str(cut.relative_to(folder)),'status':m['status']})
            if m['status']=='COMPLETE':return {'id':source['id'],'status':'COMPLETE','cut':str(cut.relative_to(folder)),'rows':m['datasets'][0]['row_count'],'bytes':m['datasets'][0]['bytes'],'attempts':attempts}
        return {'id':source['id'],'status':'FAILED','attempts':attempts}
    pending=[source for source in sources if source['id'] not in completed]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(collect,s):s for s in pending}
        for future in as_completed(futures):
            source=futures[future]
            try:result=future.result()
            except Exception as e:result={'id':source['id'],'status':'FAILED','error':str(e)}
            record['sources'].append(result)
            # Mutable operational progress is separate from immutable raw/result manifests.
            (folder/'progress.json').write_text(json.dumps({**record,'updated_at':now()},indent=2),encoding='utf-8')
            print(json.dumps(result),flush=True)
    record.update(status='COMPLETE' if len(record['sources'])==len(sources) and all(s['status']=='COMPLETE' for s in record['sources']) else 'PARTIAL',completed_at=now())
    record['sources'].sort(key=lambda s:s['id'])
    if record['status']=='COMPLETE':write_once(folder/'manifest.json',record);print('Nationwide manifest: '+str(folder/'manifest.json'),flush=True)
    else:
        partial=folder/f"partial-manifest-{now().replace(':','').replace('.','')}.json";write_once(partial,record);print('Partial collection retained for --collection resume: '+str(folder),flush=True)
    if build_warehouse and record['status']=='COMPLETE':
        from nationwide_warehouse import build
        result=build(folder,ROOT/'warehouse/nationwide/curated'/f"{record['snapshot_id']}.duckdb")
        print(json.dumps(result),flush=True)
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-root',default=str(ROOT/'warehouse/nationwide/raw'));p.add_argument('--collection',help='Resume an existing incomplete collection directory');p.add_argument('--workers',type=int,default=3);p.add_argument('--build-warehouse',action='store_true');a=p.parse_args()
    result=run(a.output_root,a.workers,a.build_warehouse,a.collection);raise SystemExit(0 if result['status']=='COMPLETE' else 1)
