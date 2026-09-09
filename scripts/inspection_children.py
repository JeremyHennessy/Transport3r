"""Complete child extracts; raw payloads retain their original fields and parent IDs."""
import concurrent.futures
import re

from snapshot_store import digest, now, write_once
from verify_snapshot import timestamp

PARENT = 'fx4q-ay7w'
CHILDREN = {'wt8s-2hbx':'text', '876r-jsdb':'number', 'qbt8-7vic':'text', '5qik-smay':'text'}
BATCH_SIZE = 250


def parent_index(rows):
    result = {}
    for row in rows:
        key, dot = row.get('inspection_id'), row.get('dot_number')
        if not isinstance(key,str) or not re.fullmatch(r'[1-9][0-9]*',key) or key in result:
            raise ValueError('Missing/duplicate daily inspection parent ID')
        if not isinstance(dot,str) or not re.fullmatch(r'[1-9][0-9]*',dot):
            raise ValueError('Invalid parent USDOT')
        result[key] = dot
    return result


def child_dot(row, parents):
    dot = parents.get(row.get('inspection_id'))
    if dot is None or ('dot_number' in row and str(row['dot_number']) != dot):
        raise ValueError('Orphan or cross-carrier inspection child')
    return dot


def batches(parents):
    ids = sorted(parents, key=int)
    return [ids[i:i+BATCH_SIZE] for i in range(0,len(ids),BATCH_SIZE)]


def child_where(sid, ids):
    if sid not in CHILDREN or not ids or any(not re.fullmatch(r'[1-9][0-9]*',key) for key in ids):
        raise ValueError('Invalid inspection child query')
    return 'inspection_id in ('+','.join("'"+key+"'" if CHILDREN[sid]=='text' else key for key in ids)+')'


def collect_children(sid, parents, folder, parent_lineage, max_rows=100000, page_size=1000):
    from cohort_snapshot import query, state, stable, hash_file
    if sid not in CHILDREN or not 1 <= max_rows <= 1000000 or not 1 <= page_size <= 10000:
        raise ValueError('Invalid child acquisition bounds or source')
    started = now()
    before = state(sid, 'inspection_id is not null')
    columns = {c['fieldName']:c['dataTypeName'] for c in before['metadata']['columns']}
    if columns.get('inspection_id') != CHILDREN[sid]:
        raise ValueError('Inspection child key schema changed')

    selected_batches = batches(parents)
    def preflight(ids):
        return int(query(sid,select='count(*) as count',where=child_where(sid,ids))[0]['count'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        counts = list(pool.map(preflight,selected_batches))
    if any(count<0 for count in counts) or sum(counts)>max_rows:
        raise ValueError('Complete child source exceeds accepted row ceiling')

    def collect_batch(index, ids, count_before):
        where = child_where(sid,ids)
        if count_before > max_rows:
            raise ValueError('Child batch exceeds accepted row ceiling')
        pages, seen, rows, offset = [], set(), [], 0
        while True:
            batch = query(sid,select='*, :id as source_row_id',where=where,order=':id',limit=page_size,offset=offset)
            name = f'{sid}.batch-{index:05d}.page-{offset:08d}.json'
            write_once(folder/name,batch)
            pages.append({'path':name,'sha256':hash_file(folder/name),'rows':len(batch),'offset':offset})
            if len(batch)>page_size or len(rows)+len(batch)>count_before:
                raise ValueError('Child response exceeds accepted row ceiling')
            for row in batch:
                key = row.get('source_row_id')
                if not key or key in seen or row.get('inspection_id') not in ids:
                    raise ValueError('Duplicate/missing child row ID or wrong parent batch')
                child_dot(row,parents)
                seen.add(key)
            rows.extend(batch)
            if len(batch)<page_size:
                break
            offset += len(batch)
        count_after = int(query(sid,select='count(*) as count',where=where)[0]['count'])
        if count_before != count_after or len(rows)!=count_after:
            raise ValueError('Child query count changed or pages incomplete')
        return {'where':where,'parent_ids':ids,'row_count':len(rows),'count_before':count_before,
                'count_after':count_after,'pages':pages}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(collect_batch,i,ids,counts[i]) for i,ids in enumerate(selected_batches)]
        results = [future.result() for future in futures]
    after = state(sid,'inspection_id is not null')
    stable(before,after)
    parent_after = state(PARENT,parent_lineage['where'])
    stable(parent_lineage['after'],parent_after)
    row_count = sum(r['row_count'] for r in results)
    if row_count > max_rows:
        raise ValueError('Complete child source exceeds accepted row ceiling')
    name = f'{sid}.lineage.json'
    write_once(folder/name,{'scope':'VERIFIED_INSPECTION_PARENTS','parent_map_sha256':digest(parents),
                           'parent_source_after':parent_after,'before':before,'after':after,
                           'order':':id','select':'*, :id as source_row_id','batches':results})
    return {'id':sid,'status':'COMPLETE','started_at':started,'available_at':now(),'row_count':row_count,
            'lineage':name,'lineage_sha256':hash_file(folder/name),
            'pages':[page for batch in results for page in batch['pages']]}


def verify_children(source, lineage, parents, parent_lineage, read, max_rows):
    from cohort_snapshot import stable
    sid = source['id']
    stable(lineage['before'],lineage['after'])
    stable(parent_lineage['after'],lineage['parent_source_after'])
    if (lineage.get('scope'),lineage.get('parent_map_sha256'),lineage.get('order'),lineage.get('select')) != (
        'VERIFIED_INSPECTION_PARENTS',digest(parents),':id','*, :id as source_row_id'):
        raise ValueError('Child query lineage or parent map differs')
    if not timestamp(source['started_at']) <= timestamp(lineage['before']['observed_at']) <= timestamp(lineage['after']['observed_at']) <= timestamp(lineage['parent_source_after']['observed_at']) <= timestamp(source['available_at']):
        raise ValueError('Invalid child acquisition chronology')
    expected_batches = batches(parents)
    if len(lineage['batches']) != len(expected_batches):
        raise ValueError('Missing child parent batches')
    if source['pages'] != [p for b in lineage['batches'] for p in b['pages']]:
        raise ValueError('Child page manifest differs from lineage')
    rows, seen = [], set()
    for b, ids in zip(lineage['batches'],expected_batches):
        if b['parent_ids'] != ids or b['where'] != child_where(sid,ids) or not b['pages']:
            raise ValueError('Child parent query scope differs')
        count = 0
        for page in b['pages']:
            batch = read(page['path'],page['sha256'])
            if len(batch)!=page['rows'] or page['offset']!=count:
                raise ValueError('Noncontiguous child pages')
            for row in batch:
                key = row.get('source_row_id')
                if not key or key in seen or row.get('inspection_id') not in ids:
                    raise ValueError('Duplicate/missing child row ID or wrong parent batch')
                child_dot(row,parents)
                seen.add(key)
            rows.extend(batch)
            count += len(batch)
        if count != b['row_count'] or count != b['count_before'] or count != b['count_after']:
            raise ValueError('Child page/query count mismatch')
    if len(rows)!=source['row_count'] or len(rows)>max_rows:
        raise ValueError('Child source total mismatch or ceiling exceeded')
    return rows
