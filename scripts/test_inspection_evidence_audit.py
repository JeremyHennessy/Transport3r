import copy
import datetime as dt
import pathlib
import unittest
from unittest.mock import patch

from inspection_evidence_audit import DAILY, SMS, VIOLATION, audit_cut, audit_rows, calendar_counts


class InspectionAuditTests(unittest.TestCase):
    start, end = dt.date(2026, 1, 1), dt.date(2026, 3, 31)

    def data(self):
        parent = {'dot_number':'1', 'source_row_id':'p1', 'unique_id':'sms1', 'insp_date':'01-JAN-26'}
        violation = {'dot_number':'1', 'source_row_id':'v1', 'unique_id':'sms1', 'insp_date':'20260101'}
        return {DAILY:[{'dot_number':'1','source_row_id':'d1','inspection_id':'daily1','insp_date':'20260101'}],
                SMS:[parent], VIOLATION:[violation, {**violation,'source_row_id':'v2'}]}

    def test_many_violations_do_not_multiply_inspections(self):
        r = audit_rows(self.data(), ['1'], self.start, self.end)
        self.assertEqual(r['status'], 'PASS')
        self.assertEqual(r['matched_violation_rows'], 2)
        self.assertEqual(r['carriers'][0]['window_sms_parents_with_violations'], 1)
        self.assertEqual(r['sms_parent_rows'], 1)

    def test_sparse_months_are_observations_not_missing_sources(self):
        r = audit_rows(self.data(), ['1','2'], self.start, self.end)
        self.assertEqual(r['status'], 'PASS')
        month = r['carriers'][0]['sources'][SMS]['months'][1]
        self.assertEqual(month, {'month':'2026-02','known_rows':0,'window_rows':0,'interpretation':'NO_OBSERVED_ROWS'})
        self.assertEqual(r['sms_release_alignment'], 'NOT_ESTABLISHED')
        self.assertIsNone(r['risk_score'])

    def test_duplicate_parents_and_carrier_contamination_fail(self):
        for sid, field in [(DAILY,'inspection_id'),(SMS,'unique_id')]:
            with self.subTest(sid=sid):
                data = self.data(); data[sid].append({**data[sid][0], 'source_row_id':'different'})
                with self.assertRaisesRegex(ValueError, 'parent identity'):
                    audit_rows(data,['1'],self.start,self.end)
        data = self.data(); data[VIOLATION][0]['dot_number']='9'
        with self.assertRaisesRegex(ValueError, 'out-of-cohort'):
            audit_rows(data,['1'],self.start,self.end)

    def test_orphan_cross_carrier_and_conflicting_dates_are_incomplete(self):
        for edits, reason in [({'unique_id':'absent'},'ORPHAN_VIOLATION'),
                              ({'dot_number':'2'},'CROSS_CARRIER_PARENT'),
                              ({'insp_date':'20260102'},'CONFLICTING_JOIN_DATE')]:
            with self.subTest(reason=reason):
                data = self.data(); data[VIOLATION][0].update(edits)
                r = audit_rows(data,['1','2'],self.start,self.end)
                self.assertEqual(r['status'],'INCOMPLETE')
                c = next(c for c in r['carriers'] if c['dot_number']==data[VIOLATION][0]['dot_number'])
                self.assertIsNone(c['window_sms_parents_with_violations'])
                self.assertEqual(c['join_issues'][0]['reason'], reason)

    def test_unknown_dates_do_not_become_zero(self):
        data = self.data(); data[SMS][0]['insp_date']='invalid'
        r = audit_rows(data,['1'],self.start,self.end)
        source = r['carriers'][0]['sources'][SMS]
        self.assertIsNone(source['window_rows'])
        self.assertIsNone(source['months'][0]['window_rows'])
        self.assertEqual(source['known_window_rows'],0)
        self.assertEqual(r['status'],'INCOMPLETE')

    def test_explicit_inclusive_boundaries_and_future_exclusion(self):
        rows = [{'insp_date':v} for v in ['20251231','20260101','20260331','20260401']]
        r = calendar_counts(rows,self.start,self.end)
        self.assertEqual((r['before_window'],r['window_rows'],r['after_window']),(1,2,1))
        self.assertEqual(sum(m['known_rows'] for m in r['months']),2)
        with self.assertRaisesRegex(ValueError,'ordered'):
            audit_rows(self.data(),['1'],self.end,self.start)

    def test_missing_source_and_duplicate_raw_row_fail(self):
        data=self.data(); data.pop(VIOLATION)
        with self.assertRaisesRegex(ValueError,'required'):
            audit_rows(data,['1'],self.start,self.end)
        data=self.data(); data[VIOLATION].append(copy.deepcopy(data[VIOLATION][0]))
        with self.assertRaisesRegex(ValueError,'raw identity'):
            audit_rows(data,['1'],self.start,self.end)

    def test_future_window_rejected_after_verified_cut_check(self):
        with patch('inspection_evidence_audit.load_verified', return_value=(
            {'completed_at':'2026-03-01T00:00:00Z'}, {'dots':['1']}, self.data())) as loader:
            with self.assertRaisesRegex(ValueError,'knowledge time'):
                audit_cut(pathlib.Path('cut'),self.start,self.end,'2026-03-01T00:00:00Z')
            loader.assert_called_once_with(pathlib.Path('cut'),'2026-03-01T00:00:00Z')


if __name__ == '__main__':
    unittest.main()
