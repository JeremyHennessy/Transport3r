"""Independently reconcile an immutable nationwide warehouse, without changing it.

Run with --deep to recount exact duplicates of ORIGINAL source columns. A shallow
PASS is not a release-ready duplicate audit. No result certifies actuarial risk,
source truth, historical completeness, or a live browser's displayed totals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

from nationwide_evidence import acceptance, connect
from nationwide_warehouse import duplicate_rows, ident, table
from source_contract import catalog_sources

SCHEMA = 'TRANSPORT3R_WAREHOUSE_AUDIT_2'
DUPLICATE_RULE = 'EXACT_ORIGINAL_SOURCE_COLUMNS_V2'
STATUSES = {'RESOLVED', 'IDENTIFIED_ONLY', 'UNRESOLVED'}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(path: pathlib.Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def count(value: object) -> bool:
    return type(value) is int and value >= 0


def audit(path: str | pathlib.Path, deep: bool = False) -> dict:
    """Return a failing receipt rather than accepting partial or corrupt evidence."""
    path = pathlib.Path(path).resolve(strict=True)
    before = fingerprint(path)
    report = {
        'schema_version': SCHEMA, 'status': 'FAIL', 'release_ready': False,
        'audited_at': datetime.now(timezone.utc).isoformat(),
        'warehouse_sha256': None, 'identity_contract': 'FMCSA_CARRIER_IDENTITY_1',
        'scope': 'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES',
        'cut_id': None, 'cut_available_at': None, 'source_count': 0,
        'raw_rows': 0, 'receipt_rows': None, 'census_carriers': None,
        'deep_exact_duplicates_checked': bool(deep),
        'duplicate_rule': DUPLICATE_RULE if deep else None,
        'checks': {}, 'sources': [], 'failures': [],
        'limits': [
            'Raw source rows are not unique carriers, incidents, vehicles or claims.',
            'Source digests are compared with receipts; original source byte files are not re-read.',
            'Mapping counts are checked; source statements are not independently adjudicated.',
            'Does not certify current API/browser counts or actuarial/geographic risk.',
            'A shallow PASS is not a release-ready exact-duplicate audit.',
        ],
    }
    failures = report['failures']
    db = connect(path)
    try:
        # Reuse the strict production receipt contract BEFORE SQL. Never accept a
        # failed receipt merely because physical row counts happen to agree.
        try:
            receipt = acceptance(db)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            failures.append('acceptance_receipt: ' + str(error))
            receipt = None
        if receipt is not None:
            report.update(cut_id=receipt['cut_id'], cut_available_at=receipt['cut_available_at'],
                          receipt_rows=receipt['rows'])
            entries = {item['source']: item for item in receipt['source_acceptance']}
            expected = {source['id'] for source in catalog_sources()}
            embedded = {item['source']: item for item in receipt['source_lineage']}
            lineage = db.execute('SELECT source_id,cut,sha256,available_at,rows_updated_at,'
                                 'published_rows,acquired_rows,warehouse_rows '
                                 'FROM source_lineage ORDER BY source_id').fetchall()
            ids = [row[0] for row in lineage]
            report['checks']['source_coverage'] = len(ids) == len(expected) and set(ids) == expected
            report['checks']['receipt_scope'] = receipt.get('scope') == report['scope']
            if not report['checks']['source_coverage']:
                failures.append('source_coverage: physical lineage differs from the registered source set')
            mapping_totals = {name: 0 for name in STATUSES}
            for sid, cut, digest, available, updated, published, acquired, warehouse in lineage:
                if sid not in expected:
                    failures.append('unregistered_source: ' + str(sid))
                    continue
                item, saved = entries[sid], embedded[sid]
                raw, mapping, joined = (table(sid), table(sid).replace('raw_', 'mapping_'),
                                        table(sid).replace('raw_', 'carrier_'))
                raw_count, raw_unique = db.execute(
                    f'SELECT count(*),count(DISTINCT _warehouse_row_id) FROM {ident(raw)}').fetchone()
                map_count, map_unique = db.execute(
                    f'SELECT count(*),count(DISTINCT _warehouse_row_id) FROM {ident(mapping)}').fetchone()
                missing = db.execute(f'SELECT count(*) FROM {ident(raw)} r '
                                     f'ANTI JOIN {ident(mapping)} m USING (_warehouse_row_id)').fetchone()[0]
                orphan = db.execute(f'SELECT count(*) FROM {ident(mapping)} m '
                                    f'ANTI JOIN {ident(raw)} r USING (_warehouse_row_id)').fetchone()[0]
                joined_count = db.execute(f'SELECT count(*) FROM {ident(joined)}').fetchone()[0]
                statuses = dict(db.execute(f'SELECT _mapping_status,count(*) FROM {ident(mapping)} GROUP BY 1').fetchall())
                reasons = dict(db.execute(f'SELECT _mapping_reason,count(*) FROM {ident(mapping)} GROUP BY 1').fetchall())
                values = [published, acquired, warehouse, raw_count] + [
                    item.get(key) for key in ('published_rows', 'acquired_rows', 'warehouse_rows')]
                checks = {
                    'source_counts': all(count(value) for value in values) and len(set(values)) == 1,
                    'raw_identity': raw_count == raw_unique,
                    'mapping_cardinality': raw_count == map_count == map_unique and missing == orphan == 0,
                    'joined_rows': joined_count == raw_count,
                    'mapping_status': set(statuses) <= STATUSES and statuses == item['mapping_status']
                                      and sum(statuses.values()) == raw_count,
                    'mapping_reasons': reasons == item['mapping_reasons'] and sum(reasons.values()) == raw_count
                                       and all(isinstance(key, str) and key.strip() for key in reasons),
                    'provenance': [cut, digest, available, updated, published, acquired, warehouse] == [
                        saved.get(key) for key in ('cut', 'sha256', 'available_at', 'rows_updated_at',
                                                   'published_rows', 'acquired_rows', 'warehouse_rows')]
                                  and digest == item.get('sha256'),
                }
                duplicates = None
                if deep:
                    duplicates = duplicate_rows(db, raw)
                    checks['exact_duplicates'] = count(item.get('exact_duplicate_rows')) and duplicates == item['exact_duplicate_rows']
                for key, passed in checks.items():
                    if not passed:
                        failures.append(sid + ': ' + key)
                for key in STATUSES:
                    mapping_totals[key] += statuses.get(key, 0)
                report['sources'].append({
                    'source': sid, 'sha256': digest, 'available_at': available, 'rows_updated_at': updated,
                    'published': published, 'acquired': acquired, 'warehouse': warehouse,
                    'actual_raw': raw_count, 'actual_mapping': map_count, 'actual_joined': joined_count,
                    'distinct_mapping_rows': map_unique, 'missing_mapping_rows': missing,
                    'orphan_mapping_rows': orphan, 'mapping_status': statuses,
                    'exact_duplicate_rows': duplicates,
                    'distinct_source_rows': raw_count - duplicates if duplicates is not None else None,
                    'checks': checks,
                })
            report['source_count'] = len(report['sources'])
            report['raw_rows'] = sum(item['actual_raw'] for item in report['sources'])
            census = db.execute("SELECT count(DISTINCT _dot_number) FROM mapping_az4n_8mr2 "
                                "WHERE _mapping_status='RESOLVED'").fetchone()[0]
            report['census_carriers'] = census
            report['checks'].update(
                aggregate_rows=count(receipt.get('rows')) and report['raw_rows'] == receipt['rows'],
                audited_sources=report['source_count'] == len(expected),
                census_carriers=count(receipt.get('census_carriers')) and census == receipt['census_carriers'],
                mapping_totals={key.lower(): value for key, value in mapping_totals.items()} == receipt['mapping_totals'],
            )
            failures.extend(key for key, passed in report['checks'].items() if not passed and key != 'source_coverage')
    except Exception as error:
        failures.append('warehouse_query: ' + str(error))
    finally:
        db.close()
    report['warehouse_sha256'] = sha256(path)
    stable = before == fingerprint(path) and not pathlib.Path(str(path) + '.wal').exists()
    report['checks']['immutable_file'] = stable
    if not stable:
        failures.append('immutable_file: warehouse changed during the audit or has a WAL')
    report['status'] = 'PASS' if not failures else 'FAIL'
    report['release_ready'] = report['status'] == 'PASS' and deep
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('warehouse')
    parser.add_argument('--output', help='New JSON report path; existing reports are never overwritten')
    parser.add_argument('--deep', action='store_true', help='Recount exact original-row duplicates')
    args = parser.parse_args()
    if args.output and pathlib.Path(args.output).exists():
        parser.error('Use a new output path; an earlier audit report already exists')
    try:
        result = audit(args.warehouse, args.deep)
    except Exception as error:
        result = {'schema_version': SCHEMA, 'status': 'ERROR', 'release_ready': False, 'failures': [str(error)]}
    text = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        with open(args.output, 'x', encoding='utf-8') as handle:
            handle.write(text)
    print(text)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
