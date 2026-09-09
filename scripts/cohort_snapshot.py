"""Current, cohort-scoped source acquisition. Never an historical reconstruction."""
import argparse
import hashlib
import json
import pathlib
import re
import urllib.parse

from snapshot_store import create_cut, fetch_json, now, write_once, digest
from verify_snapshot import timestamp
from inspection_children import CHILDREN, PARENT, parent_index, child_dot, collect_children, verify_children

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = 'https://data.transportation.gov'
SOURCES = ['az4n-8mr2', 'fx4q-ay7w', 'aayw-vxb3', 'm3ry-qcip', 'h3zn-uid9', '4y6x-dmck', 'h9zy-gjn8']
PROFILES = {
    'baseline': SOURCES,
    'underwriting_evidence_v1': SOURCES + ['kjg3-diqy', 'rbkj-cgst', '8mt8-2mdr', '4wxs-vbns',
                                         'inys-ebih', 'c5y8-a4uz', 'p2mt-9ige'],
}
DOT_FIELDS = {'inys-ebih': 'usdot_number', 'c5y8-a4uz': 'usdot_number'}
PROFILES['underwriting_evidence_v2'] = PROFILES['underwriting_evidence_v1'] + list(CHILDREN)


def source_dot(sid, row, parents=None):
    if sid in CHILDREN:
        return child_dot(row, parents or {})
    return str(row.get(DOT_FIELDS.get(sid, 'dot_number')))


def cohort_where(sid, dots):
    return DOT_FIELDS.get(sid, 'dot_number') + ' in (' + ','.join("'"+d+"'" for d in dots) + ')'
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
    if not 1 <= page_size <= 10000 or not 1 <= max_rows <= 1000000:
        raise ValueError('Acquisition bounds require page size 1..10000 and row ceiling 1..1000000')
    where = cohort_where(sid, dots)
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
            if not key or key in seen or source_dot(sid, row) not in dots:
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

def acquire(root, per_stratum=10, cohort_path=None, profile='baseline', max_rows=100000):
    if profile not in PROFILES or not 1 <= max_rows <= 1000000:
        raise ValueError('Unknown source profile or invalid row ceiling')
    folder, manifest = create_cut(pathlib.Path(root), schema_version=3 if profile == 'baseline' else 5 if profile == 'underwriting_evidence_v2' else 4, acquisition_kind='CURRENT_COHORT_PUBLIC_SOURCE')
    manifest['scope'] = 'EXPLICIT_USDOT_COHORT'
    if profile != 'baseline':
        manifest.update({'source_profile': profile, 'max_rows_per_source': max_rows})
    try:
        cohort = json.loads(pathlib.Path(cohort_path).read_text(encoding='utf-8')) if cohort_path else select_cohort(per_stratum)
        dots = cohort['dots']
        if len(dots) != len(set(dots)) or not 1 <= len(dots) <= 140 or any(not re.fullmatch(r'[1-9][0-9]*', d) for d in dots):
            raise ValueError('Cohort requires 1..140 unique positive USDOT strings')
        if timestamp(cohort['selected_at']) > timestamp(now()):
            raise ValueError('Cohort selection is in the future')
        write_once(folder/'cohort.json', cohort)
        results, parents, parent_lineage = [], None, None
        for sid in PROFILES[profile]:
            try:
                if sid in CHILDREN:
                    if parents is None:
                        raise ValueError('Verified inspection parent acquisition unavailable')
                    result = collect_children(sid,parents,folder,parent_lineage,max_rows=max_rows)
                else:
                    result = collect(sid, dots, folder, max_rows=max_rows)
                    if sid == PARENT and profile == 'underwriting_evidence_v2':
                        parents = parent_index([r for page in result['pages'] for r in json.loads((folder/page['path']).read_text(encoding='utf-8'))])
                        parent_lineage = json.loads((folder/result['lineage']).read_text(encoding='utf-8'))
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
    version = m.get('schema_version')
    if version not in (3,4,5) or (m.get('status'),m.get('acquisition_kind'),m.get('historical_reconstruction')) != ('COMPLETE','CURRENT_COHORT_PUBLIC_SOURCE',False):
        raise ValueError('Only complete cohort v3/v4/v5 cuts are eligible')
    profile = 'baseline' if version == 3 else m.get('source_profile')
    if profile not in PROFILES or {'baseline':3,'underwriting_evidence_v1':4,'underwriting_evidence_v2':5}[profile] != version:
        raise ValueError('Unknown or incompatible source profile')
    required = PROFILES[profile]
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
    if len(cohort['dots']) != len(set(cohort['dots'])) or not 1 <= len(cohort['dots']) <= 140 or any(not isinstance(d,str) or not re.fullmatch(r'[1-9][0-9]*',d) for d in cohort['dots']):
        raise ValueError('Invalid cohort population')
    if len(m['datasets']) != len(required) or {x['id'] for x in m['datasets']} != set(required):
        raise ValueError('Required source set incomplete')
    data = {}
    for source in m['datasets']:
        if source['status'] != 'COMPLETE' or not started <= timestamp(source['started_at']) <= timestamp(source['available_at']) <= completed:
            raise ValueError('Invalid source availability')
        lineage = read(source['lineage'],source['lineage_sha256'])
        stable(lineage['before'],lineage['after'])
        if source['id'] in CHILDREN:
            if PARENT not in data:
                raise ValueError('Verified parents must precede inspection children')
            parent_source = next(s for s in m['datasets'] if s['id']==PARENT)
            if timestamp(parent_source['available_at']) > timestamp(source['started_at']):
                raise ValueError('Child acquisition preceded verified parent availability')
            parent_lineage = read(parent_source['lineage'],parent_source['lineage_sha256'])
            data[source['id']] = verify_children(source,lineage,parent_index(data[PARENT]),parent_lineage,read,m['max_rows_per_source'])
            continue
        if version >= 4:
            if lineage.get('where') != cohort_where(source['id'],cohort['dots']) or lineage.get('order') != ':id' or lineage.get('select') != '*, :id as source_row_id':
                raise ValueError('Query scope differs from the preserved cohort contract')
            if not timestamp(cohort['selected_at']) <= timestamp(source['started_at']) <= timestamp(lineage['before']['observed_at']) <= timestamp(lineage['after']['observed_at']) <= timestamp(source['available_at']):
                raise ValueError('Source observation times differ from acquisition lineage')
            if not source['pages'] or source['row_count'] > m['max_rows_per_source']:
                raise ValueError('Missing source pages or source exceeds accepted ceiling')
        rows, seen = [], set()
        for page in source['pages']:
            batch = read(page['path'],page['sha256'])
            if len(batch) != page['rows'] or page['offset'] != len(rows):
                raise ValueError('Noncontiguous pages')
            for row in batch:
                key = row.get('source_row_id')
                if not key or key in seen or source_dot(source['id'], row) not in cohort['dots']:
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
    parser.add_argument('--profile',choices=PROFILES,default='baseline')
    parser.add_argument('--max-rows',type=int,default=100000,help='Per-source fail-closed ceiling; never a truncated successful cut')
    args = parser.parse_args()
    _, result = acquire(args.output_root,args.per_stratum,args.cohort,args.profile,args.max_rows)
    raise SystemExit(0 if result['status']=='COMPLETE' else 2)
