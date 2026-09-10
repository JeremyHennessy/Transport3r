from contextlib import closing
import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from compliance_tracking import assess,order_state,persist,latest,save_action,actions,SOURCES
from private_workspace_store import connect
from private_workspace import Workspace


def fixture():
    rows={sid:[]for sid in SOURCES}
    rows['az4n-8mr2']=[{'dot_number':'1','legal_name':'SYNTHETIC TEST CARRIER','status_code':'A','mcs150_date':'20260801'}]
    rows['inys-ebih']=[{'docket_number':'MC1','usdot_number':'1','op_auth_type':'Property','op_auth_status':'Active'}]
    rows['c5y8-a4uz']=[{'usdot_number':'1','policy_no':'TEST ONLY','effective_date':'20260101'}]
    return {sid:{'status':'VERIFIED','rows':value,'published_carrier_rows':len(value),'available_at':'2026-09-09T12:00:00Z','sha256':'TEST ONLY','url':'https://data.transportation.gov/d/'+sid}for sid,value in rows.items()}


class ComplianceTests(unittest.TestCase):
    def review(self,data=None,cut='fixture1',at='2026-09-09T12:00:00Z'):
        return assess('1',cut,at,data or fixture(),'TEST_FIXTURE')
    def check(self,result,key):return next(c for c in result['checks']if c['id']==key)
    def test_no_rule_trigger_is_not_a_compliance_certificate(self):
        r=self.review();self.assertEqual(r['status'],'NO_RULE_TRIGGER');self.assertIn('not certification',r['limitation'])
    def test_missing_source_and_empty_filing_never_mean_compliant(self):
        data=fixture();del data['inys-ebih'];data['c5y8-a4uz']['rows']=[]
        r=self.review(data);self.assertEqual(r['gap_count'],2);self.assertEqual(r['status'],'INCOMPLETE_EVIDENCE')
    def test_registration_and_authority_are_separate(self):
        data=fixture();data['az4n-8mr2']['rows'][0]['status_code']='I'
        r=self.review(data);self.assertEqual(self.check(r,'REGISTRATION')['state'],'REVIEW');self.assertEqual(self.check(r,'AUTHORITY')['state'],'INFORMATION')
    def test_report_age_boundary_and_future_date(self):
        data=fixture();at=dt.date(2026,9,9)
        for age,state in [(730,'INFORMATION'),(731,'REVIEW'),(-1,'DATA_GAP')]:
            data['az4n-8mr2']['rows'][0]['mcs150_date']=str(at-dt.timedelta(days=age))
            self.assertEqual(self.check(self.review(data),'REPORT_AGE')['state'],state)
    def test_authority_conflicts_remain_unknown(self):
        data=fixture();data['inys-ebih']['rows'].append({**data['inys-ebih']['rows'][0],'op_auth_status':'Inactive'})
        self.assertEqual(self.check(self.review(data),'AUTHORITY')['state'],'DATA_GAP')
    def test_exact_duplicate_filings_and_source_ids_do_not_multiply(self):
        data=fixture();r=data['c5y8-a4uz']['rows'][0];r['source_row_id']='a'
        data['c5y8-a4uz']['rows'].append({**r,'source_row_id':'b'})
        self.assertEqual(len(self.check(self.review(data),'FILINGS')['values']),1)
    def test_order_dates_ignore_registration_status_and_rescission_boundaries(self):
        at=dt.date(2026,9,9);r={'oos_date':'20260901','status':'A'}
        self.assertEqual(order_state(r,at),'ISSUED_NO_RESCISSION_RECORDED')
        self.assertEqual(order_state({**r,'rescind_date':'20260909'},at),'RESCINDED')
        self.assertEqual(order_state({**r,'rescind_date':'20260910'},at),'RESCISSION_SCHEDULED')
        self.assertEqual(order_state({**r,'rescind_date':'20250801'},at),'UNKNOWN')
        self.assertEqual(order_state({**r,'oos_date':'20260910'},at),'FUTURE_ISSUE')
    def test_history_window_is_inclusive_and_replacement_is_not_a_gap(self):
        data=fixture();data['3uet-3z4i']['rows']=[{'cancl_effective_date':str(dt.date(2026,9,9)+dt.timedelta(days=d)),'filing_status_reason':'Replaced'} for d in (-31,-30,30,31)]
        c=self.check(self.review(data),'FILING_CHANGES');self.assertEqual(len(c['values']['near_observation']),2);self.assertIn('does not establish a coverage gap',c['action'])
    def test_case_insensitive_source_fields_and_invalid_filing_date(self):
        data=fixture();data['c5y8-a4uz']['rows']=[{'EFFECTIVE_DATE':'not a date','POLICY_NO':'TEST'}]
        self.assertEqual(self.check(self.review(data),'FILINGS')['state'],'DATA_GAP')

    def test_durable_changes_only_after_subscribed_baseline_and_no_repeat_delivery(self):
        with tempfile.TemporaryDirectory() as folder,closing(connect(pathlib.Path(folder)/'private.sqlite')) as db:
            db.execute("INSERT INTO subscriptions VALUES ('1',1,'2026-09-08T00:00:00Z')");db.commit()
            self.assertEqual(persist(db,self.review())['delivered'],0)
            data=fixture();data['p2mt-9ige']['rows']=[{'oos_date':'20260909'}]
            newer=self.review(data,'fixture2','2026-09-10T12:00:00Z')
            self.assertEqual(persist(db,newer)['delivered'],1);self.assertEqual(persist(db,newer)['delivered'],0)
            alert=json.loads(db.execute('SELECT payload FROM inbox').fetchone()[0])
            self.assertIn('NEW_ENTRANT_OOS',alert['current_state']);self.assertEqual(alert['previous_cut'],'fixture1')
            self.assertEqual(latest(db,'1')['id'],newer['id'])
    def test_unchanged_day_to_day_report_age_does_not_spam(self):
        with tempfile.TemporaryDirectory() as folder,closing(connect(pathlib.Path(folder)/'private.sqlite')) as db:
            db.execute("INSERT INTO subscriptions VALUES ('1',1,'2026-09-08T00:00:00Z')");db.commit()
            persist(db,self.review());r=self.review(cut='fixture2',at='2026-09-10T12:00:00Z')
            self.assertEqual(persist(db,r)['delivered'],0)
    def test_paused_new_subscription_and_old_cut_do_not_backfill_alerts(self):
        with tempfile.TemporaryDirectory() as folder,closing(connect(pathlib.Path(folder)/'private.sqlite')) as db:
            persist(db,self.review());db.execute("INSERT INTO subscriptions VALUES ('1',1,'2026-09-10T00:00:00Z')");db.commit()
            data=fixture();data['az4n-8mr2']['rows'][0]['status_code']='I'
            self.assertEqual(persist(db,self.review(data,'fixture2','2026-09-11T12:00:00Z'))['delivered'],0)
            self.assertEqual(persist(db,self.review(cut='older',at='2026-09-01T00:00:00Z'))['delivered'],0)
            db.execute("UPDATE subscriptions SET enabled=0");db.commit()
            self.assertEqual(persist(db,self.review(cut='fixture3',at='2026-09-12T12:00:00Z'))['delivered'],0)
    def test_modified_observation_rejected_and_resolved_action_keeps_source_flag(self):
        with tempfile.TemporaryDirectory() as folder,closing(connect(pathlib.Path(folder)/'private.sqlite')) as db:
            data=fixture();data['az4n-8mr2']['rows'][0]['status_code']='I';r=self.review(data);persist(db,r)
            changed=copy.deepcopy(r);changed['name']='Tampered'
            with self.assertRaises(ValueError):persist(db,changed)
            body={'observation_id':r['id'],'check_id':'REGISTRATION','status':'resolved','notes':'TEST ONLY: recorded analyst review','due_date':'2020-01-01'}
            save_action(db,body,'TEST OWNER');self.assertEqual(latest(db,'1')['status'],'REVIEW_NEEDED');self.assertFalse(actions(db)[0]['overdue'])
            newer=self.review(cut='fixture2',at='2026-09-10T12:00:00Z');persist(db,newer)
            self.assertTrue(actions(db)[0]['evidence_changed'])
            save_action(db,{**body,'status':'open'},'TEST OWNER');self.assertTrue(actions(db)[0]['overdue'])
            self.assertEqual(db.execute('SELECT count(*) FROM compliance_action_history').fetchone()[0],2)
            with self.assertRaises(ValueError):save_action(db,{**body,'due_date':'2026-02-31'},'TEST OWNER')
    def test_refresh_busy_is_explicit_and_incomplete_cut_never_captured(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Workspace(folder)
            app.lock.acquire()
            try:self.assertFalse(app.request_check(['1']))
            finally:app.lock.release()
            with closing(connect(app.path)) as db:db.execute("INSERT INTO owner VALUES ('TEST OWNER','test','test')");db.commit()
            with patch('cohort_snapshot.acquire',return_value=(pathlib.Path(folder),{'status':'PARTIAL'})),patch('compliance_tracking.capture_verified_cut') as capture:
                app.tick(force=True,dots_override=['1']);capture.assert_not_called()
            with closing(connect(app.path)) as db:
                self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'FAILED')
                self.assertIsNone(db.execute("SELECT value FROM settings WHERE key='next_run'").fetchone())

if __name__=='__main__':unittest.main()
