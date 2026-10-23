import pathlib
import tempfile
import unittest
from unittest.mock import patch

import cohort_snapshot as cs
import validate_evidence_warehouse as gate


def source_state(**changes):
    state={'observed_at':'2026-10-23T12:00:00Z','rows_updated_at':123,
           'schema_sha256':'schema-a','table_id':'table-a','row_count':10}
    state.update(changes)
    return state


class SourceStabilityTests(unittest.TestCase):
    def test_stable_window_accepts_identical_contract_values(self):
        cs.stable(source_state(),source_state(observed_at='2026-10-23T12:01:00Z'))

    def test_changed_fields_and_values_are_reported(self):
        after=source_state(rows_updated_at=124,schema_sha256='schema-b',row_count=11)
        with self.assertRaises(cs.SourceChangedError) as raised:
            cs.stable(source_state(),after)
        message=str(raised.exception)
        self.assertIn('rows_updated_at: 123 -> 124',message)
        self.assertIn("schema_sha256: 'schema-a' -> 'schema-b'",message)
        self.assertIn('row_count: 10 -> 11',message)
        self.assertNotIn('table_id:',message)

    def test_missing_watermark_is_distinct_and_not_a_source_change(self):
        with self.assertRaisesRegex(cs.SourceWatermarkError,'before, after'):
            cs.stable(source_state(rows_updated_at=None),source_state(rows_updated_at=None))

    def test_one_fresh_cut_retry_reuses_the_preserved_cohort(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            first=root/'cut-one';second=root/'cut-two';first.mkdir();second.mkdir()
            (first/'cohort.json').write_text('{}',encoding='utf-8')
            partial={'snapshot_id':'cut-one','status':'PARTIAL','datasets':[
                {'id':'876r-jsdb','status':'FAILED','error':'SourceChangedError: Source changed during acquisition (row_count: 10 -> 11)'}]}
            complete={'snapshot_id':'cut-two','status':'COMPLETE','datasets':[]}
            with patch.object(gate,'acquire',side_effect=[(first,partial),(second,complete)]) as acquire:
                cut,manifest,attempts=gate.acquire_stable_cut(root/'raw',1,'underwriting_evidence_v3')
            self.assertEqual((cut,manifest),(second,complete))
            self.assertEqual([item['status'] for item in attempts],['PARTIAL','COMPLETE'])
            self.assertEqual(attempts[0]['failures'][0]['source_id'],'876r-jsdb')
            self.assertFalse(attempts[0]['cohort_reused']);self.assertTrue(attempts[1]['cohort_reused'])
            self.assertEqual(acquire.call_args_list[1].kwargs['cohort_path'],first/'cohort.json')

    def test_retry_is_bounded_and_hard_failures_are_not_retried(self):
        changed={'snapshot_id':'one','status':'PARTIAL','datasets':[
            {'id':'qbt8-7vic','status':'FAILED','error':'SourceChangedError: changed'}]}
        second={**changed,'snapshot_id':'two'}
        with patch.object(gate,'acquire',side_effect=[(pathlib.Path('one'),changed),(pathlib.Path('two'),second)]) as acquire:
            _,manifest,attempts=gate.acquire_stable_cut(pathlib.Path('raw'),1,'underwriting_evidence_v3')
        self.assertEqual(manifest['snapshot_id'],'two');self.assertEqual(len(attempts),2);self.assertEqual(acquire.call_count,2)

        for error in ['SourceWatermarkError: missing','ValueError: wrong schema']:
            hard={'snapshot_id':'hard','status':'PARTIAL','datasets':[{'id':'876r-jsdb','status':'FAILED','error':error}]}
            with self.subTest(error=error),patch.object(gate,'acquire',return_value=(pathlib.Path('hard'),hard)) as acquire:
                _,_,attempts=gate.acquire_stable_cut(pathlib.Path('raw'),1,'underwriting_evidence_v3')
                self.assertEqual(len(attempts),1);self.assertEqual(acquire.call_count,1)


if __name__ == '__main__':
    unittest.main()
