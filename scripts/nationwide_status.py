"""Report actual open-file transfer sizes, source completion and warehouse promotion."""
import argparse,json,pathlib

def status(folder):
    folder=pathlib.Path(folder).resolve()
    requested=json.loads((folder/'requested-sources.json').read_text(encoding='utf-8'))
    sources=[]
    for source in requested:
        cuts=sorted((folder/source['id']).glob('*'))
        accepted=[];transfers=[]
        for cut in cuts:
            manifest=cut/'manifest.json'
            if manifest.exists():
                m=json.loads(manifest.read_text(encoding='utf-8'))
                if m['status']=='COMPLETE':accepted.extend(m['datasets'])
            for path in cut.glob('*.partial'):
                # Windows directory metadata can show zero until the writer closes.
                # Opening the stream obtains the current file length.
                with path.open('rb') as handle:size=handle.seek(0,2)
                transfers.append({'path':str(path),'bytes':size})
        sources.append({'id':source['id'],'state':'COMPLETE' if accepted else 'TRANSFERRING_OR_PARTIAL' if transfers else 'QUEUED','rows':accepted[-1]['row_count'] if accepted else None,'bytes':accepted[-1]['bytes'] if accepted else sum(t['bytes'] for t in transfers),'transfers':transfers})
    manifest=folder/'manifest.json'
    collection=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else None
    return {'collection':str(folder),'status':collection['status'] if collection else 'IN_PROGRESS','sources_complete':sum(s['state']=='COMPLETE' for s in sources),'sources_requested':len(sources),'bytes_written':sum(s['bytes'] for s in sources),'sources':sources}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('collection');a=p.parse_args();print(json.dumps(status(a.collection),indent=2))
