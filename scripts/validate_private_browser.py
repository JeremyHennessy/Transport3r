"""Synthetic-only browser gate for the loopback private coverage workbench.

No real insurer data is read. The temporary service binds only 127.0.0.1. The
scheduler is not started, and no external source acquisition is requested.
"""
import argparse
import json
import pathlib
import secrets
import tempfile
import threading
from playwright.sync_api import sync_playwright
import coverage_requirements as templates
from private_workspace import Workspace, make_server
from verify_live_ui import chrome


def run(output):
    output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=False)
    result={'status':'FAIL','simulation':True,'scope':'SYNTHETIC_SINGLE_OWNER_LOOPBACK', 'checks':[]}
    with tempfile.TemporaryDirectory(prefix='transport3r-private-browser-') as temp:
        app=Workspace(temp);server=make_server(app,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=chrome(),args=['--no-sandbox','--disable-dev-shm-usage'])
                try:
                    context=browser.new_context(viewport={'width':1440,'height':1000})
                    assert context.request.get(base+'/api/state').status==401
                    page=context.new_page();page.goto(base,wait_until='domcontentloaded')
                    page.get_by_role('heading',name='Set up your private workspace').wait_for()
                    form=page.locator('#loginForm')
                    form.locator('[name=name]').fill('SYNTHETIC QA OWNER')
                    form.locator('[name=password]').fill(secrets.token_urlsafe(24))
                    form.get_by_role('button',name='Continue').click()
                    page.get_by_role('heading',name='Your underwriting workspace').wait_for()
                    assert any(cookie['name']=='t3session' and cookie['httpOnly'] and cookie['sameSite']=='Strict' for cookie in context.cookies())
                    policy=page.locator('#portfolioForm')
                    for name,value in {'account_id':'SYNTHETIC-ACCOUNT','policy_id':'SYNTHETIC-POLICY','dot_number':'3706',
                        'policy_start':'2026-01-01','policy_end':'2027-01-01','notes':'SYNTHETIC QA: no real policy or client data.'}.items():
                        policy.locator(f'[name={name}]').fill(value)
                    policy.get_by_role('button',name='Save policy',exact=True).click()
                    page.get_by_text('Policy saved.',exact=True).wait_for()
                    page.get_by_role('button',name='Review insurance lines').click()
                    review=page.locator('#insuranceReviewForm')
                    assert review.locator('[name=account_id]').input_value()=='SYNTHETIC-ACCOUNT'
                    assert review.locator('[name=dot_number]').input_value()=='3706'
                    review.locator('[name=line]').select_option('motor-truck-cargo')
                    review.locator('[name=notes]').fill('SYNTHETIC QA: request shipment records; no actual coverage established.')
                    review.locator('[name=due_date]').fill('2027-01-01')
                    with page.expect_response(lambda response: response.url.endswith('/api/insurance-review') and response.request.method=='POST') as saved_response:
                        review.get_by_role('button',name='Save private review').click()
                    assert saved_response.value.status==200
                    page.get_by_text('Private insurance review saved with an audit trail.',exact=True).wait_for()
                    page.get_by_role('button',name='Edit review',exact=True).click()
                    review.locator('[name=status]').select_option('in_review')
                    review.locator('[name=notes]').fill('SYNTHETIC QA: second analyst review; claims remain unavailable.')
                    with page.expect_response(lambda response: response.url.endswith('/api/insurance-review') and response.request.method=='POST') as saved_response:
                        review.get_by_role('button',name='Save private review').click()
                    assert saved_response.value.status==200
                    page.get_by_text('Private insurance review saved with an audit trail.',exact=True).wait_for()
                    state=context.request.get(base+'/api/state').json()
                    assert len(state['insurance_reviews'])==1
                    saved=state['insurance_reviews'][0]
                    assert saved['status']=='in_review' and saved['dot']=='3706'
                    history=context.request.get(base+'/api/insurance-review-history?id='+saved['id']).json()
                    assert len(history)==2
                    assert history[0]['previous_json'] is None
                    assert 'needs_data' in history[1]['previous_json']
                    page.get_by_role('button',name='Review audit history',exact=True).click()
                    page.locator('#insuranceReviewList pre').wait_for()
                    for width in (1440,390):
                        page.set_viewport_size({'width':width,'height':1000})
                        page.locator('#insurance-reviews').scroll_into_view_if_needed()
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                        page.screenshot(path=str(output/f'private-synthetic-review-{width}.png'))
                    result['checks'].append('Authenticated policy-to-USDOT review, edit and two immutable history entries pass in a real browser')
                    page.get_by_role('button',name='Requested documents',exact=True).click()
                    page.get_by_role('heading',name='Coverage document checklist',exact=True).wait_for()
                    assert page.locator('#coverageChecklistItems .record').count()==4
                    assert '4 outstanding' in page.locator('#coverageChecklistSummary').inner_text()
                    card=page.locator('[data-requirement-key="commodity-mix"]')
                    card.get_by_role('button',name='Edit document request',exact=True).click()
                    followup=page.locator('#coverageRequirementForm')
                    followup.locator('[name=status]').select_option('requested')
                    followup.locator('[name=due_date]').fill('2030-01-01')
                    followup.locator('[name=notes]').fill('SYNTHETIC ONLY: request shipment values and commodity schedule')
                    followup.get_by_role('button',name='Save document follow-up',exact=True).click()
                    page.get_by_text('Document follow-up saved locally with change history.',exact=True).wait_for()
                    card.get_by_role('button',name='Edit document request',exact=True).click()
                    followup.locator('[name=status]').select_option('received')
                    followup.locator('[name=received_on]').fill('2020-01-01')
                    followup.locator('[name=evidence_url]').fill('https://example.org/synthetic-document')
                    with page.expect_response(lambda r: r.url.endswith('/api/insurance-requirement') and r.request.method=='POST') as written:
                        followup.get_by_role('button',name='Save document follow-up',exact=True).click()
                    assert written.value.status==200
                    card.get_by_text('Received, not yet reviewed',exact=True).wait_for()
                    assert '4 outstanding' in page.locator('#coverageChecklistSummary').inner_text()
                    card.get_by_role('button',name='Edit document request',exact=True).click()
                    followup.locator('[name=status]').select_option('reviewed')
                    followup.locator('[name=notes]').fill('SYNTHETIC ONLY: analyst checked document date and exact policy identity')
                    with page.expect_response(lambda r: r.url.endswith('/api/insurance-requirement') and r.request.method=='POST') as written:
                        followup.get_by_role('button',name='Save document follow-up',exact=True).click()
                    assert written.value.status==200
                    card.get_by_text('Reviewed by analyst',exact=True).wait_for()
                    assert '3 outstanding' in page.locator('#coverageChecklistSummary').inner_text()
                    plan=context.request.get(base+'/api/insurance-requirements?review_id='+saved['id']).json()
                    assert plan['coverage_determined'] is False
                    documents=context.request.get(base+'/api/insurance-requirement-history?review_id='+saved['id']+'&requirement_key=commodity-mix').json()
                    assert len(documents)==3 and documents[0]['previous_json'] is None
                    assert json.loads(documents[2]['previous_json'])['status']=='received'
                    for width in (1440,390):
                        page.set_viewport_size({'width':width,'height':1000})
                        page.locator('#coverageChecklist').scroll_into_view_if_needed()
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                        page.screenshot(path=str(output/f'private-synthetic-documents-{width}.png'))
                    result['checks'].append('Private four-document coverage checklist, request/receive/review states, revision checks and three immutable history entries pass')
                    # Simulate an explicit template release in this synthetic server.
                    # Prior completed items must not silently certify the new prompts.
                    old_version=templates.VERSION
                    old_prompts=templates.TEMPLATES['motor-truck-cargo']
                    prior_item=next(item for item in plan['items'] if item['requirement_key']=='commodity-mix')
                    card.get_by_role('button',name='Edit document request',exact=True).click()
                    try:
                        templates.VERSION='COVERAGE_CHECKLIST_SYNTHETIC_UPGRADE'
                        with page.expect_response(lambda r: r.url.endswith('/api/insurance-requirement') and r.request.method=='POST') as rejected:
                            followup.get_by_role('button',name='Save document follow-up',exact=True).click()
                        assert rejected.value.status==400
                        assert len(context.request.get(base+'/api/insurance-requirement-history?review_id='+saved['id']+'&requirement_key=commodity-mix').json())==3
                        page.get_by_role('button',name='Requested documents',exact=True).click()
                        page.get_by_text('Template updated: this prior review is not counted complete until explicitly reviewed against the current prompts.',exact=True).wait_for()
                        assert '4 outstanding' in page.locator('#coverageChecklistSummary').inner_text()
                        card.get_by_role('button',name='Edit document request',exact=True).click()
                        assert followup.locator('[name=expected_template_version]').input_value()==templates.VERSION
                        followup.locator('[name=notes]').fill('SYNTHETIC ONLY: explicitly re-reviewed revised template')
                        with page.expect_response(lambda r: r.url.endswith('/api/insurance-requirement') and r.request.method=='POST') as rewritten:
                            followup.get_by_role('button',name='Save document follow-up',exact=True).click()
                        assert rewritten.value.status==200
                        page.locator('#coverageChecklistSummary').filter(has_text='3 outstanding').wait_for()
                        plan=context.request.get(base+'/api/insurance-requirements?review_id='+saved['id']).json()
                        current=next(item for item in plan['items'] if item['requirement_key']=='commodity-mix')
                        assert current['id']==prior_item['id'] and current['revision']==4 and not current['needs_template_review']
                        templates.TEMPLATES['motor-truck-cargo']=[item for item in old_prompts if item[0]!='commodity-mix']
                        page.get_by_role('button',name='Requested documents',exact=True).click()
                        page.get_by_text('Retired prompt: commodity-mix',exact=True).wait_for()
                        assert '3 outstanding' in page.locator('#coverageChecklistSummary').inner_text()
                        page.get_by_role('button',name='Retired document history',exact=True).click()
                        page.locator('#coverageRequirementHistory').wait_for()
                        archived=context.request.get(base+'/api/insurance-requirement-history?review_id='+saved['id']+'&requirement_key=commodity-mix').json()
                        assert len(archived)==4 and json.loads(archived[-1]['previous_json'])['template_version']==old_version
                        for width in (1440,390):
                            page.set_viewport_size({'width':width,'height':1000})
                            page.locator('#coverageChecklist').scroll_into_view_if_needed()
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                            page.screenshot(path=str(output/f'private-synthetic-template-upgrade-{width}.png'))
                        result['checks'].append('Template release rejects stale save, requires explicit re-review, preserves exact record/history IDs and retains read-only retired prompts')
                    finally:
                        templates.VERSION=old_version
                        templates.TEMPLATES['motor-truck-cargo']=old_prompts
                    bad=context.request.post(base+'/api/insurance-review',headers={'Origin':'https://unrelated.example','Content-Type':'application/json'},data={})
                    assert bad.status==403
                    page.get_by_role('button',name='Sign out',exact=True).click()
                    page.get_by_role('heading',name='Sign in',exact=True).wait_for()
                    assert context.request.get(base+'/api/state').status==401
                    result['checks'].append('HttpOnly/SameSite session, cross-origin write rejection and logout access revocation pass')
                    result['checks'].append('Desktop/mobile review screenshots have no document overflow; all records are synthetic')
                    result['status']='PASS'
                finally:browser.close()
        finally:
            app.stop.set();server.shutdown();server.server_close();thread.join()
            (output/'synthetic-private-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output');args=parser.parse_args();run(args.output)
