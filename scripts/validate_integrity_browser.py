"""Synthetic integration: raw DuckDB -> deep audit -> real HTTP API -> built UI.

All records are generated test data. Screenshots and this receipt NEVER prove
production ingestion, current FMCSA counts or a public evidence deployment.
"""
from __future__ import annotations
import argparse
import functools
import json
import os
import pathlib
import subprocess
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright
from audit_warehouse_integrity import audit
from evidence_api import EvidenceServer, Handler
from test_audit_warehouse_integrity import make_fixture
from verify_live_ui import capture_route, chrome, ROUTES
from atlas_browser_scenarios import NETWORK_OBSERVER, exercise as exercise_atlas

ROOT=pathlib.Path(__file__).resolve().parents[1]


class Static(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        value=unquote(urlsplit(path).path)
        if value.startswith('/Transport3r/'):
            value=value[len('/Transport3r/'):]
        target=(self.server.root/value.lstrip('/')).resolve()
        if not target.is_relative_to(self.server.root):
            return str(self.server.root/'not-found')
        return str(target)
    def log_message(self,*args):pass


def start(server):
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    return thread


def run(output):
    output=pathlib.Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    receipt={'status':'FAIL','simulation':True,'scope':'SYNTHETIC_RAW_WAREHOUSE_API_UI', 'checks':[], 'screenshots':[]}
    with tempfile.TemporaryDirectory(prefix='transport3r-integrity-test-') as temporary:
        temp=pathlib.Path(temporary)
        path=temp/'fixture.duckdb'
        make_fixture(path)
        report=audit(path,deep=True)
        assert report['status']=='PASS',report
        report_path=temp/'audit.json'
        report_path.write_text(json.dumps(report))
        api=EvidenceServer(('127.0.0.1',0),Handler,path,'*',audit_report=report_path)
        api_thread=start(api)
        web=ThreadingHTTPServer(('127.0.0.1',0),Static)
        web.root=(ROOT/'dist').resolve()
        web_thread=start(web)
        base=f'http://127.0.0.1:{web.server_port}/Transport3r/'
        errors=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=chrome(),args=['--no-sandbox','--disable-dev-shm-usage'])
                try:
                    # The default public build must never infer numbers without an API.
                    for width in (1440,390):
                        context=browser.new_context(viewport={'width':width,'height':1000})
                        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base+'#/integrity')
                        page.get_by_text('Nationwide audit service is not connected',exact=True).wait_for()
                        assert page.locator('.t3-integrity-metrics strong').all_inner_texts()==['\u2014']*4
                        assert page.locator('tbody tr').count()==36
                        assert page.get_by_role('button',name='Export verified audit').count()==0
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                        name=f'integrity-unconfigured-{width}.png'
                        page.screenshot(path=str(output/name),full_page=False)
                        receipt['screenshots'].append(name)
                        context.close()
                    receipt['checks'].append('Unconfigured public build: 36 sources, unknown totals, no audit export, desktop/mobile without overflow')
                    # Compile a distinct test build, not a public fixture file.
                    env={**os.environ,'VITE_EVIDENCE_API_URL':f'http://127.0.0.1:{api.server_port}'}
                    built=temp/'built'
                    subprocess.run(['node','--input-type=module','-e',
                        "import {buildPublic} from './scripts/build-public.mjs';import{execFileSync}from'node:child_process';await buildPublic(execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),process.argv[1]);",str(built)],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
                    web.root=built.resolve()
                    for width in (1440,390):
                        context=browser.new_context(viewport={'width':width,'height':1000},accept_downloads=True)
                        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base+'#/integrity')
                        page.get_by_text('Installed warehouse matches its independent audit',exact=True).wait_for()
                        assert page.locator('.t3-integrity-metrics strong').all_inner_texts()==['8','2','36','0']
                        assert page.locator('.t3-integrity-pipeline strong').all_inner_texts()==['8']*5
                        assert page.locator('tbody tr').count()==36
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                        name=f'integrity-synthetic-verified-{width}.png'
                        page.screenshot(path=str(output/name),full_page=False)
                        receipt['screenshots'].append(name)
                        search=page.get_by_role('searchbox',name='Find a source')
                        search.fill('fx4q-ay7w')
                        assert page.locator('tbody tr').count()==1
                        assert 'q=fx4q-ay7w' in page.url
                        page.reload()
                        page.get_by_text('Installed warehouse matches its independent audit',exact=True).wait_for()
                        assert page.locator('tbody tr').count()==1
                        assert page.get_by_role('searchbox',name='Find a source').input_value()=='fx4q-ay7w'
                        with page.expect_download() as download:
                            page.get_by_role('button',name='Export verified audit').click()
                        saved=json.loads(pathlib.Path(download.value.path()).read_text())
                        assert saved['raw_rows']==8 and len(saved['sources'])==36
                        assert saved['warehouse_sha256']==api.warehouse_sha256
                        assert not any(key in saved for key in ('client_policy','warehouse','local_path'))
                        page.get_by_role('link',name='Atlas',exact=True).click()
                        page.get_by_role('heading',name='Carrier Geography Atlas').wait_for()
                        page.go_back()
                        page.get_by_text('Installed warehouse matches its independent audit',exact=True).wait_for()
                        assert page.locator('tbody tr').count()==1
                        context.close()
                    receipt['checks'].append('Real API and production UI reconcile all five stages to 8 synthetic raw rows / 2 carriers / 36 sources / 0 duplicates')
                    receipt['checks'].append('Source search survives reload and browser back; audit download retains all 36 sources and exact warehouse SHA')
                    context=browser.new_context();page=context.new_page()
                    page.goto(base+'#/integrity')
                    page.get_by_text('Installed warehouse matches its independent audit',exact=True).wait_for()
                    saved_integrity=api.integrity;api.integrity=None
                    page.get_by_role('button',name='Recheck installation').click()
                    page.get_by_text('Nationwide audit could not be verified',exact=True).wait_for()
                    assert page.locator('.t3-integrity-metrics strong').all_inner_texts()==['\u2014']*4
                    assert page.get_by_role('button',name='Export verified audit').count()==0
                    api.integrity=saved_integrity
                    saved_hash=api.warehouse_sha256;api.warehouse_sha256='f'*64
                    page.get_by_role('button',name='Recheck installation').click()
                    page.get_by_text('Nationwide audit could not be verified',exact=True).wait_for()
                    assert page.locator('.t3-integrity-metrics strong').all_inner_texts()==['\u2014']*4
                    api.warehouse_sha256=saved_hash
                    context.close()
                    receipt['checks'].append('Unavailable or mismatched audit clears previously displayed totals and disables export')
                    # Test public insurance and Atlas UI with explicitly synthetic browser data.
                    web.root=(ROOT/'dist').resolve()
                    fixture=(ROOT/'scripts/report-fixture-browser.js').read_text()+'\n'+NETWORK_OBSERVER
                    for label in ('insurance','atlas-carrier','evidence','authority'):
                        route=next(r for r in ROUTES if r[0]==label)
                        for width in (1440,390):
                            context=browser.new_context()
                            context.add_init_script(fixture)
                            record=capture_route(context.new_page(),base,route,output,{'width':width,'height':1000})
                            assert record['status']=='PASS',record
                            receipt['screenshots'].append(record['screenshot'])
                            if label=='atlas-carrier':
                                exercise_atlas(context.pages[0],output,width)
                            context.close()
                    receipt['checks'].append('Insurance, Atlas, actual Evidence/Authority desktop/mobile capture, exact-generation refresh, invalid-identity no-request and delayed-response no-stale-map gates pass with synthetic data')
                    assert not errors,errors
                    receipt['status']='PASS'
                finally:browser.close()
        finally:
            api.shutdown();api.server_close();api_thread.join()
            web.shutdown();web.server_close();web_thread.join()
            (output/'synthetic-browser-result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output');args=parser.parse_args()
    run(args.output)
