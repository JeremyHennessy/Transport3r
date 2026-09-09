"""Preserve official website release identity separately from DataHub extract identity."""
import argparse,datetime as dt,hashlib,html,json,pathlib,re,urllib.request
from concurrent.futures import ThreadPoolExecutor
from snapshot_store import now,write_once,fetch_json
URL='https://ai.fmcsa.dot.gov/SMS/'
SOURCES=['kjg3-diqy','rbkj-cgst','8mt8-2mdr','4wxs-vbns','4y6x-dmck','h9zy-gjn8','m3ry-qcip','h3zn-uid9']
def parse_release(raw):
    text=html.unescape(re.sub('<[^>]+>',' ',raw));text=re.sub(r'\s+',' ',text)
    def date(label):
        match=re.search(label+r'\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})',text,re.I)
        if not match:raise ValueError('Official release date unavailable: '+label)
        return dt.datetime.strptime(match.group(1),'%B %d, %Y').date().isoformat()
    return {'website_snapshot_date':date('Data current as of:'),'website_updated_on':date('Website Updated on:')}
def capture(folder):
    folder=pathlib.Path(folder);folder.mkdir(parents=True,exist_ok=False)
    with urllib.request.urlopen(URL,timeout=30) as response:raw=response.read()
    (folder/'sms-home.html').write_bytes(raw);release=parse_release(raw.decode('utf-8'))
    def metadata(sid):
        value=fetch_json(f'https://data.transportation.gov/api/views/{sid}.json');write_once(folder/f'{sid}.metadata.json',value)
        return {'id':sid,'rows_updated_at':value.get('rowsUpdatedAt'),'table_id':value.get('tableId'),'explicit_snapshot_fields':[c['fieldName'] for c in value['columns'] if 'snapshot' in c['fieldName'].lower()],'binding_status':'UNVERIFIED'}
    with ThreadPoolExecutor(max_workers=4) as pool:sources=list(pool.map(metadata,SOURCES))
    report={'version':1,'observed_at':now(),'website':URL,'html_sha256':hashlib.sha256(raw).hexdigest(),**release,'datahub_sources':sources,'datahub_month_binding':'UNVERIFIED','reason':'A website release date or matching maximum event date does not attest to the identity of these DataHub extracts. Require an official release artifact/identifier and verified linkage before month-aligned modelling.'}
    write_once(folder/'release-observation.json',report);return report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();print(json.dumps(capture(args.output),indent=2))
