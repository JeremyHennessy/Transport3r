"""Append-only acquisition cuts. A current download is never a historical reconstruction."""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import urllib.request
import uuid
from typing import Any

BASE = 'https://data.transportation.gov'
USER_AGENT = 'Transport3r snapshot acquisition (+https://github.com/JeremyHennessy/Transport3r)'

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')

def write_once(path: pathlib.Path, value: Any):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)

def source_state(dataset_id):
    metadata = fetch_json(f'{BASE}/api/views/{dataset_id}.json')
    counts = fetch_json(f'{BASE}/resource/{dataset_id}.json?$select=count(*)%20as%20count')
    count = int(counts[0]['count'])
    if count < 0:
        raise ValueError('Negative source row count')
    columns = [c for c in metadata['columns'] if not c.get('fieldName', '').startswith(':')]
    schema = [{key: c.get(key) for key in ['fieldName', 'name', 'dataTypeName', 'position']} for c in columns]
    return {'observed_at': now(), 'metadata': metadata, 'row_count': count,
            'schema_sha256': digest(schema), 'rows_updated_at': metadata.get('rowsUpdatedAt'),
            'table_id': metadata.get('tableId')}

def create_cut(root: pathlib.Path, date_label=None, snapshot_id=None, clean=False, *, schema_version=2, acquisition_kind='CURRENT_PUBLIC_SOURCE'):
    started = now()
    if clean:
        raise ValueError('--clean is disabled: existing cuts are retained. Start a new snapshot ID.')
    if date_label and date_label != started[:10]:
        raise ValueError('--date cannot backdate or postdate current acquisition; it does not retrieve historical data.')
    identifier = snapshot_id or f"{started.replace('-', '').replace(':', '').replace('.', '')}-{uuid.uuid4().hex[:8]}"
    if identifier in {'.', '..'} or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', identifier):
        raise ValueError('Invalid snapshot ID')
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    output = (root / identifier).resolve()
    if output.parent != root:
        raise ValueError('Snapshot path escaped its root')
    output.mkdir(exist_ok=False)
    run = {'schema_version': schema_version, 'snapshot_id': identifier, 'snapshot_date': started[:10],
           'started_at': started, 'acquisition_kind': acquisition_kind,
           'historical_reconstruction': False}
    write_once(output / 'run.json', run)
    return output, run

def download(source: dict[str, Any], output_dir: pathlib.Path, max_bytes: int | None):
    dataset_id = source['id']
    if not re.fullmatch(r'[a-z0-9]{4}-[a-z0-9]{4}', dataset_id):
        raise ValueError('Invalid source ID')
    target = output_dir / f'{dataset_id}.csv'
    partial = output_dir / f'{dataset_id}.csv.partial'
    if target.exists() or partial.exists():
        raise FileExistsError(f'Acquisition already exists for {dataset_id}; use a new cut')
    started = now()
    before = source_state(dataset_id)
    write_once(output_dir / f'{dataset_id}.metadata-before.json', before)
    url = f'{BASE}/api/views/{dataset_id}/rows.csv?accessType=DOWNLOAD'
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/csv'})
    checksum, size = hashlib.sha256(), 0
    with urllib.request.urlopen(request, timeout=120) as response, partial.open('xb') as handle:
        expected_bytes = response.headers.get('Content-Length')
        while chunk := getattr(response, 'read1', response.read)(64 * 1024):
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise ValueError(f'{dataset_id} exceeded --max-bytes={max_bytes}')
            checksum.update(chunk)
            handle.write(chunk)
    if expected_bytes is not None and int(expected_bytes) != size:
        raise ValueError('Incomplete response length; partial file retained')
    columns = [c for c in before['metadata']['columns'] if not c.get('fieldName', '').startswith(':')]
    norm = lambda value: re.sub(r'[^a-z0-9]', '', str(value).lower())
    with partial.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle, strict=True)
        header = next(reader, [])
        if len(header) != len(columns) or any(norm(name) not in {norm(column.get('name')), norm(column.get('fieldName'))} for name, column in zip(header, columns)):
            raise ValueError('CSV header differs from source schema')
        row_count = 0
        for row in reader:
            if len(row) != len(header):
                raise ValueError(f'Malformed CSV row {row_count + 2}')
            row_count += 1
    after = source_state(dataset_id)
    write_once(output_dir / f'{dataset_id}.metadata-after.json', after)
    for marker in ['rows_updated_at', 'schema_sha256', 'table_id', 'row_count']:
        if before[marker] != after[marker]:
            raise ValueError(f'Source changed during acquisition ({marker}); partial file retained')
    if row_count != after['row_count']:
        raise ValueError(f'CSV count {row_count} differs from source count {after["row_count"]}')
    if before['rows_updated_at'] is None:
        raise ValueError('Source update watermark unavailable; acquisition cannot be accepted')
    # Atomic, no-replace promotion on the same filesystem, without doubling warehouse storage.
    os.link(partial, target)
    # Keep the transfer name as recovery evidence; both names refer to the validated bytes.
    completed = now()
    result = {'id': dataset_id, 'name': source['name'], 'family': source['family'], 'status': 'COMPLETE',
              'acquired_started_at': started, 'available_at': completed, 'bytes': size, 'sha256': checksum.hexdigest(),
              'row_count': row_count, 'schema_sha256': after['schema_sha256'], 'rows_updated_at': after['rows_updated_at'],
              'path': target.name, 'source_url': url, 'metadata_before': f'{dataset_id}.metadata-before.json',
              'metadata_after': f'{dataset_id}.metadata-after.json',
              'metadata_before_sha256': hashlib.sha256((output_dir / f'{dataset_id}.metadata-before.json').read_bytes()).hexdigest(),
              'metadata_after_sha256': hashlib.sha256((output_dir / f'{dataset_id}.metadata-after.json').read_bytes()).hexdigest()}
    write_once(output_dir / f'{dataset_id}.result.json', result)
    return result

def acquire(sources, root, *, date_label=None, snapshot_id=None, clean=False, max_bytes=None):
    if max_bytes is not None and max_bytes < 1:
        raise ValueError('--max-bytes must be positive')
    if not sources or len({source['id'] for source in sources}) != len(sources):
        raise ValueError('A nonempty unique source selection is required')
    if any(not re.fullmatch(r'[a-z0-9]{4}-[a-z0-9]{4}', source['id']) for source in sources):
        raise ValueError('Invalid source ID')
    output, manifest = create_cut(pathlib.Path(root), date_label, snapshot_id, clean)
    results = []
    for source in sources:
        try:
            result = download(source, output, max_bytes)
        except Exception as error:
            result = {'id': source['id'], 'name': source['name'], 'family': source['family'], 'status': 'FAILED',
                      'failed_at': now(), 'error': f'{type(error).__name__}: {error}'}
            write_once(output / f'{source["id"]}.failure.json', result)
        results.append(result)
        print(f"{source['id']}: {result['status']}", flush=True)
    failed = sum(result['status'] != 'COMPLETE' for result in results)
    manifest.update({'datasets': results, 'completed_at': now(), 'source_count': len(results),
                     'success_count': len(results) - failed, 'failure_count': failed,
                     'status': 'COMPLETE' if not failed else 'FAILED' if failed == len(results) else 'PARTIAL'})
    write_once(output / 'manifest.json', manifest)
    print(f'Manifest: {output / "manifest.json"}', flush=True)
    return output, manifest
