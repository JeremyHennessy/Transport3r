import unittest
import contextlib
import io
import json
from sms_source_cut import assess_source_cut, state_issues, capture_sources
from unittest.mock import patch

SID = '4y6x-dmck'
def state(at):
    return {'source_id': SID, 'observed_at': at, 'row_count': 10, 'rows_updated_at': 1700000000,
            'schema_sha256': 'a'*64, 'table_id': 't1', 'metadata': {'id': SID, 'rowsUpdatedAt': 1700000000, 'tableId': 't1'}}
def cut():
    return {'schema_version':1,'started_at':'2026-01-01T00:00:00Z','queries_started_at':'2026-01-01T00:01:00Z',
            'queries_completed_at':'2026-01-01T00:02:00Z','completed_at':'2026-01-01T00:03:00Z',
            'before':{SID:state('2026-01-01T00:00:30Z')},'after':{SID:state('2026-01-01T00:02:30Z')}}

class SourceCutTests(unittest.TestCase):
    def test_stable_query_window_is_accepted_without_a_monthly_date(self):
        self.assertEqual(assess_source_cut(cut(), [SID]), [])

    def test_each_rollover_marker_is_rejected_even_if_row_count_is_unchanged(self):
        for marker, value in [('rows_updated_at',1700000001),('schema_sha256','b'*64),('table_id','t2'),('row_count',11)]:
            data=cut(); data['after'][SID][marker]=value
            if marker=='rows_updated_at': data['after'][SID]['metadata']['rowsUpdatedAt']=value
            if marker=='table_id': data['after'][SID]['metadata']['tableId']=value
            self.assertIn(f'SOURCE_CHANGED:{SID}:{marker}',assess_source_cut(data,[SID]))

    def test_failed_missing_wrong_and_malformed_observations_are_rejected(self):
        for replacement in [None,{}, {'error':'HTTP 503'}, {**state('2026-01-01T00:00:30Z'),'source_id':'other'},
                            {**state('2026-01-01T00:00:30Z'),'rows_updated_at':None},
                            {**state('2026-01-01T00:00:30Z'),'row_count':-1}]:
            data=cut(); data['before'][SID]=replacement
            self.assertTrue(assess_source_cut(data,[SID]))

    def test_observations_must_bracket_all_queries_with_explicit_timezones(self):
        for phase, at in [('before','2026-01-01T00:01:01Z'),('after','2026-01-01T00:01:59Z'),('before','2026-01-01T00:00:30')]:
            data=cut(); data[phase][SID]['observed_at']=at
            self.assertTrue(assess_source_cut(data,[SID]))
        data=cut(); data['queries_completed_at']='2025-01-01T00:00:00Z'
        self.assertTrue(assess_source_cut(data,[SID]))

    def test_network_failure_is_retained_as_failed_observation(self):
        with patch('sms_source_cut.source_state',side_effect=RuntimeError('HTTP 503')):
            result=capture_sources([SID])
        self.assertIn('HTTP 503',result[SID]['error'])
        self.assertTrue(state_issues(SID,result[SID]))

    def test_live_validator_rejects_a_rollover_even_when_all_numeric_measures_match(self):
        import validate_sms_v321_replay as validator
        from snapshot_store import now
        captures = []
        def capture(ids):
            captures.append('capture')
            states = {}
            for sid in ids:
                item = state(now()); item['source_id'] = sid; item['metadata']['id'] = sid
                if len(captures) == 2:
                    item['rows_updated_at'] += 1; item['metadata']['rowsUpdatedAt'] += 1
                states[sid] = item
            return states
        outputs = [{'dot_number':str(dot), **{rule['official']:'0' for rule in validator.RULES.values()}} for dot in range(1,4)]
        def fetch(sid, params):
            self.assertEqual(len(captures),1, 'Data queries must be between the two observations')
            return [{'unique_id':'i', 'time_weight':'1', **{rule['flag']:'Y' for rule in validator.RULES.values()}}] if sid == validator.INSPECTION_ID else []
        output = io.StringIO()
        with patch.object(validator,'capture_sources',side_effect=capture), patch.object(validator,'choose_candidates',return_value=outputs), patch.object(validator,'fetch_json',side_effect=fetch), contextlib.redirect_stdout(output):
            code = validator.main()
        result = json.loads(output.getvalue())
        self.assertEqual(code,2)
        self.assertEqual(result['match_count'],12)
        self.assertEqual(result['status'],'source_cut_rejected')
        self.assertTrue(any(issue.startswith('SOURCE_CHANGED:') for issue in result['source_cut']['issues']))
