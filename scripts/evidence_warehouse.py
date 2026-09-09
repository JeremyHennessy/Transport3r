"""Promote verified acquisition cuts into a local, append-only-by-writer SQLite warehouse."""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sqlite3

from cohort_snapshot import PROFILES, ROOT, hash_file, load_verified, source_dot
from inspection_children import PARENT, parent_index
from snapshot_store import digest, now, write_once
from verify_snapshot import timestamp

SCHEMA_VERSION = 1
DEFAULT_DB = ROOT / 'warehouse/curated/evidence.sqlite'
DDL = '''
CREATE TABLE cuts (
 cut_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL, manifest_json TEXT NOT NULL,
 cohort_json TEXT NOT NULL, cohort_sha256 TEXT NOT NULL, profile TEXT NOT NULL,
 available_at TEXT NOT NULL, available_us INTEGER NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE members (cut_id TEXT NOT NULL REFERENCES cuts(cut_id), dot TEXT NOT NULL,
 PRIMARY KEY(cut_id,dot));
CREATE TABLE sources (cut_id TEXT NOT NULL REFERENCES cuts(cut_id), source_id TEXT NOT NULL,
 row_count INTEGER NOT NULL, rows_sha256 TEXT NOT NULL, lineage_json TEXT NOT NULL,
 lineage_sha256 TEXT NOT NULL, PRIMARY KEY(cut_id,source_id));
CREATE TABLE records (cut_id TEXT NOT NULL, source_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
 source_row_id TEXT NOT NULL, dot TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(cut_id,source_id,source_row_id), UNIQUE(cut_id,source_id,ordinal),
 FOREIGN KEY(cut_id,source_id) REFERENCES sources(cut_id,source_id),
 FOREIGN KEY(cut_id,dot) REFERENCES members(cut_id,dot));
CREATE INDEX carrier_records ON records(cut_id,dot,source_id,ordinal);
CREATE INDEX available_cuts ON cuts(available_us);
PRAGMA user_version=1;
'''


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def time_us(value):
    delta = timestamp(value).astimezone(dt.timezone.utc) - dt.datetime(1970,1,1,tzinfo=dt.timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def connect(db, writable=False):
    path = pathlib.Path(db).resolve()
    if writable:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30)
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if version == 0 and not tables:
            connection.executescript(DDL)
        elif version != SCHEMA_VERSION or {row[0] for row in tables} != {'cuts','members','sources','records'}:
            connection.close()
            raise ValueError('Unrecognized database; no schema was replaced')
        connection.execute('PRAGMA journal_mode=WAL')
    else:
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=30)
        if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
            connection.close()
            raise ValueError('Unrecognized warehouse schema')
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


def insert_source(connection, folder, cut_id, source, rows, parents=None):
    sid = source['id']
    lineage_text = (folder/source['lineage']).read_bytes().decode('utf-8')
    if hashlib.sha256(lineage_text.encode()).hexdigest() != source['lineage_sha256']:
        raise ValueError('Source lineage changed during promotion')
    connection.execute('INSERT INTO sources VALUES (?,?,?,?,?,?)',
                       (cut_id,sid,len(rows),digest(rows),lineage_text,source['lineage_sha256']))
    connection.executemany('INSERT INTO records VALUES (?,?,?,?,?,?)',
        ((cut_id,sid,i,row['source_row_id'],source_dot(sid,row,parents),encode(row)) for i,row in enumerate(rows)))


