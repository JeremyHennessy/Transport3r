"""Successful count evidence must outrank a concurrent transient failure."""
import pathlib
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import cohort_snapshot as cs
import inspection_children as child
from snapshot_store import now


class PreflightCeilingPriorityTests(unittest.TestCase):
    def check_rejection(self, counts, maximum):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            parents = {str(i): '1' for i in range(1, len(counts) + 1)}
            state = {'observed_at': now(), 'rows_updated_at': 1,
                     'metadata': {'columns': [{'fieldName': 'inspection_id', 'dataTypeName': 'text'}]}}
            def query(source, **params):
                self.assertEqual(params['select'], 'count(*) as count', 'No pages may be requested')
                identifier = int(params['where'].split("'")[1])
                value = counts[identifier - 1]
                if value is None:
                    raise urllib.error.HTTPError('https://example.invalid', 503, 'Unavailable', {}, None)
                return [{'count': str(value)}]
            with patch.object(child, 'BATCH_SIZE', 1), patch.object(cs, 'state', return_value=state), \
                 patch.object(cs, 'query', side_effect=query):
                with self.assertRaises(ValueError) as raised:
                    child.collect_children('wt8s-2hbx', parents, folder, {}, max_rows=maximum)
            self.assertIs(type(raised.exception), ValueError)
            self.assertIn('ceiling', str(raised.exception))
            self.assertEqual(list(folder.iterdir()), [])

    def test_over_limit_success_beats_parallel_http_503(self):
        self.check_rejection([2, None], 1)

    def test_combined_success_counts_beat_parallel_http_503(self):
        self.check_rejection([1, None, 1], 1)

    def test_negative_count_beats_parallel_http_503(self):
        self.check_rejection([None, -1], 10)


if __name__ == '__main__':
    unittest.main()
