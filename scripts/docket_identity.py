"""Exact docket identity only; no carrier-name matching or numeric-prefix stripping."""
import re
from snapshot_store import digest
BRIDGE='6eyk-hxee'
DOCKET_ONLY='ypjt-5ydn'
LEGACY_DOT={BRIDGE,'qh9u-swkp','9mw4-x3tu','2emp-mxtb','6sqe-dvqs','96tg-4mhf','sa6p-acbp'}
IDENTITY_CONTRACT='LEGACY_USDOT_CANONICAL_AND_8_DIGIT_1'

def canonical_dot(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]+',value) or int(value)<=0:raise ValueError('Invalid legacy bridge USDOT')
    return str(int(value))


def docket_index(rows):
    result={}
    for row in rows:
        docket=row.get('docket_number');dot=canonical_dot(row.get('dot_number'))
        if not isinstance(dot,str) or not re.fullmatch(r'[1-9][0-9]*',dot):raise ValueError('Invalid legacy bridge USDOT')
        if docket is None or not str(docket).strip():continue
        if not isinstance(docket,str) or not re.fullmatch(r'[A-Za-z]{1,3}[0-9]+',docket):raise ValueError('Unresolved docket format')
        if docket in result and result[docket]!=dot:raise ValueError('Docket maps to multiple carriers')
        result[docket]=dot
    return result

def docket_where(field,dockets):
    if field not in ('docket_number','prefix_docket_number'):raise ValueError('Invalid docket field')
    if any(not re.fullmatch(r'[A-Za-z]{1,3}[0-9]+',d) for d in dockets):raise ValueError('Invalid docket query')
    return field+' in ('+','.join("'"+d+"'" for d in sorted(dockets))+')' if dockets else '1=0'

def docket_dot(row,index):
    dot=index.get(row.get('prefix_docket_number'))
    if dot is None or ('dot_number' in row and canonical_dot(row['dot_number'])!=dot):raise ValueError('Orphan or cross-carrier docket filing')
    return dot

def verify_bridge(proof,expected):
    from cohort_snapshot import stable
    if proof.get('source_id')!=BRIDGE or proof.get('where')!=docket_where('docket_number',expected):raise ValueError('Docket bridge scope differs')
    stable(proof['before'],proof['after'])
    rows=proof['rows'];seen=set()
    for row in rows:
        key=row.get('source_row_id')
        if not key or key in seen or row.get('docket_number') not in expected:raise ValueError('Invalid global docket bridge row')
        seen.add(key)
    if len(rows)!=proof['after']['row_count'] or digest(rows)!=proof.get('rows_sha256'):raise ValueError('Docket bridge completeness differs')
    if docket_index(rows)!=expected:raise ValueError('Global docket ownership conflicts with selected cohort')
    return expected

def capture_bridge(expected,parent_lineage,max_rows=100000):
    from cohort_snapshot import query,state,stable
    where=docket_where('docket_number',expected);before=state(BRIDGE,where)
    if before['row_count']>max_rows:raise ValueError('Docket bridge exceeds ceiling')
    rows=[];offset=0
    while True:
        batch=query(BRIDGE,select='*, :id as source_row_id',where=where,order=':id',limit=1000,offset=offset)
        rows.extend(batch)
        if len(rows)>max_rows:raise ValueError('Docket bridge exceeds ceiling')
        if len(batch)<1000:break
        offset+=len(batch)
    after=state(BRIDGE,where);stable(before,after)
    # Same publication/schema as the earlier cohort bridge, despite a broader DOT scope.
    for key in ['rows_updated_at','schema_sha256','table_id']:
        if parent_lineage['after'][key]!=after[key]:raise ValueError('Legacy bridge changed during acquisition')
    proof={'source_id':BRIDGE,'where':where,'before':before,'after':after,'rows':rows,'rows_sha256':digest(rows)}
    verify_bridge(proof,expected)
    return proof
