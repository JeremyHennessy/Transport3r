"""Real loopback HTTP calls against synthetic local private-workspace records."""
import http.client
import json
import base64
import pathlib
import tempfile
import threading
import unittest

from private_workspace import Workspace, make_server
from private_workspace_store import save_portfolio
from test_private_loss_history import POLICY, envelope

class PrivateLossApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=pathlib.Path(self.temp.name);self.app=Workspace(self.folder)
        save_portfolio(self.folder,[POLICY]);self.server=make_server(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.cookie='';self.origin=f'http://127.0.0.1:{self.server.server_port}'
        def stop():
            self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.addCleanup(stop);self.source={'source_base64':base64.b64encode(json.dumps(envelope()).encode()).decode()}

    def request(self,path,body=None,origin=True,host=None,raw=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        headers={'Host':host or self.origin.removeprefix('http://'),'Cookie':self.cookie}
        if body is not None or raw is not None:
            headers['Content-Type']='application/json'
            if origin:headers['Origin']=self.origin
        data=raw if raw is not None else None if body is None else json.dumps(body)
        conn.request('GET' if data is None else 'POST',path,data,headers)
        response=conn.getresponse();payload=response.read();cookie=response.getheader('Set-Cookie')
        if cookie:self.cookie=cookie.split(';')[0]
        result=(response.status,json.loads(payload));conn.close();return result

    def login(self):
        self.assertEqual(self.request('/api/setup',{'name':'Synthetic reviewer','password':'synthetic-test-password'})[0],200)

    def approved(self):
        status,plan=self.request('/api/loss-history/preview',self.source);self.assertEqual(status,200)
        return {**self.source,'expected_preview':plan['preview_sha256'],'approval_token':plan['approval_token'],'approved':True}

    def test_all_loss_routes_require_authentication(self):
        for path,body in (('/api/loss-history/preview',self.source),('/api/loss-history/import',{}),
                          ('/api/loss-history/batches',None),('/api/loss-history/summary?batch_id='+'a'*64,None)):
            with self.subTest(path=path):self.assertEqual(self.request(path,body)[0],401)
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_cross_origin_and_host_are_rejected(self):
        self.login()
        self.assertEqual(self.request('/api/loss-history/preview',self.source,origin=False)[0],403)
        self.assertEqual(self.request('/api/loss-history/batches',host='attacker.example')[0],403)
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_end_to_end_preview_import_summary_and_policy_guard(self):
        self.login();approved=self.approved();self.assertFalse((self.folder/'loss-history.sqlite').exists())
        status,result=self.request('/api/loss-history/import',approved);self.assertEqual(status,200,result)
        self.assertEqual(result['imported_rows'],1)
        history=self.request('/api/loss-history/batches')[1]
        self.assertEqual(history['batches'][0]['reviewer'],'Synthetic reviewer')
        summary=self.request('/api/loss-history/summary?batch_id='+result['batch_id'])[1]
        self.assertEqual(summary,result['summary'])
        self.assertEqual(self.request('/api/portfolio',{'records':[{**POLICY,'dot_number':'999'}]})[0],400)
        self.assertEqual(self.request('/api/loss-history/import',approved)[1]['imported_rows'],0)

    def test_logout_invalidates_approved_import(self):
        self.login();approved=self.approved();old=self.cookie
        self.assertEqual(self.request('/api/logout',{})[0],200);self.cookie=old
        self.assertEqual(self.request('/api/loss-history/import',approved)[0],401)
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_review_identity_cannot_be_supplied_by_caller(self):
        self.login();approved=self.approved()
        self.assertEqual(self.request('/api/loss-history/import',{**approved,'reviewer':'Different user'})[0],400)
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_duplicate_outer_json_fields_are_rejected(self):
        self.login()
        self.assertEqual(self.request('/api/loss-history/import',raw='{"approved":false,"approved":true}')[0],400)
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_strict_history_query_and_unknown_batch(self):
        self.login()
        for suffix in ('?offset=-1','?limit=200','?limit=1&limit=2','?tenant_id=other'):
            with self.subTest(suffix=suffix):self.assertEqual(self.request('/api/loss-history/batches'+suffix)[0],400)
        self.assertEqual(self.request('/api/loss-history/summary?batch_id='+'a'*64)[0],400)

if __name__=='__main__':unittest.main()
