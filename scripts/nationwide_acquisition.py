"""Complete nationwide source files, independently verified and preserved per source."""
import argparse,json,pathlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from snapshot_store import acquire,now,write_once,create_cut
ROOT=pathlib.Path(__file__).resolve().parents[1]

def run(output_root,workers=3,build_warehouse=False):
    if not 1<=workers<=4:raise ValueError('Use 1..4 download workers')
    sources=json.loads((ROOT/'data/fmcsa_sources.json').read_text(encoding='utf-8'))
    folder,record=create_cut(pathlib.Path(output_root),schema_version=7,acquisition_kind='NATIONWIDE_SOURCE_COLLECTION')
    record.update(scope='ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES',source_count=len(sources),sources=[])
    write_once(folder/'requested-sources.json',sources)
    print('Nationwide collection: '+str(folder),flush=True)
    def collect(source):
        attempts=[]
        for attempt in range(1,4):
            cut,m=acquire([source],folder/source['id'])
            attempts.append({'cut':str(cut.relative_to(folder)),'status':m['status']})
            if m['status']=='COMPLETE':return {'id':source['id'],'status':'COMPLETE','cut':str(cut.relative_to(folder)),'rows':m['datasets'][0]['row_count'],'bytes':m['datasets'][0]['bytes'],'attempts':attempts}
        return {'id':source['id'],'status':'FAILED','attempts':attempts}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(collect,s):s for s in sources}
        for future in as_completed(futures):
            source=futures[future]
            try:result=future.result()
            except Exception as e:result={'id':source['id'],'status':'FAILED','error':str(e)}
            record['sources'].append(result)
            # Mutable operational progress is separate from immutable raw/result manifests.
            (folder/'progress.json').write_text(json.dumps({**record,'updated_at':now()},indent=2),encoding='utf-8')
            print(json.dumps(result),flush=True)
    record.update(status='COMPLETE' if all(s['status']=='COMPLETE' for s in record['sources']) else 'PARTIAL',completed_at=now())
    record['sources'].sort(key=lambda s:s['id']);write_once(folder/'manifest.json',record)
    print('Nationwide manifest: '+str(folder/'manifest.json'),flush=True)
    if build_warehouse and record['status']=='COMPLETE':
        from nationwide_warehouse import build
        result=build(folder,ROOT/'warehouse/nationwide/curated'/f"{record['snapshot_id']}.duckdb")
        print(json.dumps(result),flush=True)
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-root',default=str(ROOT/'warehouse/nationwide/raw'));p.add_argument('--workers',type=int,default=3);p.add_argument('--build-warehouse',action='store_true');a=p.parse_args()
    result=run(a.output_root,a.workers,a.build_warehouse);raise SystemExit(0 if result['status']=='COMPLETE' else 1)
