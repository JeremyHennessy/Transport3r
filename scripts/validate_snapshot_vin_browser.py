"""Actual built-UI checks using a synthetic audited warehouse and synthetic VIN sources.

No live acquisition, private files or production acceptance is performed here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright
from audit_warehouse_integrity import audit
from evidence_api import EvidenceServer, Handler
from test_audit_warehouse_integrity import make_fixture
from validate_integrity_browser import Static, start
from verify_live_ui import chrome

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIN = '3C63RRGLXNG286232'
OTHER_VIN = '3C63RRGLXPG628183'


def run(output):
    output = pathlib.Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'FAIL', 'simulation': True,
              'scope': 'SYNTHETIC_ACCEPTED_WAREHOUSE_REPORT_AND_VIN_UNIT_LINKS',
              'checks': [], 'screenshots': []}
    errors = []

    def capture(page, name):
        path = output / (name + '.png')
        page.screenshot(path=str(path), animations='disabled')
        result['screenshots'].append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})

    with tempfile.TemporaryDirectory(prefix='transport3r-snapshot-vin-') as temporary:
        temp = pathlib.Path(temporary)
        warehouse = temp / 'fixture.duckdb'
        make_fixture(warehouse)
        report = audit(warehouse, deep=True)
        assert report['status'] == 'PASS', report
        audit_file = temp / 'audit.json'
        audit_file.write_text(json.dumps(report))
        api = EvidenceServer(('127.0.0.1', 0), Handler, warehouse, '*', audit_report=audit_file)
        api_thread = start(api)
        web = ThreadingHTTPServer(('127.0.0.1', 0), Static)
        web.root = (ROOT / 'dist').resolve()
        web_thread = start(web)
        base = f'http://127.0.0.1:{web.server_port}/Transport3r/'
        try:
            built = temp / 'warehouse-build'
            env = {**os.environ, 'VITE_EVIDENCE_API_URL': f'http://127.0.0.1:{api.server_port}'}
            subprocess.run(['node', '--input-type=module', '-e',
                "import{buildPublic}from'./scripts/build-public.mjs';import{execFileSync}from'node:child_process';await buildPublic(execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),process.argv[1]);",
                str(built)], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
            web.root = built.resolve()
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=chrome(), args=['--no-sandbox', '--disable-dev-shm-usage'])
                try:
                    for width in (1440, 390):
                        context = browser.new_context(viewport={'width': width, 'height': 1000}, accept_downloads=True)
                        external = []

                        def reject_external(route):
                            external.append(route.request.url)
                            route.abort()

                        context.route('https://data.transportation.gov/**', reject_external)
                        page = context.new_page()
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(base + '#/carrier/3706/report?format=brief&start=2026-01-01&end=2026-10-23')
                        page.get_by_test_id('carrier-report').wait_for(timeout=30000)
                        text = page.get_by_test_id('carrier-report').inner_text()
                        assert 'synthetic-test-cut' in text and 'without a live refetch' in text
                        assert not external, external
                        with page.expect_download() as download:
                            page.get_by_role('button', name='Download evidence archive', exact=True).click()
                        saved = json.loads(pathlib.Path(download.value.path()).read_text())
                        assert saved['window']['provenance']['warehouseSha256'] == api.warehouse_sha256
                        assert saved['window']['provenance']['cutId'] == saved['evidence']['completenessReceipt']['cutId']
                        assert saved['window']['sources'][0]['accounting']['missingDates'] == 1
                        assert saved['window']['sources'][0]['slice']['total'] is None
                        assert not external, external
                        capture(page, f'accepted-snapshot-report-{width}')
                        context.close()
                    result['checks'].append('Accepted report and archive use the exact cut/hash, preserve missing-date uncertainty and make no live FMCSA safety request')
                    web.root = (ROOT / 'dist').resolve()
                    rows_by_source = {
                        'az4n-8mr2': [{'dot_number': '3938496', 'legal_name': 'SYNTHETIC VIN CARRIER', 'status_code': 'A', 'power_units': '2'}],
                        'fx4q-ay7w': [
                            {'dot_number': '3938496', 'inspection_id': '1000', 'insp_date': '20260115', 'report_state': 'TX'},
                            {'dot_number': '3938496', 'inspection_id': '1001', 'insp_date': '20260215', 'report_state': 'NY'}],
                        'wt8s-2hbx': [
                            {'inspection_id': '1000', 'insp_unit_id': '101', 'insp_unit_number': '1', 'insp_unit_vehicle_id_number': VIN},
                            {'inspection_id': '1000', 'insp_unit_id': '102', 'insp_unit_number': '2', 'insp_unit_vehicle_id_number': OTHER_VIN},
                            {'inspection_id': '1001', 'insp_unit_id': '201', 'insp_unit_number': '1', 'insp_unit_vehicle_id_number': VIN}],
                        '876r-jsdb': [
                            {'inspection_id': '1000', 'insp_violation_id': '10001', 'insp_unit_id': '101', 'insp_viol_unit': '1', 'viol_code': '393.9', 'viol_desc': 'SYNTHETIC TRACTOR LIGHT', 'out_of_service_indicator': 'Y', 'defect_verification_id': '99'},
                            {'inspection_id': '1000', 'insp_violation_id': '10002', 'insp_unit_id': '102', 'insp_viol_unit': '2', 'viol_code': '393.75', 'viol_desc': 'SYNTHETIC TRAILER TIRE', 'out_of_service_indicator': 'N'},
                            {'inspection_id': '1001', 'insp_violation_id': '10003', 'insp_unit_id': '201', 'insp_viol_unit': '1', 'viol_code': '393.9', 'viol_desc': 'SYNTHETIC TRACTOR LIGHT'},
                            {'inspection_id': '1001', 'insp_violation_id': '10004', 'insp_viol_unit': 'D', 'viol_code': '395.8', 'viol_desc': 'SYNTHETIC DRIVER CONTEXT'}]}
                    unexpected = []

                    def source(route):
                        url = urlsplit(route.request.url)
                        if url.hostname in ('127.0.0.1', 'localhost'):
                            route.continue_()
                            return
                        if url.hostname != 'data.transportation.gov':
                            unexpected.append(route.request.url)
                            route.abort()
                            return
                        sid = url.path.rsplit('/', 1)[-1].replace('.json', '')
                        params = parse_qs(url.query)
                        if '/api/views/' in url.path:
                            route.fulfill(json={'id': sid, 'tableId': 1, 'rowsUpdatedAt': 1, 'viewLastModified': 1, 'columns': []})
                            return
                        rows = rows_by_source.get(sid, [])
                        select = params.get('$select', [''])[0]
                        if 'count(' in select:
                            route.fulfill(json=[{'count': str(len(rows))}])
                            return
                        offset = int(params.get('$offset', ['0'])[0])
                        rows = rows[offset:offset + int(params.get('$limit', ['5000'])[0])]
                        if 'transport_row_id' in select:
                            rows = [{**row, 'transport_row_id': f'{sid}:{offset+i}'} for i, row in enumerate(rows)]
                        route.fulfill(json=rows)

                    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                    context.route('**/*', source)
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '#/carrier/3938496/vin/' + VIN, wait_until='domcontentloaded')
                    findings = page.get_by_test_id('vin-unit-evidence')
                    findings.get_by_text('2 linked violation records', exact=True).wait_for(timeout=30000)
                    text = findings.inner_text()
                    assert 'SYNTHETIC TRACTOR LIGHT' in text
                    assert 'SYNTHETIC TRAILER TIRE' not in text and 'SYNTHETIC DRIVER CONTEXT' not in text
                    assert '1 carrier-scope records could not be assigned' in text
                    assert '393.9 (2 inspections)' in text
                    for width in (1440, 390):
                        page.set_viewport_size({'width': width, 'height': 1000})
                        findings.scroll_into_view_if_needed()
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                        capture(page, f'vin-specific-findings-{width}')
                    assert not unexpected, unexpected
                    context.close()
                    result['checks'].append('VIN findings link exact vehicle units, exclude trailer/driver-only findings, preserve unknowns and remain readable on desktop/mobile')
                    assert not errors, errors
                    result['status'] = 'PASS'
                finally:
                    browser.close()
        except Exception as error:
            result['error'] = str(error)
            result['runtime_errors'] = errors
            raise
        finally:
            api.shutdown(); api.server_close(); api_thread.join()
            web.shutdown(); web.server_close(); web_thread.join()
            (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    run(parser.parse_args().output)