def verify_cut(connection, cut_id):
    cut = connection.execute('SELECT * FROM cuts WHERE cut_id=?',(cut_id,)).fetchone()
    if cut is None:
        raise ValueError('Cut not in warehouse')
    for field in ['manifest','cohort']:
        if hashlib.sha256(cut[f'{field}_json'].encode()).hexdigest() != cut[f'{field}_sha256']:
            raise ValueError('Stored manifest/cohort hash differs')
    manifest, cohort = json.loads(cut['manifest_json']), json.loads(cut['cohort_json'])
    if manifest['cohort_sha256'] != cut['cohort_sha256']:
        raise ValueError('Stored cohort lineage differs from source manifest')
    profile = manifest.get('source_profile','baseline')
    if manifest['status'] != 'COMPLETE' or profile not in PROFILES or profile != cut['profile'] or manifest['snapshot_id'] != cut_id:
        raise ValueError('Stored source profile or cut identity differs')
    if manifest['completed_at'] != cut['available_at'] or time_us(cut['available_at']) != cut['available_us']:
        raise ValueError('Stored cut availability differs')
    members = [row[0] for row in connection.execute('SELECT dot FROM members WHERE cut_id=?',(cut_id,))]
    if set(members) != set(cohort['dots']) or len(members) != len(cohort['dots']):
        raise ValueError('Stored cohort membership differs')
    sources = connection.execute('SELECT * FROM sources WHERE cut_id=?',(cut_id,)).fetchall()
    if {row['source_id'] for row in sources} != set(PROFILES[profile]):
        raise ValueError('Stored required sources are incomplete')
    expected = {row['id']: row for row in manifest['datasets']}
    parents = parent_index([json.loads(r[0]) for r in connection.execute(
        'SELECT payload FROM records WHERE cut_id=? AND source_id=? ORDER BY ordinal',(cut_id,PARENT))]) if profile=='underwriting_evidence_v2' else None
    counts = {}
    for source in sources:
        sid = source['source_id']
        if hashlib.sha256(source['lineage_json'].encode()).hexdigest() != source['lineage_sha256'] or source['lineage_sha256'] != expected[sid]['lineage_sha256']:
            raise ValueError('Stored source lineage hash differs')
        records = connection.execute('SELECT * FROM records WHERE cut_id=? AND source_id=? ORDER BY ordinal',(cut_id,sid)).fetchall()
        rows = [json.loads(record['payload']) for record in records]
        if len(rows) != source['row_count'] or len(rows) != expected[sid]['row_count'] or digest(rows) != source['rows_sha256']:
            raise ValueError('Stored source row count/hash differs')
        for i,(record,row) in enumerate(zip(records,rows)):
            if record['ordinal'] != i or record['dot'] != source_dot(sid,row,parents) or record['dot'] not in members or record['source_row_id'] != row['source_row_id']:
                raise ValueError('Stored record index differs from raw identity')
        counts[sid] = len(rows)
    return {'status':'VERIFIED','cut_id':cut_id,'profile':profile,'carriers':len(members),
            'source_rows':counts,'total_rows':sum(counts.values()),'available_at':cut['available_at'],
            'manifest_sha256':cut['manifest_sha256'],'historical_validity':'NOT_CERTIFIED'}


def promote(folder, db=DEFAULT_DB):
    folder = pathlib.Path(folder).resolve()
    manifest_hash = hash_file(folder/'manifest.json')
    manifest, cohort, data = load_verified(folder)
    if timestamp(manifest['completed_at']) > timestamp(now()):
        raise ValueError('Cannot promote a future-dated acquisition')
    manifest_text = (folder/'manifest.json').read_bytes().decode('utf-8')
    cohort_text = (folder/manifest['cohort_path']).read_bytes().decode('utf-8')
    if hashlib.sha256(manifest_text.encode()).hexdigest() != manifest_hash or hashlib.sha256(cohort_text.encode()).hexdigest() != manifest['cohort_sha256']:
        raise ValueError('Raw manifest/cohort changed during promotion')
    connection = connect(db, writable=True)
    cut_id = manifest['snapshot_id']
    try:
        connection.execute('BEGIN IMMEDIATE')
        existing = connection.execute('SELECT manifest_sha256 FROM cuts WHERE cut_id=?',(cut_id,)).fetchone()
        if existing:
            if existing[0] != manifest_hash:
                raise ValueError('Cut ID already exists with different manifest bytes')
            result = verify_cut(connection,cut_id)
            connection.rollback()
            return {**result,'promotion':'ALREADY_PRESENT'}
        connection.execute('INSERT INTO cuts VALUES (?,?,?,?,?,?,?,?,?)',
            (cut_id,manifest_hash,manifest_text,cohort_text,manifest['cohort_sha256'],manifest.get('source_profile','baseline'),
             manifest['completed_at'],time_us(manifest['completed_at']),now()))
        connection.executemany('INSERT INTO members VALUES (?,?)',((cut_id,dot) for dot in cohort['dots']))
        parents = parent_index(data[PARENT]) if manifest.get('source_profile')=='underwriting_evidence_v2' else None
        for source in manifest['datasets']:
            insert_source(connection,folder,cut_id,source,data[source['id']],parents)
        result = verify_cut(connection,cut_id)
        connection.commit()
        return {**result,'promotion':'INSERTED'}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def verify(db=DEFAULT_DB):
    connection = connect(db)
    try:
        connection.execute('BEGIN')
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite integrity or relationship check failed')
        cuts = connection.execute('SELECT cut_id FROM cuts ORDER BY available_us,cut_id').fetchall()
        if not cuts:
            raise ValueError('Warehouse contains no complete cuts')
        return {'status':'VERIFIED','cuts':[verify_cut(connection,row[0]) for row in cuts]}
    finally:
        connection.close()


