import pathlib,sqlite3,tempfile,unittest
from material_alerts import compare_states
from portfolio_store import import_records,validate

class MonitoringTests(unittest.TestCase):
    def test_newly_observed_is_not_newly_occurred(self):
        changes,issues=compare_states('1','aayw-vxb3',[{'crash_id':'a'}],[{'crash_id':'a'},{'crash_id':'b','report_date':'20200101'}])
        self.assertEqual(changes[0]['rule'],'NEWLY_OBSERVED_CRASH_REPORT');self.assertIn('not necessarily newly occurred',changes[0]['materiality']);self.assertEqual(issues,[])
    def test_missing_exposure_is_not_zero_change(self):
        changes,issues=compare_states('1','az4n-8mr2',[{'power_units':'10'}],[{'power_units':None}]);self.assertEqual(changes,[]);self.assertIn('UNKNOWN_power_units',issues)
    def test_source_row_ids_are_not_filing_changes(self):
        a=[{'source_row_id':'old','insurance_company_name':'Insurer'}];b=[{'source_row_id':'new','insurance_company_name':'Insurer'}]
        self.assertEqual(compare_states('1','c5y8-a4uz',a,b)[0],[])
    def test_duplicate_event_identity_blocks_change_rule(self):
        self.assertEqual(compare_states('1','fx4q-ay7w',[],[{'inspection_id':'a'},{'inspection_id':'a'}])[1],['EVENT_IDENTITY_NOT_UNIQUE'])
    def test_violation_changes_preserve_prior_and_current(self):
        changes,_=compare_states('1','876r-jsdb',[],[{'inspection_id':'a','viol_code':'X'}])
        self.assertEqual(changes[0]['rule'],'VIOLATION_EVIDENCE_CHANGED')
        self.assertEqual(changes[0]['previous'],[])
        self.assertIn('not established deterioration',changes[0]['materiality'])
    def record(self):return {'account_id':'TEST','policy_id':'TEST POLICY','dot_number':'1','policy_start':'2026-01-01','policy_end':'2027-01-01','status':'quoted','review_status':'unreviewed','premium_minor':None}
    def test_private_persistence_is_versioned_idempotent_and_transactional(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'private.sqlite';row=self.record()
            self.assertEqual(import_records(path,[row])['changes'],1);self.assertEqual(import_records(path,[row])['changes'],0)
            with self.assertRaises(ValueError):import_records(path,[row,{**row,'policy_id':'bad','scheduled_units':-1}])
            db=sqlite3.connect(path);self.assertEqual(db.execute('select count(*) from portfolio').fetchone()[0],1);self.assertEqual(db.execute('select count(*) from portfolio_history').fetchone()[0],1);db.close()
    def test_private_data_and_currency_are_not_guessed(self):
        with self.assertRaises(ValueError):validate({**self.record(),'premium_minor':1000})
        with self.assertRaises(ValueError):import_records('public/private.sqlite',[self.record()])

if __name__=='__main__':unittest.main()
