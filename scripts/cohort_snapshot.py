"""Current, cohort-scoped source acquisition. Never an historical reconstruction."""
import argparse
import hashlib
import json
import pathlib
import re
import urllib.parse

from snapshot_store import create_cut, fetch_json, now, write_once, digest
from verify_snapshot import timestamp

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = 'https://data.transportation.gov'
SOURCES = ['az4n-8mr2', 'fx4q-ay7w', 'aayw-vxb3', 'm3ry-qcip', 'h3zn-uid9', '4y6x-dmck', 'h9zy-gjn8']
STRATA = {
    'one_unit': "fleetsize='A'", 'two_to_six': "fleetsize in ('B','C')",
    'seven_to_eleven': "fleetsize in ('D','E')", 'twelve_to_nineteen': "fleetsize in ('F','G','H')",
    'large': "fleetsize in ('V','W','X','Y','Z')", 'passenger_reported': "crgo_passengers='X'",
    'hazmat_reported': "hm_ind='Y'",
}

def query(sid, **params):
    url = f'{BASE}/resource/{sid}.json?' + urllib.parse.urlencode({'$'+key: value for key, value in params.items()})
    return fetch_json(url)

def state(sid, where):
    metadata = fetch_json(f'{BASE}/api/views/{sid}.json')
    columns = [{k: c.get(k) for k in ['fieldName', 'dataTypeName', 'position']} for c in metadata['columns'] if not c['fieldName'].startswith(':')]
    return {'observed_at': now(), 'metadata': metadata, 'schema_sha256': digest(columns),
            'rows_updated_at': metadata.get('rowsUpdatedAt'), 'table_id': metadata.get('tableId'),
            'row_count': int(query(sid, select='count(*) as count', where=where)[0]['count'])}

def stable(before, after):
    if before['rows_updated_at'] is None or any(before[k] != after[k] for k in ['rows_updated_at','schema_sha256','table_id','row_count']):
        raise ValueError('Source changed or has no update watermark')

def select_cohort(per_stratum):
    if not 1 <= per_stratum <= 20:
        raise ValueError('Pilot selection requires 1..20 carriers per stratum')
    before = state('az4n-8mr2', "status_code='A'")
    selections, dots = [], set()
    for name, condition in STRATA.items():
        params = {'select':'dot_number,power_units,fleetsize,crgo_passengers,hm_ind,carrier_operation',
                  'where':f"status_code='A' AND ({condition})", 'order':'dot_number', 'limit':per_stratum}
        rows = query('az4n-8mr2', **params)
        if not rows:
            raise ValueError(f'No carriers returned for selection stratum {name}')
        selections.append({'stratum':name, 'query':params, 'rows':rows})
        dots.update(str(int(row['dot_number'])) for row in rows)
    after = state('az4n-8mr2', "status_code='A'")
    stable(before, after)
    return {'selected_at':now(), 'selection':'LOWEST_USDOT_WITHIN_EXPLICIT_STRATA',
            'representative':False, 'outcome_selected':False, 'selections':selections,
            'metadata_before':before, 'metadata_after':after, 'dots':sorted(dots, key=int)}

def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        while block := handle.read(1024*1024):
            h.update(block)
    return h.hexdigest()

def collect(sid, dots, folder, page_size=1000, max_rows=100000):
    if not dots or any(not re.fullmatch(r'[1-9][0-9]*', d) for d in dots):
        raise ValueError('Explicit positive USDOT identifiers required')
    where = 'dot_number in (' + ','.join("'"+d+"'" for d in dots) + ')'
    started = now()
    before = state(sid, where)
    if before['row_count'] > max_rows:
        raise ValueError('Selected source exceeds row ceiling; narrow the cohort')
    seen, pages, rows = set(), [], []
    offset = 0
    while True:
        batch = query(sid, select='*, :id as source_row_id', where=where, order=':id', limit=page_size, offset=offset)
        name = f'{sid}.page-{offset:08d}.json'
        write_once(folder/name, batch)
        pages.append({'path':name, 'sha256':hash_file(folder/name), 'rows':len(batch), 'offset':offset})
        if len(batch) > page_size or len(rows)+len(batch) > max_rows:
            raise ValueError('Response exceeded the requested acquisition bound')
        for row in batch:
            key = row.get('source_row_id')
            if not key or key in seen or str(row.get('dot_number')) not in dots:
                raise ValueError('Duplicate/missing source row ID or cross-carrier contamination')
            seen.add(key)
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    after = state(sid, where)
    stable(before, after)
    if len(rows) != after['row_count']:
        raise ValueError('Paged row count differs from selected source count')
    lineage_name = f'{sid}.lineage.json'
    write_once(folder/lineage_name, {'before':before, 'after':after, 'where':where, 'order':':id', 'select':'*, :id as source_row_id'})
    return {'id':sid, 'status':'COMPLETE', 'started_at':started, 'available_at':now(), 'row_count':len(rows),
            'lineage':lineage_name, 'lineage_sha256':hash_file(folder/lineage_name), 'pages':pages}

