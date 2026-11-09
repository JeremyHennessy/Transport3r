"""Verify deployed routes and capture the SAME browser state that passed assertions.

No virtual clock and no second screenshot browser. Every original Pages assertion
is retained. Missing sources, runtime errors or a 45-second readiness timeout
remain failures. Desktop/mobile diagnostics are retained even on failure.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

ROUTES = [
    ('overview', '#/overview', ['Know the carrier before you price the risk.']),
    ('carriers', '#/carriers', ['Nationwide carrier intelligence']),
    ('atlas', '#/atlas', ['Carrier Geography Atlas']),
    ('atlas-carrier', '#/atlas?dot=3938496', ['Carrier Geography Atlas']),
    ('summary', '#/carrier/3938496/summary', ['Underwriting evidence at a glance']),
    ('safety', '#/carrier/3938496/safety', ['Violation evidence']),
    ('authority', '#/carrier/3938496/authority', ['Authority', 'Operating authority']),
    ('evidence', '#/carrier/3938496/evidence', ['Evidence', 'Evidence lineage']),
    ('portfolio', '#/portfolio', ['Portfolio']),
    ('alerts', '#/alerts', ['Alerts']),
    ('methodology', '#/methodology', ['Methodology']),
    ('fleet', '#/carrier/3938496/fleet', ['Reported fleet exposure', '3C63RRGLXNG286232']),
    ('insurance', '#/carrier/3938496/insurance', ['Coverage continuity', 'Review by coverage line']),
    ('sms', '#/carrier/3938496/sms', ['Official output and Transport replay']),
    ('sources', '#/sources', ['All 36 configured FMCSA/DOT datasets']),
    ('inspection', '#/carrier/3938496/inspection/82574029', ['Retrieved directly by inspection ID']),
    ('vin', '#/carrier/3938496/vin/3C63RRGLXPG628183?inspection=82574029', ['Observed vehicle evidence']),
    ('integrity', '#/integrity', ['Data Integrity', 'All 36 FMCSA / DOT sources']),
]
ERRORS = ['Transport3r could not render this view.', 'Carrier identity could not load.',
          'This evidence tab could not load.', 'Carrier geography could not load.']


READINESS_JS = r'''({expected, errors, label}) => {
    // CSS uppercase and whitespace do not change the asserted meaning.
    const normal = value => value.replace(/\s+/g, ' ').trim().toLocaleLowerCase('en-US');
    const text = normal(document.body.innerText);
    const error = errors.find(message => text.includes(normal(message)));
    if (error) return {error};
    if (!expected.every(message => text.includes(normal(message)))) return false;
    if (label === 'atlas-carrier' && !document.querySelector('.t3-atlas-map-panel svg')) return false;
    if (label === 'insurance' && document.querySelectorAll('.t3-insurance-line').length !== 8) return false;
    if (label === 'integrity' && text.includes(normal('Checking the installed evidence service'))) return false;
    // The 36 static registry rows can render before async release/probe metadata.
    // Do not capture the initial "Not verified" provenance placeholders as final UI.
    if (label === 'integrity' && !text.includes(normal('not a live check'))) return false;
    if (label === 'carriers' && !document.querySelector('.t3-carrier-row:not(.header) .carrier-name a')) return false;
    if (label === 'vin' && !document.querySelector('[data-testid="vin-detail"]')) return false;
    if (label === 'evidence' && !document.querySelector('.c360-card .c360-raw-census')) return false;
    if (label === 'authority' && !document.querySelector('.c360-table.authority')) return false;
    return {ready:true};
}'''


def chrome():
    executable = os.environ.get('CHROME_BIN') or next((shutil.which(name) for name in
        ('google-chrome', 'google-chrome-stable', 'chromium') if shutil.which(name)), None)
    if not executable:
        raise RuntimeError('System Chrome/Chromium is required')
    return executable


def capture_route(page, base, route, output, viewport):
    label, fragment, expected = route
    name = f'{label}-{viewport["width"]}'
    result = {'route': fragment, 'viewport': viewport, 'status': 'FAIL', 'checks': [], 'errors': [],
              'acceptance_scope': 'ROUTE_SHELL_AND_VISIBLE_PREVIEW_ONLY',
              'full_source_reconciliation': 'NOT_TESTED'}
    page_errors = []
    page.on('pageerror', lambda error: page_errors.append(str(error)))
    page.set_viewport_size(viewport)
    page.set_default_timeout(45000)
    try:
        page.goto(base.rstrip('/') + '/' + fragment, wait_until='domcontentloaded', timeout=45000)
        outcome = page.wait_for_function(READINESS_JS, arg={'expected': expected, 'errors': ERRORS, 'label': label}, timeout=45000).json_value()
        if outcome.get('error'):
            raise AssertionError(outcome['error'])
        result['checks'].append('Every required route assertion passed in the captured page')
        # Keep live-data acquisition separate from render readiness. The page can
        # render a valid preview while its independent 36-source sweep is pending.
        # None of the screenshots or heading checks certify a nationwide source cut.
        source_status = page.locator('[data-testid="complete-data-status"]')
        if source_status.count():
            status_text = source_status.first.inner_text(timeout=5000)
            if 'Loading complete carrier evidence' in status_text:
                sweep_state = 'LOADING_NOT_ACCEPTED'
            elif 'Complete loading needs attention' in status_text:
                sweep_state = 'INCOMPLETE_NOT_ACCEPTED'
            elif 'Complete carrier evidence loaded' in status_text:
                sweep_state = 'UI_REPORTED_COMPLETE_NOT_INDEPENDENTLY_AUDITED'
            else:
                sweep_state = 'UNKNOWN_NOT_ACCEPTED'
            result['carrier_sweep'] = {
                'state': sweep_state,
                'visible_progress': status_text[:280],
                'independent_acceptance': False,
            }
            result['checks'].append('Carrier sweep state retained separately; UI route pass does not certify source completeness')
        if label == 'insurance':
            assert page.locator('.t3-insurance-line').count() == 8
            result['checks'].append('Eight insurance lines rendered without a numerical risk model')
        if label == 'vin':
            assert page.locator('a[href="#/carrier/3938496/inspection/82574029"]').count() > 0
            result['checks'].append('Observed VIN links back to its exact inspection')
        if label == 'atlas-carrier':
            assert page.locator('.t3-atlas-provenance').count() == 1
            result['checks'].append('Actual state map and source retrieval provenance rendered')
        if label == 'integrity':
            assert page.locator('tbody tr').count() == 36, 'Expected all 36 Data Integrity source rows'
            assert 'not a live check' in page.locator('body').inner_text(), 'Bundled probe freshness did not finish rendering'
            result['checks'].append('All 36 sources shown with explicit saved-probe freshness')
        dimensions = page.evaluate('({viewport:innerWidth,document:document.documentElement.scrollWidth})')
        result['dimensions'] = dimensions
        if dimensions['document'] > dimensions['viewport'] + 2:
            raise AssertionError('Page-level horizontal overflow: ' + str(dimensions))
        if page_errors:
            raise AssertionError('Browser runtime errors: ' + '; '.join(page_errors))
        result['checks'].append('No document overflow or browser runtime error')
        result['status'] = 'PASS'
    except Exception as error:
        result['errors'].append(str(error))
    finally:
        result['runtime_errors'] = page_errors
        try:
            (output / (name + '.html')).write_text(page.content(), encoding='utf-8')
            image = output / (name + '.png')
            page.screenshot(path=str(image), full_page=False, animations='disabled', timeout=15000)
            result['screenshot'] = image.name
            result['screenshot_sha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
            if result['status'] == 'PASS':
                retain_section(page, label, output, name, result)
        except Exception as error:
            result['status'] = 'FAIL'
            result['errors'].append('Screenshot/DOM retention failed: ' + str(error))
        (output / (name + '.json')).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


SECTION_SELECTORS = {
    'carriers': '.t3-table-panel',
    'atlas-carrier': '.t3-atlas-map-panel',
    'summary': '.c360-card:not([data-testid="carrier-insight"]):not([data-testid="complete-data-status"])',
    'safety': '.c360-card:not([data-testid="carrier-insight"]):not([data-testid="complete-data-status"])',
    'authority': '.c360-card:not([data-testid="carrier-insight"]):not([data-testid="complete-data-status"])',
    'evidence': '.c360-card:has(.c360-raw-census)',
    'insurance': '[data-testid="insurance-line-review"]',
    'sms': '.c360-card:not([data-testid="carrier-insight"]):not([data-testid="complete-data-status"])',
    'inspection': '[data-testid="inspection-detail"]',
    'vin': '[data-testid="vin-detail"]',
    'integrity': '.t3-integrity-pipeline, .t3-integrity-table-wrap',
}


def retain_section(page, label, output, name, result):
    """Retain tab content, not another identical shared-header screenshot."""
    selector = SECTION_SELECTORS.get(label)
    if not selector:
        return
    target = page.locator(selector).first
    target.wait_for(state='visible', timeout=45000)
    # Wait for target layout before scrolling; never capture the shared loading card.
    target.scroll_into_view_if_needed(timeout=45000)
    # Scroll with allowance for sticky navigation; do not change page content.
    target.evaluate("el => window.scrollTo({top: Math.max(0, el.getBoundingClientRect().top + scrollY - 170), behavior: 'instant'})")
    page.wait_for_timeout(150)
    box = target.bounding_box()
    viewport = page.viewport_size
    assert box and box['y'] < viewport['height'] and box['y'] + box['height'] > 0, 'Expected section is outside captured viewport'
    image = output / (name + '-section.png')
    page.screenshot(path=str(image), full_page=False, animations='disabled', timeout=15000)
    result['section_selector'] = selector
    result['section_screenshot'] = image.name
    result['section_screenshot_sha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
    result['section_bounds'] = box
    result['checks'].append('Tab-specific content is visible in a separate same-page screenshot')


def run(base, expected_sha, output, labels=None):
    if not re.fullmatch('[0-9a-f]{40}', expected_sha):
        raise ValueError('Expected full commit SHA required')
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=False)
    selected = ROUTES if labels is None else [route for route in ROUTES if route[0] in labels]
    if labels is not None and {r[0] for r in selected} != set(labels):
        raise ValueError('Unknown selected route')
    result = {'status': 'FAIL', 'expected_commit': expected_sha,
              'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'ALL_RELEASE_ROUTES' if labels is None else 'EXPLICIT_ROUTE_SUBSET',
              'base_url': base, 'routes': [], 'errors': [],
              'data_acceptance_scope': 'UI_ONLY_NO_NATIONWIDE_SOURCE_OR_INSURER_RECONCILIATION'}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome(), args=['--no-sandbox', '--disable-dev-shm-usage'])
            try:
                response = browser.new_context().request.get(base.rstrip('/') + '/release-manifest.json', timeout=45000)
                manifest = response.json()
                assert response.status == 200 and manifest['commit'] == expected_sha, 'Hosted release SHA differs'
                result['observed_commit'] = manifest['commit']
                for viewport in ({'width':1440,'height':1200}, {'width':390,'height':844}):
                    for route in selected:
                        context = browser.new_context(viewport=viewport)
                        try:
                            record = capture_route(context.new_page(), base, route, output, viewport)
                            result['routes'].append(record)
                            print(route[0], viewport['width'], record['status'], flush=True)
                        finally:
                            context.close()
                result['status'] = 'PASS' if result['routes'] and all(r['status']=='PASS' for r in result['routes']) else 'FAIL'
            finally:
                browser.close()
    except Exception as error:
        result['errors'].append(str(error))
    (output / 'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default=os.environ.get('PAGE_URL'))
    parser.add_argument('--expected-sha', default=os.environ.get('EXPECTED_SHA'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--routes', nargs='+', help='Explicit diagnostic subset only; deployment omits this option')
    args = parser.parse_args()
    if not args.base or not args.expected_sha:
        parser.error('Base URL and expected SHA are required')
    result = run(args.base, args.expected_sha, args.output, args.routes)
    print(json.dumps({'status':result['status'], 'routes_checked':len(result['routes']), 'errors':result['errors']}))
    sys.exit(0 if result['status']=='PASS' else 1)
