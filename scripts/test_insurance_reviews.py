"""Private insurer review validation and durable change-history regression."""
import sqlite3
import unittest
from insurance_reviews import ensure, save_review, list_reviews, history

POLICY={'account_id':'A1','policy_id':'Q1','dot_number':'3706'}
BODY={'account_id':'A1','policy_id':'Q1','dot_number':'3706',
      'line':'auto-liability','status':'needs_data','notes':'Require three full years of claims history',
      'evidence_url':'https://www.fmcsa.dot.gov/','source_cut':'','due_date':'2026-12-01'}

class CoverageReviewTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        ensure(self.db)
    def tearDown(self):self.db.close()
    def test_save_idempotent_and_versioned(self):
        first=save_review(self.db,BODY,[POLICY],'Analyst')
        self.assertTrue(first['changed'])
        second=save_review(self.db,BODY,[POLICY],'Analyst')
        self.assertEqual(first['id'],second['id']);self.assertFalse(second['changed'])
        updated=save_review(self.db,{**BODY,'status':'in_review','notes':'Claims still pending insurer confirmation'},[POLICY],'Analyst')
        self.assertTrue(updated['changed']);self.assertEqual(first['id'],updated['id'])
        rows=list_reviews(self.db);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'in_review')
        changes=history(self.db,first['id'])
        self.assertEqual(len(changes),2)
        self.assertIsNone(changes[0]['previous_json'])
        self.assertIn('needs_data',changes[1]['previous_json'])
    def test_requires_saved_matching_account_policy_dot(self):
        for policies in ([],[{**POLICY,'dot_number':'3707'}],[{**POLICY,'policy_id':'Q2'}]):
            with self.assertRaisesRegex(ValueError,'existing private'):
                save_review(self.db,BODY,policies,'Analyst')
        self.assertEqual(list_reviews(self.db),[])
    def test_rejects_unreviewed_claims_and_unsafe_source_reference(self):
        cases=[
            ({'line':'invented'},'Unsupported insurance line'),
            ({'status':'approved'},'Unsupported review status'),
            ({'notes':'no'},'at least 10'),
            ({'evidence_url':'javascript:alert(1)'},'HTTP'),
            ({'evidence_url':'https://user:password@example.com/a'},'embedded credentials'),
            ({'due_date':'2026-13-80'},'valid calendar'),
            ({'source_cut':'x'*251},'maximum length'),
            ({'risk_score':99},'Unknown review fields'),
        ]
        for patch,error in cases:
            with self.subTest(patch=patch),self.assertRaisesRegex(ValueError,error):
                save_review(self.db,{**BODY,**patch},[POLICY],'Analyst')
    def test_nullable_evidence_references_and_unknown_not_zero(self):
        row=save_review(self.db,{**BODY,'evidence_url':'','source_cut':'','due_date':''},[POLICY],'Owner')
        item=list_reviews(self.db)[0]
        self.assertIsNone(item['evidence_url']);self.assertIsNone(item['source_cut'])
        self.assertFalse('risk_score' in item);self.assertEqual(item['status'],'needs_data')
        self.assertEqual(len(history(self.db,row['id'])),1)

if __name__=='__main__':unittest.main()
