"""Synthetic local intake; no actual insurer records or production acceptance."""
import copy
import hashlib
import json
import base64
import pathlib
import sqlite3
import tempfile
import unittest

import private_loss_service as service
from private_workspace_store import save_portfolio
from test_private_loss_history import POLICY, CLAIM, envelope

class LossServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=pathlib.Path(self.temp.name)
        save_portfolio(self.folder,[copy.deepcopy(POLICY)])
        self.body={'source_base64':base64.b64encode(json.dumps(envelope(),sort_keys=True).encode()).decode()}
        self.secret=b'synthetic-test-secret-not-production'
        self.actor='Synthetic owner';self.session='synthetic-session';self.clock=lambda:1000

    def plan(self):
        return service.preview_request(self.folder,self.body,self.actor,self.session,self.secret,self.clock)

    def request(self,plan=None):
        p=self.plan() if plan is None else plan
        return {**self.body,'expected_preview':p['preview_sha256'],'approval_token':p['approval_token'],'approved':True}

    def commit(self,body=None,**overrides):
        options={'actor':self.actor,'session':self.session,'secret':self.secret,'clock':self.clock,**overrides}
        return service.import_request(self.folder,self.request() if body is None else body,**options)

    def test_preview_is_nonwriting_and_contains_no_raw_claims(self):
        before={p.name:p.read_bytes() for p in self.folder.iterdir()}
        plan=self.plan();self.assertEqual(plan['status'],'READY_FOR_PRIVATE_IMPORT')
        self.assertTrue(plan['approval_token']);self.assertFalse((self.folder/'loss-history.sqlite').exists())
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.folder.iterdir()})
        self.assertNotIn(CLAIM['claim_id'],json.dumps(plan));self.assertNotIn('source_base64',plan)

    def test_request_requires_exact_fields_and_explicit_permission(self):
        for body in ({},{**self.body,'reviewer':'Forged'}, {'source_base64':1}, {'source_base64':''}):
            with self.subTest(body=body),self.assertRaises(ValueError):
                service.preview_request(self.folder,body,self.actor,self.session,self.secret,self.clock)
        for body in ({**self.request(),'approved':False},{**self.request(),'approved':1},{**self.request(),'reviewer':'Forged'}):
            with self.subTest(body=list(body)),self.assertRaises(ValueError):self.commit(body)
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_original_bom_bytes_are_bound_without_text_transcoding(self):
        original=b'\xef\xbb\xbf'+json.dumps(envelope()).encode()
        self.body={'source_base64':base64.b64encode(original).decode()}
        plan=self.plan()
        self.assertEqual(plan['source_sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(self.commit(self.request(plan))['source_sha256'],plan['source_sha256'])
        for value in ('!', 'YQ', 'YQ==\n', 123, 'A'*2_666_672):
            with self.subTest(value=str(value)[:20]),self.assertRaises(ValueError):
                service.raw_source({'source_base64':value})

    def test_concurrent_portfolio_change_and_claim_commit_cannot_both_succeed(self):
        import threading
        from portfolio_store import import_records
        request=self.request();barrier=threading.Barrier(2);outcomes=[]
        def run(label,fn):
            barrier.wait()
            try:fn();outcomes.append((label,True))
            except ValueError:outcomes.append((label,False))
        threads=[threading.Thread(target=run,args=('claims',lambda:self.commit(request))),
                 threading.Thread(target=run,args=('policy',lambda:import_records(self.folder/'portfolio.sqlite',[{**POLICY,'dot_number':'999'}])))]
        for thread in threads:thread.start()
        for thread in threads:thread.join(5);self.assertFalse(thread.is_alive())
        self.assertEqual(sum(ok for _,ok in outcomes),1)

    def test_import_is_atomic_idempotent_and_author_attributed(self):
        body=self.request();first=self.commit(body);again=self.commit(body)
        self.assertEqual(first['imported_rows'],1);self.assertFalse(again['changed'])
        self.assertEqual(again['imported_rows'],0)
        history=service.list_batches(self.folder)
        self.assertEqual(len(history['batches']),1)
        self.assertEqual(history['batches'][0]['reviewer'],self.actor)
        self.assertFalse(history['missing_history_is_zero'])

    def test_token_tamper_wrong_actor_session_secret_and_expiry_fail(self):
        request=self.request()
        for kwargs in ({'actor':'Someone else'},{'session':'another-session'},{'secret':b'restarted-server'},
                       {'clock':lambda:1600},{'clock':lambda:1601}):
            with self.subTest(kwargs=list(kwargs)),self.assertRaises(ValueError):self.commit(request,**kwargs)
        for token in ('',None,{},'invalid','x'*2049,request['approval_token']+'x'):
            with self.subTest(token=str(token)[:15]),self.assertRaises(ValueError):
                self.commit({**request,'approval_token':token})
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_changed_source_or_portfolio_requires_new_preview(self):
        request=self.request();changed=envelope([{**CLAIM,'paid_minor':1}])
        with self.assertRaisesRegex(ValueError,'PREVIEW_CHANGED'):
            self.commit({**request,'source_base64':base64.b64encode(json.dumps(changed).encode()).decode()})
        save_portfolio(self.folder,[{**POLICY,'review_status':'in_review'}])
        with self.assertRaisesRegex(ValueError,'PREVIEW_CHANGED'):self.commit(request)
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_invalid_row_gets_no_approval_and_cannot_import(self):
        self.body={'source_base64':base64.b64encode(json.dumps(envelope([{**CLAIM,'dot_number':'999'}])).encode()).decode()}
        plan=self.plan();self.assertEqual(plan['status'],'REVIEW_REQUIRED');self.assertIsNone(plan['approval_token'])
        with self.assertRaisesRegex(ValueError,'REVIEW_REQUIRED'):self.commit(self.request(plan))
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_saved_valuation_conflict_is_rejected_without_partial_import(self):
        self.commit()
        self.body={'source_base64':base64.b64encode(json.dumps(envelope([{**CLAIM,'claim_id':'NEW-ROW'},{**CLAIM,'paid_minor':1}])).encode()).decode()}
        with self.assertRaisesRegex(ValueError,'CONFLICTING_SAVED_VALUATION'):self.commit()
        with sqlite3.connect(self.folder/'loss-history.sqlite') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM loss_observations').fetchone()[0],1)
        self.assertEqual(len(service.list_batches(self.folder)['batches']),1)

    def test_summary_read_does_not_mutate_file_or_sum_unknown_as_known_zero(self):
        result=self.commit();path=self.folder/'loss-history.sqlite';before=hashlib.sha256(path.read_bytes()).hexdigest()
        value=service.batch_summary(self.folder,result['batch_id']);service.list_batches(self.folder)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
        self.assertEqual(value['groups'][0]['paid_minor'],{'known_sum':'0','unknown_count':0})
        self.assertEqual(value['groups'][0]['outstanding_minor'],{'known_sum':'0','unknown_count':1})
        self.assertFalse(value['population_complete']);self.assertIsNone(value['actuarial_score'])
        self.assertEqual(value['batch_id'],result['batch_id'])
        self.assertEqual(value['provenance']['reviewer'],self.actor)
        self.assertEqual(value['provenance']['source_sha256'],hashlib.sha256(service.raw_source(self.body)).hexdigest())
        self.assertEqual(value['provenance']['verification_scope'],'NORMALIZED_FILE_NOT_UPSTREAM_INSURER_DOCUMENT')

    def test_no_ledger_history_does_not_create_file_or_imply_zero_losses(self):
        result=service.list_batches(self.folder)
        self.assertEqual(result['status'],'NOT_IMPORTED');self.assertFalse(result['missing_history_is_zero'])
        with self.assertRaises(ValueError):service.batch_summary(self.folder,'a'*64)
        self.assertFalse((self.folder/'loss-history.sqlite').exists())

    def test_policy_identity_and_period_cannot_detach_saved_claims(self):
        self.commit()
        for changes in ({'dot_number':'999'},{'currency':'CAD'},{'policy_start':'2019-01-01'},
                        {'policy_end':'2022-01-01'}):
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,'SAVED_CLAIMS'):
                save_portfolio(self.folder,[{**POLICY,**changes}])
        self.assertEqual(save_portfolio(self.folder,[{**POLICY,'review_status':'in_review'}])['changes'],1)

    def test_bad_history_inputs_do_not_allow_sql_or_paths(self):
        self.commit()
        for value in ('../../etc/passwd',"' OR 1=1",None,'A'*64):
            with self.subTest(value=value),self.assertRaises(ValueError):service.batch_summary(self.folder,value)
        for limit,offset in ((0,0),(101,0),(True,0),(1,-1),(1,100001)):
            with self.subTest(limit=limit,offset=offset),self.assertRaises(ValueError):service.list_batches(self.folder,limit,offset)

    def test_unknown_schema_and_public_storage_are_rejected(self):
        self.commit();path=self.folder/'loss-history.sqlite'
        with sqlite3.connect(path) as db:db.execute("UPDATE loss_ledger_schema SET schema='unknown'")
        with self.assertRaises(ValueError):service.list_batches(self.folder)
        with self.assertRaises(ValueError):service.preview_request(self.folder/'public',self.body,self.actor,self.session,self.secret)
