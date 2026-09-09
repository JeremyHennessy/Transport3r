"""Verify stable source observations around a query window, not a monthly SMS date."""
from concurrent.futures import ThreadPoolExecutor
from http.client import RemoteDisconnected
import time
from urllib.error import HTTPError, URLError
from snapshot_store import source_state, now
from verify_snapshot import timestamp

SMS_RUNTIME_SOURCES = ['4y6x-dmck', 'h9zy-gjn8', 'm3ry-qcip', 'h3zn-uid9', 'rbkj-cgst', '8mt8-2mdr']
MARKERS = ['rows_updated_at', 'schema_sha256', 'table_id', 'row_count']


def capture_sources(source_ids):
    def capture(sid):
        attempts = []
        for attempt in range(1, 4):
            try:
                observation = source_state(sid)
                attempts.append({'attempt': attempt, 'status': 'PASS', 'observed_at': observation.get('observed_at')})
                return {'source_id': sid, **observation, 'acquisition_attempts': attempts}
            except Exception as error:
                failure = {'attempt': attempt, 'status': 'FAIL', 'observed_at': now(), 'error': f'{type(error).__name__}: {error}'}
                attempts.append(failure)
                transient = (error.code == 429 or 500 <= error.code < 600) if isinstance(error, HTTPError) else isinstance(error, (URLError, RemoteDisconnected, TimeoutError, ConnectionError))
                if not transient or attempt == 3:
                    return {'source_id': sid, 'observed_at': failure['observed_at'], 'error': failure['error'], 'acquisition_attempts': attempts}
                time.sleep(attempt)
    with ThreadPoolExecutor(max_workers=6) as pool:
        return dict(zip(source_ids, pool.map(capture, source_ids)))


def state_issues(sid, state):
    if not isinstance(state, dict) or state.get('error'):
        return [f'UNAVAILABLE_SOURCE_STATE:{sid}']
    issues = []
    if state.get('source_id') != sid or state.get('metadata', {}).get('id') != sid:
        issues.append(f'SOURCE_ID_MISMATCH:{sid}')
    watermark = state.get('rows_updated_at')
    if type(watermark) is not int or watermark <= 0 or watermark != state.get('metadata', {}).get('rowsUpdatedAt'):
        issues.append(f'INVALID_UPDATE_WATERMARK:{sid}')
    if type(state.get('row_count')) is not int or state['row_count'] < 0:
        issues.append(f'INVALID_ROW_COUNT:{sid}')
    if not state.get('table_id') or state['table_id'] != state.get('metadata', {}).get('tableId'):
        issues.append(f'INVALID_TABLE_ID:{sid}')
    if not isinstance(state.get('schema_sha256'), str) or len(state['schema_sha256']) != 64 or any(c not in '0123456789abcdef' for c in state['schema_sha256']):
        issues.append(f'INVALID_SCHEMA_HASH:{sid}')
    try:
        observed = timestamp(state['observed_at'])
        if type(watermark) is int and watermark > observed.timestamp():
            issues.append(f'FUTURE_UPDATE_WATERMARK:{sid}')
    except (ValueError, TypeError, KeyError, AttributeError):
        issues.append(f'INVALID_OBSERVATION_TIME:{sid}')
    return issues


def assess_source_cut(cut, source_ids):
    issues = []
    if cut.get('schema_version') != 1:
        issues.append('INVALID_SOURCE_CUT_VERSION')
    try:
        start, first, last, end = [timestamp(cut[key]) for key in ['started_at', 'queries_started_at', 'queries_completed_at', 'completed_at']]
        if not start <= first <= last <= end:
            raise ValueError('Reversed query window')
    except (ValueError, TypeError, KeyError, AttributeError):
        return ['INVALID_QUERY_WINDOW']
    if set(cut.get('before', {})) != set(source_ids) or set(cut.get('after', {})) != set(source_ids):
        issues.append('INCOMPLETE_SOURCE_SET')
    for sid in source_ids:
        before, after = cut.get('before', {}).get(sid), cut.get('after', {}).get(sid)
        invalid = state_issues(sid, before) + state_issues(sid, after)
        issues.extend(invalid)
        if invalid:
            continue
        if not start <= timestamp(before['observed_at']) <= first or not last <= timestamp(after['observed_at']) <= end:
            issues.append(f'OBSERVATIONS_DO_NOT_BRACKET_QUERIES:{sid}')
        for marker in MARKERS:
            if before[marker] != after[marker]:
                issues.append(f'SOURCE_CHANGED:{sid}:{marker}')
    return issues
