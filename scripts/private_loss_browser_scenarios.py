"""Additional synthetic-only loss review exercise for the existing approved CI browser gate."""
import hashlib
import json
import pathlib


def exercise(page,context,base,folder,output,result):
    policy={'account_id':'SYNTHETIC-ACCOUNT','policy_id':'SYNTHETIC-LOSS-POLICY','dot_number':'3706',
            'policy_start':'2020-01-01','policy_end':'2021-01-01','status':'expired','review_status':'reviewed','currency':'USD'}
    headers={'Origin':base,'Content-Type':'application/json'}
    assert context.request.post(base+'/api/portfolio',headers=headers,data={'records':[policy]}).status==200
    claim={'claim_id':'SYNTHETIC-CLAIM','account_id':policy['account_id'],'policy_id':policy['policy_id'],
           'dot_number':'3706','coverage_line':'auto-liability','loss_date':'2020-03-01','reported_date':'2020-03-02',
           'status':'open','currency':'USD','paid_minor':0,'outstanding_minor':None}
    envelope={'schema':'PRIVATE_LOSS_HISTORY_1','source_id':'SYNTHETIC-INSURER','document_reference':'SYNTHETIC ONLY',
              'valuation_date':'2020-12-31','permission_confirmed':True,
              'amount_basis':'GROSS_INDEMNITY_EXCLUDING_EXPENSES_AND_RECOVERIES','claims':[claim]}
    raw=b'\xef\xbb\xbf'+json.dumps(envelope).encode()
    source=page.locator('#lossHistoryFile');preview=page.locator('#lossHistoryPreview');commit=page.locator('#lossHistoryImport')
    def upload(value):
        source.set_input_files({'name':'synthetic-loss.json','mimeType':'application/json','buffer':value})
        page.wait_for_function("!document.getElementById('lossHistoryPreview').disabled")
    upload(raw)
    with page.expect_response(lambda r:r.url.endswith('/api/loss-history/preview') and r.request.method=='POST') as response:preview.click()
    assert response.value.status==200
    assert response.value.json()['source_sha256']==hashlib.sha256(raw).hexdigest()
    page.get_by_role('heading',name='Ready for explicit review approval',exact=True).wait_for()
    assert commit.is_disabled() and not (pathlib.Path(folder)/'loss-history.sqlite').exists()
    # Selecting another file invalidates the prior preview and approval.
    invalid={**envelope,'claims':[{**claim,'dot_number':'999'}]}
    upload(json.dumps(invalid).encode());assert commit.is_disabled()
    preview.click();page.get_by_role('heading',name='Review required; no rows imported',exact=True).wait_for()
    assert page.locator('#lossHistoryApproval').is_disabled()
    assert not (pathlib.Path(folder)/'loss-history.sqlite').exists()
    upload(raw);preview.click();page.get_by_role('heading',name='Ready for explicit review approval',exact=True).wait_for()
    page.locator('#lossHistoryApproval').check()
    with page.expect_response(lambda r:r.url.endswith('/api/loss-history/import') and r.request.method=='POST') as response:commit.click()
    assert response.value.status==200
    imported=response.value.json();assert imported['imported_rows']==1
    page.get_by_role('heading',name='Imported privately',exact=True).wait_for()
    assert source.input_value()=='' and commit.is_disabled()
    assert imported['summary']['groups'][0]['paid_minor']=={'known_sum':'0','unknown_count':0}
    assert imported['summary']['groups'][0]['outstanding_minor']=={'known_sum':'0','unknown_count':1}
    assert 'known minor units' in page.locator('#lossHistoryImportResult').inner_text()
    # The export is synthetic and excludes login/approval secrets and raw source content.
    with page.expect_download() as downloaded:
        page.locator('#lossHistoryImportResult').get_by_role('button',name='Export this private valuation summary').click()
    export_path=pathlib.Path(output)/'synthetic-loss-valuation-summary.json';downloaded.value.save_as(export_path)
    assert json.loads(export_path.read_text())==imported['summary']
    assert not any(word in export_path.read_text() for word in ('approval_token','source_base64','SYNTHETIC-CLAIM'))
    for width in (1440,390):
        page.set_viewport_size({'width':width,'height':1000});page.locator('#loss-history').scroll_into_view_if_needed()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
        page.screenshot(path=str(pathlib.Path(output)/f'private-synthetic-loss-history-{width}.png'))
    result['checks'].append('Loss-file byte hash including BOM, nonwriting preview, invalid-file rejection, explicit approval, authenticated import, unknown/zero summary, private export and desktop/mobile layout pass with synthetic records')