def carrier_evidence(db, dot, as_of=None, profile=None, include_records=False):
    if not re.fullmatch(r'[1-9][0-9]*',dot):
        raise ValueError('Positive USDOT identifier required')
    as_of = as_of or now()
    if timestamp(as_of) > timestamp(now()):
        raise ValueError('Future observations are not available')
    if profile is not None and profile not in PROFILES:
        raise ValueError('Unknown profile')
    connection = connect(db)
    try:
        connection.execute('BEGIN')
        cuts = connection.execute('''SELECT cuts.* FROM cuts JOIN members USING(cut_id)
            WHERE dot=? AND available_us<=? AND (? IS NULL OR profile=?)
            ORDER BY available_us DESC,cut_id DESC LIMIT 1''',(dot,time_us(as_of),profile,profile)).fetchall()
        if not cuts:
            raise ValueError('No preserved cohort cut was available for this USDOT and as-of time')
        cut = cuts[0]
        verify_cut(connection,cut['cut_id'])
        acquired = {source['id']:source for source in json.loads(cut['manifest_json'])['datasets']}
        sources = []
        for source in connection.execute('SELECT * FROM sources WHERE cut_id=? ORDER BY source_id',(cut['cut_id'],)):
            sid = source['source_id']
            rows = [json.loads(row[0]) for row in connection.execute('SELECT payload FROM records WHERE cut_id=? AND source_id=? AND dot=? ORDER BY ordinal',(cut['cut_id'],sid,dot))]
            lineage = json.loads(source['lineage_json'])
            item = {'source_id':sid,'carrier_rows':len(rows),'cohort_rows':source['row_count'],
                    'scope':'ALL_RETURNED_ROWS_FOR_USDOT_IN_PRESERVED_COHORT_CUT','browser_cap_applied':False,
                    'status':'ROWS_RETURNED' if rows else 'NO_ROWS_RETURNED',
                    'source_acquisition_started_at':acquired[sid]['started_at'],
                    'source_available_at':acquired[sid]['available_at'],
                    'source_rows_updated_at':lineage['after']['rows_updated_at']}
            if include_records:
                item['rows'] = rows
            sources.append(item)
        return {'dot_number':dot,'as_of':as_of,'cut_id':cut['cut_id'],'cut_available_at':cut['available_at'],
                'source_manifest_sha256':cut['manifest_sha256'],'profile':cut['profile'],'sources':sources,
                'risk_score':None,'forecast':None,
                'limitations':'Complete for the preserved cohort queries only. Empty is not no historical activity. Sources have distinct publication windows; neither matching monthly cuts nor historical validity is certified.'}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=str(DEFAULT_DB))
    sub = parser.add_subparsers(dest='command',required=True)
    acquire = sub.add_parser('promote'); acquire.add_argument('cut')
    sub.add_parser('verify')
    for command in ['inspect','export']:
        query = sub.add_parser(command)
        query.add_argument('--dot',required=True)
        query.add_argument('--as-of')
        query.add_argument('--profile',choices=PROFILES)
        if command == 'export': query.add_argument('--output',required=True)
    args = parser.parse_args()
    if args.command == 'promote': result = promote(args.cut,args.db)
    elif args.command == 'verify': result = verify(args.db)
    else:
        result = carrier_evidence(args.db,args.dot,args.as_of,args.profile,args.command=='export')
        if args.command == 'export':
            write_once(pathlib.Path(args.output),result)
            result = {'status':'EXPORTED','path':args.output,'cut_id':result['cut_id'],'sources':len(result['sources']),
                      'rows':sum(source['carrier_rows'] for source in result['sources'])}
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
