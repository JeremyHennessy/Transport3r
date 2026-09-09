import http.client
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from private_workspace import Workspace,make_server
from private_workspace_store import connect,relationship,review_relationship,group_members,deliver
from material_alerts import DDL

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        self.app=Workspace(self.root);self.server=make_server(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.cookie=None
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,origin=True,host=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        headers={}
        if self.cookie:headers['Cookie']=self.cookie
        if host:headers['Host']=host
        if body is not None:
            headers['Content-Type']='application/json'
            if origin:headers['Origin']=f'http://127.0.0.1:{self.server.server_port}'
        c.request('GET' if body is None else 'POST',path,json.dumps(body) if body is not None else None,headers)
        r=c.getresponse();data=r.read();cookie=r.getheader('Set-Cookie')
        if cookie:self.cookie=cookie.split(';')[0]
        result=(r.status,json.loads(data));c.close();return result
    def login(self):
        self.assertEqual(self.request('/api/setup',{'name':'Test owner','password':'fixture-only-password'})[0],200)
    def test_auth_origin_and_host_boundaries(self):
        self.assertEqual(self.request('/api/state')[0],401)
        for path in ('/api/identity-screen?dot=3706','/api/ghost?dot=3706','/api/ghost-queue','/api/group?dot=3706','/api/screening-history?id=test'):
            self.assertEqual(self.request(path)[0],401)
        self.assertEqual(self.request('/api/setup',{'name':'Test','password':'fixture-only-password'},origin=False)[0],403)
        self.assertEqual(self.request('/api/session',host='attacker.test')[0],403)
        self.login();self.assertEqual(self.request('/api/state')[0],200)
        self.assertEqual(self.request('/api/subscribe',{'dot':'3706','enabled':True},origin=False)[0],403)
        self.assertEqual(self.request('/api/screening-case',{'kind':'ghost','dot':'3706'},origin=False)[0],403)
        self.request('/api/logout',{});self.assertEqual(self.request('/api/state')[0],401)
    def test_portfolio_roundtrip_preserves_private_values_and_rejects_bad_batch(self):
        self.login()
        record={'account_id':'TEST','policy_id':'P1','dot_number':'3706','policy_start':'2026-01-01','policy_end':'2027-01-01','status':'watch','review_status':'unreviewed','insured_vmt':None}
        self.assertEqual(self.request('/api/portfolio',{'records':[record]})[1]['changes'],1)
        self.assertEqual(self.request('/api/portfolio',{'records':[record]})[1]['changes'],0)
        self.assertEqual(self.request('/api/portfolio',{'records':[record,{**record,'policy_id':'P2','scheduled_units':-1}]})[0],400)
        saved=self.request('/api/state')[1]['portfolio'];self.assertEqual(len(saved),1);self.assertIsNone(saved[0]['insured_vmt'])
    def test_only_reviewed_ownership_edges_enter_group_and_revocations_take_effect(self):
        db=connect(self.app.path)
        try:
            shared={'dot_a':'1','dot_b':'2','kind':'shared_registration_details','evidence_url':'https://example.org/evidence','notes':'Shared office address only'}
            sid=relationship(db,shared,'Owner');review_relationship(db,{'id':sid,'status':'approved','review_note':'Reviewed shared address only'},'Owner')
            self.assertEqual(group_members(db,'1'),['1'])
            oid=relationship(db,{**shared,'kind':'common_ownership','notes':'Documented ownership reference'},'Owner')
            self.assertEqual(group_members(db,'1'),['1'])
            review_relationship(db,{'id':oid,'status':'approved','review_note':'Reviewed ownership document'},'Owner')
            self.assertEqual(group_members(db,'1'),['1','2'])
            review_relationship(db,{'id':oid,'status':'revoked','review_note':'Ownership changed in later evidence'},'Owner')
            self.assertEqual(group_members(db,'1'),['1']);self.assertEqual(db.execute('SELECT count(*) FROM relationship_history').fetchone()[0],5)
        finally:db.close()
    def test_inbox_delivery_is_idempotent_and_only_after_subscription(self):
        db=connect(self.app.path);alerts=self.root/'alerts.sqlite'
        source=sqlite3.connect(alerts);source.executescript(DDL)
        row=('alert1','3706','TEST','source','cut1','cut2','2026-01-01','2026-01-02','2026-01-03','null','{}','https://example.org','Newly observed, not newly occurred')
        source.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',row);source.commit();source.close()
        try:
            self.assertEqual(deliver(db,alerts),0)
            db.execute("INSERT INTO subscriptions VALUES ('3706',1,'2026-01-04')");db.commit();self.assertEqual(deliver(db,alerts),0)
            db.execute("UPDATE subscriptions SET created_at='2026-01-01'");db.commit()
            self.assertEqual(deliver(db,alerts),1);self.assertEqual(deliver(db,alerts),0)
            self.assertEqual(json.loads(db.execute('SELECT payload FROM inbox').fetchone()[0])['previous_cut'],'cut1')
        finally:db.close()
    def test_scheduler_records_failure_and_does_not_promote_partial_acquisition(self):
        self.login();self.request('/api/subscribe',{'dot':'3706','enabled':True})
        with patch('cohort_snapshot.acquire',return_value=(self.root,{'status':'PARTIAL'})),patch('evidence_warehouse.promote') as promote:
            self.app.tick(force=True);promote.assert_not_called()
        state=self.request('/api/state')[1]
        self.assertEqual(state['jobs'][0]['status'],'FAILED');self.assertEqual(state['inbox'],[])
    def test_scheduled_verified_comparison_delivers_once_and_read_state_persists(self):
        from snapshot_store import now
        self.login();self.request('/api/subscribe',{'dot':'3706','enabled':True})
        def compare(evidence,alerts):
            db=sqlite3.connect(alerts);db.executescript(DDL)
            db.execute('INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',('scheduled-test','3706','TEST_ONLY','source','cut1','cut2','2026-01-01','2026-01-02',now(),'null','{}','https://example.org','Test-only evidence change'))
            db.commit();db.close();return {'status':'COMPARED'}
        with patch('cohort_snapshot.acquire',return_value=(self.root,{'status':'COMPLETE'})),patch('evidence_warehouse.promote'),patch('material_alerts.run',side_effect=compare):
            self.app.tick(force=True);self.app.tick(force=True)
        saved=self.request('/api/state')[1]
        self.assertEqual(len(saved['inbox']),1);self.assertEqual(saved['jobs'][0]['status'],'COMPLETE')
        self.request('/api/read',{'id':'scheduled-test'})
        self.assertIsNotNone(self.request('/api/state')[1]['inbox'][0]['read_at'])

@unittest.skipUnless(importlib.util.find_spec('duckdb'),'DuckDB is required for warehouse analytics')
class PeerTests(unittest.TestCase):
    def test_peer_denominators_and_unknowns_are_preserved(self):
        import duckdb
        from workspace_analytics import peers,group_summary
        db=duckdb.connect()
        try:
            db.execute('CREATE TABLE raw_az4n_8mr2(dot_number VARCHAR,phy_country VARCHAR,carrier_operation VARCHAR,fleetsize VARCHAR,status_code VARCHAR,power_units VARCHAR,total_drivers VARCHAR,mcs150_date VARCHAR,legal_name VARCHAR,mcs150_mileage VARCHAR,mcs150_mileage_year VARCHAR)')
            db.execute('CREATE TABLE source_lineage(source_id VARCHAR,cut VARCHAR,available_at VARCHAR,sha256 VARCHAR)')
            db.execute("INSERT INTO source_lineage VALUES ('az4n-8mr2','fixture','2026-09-09T00:00:00Z','fixture-hash')")
            rows=[(str(i),'US','A','K','A',str(i),'10','20260901','Fixture',None,None) for i in range(1,36)]
            rows += [('36','US','A','K','A',None,'10','20260901','Missing',None,None),('37','US','A','K','A','10','10','20200101','Stale',None,None),('38','CA','A','K','A','10','10','20260901','Other country',None,None)]
            db.executemany('INSERT INTO raw_az4n_8mr2 VALUES (?,?,?,?,?,?,?,?,?,?,?)',rows)
            result=peers(db,'1');self.assertEqual(result['candidate_count'],37);self.assertEqual(result['eligible_count'],35);self.assertEqual(result['excluded_count'],2)
            self.assertEqual(result['quartiles']['power_units'],[9.5,18.0,26.5]);self.assertIsNone(peers(db,'36')['quartiles'])
            group=group_summary(db,['1','36','999']);self.assertEqual(group['reported_totals']['power_units'],{'sum':1,'known':1,'denominator':3});self.assertEqual(group['missing'],['999'])
        finally:db.close()

if __name__=='__main__':unittest.main()
