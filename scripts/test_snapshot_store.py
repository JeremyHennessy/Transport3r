import copy
import hashlib
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import snapshot_store as store
from verify_snapshot import verify

SOURCE = {'id': 'abcd-1234', 'name': 'Test source', 'family': 'test'}
BODY = b'DOT_NUMBER,VALUE\n1,"quoted, value"\n'
STATE = {'observed_at': '2026-09-08T00:00:00Z', 'row_count': 1, 'rows_updated_at': 123,
         'schema_sha256': 'schema', 'table_id': 'table',
         'metadata': {'columns': [{'fieldName':'dot_number','name':'DOT_NUMBER'}, {'fieldName':'value','name':'VALUE'}]}}

class Response(io.BytesIO):
    def __init__(self, body=BODY, length=None):
        super().__init__(body)
        self.headers = {'Content-Length': str(len(body) if length is None else length)}

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def run_cut(self, **kwargs):
        with patch.object(store, 'source_state', side_effect=kwargs.pop('states', [copy.deepcopy(STATE), copy.deepcopy(STATE)])), \
             patch.object(store.urllib.request, 'urlopen', return_value=kwargs.pop('response', Response())):
            return store.acquire([SOURCE], self.root, **kwargs)

    def test_complete_cut_has_verified_lineage_and_is_not_replaced(self):
        output, manifest = self.run_cut(snapshot_id='cut-one')
        result = manifest['datasets'][0]
        self.assertEqual(manifest['status'], 'COMPLETE')
        self.assertFalse(manifest['historical_reconstruction'])
        self.assertEqual(result['row_count'], 1)
        self.assertEqual(result['sha256'], hashlib.sha256(BODY).hexdigest())
        self.assertGreaterEqual(result['available_at'], result['acquired_started_at'])
        original = (output/'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_cut(snapshot_id='cut-one')
        self.assertEqual((output/'manifest.json').read_bytes(), original)
        self.assertEqual((output/'abcd-1234.csv').read_bytes(), BODY)
        self.assertEqual(verify(output)['row_count'], 1)
        with self.assertRaisesRegex(ValueError, 'as-of'):
            verify(output, '2001-01-01T00:00:00Z')
        (output/'abcd-1234.csv').write_bytes(BODY + b'2,changed\n')
        with self.assertRaisesRegex(ValueError, 'hash/size'):
            verify(output)

    def test_backdating_and_clean_are_rejected_without_writes(self):
        for options in [{'date_label':'2001-01-01'}, {'clean':True}, {'snapshot_id':'../outside'}]:
            with self.assertRaises(ValueError):
                self.run_cut(**options)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_metadata_tampering_is_rejected_offline(self):
        output, _ = self.run_cut()
        metadata = output/'abcd-1234.metadata-after.json'
        metadata.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Metadata artifact hash'):
            verify(output)

    def test_distinct_runs_on_same_day_have_distinct_ids(self):
        one, _ = self.run_cut()
        two, _ = self.run_cut()
        self.assertNotEqual(one, two)
        self.assertTrue((one/'manifest.json').exists())

    def test_changed_source_is_rejected_and_partial_bytes_retained(self):
        after = copy.deepcopy(STATE)
        after['rows_updated_at'] += 1
        output, manifest = self.run_cut(states=[STATE, after])
        self.assertEqual(manifest['status'], 'FAILED')
        self.assertIn('Source changed', manifest['datasets'][0]['error'])
        self.assertTrue((output/'abcd-1234.csv.partial').exists())
        self.assertFalse((output/'abcd-1234.csv').exists())

    def test_header_row_count_and_transfer_length_are_checked(self):
        for body, length, error in [(b'WRONG,VALUE\n1,x\n',None,'header'), (b'DOT_NUMBER,VALUE\n',None,'count'), (BODY,999,'length')]:
            with self.subTest(error=error):
                output, manifest = self.run_cut(response=Response(body,length))
                self.assertIn(error, manifest['datasets'][0]['error'])
                self.assertFalse((output/'abcd-1234.csv').exists())

    def test_byte_limit_fails_without_promoting(self):
        output, manifest = self.run_cut(max_bytes=5)
        self.assertEqual(manifest['failure_count'],1)
        self.assertFalse((output/'abcd-1234.csv').exists())

    def test_missing_watermark_cannot_certify_snapshot(self):
        state = copy.deepcopy(STATE)
        state['rows_updated_at'] = None
        _, manifest = self.run_cut(states=[state,state])
        self.assertIn('watermark unavailable', manifest['datasets'][0]['error'])

    def test_result_files_retain_failures_and_final_status(self):
        output, manifest = self.run_cut(response=Response(b'<html>error</html>'))
        self.assertEqual(json.loads((output/'abcd-1234.failure.json').read_text())['status'],'FAILED')
        self.assertEqual(json.loads((output/'manifest.json').read_text())['failure_count'],1)

if __name__ == '__main__':
    unittest.main()
