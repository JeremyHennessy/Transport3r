import importlib.util
import json
import pathlib
import tempfile
import unittest
from private_workspace_store import connect, save_screening_case, group_members


@unittest.skipUnless(importlib.util.find_spec('duckdb'), 'DuckDB required')
class IdentityTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.tmp=tempfile.TemporaryDirectory()
        self.path=pathlib.Path(self.tmp.name)/'test.duckdb'
        self.db=duckdb.connect(str(self.path))
        fields='dot_number legal_name status_code add_date mcs150_date power_units total_drivers mcs150_mileage mcs150_mileage_year phone cell_phone email_address company_officer_1 company_officer_2 dun_bradstreet_no phy_street phy_city phy_state phy_country phy_zip prior_revoke_dot_number'.split()
        self.fields=fields
        self.db.execute('CREATE TABLE raw_az4n_8mr2 ('+','.join(f+' VARCHAR' for f in fields)+')')
        self.db.execute('CREATE TABLE source_lineage(source_id VARCHAR,cut VARCHAR,available_at VARCHAR,sha256 VARCHAR)')
        for sid in ['az4n-8mr2','fx4q-ay7w','aayw-vxb3']:
            self.db.execute('INSERT INTO source_lineage VALUES (?,?,?,?)',[sid,'fixture-'+sid,'2026-09-09T12:00:00Z','test-only-hash'])
        self.db.execute('CREATE TABLE raw_fx4q_ay7w(_warehouse_row_id BIGINT,inspection_id VARCHAR,dot_number VARCHAR,insp_date VARCHAR,oos_total VARCHAR)')
        self.db.execute('CREATE TABLE raw_aayw_vxb3(_warehouse_row_id BIGINT,crash_id VARCHAR,dot_number VARCHAR,report_date VARCHAR)')

    def tearDown(self):
        self.db.close();self.tmp.cleanup()

    def carrier(self,identifier,**values):
        values={'dot_number':identifier,'legal_name':'TEST ONLY '+identifier,'status_code':'A','power_units':'10','total_drivers':'8',**values}
        self.db.execute('INSERT INTO raw_az4n_8mr2 VALUES ('+','.join('?' for _ in self.fields)+')',[values.get(f) for f in self.fields])

    def inspection(self,identifier,dot,date,oos='0',rowid=1):
        self.db.execute('INSERT INTO raw_fx4q_ay7w VALUES (?,?,?,?,?)',[rowid,identifier,dot,date,oos])

    def test_exact_shared_categories_cross_officer_slots_and_phone_formats(self):
        from identity_analytics import identity_screen
        self.carrier('1',phone='+1 (902) 456-7890',company_officer_1=' Jane  Doe ',email_address='OPS@TEST-FLEET.NET')
        self.carrier('2',cell_phone='9024567890',company_officer_2='JANE DOE',email_address='ops@test-fleet.net')
        self.carrier('3',phone='9024567890')
        result=identity_screen(self.db,'1')
        self.assertEqual(result['total'],2)
        first=result['candidates'][0]
        self.assertEqual(first['dot'],'2');self.assertEqual(first['category_count'],3)
        self.assertEqual(first['review_reason'],'MULTIPLE_SHARED_CATEGORIES')
        self.assertEqual(result['source']['cut'],'fixture-az4n-8mr2')
        self.assertIn('company_officer_2',first['candidate_source_values'])

    def test_missing_placeholders_and_name_similarity_do_not_match(self):
        from identity_analytics import identity_screen
        for i in ['1','2']:
            self.carrier(i,phone='0000000000',cell_phone='1234567890',email_address='unknown@example.com',company_officer_1='NOT PROVIDED',dun_bradstreet_no='000000000',legal_name='SAME LOGISTICS')
        self.assertEqual(identity_screen(self.db,'1')['total'],0)

    def test_full_address_requires_region_country_zip_and_preserves_unit(self):
        from identity_analytics import identity_screen
        a=dict(phy_street='123 Main St Unit 2',phy_city='Halifax',phy_state='NS',phy_country='CA',phy_zip='B3J 1A1')
        self.carrier('1',**a);self.carrier('2',**a)
        self.carrier('3',**{**a,'phy_street':'123 Main St Unit 3'})
        self.carrier('4',**{**a,'phy_zip':None})
        self.assertEqual([r['dot'] for r in identity_screen(self.db,'1')['candidates']],['2'])

    def test_pagination_common_contacts_and_distinct_category_order(self):
        from identity_analytics import identity_screen
        for i in range(1,55):self.carrier(str(i),phone='9024567890')
        r1=identity_screen(self.db,'1');r2=identity_screen(self.db,'1',2)
        self.assertEqual(r1['total'],53);self.assertEqual(len(r1['candidates']),50)
        self.assertEqual(len(r2['candidates']),3);self.assertFalse(r2['has_next'])
        self.assertTrue(r1['candidates'][0]['matches'][0]['common_detail'])
        self.assertFalse({c['dot'] for c in r1['candidates']}&{c['dot'] for c in r2['candidates']})

    def test_prior_revocation_reference_is_directional_evidence(self):
        from identity_analytics import identity_screen
        self.carrier('1',prior_revoke_dot_number='2');self.carrier('2',status_code='I');self.carrier('3',prior_revoke_dot_number='1')
        r=identity_screen(self.db,'1');self.assertEqual(r['total'],2)
        self.assertEqual({m['category'] for c in r['candidates'] for m in c['matches']},{'prior_revocation_reference','reverse_prior_revocation_reference'})

    def test_event_window_inclusive_deduplicated_members_and_rows(self):
        from identity_analytics import event_summary
        self.inspection('a','1','20250910','1');self.inspection('a','1','20250910','1',2)
        self.inspection('b','2','2026-09-09T00:00:00','0')
        self.inspection('old','1','20250909','2');self.inspection('other','3','20260909')
        r=event_summary(self.db,['1','2','1'])
        self.assertEqual(r['members'],['1','2']);self.assertEqual(r['metrics']['inspections']['count'],2)
        self.assertEqual(r['metrics']['inspections']['oos']['rate_pct'],50)
        self.assertEqual(r['metrics']['crash_reports']['count'],0)

    def test_conflicting_ids_and_missing_dates_fail_closed(self):
        from identity_analytics import event_summary
        self.inspection('a','1','20260901');self.inspection('a','2','20260902')
        self.inspection('bad','1','invalid')
        r=event_summary(self.db,['1','2'])
        self.assertEqual(r['status'],'PARTIAL_EVIDENCE')
        self.assertIsNone(r['metrics']['inspections']['count'])
        self.assertEqual(r['metrics']['inspections']['issues']['invalid_event_date'],1)
        self.assertIsNone(r['metrics']['inspections']['oos']['rate_pct'])

    def test_unknown_oos_is_not_zero_and_future_dates_are_disclosed(self):
        from identity_analytics import event_summary
        self.inspection('a','1','20260901',None);self.inspection('future','1','20270901')
        r=event_summary(self.db,['1'])['metrics']['inspections']
        self.assertIsNone(r['count']);self.assertEqual(r['oos']['unknown'],1)
        self.assertEqual(r['issues']['future_event_date'],1);self.assertIsNone(r['oos']['rate_pct'])

    def test_crash_vehicle_reports_not_deduplicated_by_date(self):
        from identity_analytics import event_summary
        self.db.executemany('INSERT INTO raw_aayw_vxb3 VALUES (?,?,?,?)',[(1,'a','1','20260901'),(2,'b','2','20260901')])
        r=event_summary(self.db,['1','2'])
        self.assertEqual(r['metrics']['crash_reports']['count'],2)

    def test_ghost_status_activity_is_not_operation_while_inactive(self):
        from identity_analytics import ghost_review,ghost_queue
        self.carrier('1',status_code='I');self.carrier('2');self.carrier('3',status_code='I')
        self.inspection('a','1','20260901');self.inspection('b','2','20260901');self.inspection('c','3','20200101')
        r=ghost_review(self.db,'1');self.assertEqual(r['finding'],'STATUS_ACTIVITY_REVIEW')
        self.assertIsNone(r['status_effective_date']);self.assertEqual(r['activity_while_inactive'],'NOT_ESTABLISHED')
        self.assertEqual(ghost_review(self.db,'2')['finding'],'NO_STATUS_ACTIVITY_RULE_TRIGGER')
        self.assertEqual(ghost_review(self.db,'3')['finding'],'NO_RECENT_PUBLISHED_ACTIVITY')
        queue=ghost_queue(self.db);self.assertEqual(queue['total'],1);self.assertEqual(queue['rows'][0]['dot'],'1')

    def test_unresolved_registration_and_invalid_inputs(self):
        from identity_analytics import ghost_review,identity_screen,event_summary
        self.assertEqual(ghost_review(self.db,'99')['finding'],'REGISTRATION_UNRESOLVED')
        with self.assertRaises(ValueError):identity_screen(self.db,"1' OR 1=1")
        with self.assertRaises(ValueError):identity_screen(self.db,'99')
        with self.assertRaises(ValueError):event_summary(self.db,['1'],30)

    def test_group_exposure_deduplicates_dot_and_preserves_missing_denominator(self):
        from workspace_analytics import group_summary
        self.carrier('1');r=group_summary(self.db,['1','1','2'])
        self.assertEqual(r['reported_totals']['power_units'],{'sum':10,'known':1,'denominator':2})

    def test_authenticated_api_group_review_revocation_and_case_evidence(self):
        import http.client
        import threading
        from private_workspace import Workspace,make_server
        self.carrier('1',phone='9024567890');self.carrier('2',phone='9024567890',status_code='I')
        self.inspection('a','1','20260901','1');self.inspection('b','2','20260902','0')
        self.db.execute('CREATE TABLE warehouse_acceptance(acceptance_json VARCHAR)')
        self.db.execute('INSERT INTO warehouse_acceptance VALUES (?)',[json.dumps({'status':'VERIFIED'})]);self.db.close()
        app=Workspace(pathlib.Path(self.tmp.name)/'private',self.path);server=make_server(app,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();cookie=None
        def request(path,body=None):
            nonlocal cookie
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
            headers={'Origin':f'http://127.0.0.1:{server.server_port}','Content-Type':'application/json'}
            if cookie:headers['Cookie']=cookie
            conn.request('GET' if body is None else 'POST',path,json.dumps(body) if body is not None else None,headers)
            response=conn.getresponse();result=json.loads(response.read());new=response.getheader('Set-Cookie')
            if new:cookie=new.split(';')[0]
            status=response.status;conn.close();self.assertEqual(status,200,result);return result
        try:
            request('/api/setup',{'name':'TEST ONLY','password':'fixture-only-password'})
            self.assertEqual(request('/api/group?dot=1')['members'],['1'])
            rel=request('/api/relationship',{'dot_a':'1','dot_b':'2','kind':'common_ownership','evidence_url':'https://example.org/test-only','notes':'Synthetic fixture ownership evidence'})
            self.assertEqual(request('/api/group?dot=1')['members'],['1'])
            request('/api/review',{'id':rel['id'],'status':'approved','review_note':'Synthetic test-only approval'})
            group=request('/api/group?dot=1')
            self.assertEqual(group['members'],['1','2']);self.assertEqual(group['safety']['metrics']['inspections']['count'],2)
            self.assertEqual(len(group['approved_relationships']),1)
            screen=request('/api/identity-screen?dot=1');self.assertEqual(screen['total'],1)
            case=request('/api/screening-case',{'kind':'chameleon','dot':'1','candidate_dot':'2','status':'in_review','notes':'TEST ONLY shared telephone review','evidence':{'fake':'CLIENT DATA MUST NOT BE USED'}})
            history=request('/api/screening-history?id='+case['id'])
            self.assertEqual(len(history),1)
            stored=json.loads(history[0]['payload'])['evidence']
            self.assertEqual(stored['source']['sha256'],'test-only-hash');self.assertNotIn('fake',stored)
            self.assertEqual(request('/api/ghost?dot=2')['finding'],'STATUS_ACTIVITY_REVIEW')
            self.assertEqual(request('/api/ghost-queue')['total'],1)
            request('/api/review',{'id':rel['id'],'status':'revoked','review_note':'Synthetic test-only revocation'})
            self.assertEqual(request('/api/group?dot=1')['members'],['1'])
        finally:
            server.shutdown();server.server_close();thread.join()


class CaseTests(unittest.TestCase):
    def test_durable_case_history_never_changes_ownership(self):
        with tempfile.TemporaryDirectory() as folder:
            db=connect(pathlib.Path(folder)/'workspace.sqlite')
            try:
                body={'kind':'chameleon','dot':'1','candidate_dot':'2','status':'in_review','notes':'Test-only shared office lead'}
                identity=save_screening_case(db,body,'TEST OWNER',{'source':'TEST ONLY'})
                self.assertEqual(identity,save_screening_case(db,{**body,'status':'dismissed','notes':'Shared service provider confirmed in test'},'TEST OWNER',{'source':'TEST ONLY 2'}))
                self.assertEqual(db.execute('SELECT count(*) FROM screening_history').fetchone()[0],2)
                self.assertEqual(group_members(db,'1'),['1'])
                self.assertEqual(db.execute('SELECT status FROM screening_cases').fetchone()[0],'dismissed')
                with self.assertRaises(ValueError):save_screening_case(db,{**body,'status':'confirmed_fraud'},'TEST OWNER',{})
            finally:db.close()

if __name__=='__main__':unittest.main()
