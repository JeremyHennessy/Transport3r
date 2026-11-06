"""Synthetic private intake regressions; never real insurer acceptance evidence."""
import copy
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from private_loss_history import SCHEMA, ROOT, MAX_BYTES, MAX_MONEY, preview, import_loss_history, summarize_batch, private_path
from private_workspace_store import save_portfolio

POLICY={'account_id':' ACCOUNT-TEST ','policy_id':'POLICY-TEST','dot_number':'3706',
        'policy_start':'2020-01-01','policy_end':'2021-01-01','status':'expired',
        'review_status':'reviewed','currency':'USD'}
CLAIM={'claim_id':'SYNTHETIC-1','account_id':POLICY['account_id'],'policy_id':POLICY['policy_id'],
       'dot_number':'3706','coverage_line':'auto-liability','loss_date':'2020-03-01',
       'reported_date':'2020-03-02','status':'open','currency':'USD','paid_minor':0,'outstanding_minor':None}


def envelope(rows=None,**updates):
    return {'schema':SCHEMA,'source_id':'SYNTHETIC-INSURER','document_reference':'Synthetic local loss-run reference',
            'valuation_date':'2020-12-31','permission_confirmed':True,'amount_basis':'GROSS_INDEMNITY_EXCLUDING_EXPENSES_AND_RECOVERIES',
            'claims':copy.deepcopy([CLAIM] if rows is None else rows),**updates}


def raw(data=None):return json.dumps(envelope() if data is None else data,sort_keys=True).encode()


class PrivateLossHistoryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close)
        self.policies=[copy.deepcopy(POLICY)]

    def accept(self,data=None,policies=None):
        source=raw(data);policies=self.policies if policies is None else policies
        return import_loss_history(self.db,source,policies,'Synthetic owner',preview(source,policies)['preview_sha256'])

    def test_preview_writes_nothing_and_preserves_unknowns(self):
        result=preview(raw(),self.policies)
        self.assertEqual(result['status'],'READY_FOR_PRIVATE_IMPORT')
        self.assertEqual(result['input_rows'],1);self.assertEqual(result['imported_rows'],0)
        self.assertFalse(result['public_upload']);self.assertFalse(result['population_complete'])
        self.assertNotIn('SYNTHETIC-1',json.dumps(result))
        self.assertEqual(self.db.execute('SELECT count(*) FROM sqlite_master').fetchone()[0],0)

    def test_commit_deduplicates_and_repeat_is_idempotent(self):
        result=self.accept(envelope([CLAIM,CLAIM]))
        self.assertEqual(result['exact_duplicate_rows'],1);self.assertEqual(result['imported_rows'],1)
        again=self.accept(envelope([CLAIM,CLAIM]));self.assertFalse(again['changed'])
        self.assertEqual(again['imported_rows'],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM loss_observations').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM loss_import_history').fetchone()[0],1)

    def test_unknown_money_remains_unknown_and_explicit_zero_is_retained(self):
        result=self.accept();summary=summarize_batch(self.db,result['batch_id'])
        self.assertEqual(summary['groups'][0]['paid_minor'],{'known_sum':'0','unknown_count':0})
        self.assertEqual(summary['groups'][0]['outstanding_minor'],{'known_sum':'0','unknown_count':1})
        self.assertIsNone(summary['actuarial_score']);self.assertFalse(summary['coverage_determined'])

    def test_permission_empty_or_unknown_envelopes_fail(self):
        for changes in ({'permission_confirmed':False},{'permission_confirmed':1},{'claims':[]},{'schema':'other'},
                        {'extra':'PRIVATE DATA'},{'valuation_date':'2999-01-01'},{'amount_basis':'UNKNOWN'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):preview(raw(envelope(**changes)),self.policies)

    def test_duplicate_json_fields_and_nonfinite_json_fail(self):
        for data in (b'{"schema":1,"schema":2}',b'{"value":NaN}',b'\xff',b'{'*10,b' '* (MAX_BYTES+1)):
            with self.subTest(data=data[:25]),self.assertRaises(ValueError):preview(data,self.policies)

    def test_unknown_fields_and_invalid_values_are_review_required(self):
        for changes in ({'claimant_name':'DO NOT ACCEPT'}, {'paid_minor':True},{'paid_minor':-1},{'paid_minor':1.5},
                        {'outstanding_minor':MAX_MONEY+1},{'paid_minor':'10'}, {'loss_date':'2020-02-30'},
                        {'loss_date':'2020-12-31'}, {'reported_date':'2021-01-01'}, {'status':'denied'},
                        {'coverage_line':[]},{'currency':'usd'},{'claim_id':'  '},{'dot_number':'03706'}):
            with self.subTest(changes=changes):
                value=envelope([{**CLAIM,**changes}]);plan=preview(raw(value),self.policies)
                self.assertEqual(plan['status'],'REVIEW_REQUIRED')
                with self.assertRaises(ValueError):self.accept(value)

    def test_exact_policy_and_usdot_are_required_without_fuzzy_matching(self):
        for changes,reason in (({'account_id':'ACCOUNT-TEST'},'UNMATCHED_POLICY'),
                               ({'policy_id':'UNKNOWN'},'UNMATCHED_POLICY'),
                               ({'dot_number':'999'},'USDOT_IDENTITY_MISMATCH'),
                               ({'currency':'CAD'},'POLICY_CURRENCY_UNVERIFIED_OR_DIFFERENT')):
            plan=preview(raw(envelope([{**CLAIM,**changes}])),self.policies)
            self.assertEqual(plan['issues'][0]['reason'],reason)

    def test_ambiguous_saved_policy_fails(self):
        plan=preview(raw(),[POLICY,POLICY]);self.assertEqual(plan['issues'][0]['reason'],'AMBIGUOUS_SAVED_POLICY')

    def test_policy_period_is_end_exclusive_not_a_coverage_decision(self):
        value=envelope([{**CLAIM,'loss_date':'2021-01-01','reported_date':'2021-01-01'}],valuation_date='2021-02-01')
        self.assertEqual(preview(raw(value),self.policies)['issues'][0]['reason'],'LOSS_OUTSIDE_POLICY_PERIOD_REVIEW')

    def test_closed_nonzero_reserves_need_review_not_silent_repair(self):
        plan=preview(raw(envelope([{**CLAIM,'status':'closed','outstanding_minor':1}])),self.policies)
        self.assertEqual(plan['issues'][0]['reason'],'CLOSED_WITH_OUTSTANDING_REVIEW')

    def test_conflicting_in_batch_rows_do_not_partially_commit(self):
        value=envelope([CLAIM,{**CLAIM,'paid_minor':1}]);plan=preview(raw(value),self.policies)
        self.assertEqual(plan['review_required_rows'],1)
        self.assertEqual(plan['input_rows'],plan['unique_candidate_rows']+plan['exact_duplicate_rows']+plan['review_required_rows'])
        with self.assertRaises(ValueError):self.accept(value)
        self.assertEqual(self.db.execute('SELECT count(*) FROM sqlite_master').fetchone()[0],0)

    def test_changed_preview_or_portfolio_requires_fresh_approval(self):
        approved=preview(raw(),self.policies)['preview_sha256']
        for source,policies in ((raw(envelope([{**CLAIM,'paid_minor':2}])),self.policies),
                                (raw(),[{**POLICY,'review_status':'in_review'}])):
            with self.assertRaisesRegex(ValueError,'PREVIEW_CHANGED'):
                import_loss_history(self.db,source,policies,'Synthetic owner',approved)

    def test_saved_valuation_conflict_rolls_back_other_rows(self):
        self.accept()
        value=envelope([{**CLAIM,'claim_id':'SYNTHETIC-NEW'},{**CLAIM,'paid_minor':42}])
        with self.assertRaisesRegex(ValueError,'CONFLICTING_SAVED'):self.accept(value)
        self.assertEqual(self.db.execute('SELECT count(*) FROM loss_observations').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM loss_batches').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM loss_batch_records').fetchone()[0],1)

    def test_valuations_are_immutable_and_not_summed_across_history(self):
        first=self.accept()
        second=self.accept(envelope([{**CLAIM,'paid_minor':100}],valuation_date='2021-02-01'))
        self.assertEqual(summarize_batch(self.db,first['batch_id'])['groups'][0]['paid_minor']['known_sum'],'0')
        self.assertEqual(summarize_batch(self.db,second['batch_id'])['groups'][0]['paid_minor']['known_sum'],'100')
        self.assertEqual(summarize_batch(self.db,second['batch_id'])['observations'],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM loss_observations').fetchone()[0],2)

    def test_identity_change_between_valuations_is_not_accepted(self):
        self.accept()
        value=envelope([{**CLAIM,'loss_date':'2020-02-01'}],valuation_date='2021-02-01')
        with self.assertRaisesRegex(ValueError,'IDENTITY_CHANGED'):self.accept(value)

    def test_same_observation_in_new_file_is_linked_not_counted_twice(self):
        self.accept();value=envelope(document_reference='Second synthetic copy')
        result=self.accept(value)
        self.assertEqual(result['existing_observation_rows'],1);self.assertEqual(result['imported_rows'],0)
        self.assertEqual(summarize_batch(self.db,result['batch_id'])['observations'],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM loss_observations').fetchone()[0],1)

    def test_different_sources_and_currencies_do_not_silently_merge(self):
        self.accept();self.accept(envelope(source_id='SYNTHETIC-OTHER'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM loss_observations').fetchone()[0],2)
        policies=self.policies+[{**POLICY,'policy_id':'CAD-TEST','currency':'CAD'}]
        result=self.accept(envelope([CLAIM,{**CLAIM,'policy_id':'CAD-TEST','currency':'CAD'}]),policies)
        self.assertEqual([g['currency'] for g in summarize_batch(self.db,result['batch_id'])['groups']],['CAD','USD'])

    def test_large_aggregates_use_exact_decimal_strings(self):
        result=self.accept(envelope([{**CLAIM,'paid_minor':MAX_MONEY},{**CLAIM,'claim_id':'OTHER','paid_minor':MAX_MONEY}]))
        self.assertEqual(summarize_batch(self.db,result['batch_id'])['groups'][0]['paid_minor']['known_sum'],str(MAX_MONEY*2))

    def test_no_commit_inside_active_transaction_or_served_paths(self):
        self.db.execute('CREATE TABLE test(v INTEGER)');self.db.execute('INSERT INTO test VALUES(1)')
        with self.assertRaisesRegex(ValueError,'ACTIVE_TRANSACTION'):self.accept()
        self.db.rollback()
        for name in (ROOT/'private.sqlite',pathlib.Path('/tmp/public/private.sqlite'),pathlib.Path('/tmp/dist/private.sqlite')):
            with self.assertRaises(ValueError):private_path(name)

    def test_existing_world_readable_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=pathlib.Path(temporary)/'loss-history.sqlite'
            with sqlite3.connect(path) as db:
                path.chmod(0o644)
                with self.assertRaisesRegex(ValueError,'PRIVATE_DATABASE_PERMISSIONS'):
                    import_loss_history(db,raw(),self.policies,'Synthetic owner',preview(raw(),self.policies)['preview_sha256'])

    def test_cli_preview_commit_and_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=pathlib.Path(temporary);save_portfolio(folder,self.policies)
            source=folder/'synthetic-input.json';source.write_bytes(raw())
            cmd=[sys.executable,str(ROOT/'scripts/private_loss_history.py'),'--workspace',str(folder),'--input',str(source)]
            plan=json.loads(subprocess.check_output(cmd,text=True));self.assertFalse((folder/'loss-history.sqlite').exists())
            accepted=json.loads(subprocess.check_output(cmd+['--commit','--reviewer','Synthetic owner','--expected-preview',plan['preview_sha256']],text=True))
            self.assertEqual(accepted['imported_rows'],1)
            self.assertEqual((folder/'loss-history.sqlite').stat().st_mode & 0o777,0o600)
            with sqlite3.connect(folder/'loss-history.sqlite') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM loss_import_history').fetchone()[0],1)


if __name__=='__main__':unittest.main()
