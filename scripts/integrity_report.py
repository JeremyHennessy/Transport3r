"""Validate an independent public-source audit against the exact installed cut.

Only allow-listed, aggregate public source metadata is returned. Neither local
filesystem paths nor arbitrary fields from a supplied report reach the API.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timedelta, timezone

from source_contract import catalog_sources

SCHEMA = 'TRANSPORT3R_WAREHOUSE_AUDIT_2'
GLOBAL_CHECKS = {'source_coverage', 'receipt_scope', 'aggregate_rows', 'audited_sources',
                 'census_carriers', 'mapping_totals', 'immutable_file'}
SOURCE_CHECKS = {'source_counts', 'raw_identity', 'mapping_cardinality', 'joined_rows',
                 'mapping_status', 'mapping_reasons', 'provenance', 'exact_duplicates', 'identity_mapping'}
COUNTS = ('published', 'acquired', 'warehouse', 'actual_raw', 'actual_mapping',
          'actual_joined', 'distinct_mapping_rows')
SOURCE_FIELDS = ('source', 'sha256', 'available_at', 'rows_updated_at', *COUNTS,
                 'missing_mapping_rows', 'orphan_mapping_rows', 'identity_mapping_disagreements', 'mapping_status',
                 'exact_duplicate_rows', 'distinct_source_rows', 'checks')
TOP_FIELDS = ('schema_version', 'status', 'release_ready', 'audited_at',
              'warehouse_sha256', 'identity_contract', 'scope', 'cut_id',
              'cut_available_at', 'source_count', 'raw_rows', 'receipt_rows',
              'census_carriers', 'deep_exact_duplicates_checked', 'duplicate_rule', 'checks')


def integer(value):
    return type(value) is int and 0 <= value <= 9007199254740991


def required(condition, message):
    if not condition:
        raise ValueError('Independent warehouse audit: ' + message)


def checked(values, names):
    return isinstance(values, dict) and set(values) == names and all(value is True for value in values.values())


def timestamp(value):
    required(isinstance(value, str), 'timezone-aware timestamp required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    required(parsed.utcoffset() is not None, 'timezone-aware timestamp required')
    return parsed


def public_report(report, receipt, warehouse_sha256):
    required(isinstance(report, dict) and report.get('schema_version') == SCHEMA, 'unsupported report schema')
    required(report.get('status') == 'PASS' and report.get('release_ready') is True,
             'report has not passed its release gate')
    required(report.get('deep_exact_duplicates_checked') is True and
             report.get('duplicate_rule') == 'EXACT_ORIGINAL_SOURCE_COLUMNS_V2', 'exact duplicates were not recounted')
    required(report.get('failures') == [], 'report contains failures')
    required(re.fullmatch('[0-9a-f]{64}', warehouse_sha256 or '') and
             report.get('warehouse_sha256') == warehouse_sha256, 'report belongs to another warehouse')
    for key in ('cut_id', 'cut_available_at', 'identity_contract', 'scope'):
        required(report.get(key) == receipt.get(key), 'cut or identity contract differs')
    required(checked(report.get('checks'), GLOBAL_CHECKS), 'global checks are missing or failed')
    audited = timestamp(report.get('audited_at'))
    required(timestamp(receipt['cut_available_at']) <= audited <= datetime.now(timezone.utc) + timedelta(minutes=5),
             'audit timestamp is outside the valid cut window')
    expected = {source['id'] for source in catalog_sources()}
    sources = report.get('sources')
    required(isinstance(sources, list) and len(sources) == len(expected) and all(isinstance(s, dict) for s in sources),
             'source coverage is incomplete')
    required({s.get('source') for s in sources} == expected, 'source identities are duplicated or missing')
    accepted = {s['source']: s for s in receipt['source_acceptance']}
    lineage = {s['source']: s for s in receipt['source_lineage']}
    public_sources = []
    for source in sources:
        sid = source['source']
        item, raw = accepted[sid], lineage[sid]
        required(checked(source.get('checks'), SOURCE_CHECKS), sid + ': missing or failed checks')
        required(all(integer(source.get(k)) for k in COUNTS) and
                 all(source[k] == item['warehouse_rows'] for k in COUNTS), sid + ': count mismatch')
        required(source.get('sha256') == item['sha256'] and source.get('available_at') == raw['available_at'] and
                 source.get('rows_updated_at') == raw['rows_updated_at'], sid + ': source provenance mismatch')
        required(source.get('missing_mapping_rows') == 0 and type(source.get('missing_mapping_rows')) is int and
                 source.get('orphan_mapping_rows') == 0 and type(source.get('orphan_mapping_rows')) is int,
                 sid + ': missing or orphaned mappings')
        required(type(source.get('identity_mapping_disagreements')) is int and source['identity_mapping_disagreements'] == 0,
                 sid + ': carrier identity assignments differ')
        statuses = source.get('mapping_status')
        required(isinstance(statuses, dict) and all(integer(v) for v in statuses.values()) and
                 statuses == item['mapping_status'] and sum(statuses.values()) == source['actual_raw'],
                 sid + ': mapping status mismatch')
        duplicates, distinct = source.get('exact_duplicate_rows'), source.get('distinct_source_rows')
        required(integer(duplicates) and integer(distinct) and duplicates == item.get('exact_duplicate_rows') and
                 duplicates + distinct == source['actual_raw'], sid + ': exact duplicate mismatch')
        public_sources.append({key: source[key] for key in SOURCE_FIELDS})
    total = sum(source['actual_raw'] for source in sources)
    required(all(integer(report.get(k)) for k in ('source_count', 'raw_rows', 'receipt_rows', 'census_carriers')),
             'invalid aggregate count')
    required(report['source_count'] == len(expected) and report['raw_rows'] == report['receipt_rows'] == total == receipt['rows']
             and report['census_carriers'] == receipt['census_carriers'], 'aggregate mismatch')
    value = {key: report[key] for key in TOP_FIELDS}
    value.update(sources=public_sources, failures=[], limits=[
        'Counts refer to this immutable installed warehouse, not all current live FMCSA publications.',
        'Raw rows span different grains. They are not unique carriers, incidents, vehicles or claims.',
        'Original source bytes were verified at ingestion; this audit checks stored counts and joins.',
        'No carrier route exposure, actuarial score, or private insurer record is included.',
    ])
    return value


def load_report(path, receipt, warehouse_sha256):
    path = pathlib.Path(path)
    required(path.is_file() and path.stat().st_size <= 2 * 1024 * 1024, 'missing or oversized report')
    return public_report(json.loads(path.read_text(encoding='utf-8')), receipt, warehouse_sha256)
