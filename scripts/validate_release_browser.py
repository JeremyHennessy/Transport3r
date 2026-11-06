"""Exercise delayed/failed release metadata in the actual public bundle.

Local test HTTP responses only; this does not certify a hosted deployment,
real insurer data, or a nationwide warehouse. No browser assertions are removed.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from validate_integrity_browser import Static, start, ROOT
from verify_live_ui import READINESS_JS, chrome


class ReleaseStatic(Static):
    def do_GET(self):
        if urlsplit(self.path).path.endswith('/release-manifest.json'):
            gate = self.server.release_gate
            if gate is not None and not gate.wait(timeout=10):
                self.send_error(504, 'Synthetic metadata test timed out')
                return
            if self.server.release_failure:
                self.send_error(503, 'Synthetic metadata unavailability')
                return
        super().do_GET()


def run(output):
    output = pathlib.Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'status':'FAIL','simulation':True,'production_deployed':False,
              'scope':'LOCAL_RELEASE_METADATA_FAILURE_RECOVERY','checks':[],
              'screenshots':[],'errors':[]}
    server = ThreadingHTTPServer(('127.0.0.1',0), ReleaseStatic)
    server.root = (ROOT/'dist').resolve()
    server.release_gate = None
    server.release_failure = False
    thread = start(server)
    base = f'http://127.0.0.1:{server.server_port}/Transport3r/'
    expected = json.loads((server.root/'release-manifest.json').read_text())['commit']
    args = {'expected':['Data Integrity'],'errors':[],'label':'integrity'}
    page = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome(),args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                for width in (1440,390):
                    context = browser.new_context(viewport={'width':width,'height':1000})
                    page = context.new_page()
                    runtime = []
                    page.on('pageerror',lambda error:runtime.append(str(error)))
                    try:
                        server.release_gate = threading.Event()
                        try:
                            page.goto(base+'#/integrity',wait_until='domcontentloaded')
                            page.get_by_text('Loading release metadata...',exact=True).wait_for()
                            assert page.locator('tbody tr').count()==36, 'The source table should render independently'
                            assert page.evaluate(READINESS_JS,args) is False, 'Pending provenance must not pass release readiness'
                        finally:
                            server.release_gate.set()
                            server.release_gate = None
                        page.wait_for_function(READINESS_JS,arg=args,timeout=45000)
                        release = page.locator('.t3-integrity-provenance article').first
                        assert release.locator('dd code').first.inner_text()==expected, 'Rendered release must match served manifest'
                        assert release.get_attribute('data-release-status')=='verified'
                        server.release_failure = True
                        try:
                            page.get_by_role('button',name='Recheck installation').click()
                            page.get_by_text('Release metadata unavailable:',exact=False).wait_for()
                            assert release.get_attribute('data-release-status')=='unavailable'
                            assert page.evaluate(READINESS_JS,args) is False, 'Unavailable provenance must not pass readiness'
                            assert release.locator('dd code').first.inner_text()=='Not verified', 'Failed refresh must clear old commit'
                            assert page.locator('.t3-integrity-metrics strong').all_inner_texts()==['\u2014']*4
                            assert page.get_by_role('button',name='Export verified audit').count()==0
                            name=f'release-unavailable-{width}.png'
                            release.scroll_into_view_if_needed()
                            page.screenshot(path=str(output/name),full_page=False)
                            result['screenshots'].append(name)
                        finally:
                            server.release_failure = False
                        page.get_by_role('button',name='Recheck installation').click()
                        page.wait_for_function(READINESS_JS,arg=args,timeout=45000)
                        assert release.get_attribute('data-release-status')=='verified'
                        assert release.locator('dd code').first.inner_text()==expected
                        assert page.locator('.t3-integrity-metrics strong').all_inner_texts()==['\u2014']*4
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2'), 'Document overflow'
                        assert not runtime, runtime
                        name=f'release-recovered-{width}.png'
                        release.scroll_into_view_if_needed()
                        page.screenshot(path=str(output/name),full_page=False)
                        result['screenshots'].append(name)
                        result['checks'].append(f'{width}px: delayed metadata waits; HTTP failure clears old provenance; retry restores exact release; no invented warehouse totals')
                    except Exception:
                        page.screenshot(path=str(output/f'release-failure-{width}.png'),full_page=False)
                        (output/f'release-failure-{width}.html').write_text(page.content())
                        raise
                    finally:
                        context.close()
            finally:
                browser.close()
        result['status'] = 'PASS'
    except Exception as error:
        result['errors'].append(type(error).__name__+': '+str(error))
    finally:
        if server.release_gate is not None:
            server.release_gate.set()
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
        (output/'release-metadata-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    raise SystemExit(run(parser.parse_args().output))