def acquire(root, per_stratum=10, cohort_path=None):
    folder, manifest = create_cut(pathlib.Path(root), schema_version=3, acquisition_kind='CURRENT_COHORT_PUBLIC_SOURCE')
    manifest['scope'] = 'EXPLICIT_USDOT_COHORT'
    try:
        cohort = json.loads(pathlib.Path(cohort_path).read_text(encoding='utf-8')) if cohort_path else select_cohort(per_stratum)
        dots = cohort['dots']
        if len(dots) != len(set(dots)) or not 1 <= len(dots) <= 140 or any(not re.fullmatch(r'[1-9][0-9]*', d) for d in dots):
            raise ValueError('Cohort requires 1..140 unique positive USDOT strings')
        if timestamp(cohort['selected_at']) > timestamp(now()):
            raise ValueError('Cohort selection is in the future')
        write_once(folder/'cohort.json', cohort)
        results = []
        for sid in SOURCES:
            try:
                result = collect(sid, dots, folder)
            except Exception as error:
                result = {'id':sid, 'status':'FAILED', 'failed_at':now(), 'error':f'{type(error).__name__}: {error}'}
            results.append(result)
            print(f'{sid}: {result["status"]} {result.get("row_count", "")}', flush=True)
        manifest.update({'cohort_path':'cohort.json', 'cohort_sha256':hash_file(folder/'cohort.json'),
                         'datasets':results, 'status':'COMPLETE' if all(r['status']=='COMPLETE' for r in results) else 'PARTIAL'})
    except Exception as error:
        manifest.update({'status':'FAILED', 'error':f'{type(error).__name__}: {error}'})
    manifest['completed_at'] = now()
    write_once(folder/'manifest.json', manifest)
    print(f'Manifest: {folder / "manifest.json"}', flush=True)
    return folder, manifest

def load_verified(folder, as_of=None):
    root = pathlib.Path(folder).resolve()
    m = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema_version'),m.get('status'),m.get('acquisition_kind'),m.get('historical_reconstruction')) != (3,'COMPLETE','CURRENT_COHORT_PUBLIC_SOURCE',False):
        raise ValueError('Only complete cohort v3 cuts are eligible')
    started, completed = timestamp(m['started_at']), timestamp(m['completed_at'])
    if started > completed or (as_of and completed > timestamp(as_of)):
        raise ValueError('Cut unavailable at requested as-of time')
    def read(name, checksum):
        path = (root/name).resolve()
        if path.parent != root or hash_file(path) != checksum:
            raise ValueError('Artifact path/hash integrity failure')
        return json.loads(path.read_text(encoding='utf-8'))
    cohort = read(m['cohort_path'], m['cohort_sha256'])
    if timestamp(cohort['selected_at']) > completed:
        raise ValueError('Cohort selected after cut completion')
    if len(cohort['dots']) != len(set(cohort['dots'])) or not cohort['dots']:
        raise ValueError('Invalid cohort population')
    if len(m['datasets']) != len(SOURCES) or {x['id'] for x in m['datasets']} != set(SOURCES):
        raise ValueError('Required source set incomplete')
    data = {}
    for source in m['datasets']:
        if source['status'] != 'COMPLETE' or not started <= timestamp(source['started_at']) <= timestamp(source['available_at']) <= completed:
            raise ValueError('Invalid source availability')
        lineage = read(source['lineage'],source['lineage_sha256'])
        stable(lineage['before'],lineage['after'])
        rows, seen = [], set()
        for page in source['pages']:
            batch = read(page['path'],page['sha256'])
            if len(batch) != page['rows'] or page['offset'] != len(rows):
                raise ValueError('Noncontiguous pages')
            for row in batch:
                key = row.get('source_row_id')
                if not key or key in seen or str(row.get('dot_number')) not in cohort['dots']:
                    raise ValueError('Duplicate/missing row ID or out-of-cohort row')
                seen.add(key)
            rows.extend(batch)
        if len(rows) != source['row_count'] or len(rows) != lineage['after']['row_count']:
            raise ValueError('Stored source count mismatch')
        data[source['id']] = rows
    return m, cohort, data

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',default=str(ROOT/'warehouse/raw'))
    parser.add_argument('--per-stratum',type=int,default=10)
    parser.add_argument('--cohort',help='Reuse a preserved cohort.json for a later cut')
    args = parser.parse_args()
    _, result = acquire(args.output_root,args.per_stratum,args.cohort)
    raise SystemExit(0 if result['status']=='COMPLETE' else 2)
