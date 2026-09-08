#!/usr/bin/env python3
"""Verify a completed cut offline; optional as-of gate checks acquisition availability only."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import pathlib

def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('As-of and lineage times require an explicit time zone')
    return parsed

def verify(folder, as_of=None):
    root = pathlib.Path(folder).resolve()
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 2 or manifest.get('status') != 'COMPLETE' or manifest.get('failure_count') != 0:
        raise ValueError('Only a completed v2 acquisition cut is eligible')
    if manifest.get('historical_reconstruction') is not False or manifest.get('acquisition_kind') != 'CURRENT_PUBLIC_SOURCE':
        raise ValueError('Unexpected historical/source-kind claim')
    started, completed = timestamp(manifest['started_at']), timestamp(manifest['completed_at'])
    if started > completed or (as_of and completed > timestamp(as_of)):
        raise ValueError('Cut was not available at the requested as-of time')
    datasets = manifest['datasets']
    if not datasets or len(datasets) != manifest['source_count'] or len(datasets) != manifest['success_count']:
        raise ValueError('Manifest source counts disagree')
    if len({item['id'] for item in datasets}) != len(datasets):
        raise ValueError('Duplicate dataset in manifest')
    rows, total_bytes = 0, 0
    for item in datasets:
        if item['status'] != 'COMPLETE' or not started <= timestamp(item['acquired_started_at']) <= timestamp(item['available_at']) <= completed:
            raise ValueError('Invalid dataset state or availability lineage')
        path = (root / item['path']).resolve()
        if path.parent != root or path.suffix != '.csv':
            raise ValueError('Raw path escaped the snapshot or is not a CSV')
        digest, size = hashlib.sha256(), 0
        with path.open('rb') as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        if digest.hexdigest() != item['sha256'] or size != item['bytes']:
            raise ValueError(f"Raw artifact hash/size mismatch: {item['id']}")
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.reader(handle, strict=True)
            header = next(reader, [])
            count = 0
            for row in reader:
                if len(row) != len(header):
                    raise ValueError('Malformed stored CSV row')
                count += 1
        if count != item['row_count']:
            raise ValueError('Stored row count disagrees with manifest')
        for key in ['metadata_before', 'metadata_after']:
            metadata_path = (root/item[key]).resolve()
            if metadata_path.parent != root:
                raise ValueError('Metadata path escaped snapshot')
            if hashlib.sha256(metadata_path.read_bytes()).hexdigest() != item[f'{key}_sha256']:
                raise ValueError('Metadata artifact hash mismatch')
            state = json.loads(metadata_path.read_text(encoding='utf-8'))
            if state['row_count'] != count or state['rows_updated_at'] != item['rows_updated_at'] or state['schema_sha256'] != item['schema_sha256']:
                raise ValueError('Stored metadata differs from accepted source cut')
        rows += count
        total_bytes += size
    return {'status':'VERIFIED', 'snapshot_id':manifest['snapshot_id'], 'source_count':len(datasets),
            'row_count':rows, 'bytes':total_bytes, 'available_at':manifest['completed_at'],
            'as_of':as_of, 'historical_feature_validity':'NOT_CERTIFIED'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot_directory')
    parser.add_argument('--as-of', help='Timezone-aware knowledge-time cutoff; rejects a later-acquired cut')
    args = parser.parse_args()
    print(json.dumps(verify(args.snapshot_directory, args.as_of), indent=2))
