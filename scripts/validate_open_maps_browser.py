"""Production-bundle WebGL and no-horizontal-scroll checks. Synthetic sources only."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import pathlib
import threading
from urllib.parse import urlsplit, parse_qs
from playwright.sync_api import sync_playwright
from verify_live_ui import chrome
ROOT=pathlib.Path(__file__).resolve().parents[1]
class StaticHandler(SimpleHTTPRequestHandler):
    def translate_path(self,path): return super().translate_path(path.replace('/Transport3r/','/',1))
    def log_message(self,*args): pass

def run(output):
    output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=False)
    result={'status':'FAIL','simulation':True,'scope':'SYNTHETIC_PRODUCTION_BUNDLE_MAP_AND_TABLE','checks':[],'screenshots':[]}
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(StaticHandler,directory=str(ROOT/'dist')))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    requests=[];external=[];console_errors=[];local_failures=[];workers=[];fail_map=False
    directory=[{'dot_number':str(10000+i),'legal_name':'SYNTHETIC LOGISTICS '+('LONGNAME'*18 if i==0 else str(i)),
        'dba_name':'SYNTHETIC ONLY','phy_country':'US' if i<200 else 'CA','phy_state':'TX' if i<120 else 'CA' if i<200 else 'ON',
        'phy_city':'SYNTHETIC CITY','carrier_operation':'A','status_code':'A','power_units':'20000','fleetsize':'Z',
        'total_drivers':'4','mcs150_date':'20200101','mcs150_mileage':'0','mcs150_mileage_year':'0','hm_ind':'N'} for i in range(201)]
    def source(route):
        u=urlsplit(route.request.url)
        if u.hostname in ('127.0.0.1','localhost'):route.continue_();return
        external.append(route.request.url)
        if u.hostname!='data.transportation.gov':route.abort();return
        sid=u.path.rsplit('/',1)[-1].replace('.json','');params=parse_qs(u.query);where=params.get('$where',[''])[0]
        if '/api/views/' in u.path:
            route.fulfill(json={'id':sid,'tableId':1,'rowsUpdatedAt':1,'columns':[]});return
        requests.append({'source':sid,'params':params});rows=[]
        if sid=='az4n-8mr2':
            if '3938496' in where:rows=[{**directory[0],'dot_number':'3938496','legal_name':'SYNTHETIC SUMMARY CARRIER','phy_state':'CA','power_units':'20','total_drivers':'25'}]
            else:rows=[row for row in directory if ("phy_state='TX'" not in where or row['phy_state']=='TX') and ("phy_country='US'" not in where or row['phy_country']=='US')]
            if '$group' in params:
                if fail_map:route.fulfill(status=400,json={'error':'Synthetic map failure'});return
                groups={}
                for row in rows:
                    key=(row['phy_country'],row['phy_state']);groups[key]=groups.get(key,0)+1
                route.fulfill(json=[{'phy_country':country,'phy_state':state,'count':str(n)} for (country,state),n in sorted(groups.items())]);return
        if sid=='fx4q-ay7w':rows=[{'dot_number':'3938496','inspection_id':'1000','insp_date':'20260115','county_code_state':'TX','report_state':'TX','location_desc':'SYNTHETIC EVENT STATE','insp_carrier_state':'CA'},
            {'dot_number':'3938496','inspection_id':'1001','insp_date':'20260215','county_code_state':'ZZ','report_state':'NY','location_desc':'SYNTHETIC REPORTING JURISDICTION','insp_carrier_state':'CA'}]
        if sid=='aayw-vxb3':rows=[{'dot_number':'3938496','crash_id':'800','report_date':'20260315','state':'VA','fatalities':'0','crash_carrier_state':'CA'},
            {'dot_number':'3938496','crash_id':'801','report_date':'01022026','crash_carrier_state':'CA'}]
        select=params.get('$select',[''])[0]
        if 'count(' in select:route.fulfill(json=[{'count':str(len(rows))}]);return
        offset=int(params.get('$offset',['0'])[0]);limit=int(params.get('$limit',['5000'])[0]);rows=rows[offset:offset+limit]
        if 'transport_row_id' in select:rows=[{**row,'transport_row_id':f'{sid}:{offset+i}'} for i,row in enumerate(rows)]
        route.fulfill(json=rows)
    def capture(page,name):
        path=output/(name+'.png');page.screenshot(path=str(path),animations='disabled')
        result['screenshots'].append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=chrome(),args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
            context=browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1);context.route('**/*',source)
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.set_default_timeout(20000)
            page.on('console',lambda message:console_errors.append(message.text) if message.type=='error' else None)
            page.on('worker',lambda worker:workers.append(worker.url))
            page.on('response',lambda response:local_failures.append({'url':response.url,'status':response.status}) if response.status>=400 and urlsplit(response.url).hostname=='127.0.0.1' else None)
            try:
                base=f'http://127.0.0.1:{server.server_port}/Transport3r/'
                page.goto(base+'#/carriers',wait_until='domcontentloaded');page.locator('.t3-carrier-row:not(.header) .carrier-name').first.wait_for()
                assert page.locator('.t3-carrier-row:not(.header)').count()==100
                assert not any('$group' in r['params'] for r in requests)
                page.get_by_role('button',name='Show carrier map',exact=True).click()
                page.get_by_test_id('map-matched').filter(has_text='201 matching').wait_for();page.locator('[data-testid=directory-map] [data-map-ready=true]').wait_for()
                page.wait_for_function("document.querySelectorAll('[data-testid=directory-map] .t3-map-marker').length===2")
                assert any('/Transport3r/assets/maplibre-gl-worker-' in url for url in workers),workers
                assert not local_failures,local_failures
                assert '1 outside supported' in page.get_by_test_id('directory-map').inner_text()
                page.get_by_test_id('directory-map').scroll_into_view_if_needed();capture(page,'directory-map-1440')
                result['checks'].append('Real MapLibre WebGL renders; 201 matching source rows versus 100 table rows; foreign location remains unmapped')
                page.locator('[aria-label="Matching carrier regions"] button').filter(has_text='TX').click();page.wait_for_function("location.hash.includes('state=TX')")
                page.get_by_test_id('map-matched').filter(has_text='120 matching').wait_for();page.locator('[data-testid=directory-map] [data-map-ready=true]').wait_for()
                assert page.locator('[data-testid=directory-map] .t3-map-marker').count()==1
                assert all('TX' in c.inner_text() for c in page.locator('.t3-carrier-row:not(.header) [data-label=Location]').all())
                map_where=next(r['params']['$where'][0] for r in reversed(requests) if '$group' in r['params'])
                table_where=next(r['params']['$where'][0] for r in reversed(requests) if r['source']=='az4n-8mr2' and '$group' not in r['params'] and 'count(' not in r['params'].get('$select',[''])[0])
                assert map_where==table_where
                before=sum('$group' in r['params'] for r in requests);page.get_by_role('button',name='Next page',exact=True).click()
                page.wait_for_function("document.querySelectorAll('.t3-carrier-row:not(.header)').length===20")
                assert '120 matching' in page.get_by_test_id('map-matched').inner_text();assert sum('$group' in r['params'] for r in requests)==before
                page.get_by_role('button',name='Previous page',exact=True).click();page.wait_for_function("document.querySelectorAll('.t3-carrier-row:not(.header)').length===100")
                result['checks'].append('Map selection applies exact table filters and shareable URL; pagination does not refetch full-population map')
                for width in (1712,1280,1024,768,390):
                    page.set_viewport_size({'width':width,'height':1000});page.locator('.t3-table-panel').scroll_into_view_if_needed();page.locator('.t3-exposure-flags summary').first.click()
                    d=page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth,table:document.querySelector('.t3-carrier-table').scrollWidth,container:document.querySelector('.t3-carrier-table-wrap').clientWidth})")
                    assert d['document']<=width+2,d;assert d['table']<=d['container']+2,d
                    first=page.locator('.t3-carrier-row:not(.header)').first;assert first.locator('[data-label]').count()==11
                    for cell in first.locator('[data-label]').all():assert cell.is_visible()
                    capture(page,'carrier-table-'+str(width));page.locator('.t3-exposure-flags summary').first.click()
                result['checks'].append('All 11 fields visible without horizontal overflow at 1712/1280/1024/768/390px, including long names and expanded flags')
                page.get_by_test_id('directory-map').scroll_into_view_if_needed();capture(page,'directory-map-390')
                fail_map=True;page.get_by_role('button',name='Apply filters',exact=True).click();page.get_by_role('button',name='Retry carrier map',exact=True).wait_for()
                assert page.get_by_test_id('map-matched').count()==0
                fail_map=False;page.get_by_role('button',name='Retry carrier map',exact=True).click();page.get_by_test_id('map-matched').filter(has_text='120 matching').wait_for()
                result['checks'].append('Map source failure clears stale counts; explicit retry restores filtered evidence')
                page.goto(base+'#/carrier/3938496/summary',wait_until='domcontentloaded');panel=page.get_by_test_id('carrier-safety-map');panel.wait_for()
                panel.locator('[data-map-ready=true]').wait_for();panel.get_by_text('3 mapped records',exact=True).wait_for()
                assert '1 unlocated' in panel.inner_text();assert '1 unknown/invalid dates' in panel.inner_text();assert panel.locator('.t3-map-marker').count()==3
                assert not panel.locator('.t3-map-marker').filter(has_text='CA').count()
                panel.get_by_label('Include reporting jurisdictions',exact=True).uncheck();panel.get_by_text('2 mapped records',exact=True).wait_for()
                panel.get_by_label('Crashes',exact=True).uncheck();panel.get_by_text('1 mapped records',exact=True).wait_for()
                panel.get_by_label('From',exact=True).fill('2026-02-01');panel.get_by_text('0 mapped records',exact=True).wait_for()
                panel.get_by_role('button',name='Reset map filters',exact=True).click();panel.get_by_text('3 mapped records',exact=True).wait_for()
                for width in (1440,390):
                    page.set_viewport_size({'width':width,'height':1000});panel.scroll_into_view_if_needed();assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2');capture(page,'summary-map-'+str(width))
                result['checks'].append('Summary maps unknown event states only as labelled reporting jurisdictions, rejects non-YYYYMMDD daily dates, and preserves layer/date/reset controls')
                assert not errors,errors;assert all(urlsplit(url).hostname=='data.transportation.gov' for url in external),external
                result['checks'].append('No runtime errors or external tile/geocoder requests; all source records synthetic');result['status']='PASS'
            except Exception as error:
                result['error']=str(error);result['runtime_errors']=errors;result['console_errors']=console_errors;result['local_failures']=local_failures;result['worker_urls']=workers
                capture(page,'failure');(output/'failure.html').write_text(page.content());raise
            finally:browser.close()
    finally:
        server.shutdown();server.server_close();thread.join();result['checked_at']=datetime.now(timezone.utc).isoformat();result['source_request_count']=len(requests)
        (output/'requests.json').write_text(json.dumps(requests,indent=2));(output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output');run(parser.parse_args().output)
