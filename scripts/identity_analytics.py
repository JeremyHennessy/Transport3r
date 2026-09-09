"""Reproducible registration review leads and corporate event summaries.

No ownership, evasion, illegal operation or fraud determination is inferred.
All queries use a verified, immutable local publication through open_warehouse.
"""
import datetime as dt
import json
import re
import urllib.parse
from private_workspace_store import dot
from workspace_analytics import census

VERSION = 'IDENTITY_REVIEW_1'
CENSUS = 'az4n-8mr2'
EVENTS = {
    'inspections': ('fx4q-ay7w', 'inspection_id', 'insp_date'),
    'crash_reports': ('aayw-vxb3', 'crash_id', 'report_date'),
}


def source(db, identifier):
    row = db.execute('SELECT cut,available_at,sha256 FROM source_lineage WHERE source_id=?', [identifier]).fetchone()
    if not row:
        raise ValueError('Source lineage unavailable: '+identifier)
    return {'id': identifier, 'cut': row[0], 'available_at': row[1], 'sha256': row[2],
            'url': 'https://data.transportation.gov/d/'+identifier}


def date_sql(field):
    # FMCSA dates in these sources are YYYYMMDD or ISO timestamps.
    return f"coalesce(try_strptime({field},'%Y%m%d')::DATE,try_cast({field} AS DATE))"


def window(db, days):
    if type(days) is not int or days not in (90, 365, 730):
        raise ValueError('Use an activity window of 90, 365 or 730 days')
    lineage = [source(db, sid) for sid in (CENSUS, 'fx4q-ay7w', 'aayw-vxb3')]
    end = min(dt.datetime.fromisoformat(s['available_at'].replace('Z', '+00:00')).date() for s in lineage)
    start = end-dt.timedelta(days=days-1)
    return start, end, lineage


def event_summary(db, dots, days=365):
    ids = sorted({dot(x) for x in dots}, key=int)
    if not ids:
        raise ValueError('At least one USDOT is required')
    start, end, lineage = window(db, days)
    result = {'window': {'start': str(start), 'end': str(end), 'days': days, 'inclusive': True},
              'sources': lineage, 'members': ids, 'metrics': {}, 'by_dot': {x: {} for x in ids}}
    for name, (sid, key, date) in EVENTS.items():
        table = 'raw_'+sid.replace('-', '_')
        # Ignore only ingestion row identity when collapsing exact duplicate evidence.
        db.execute('CREATE OR REPLACE TEMP TABLE identity_events AS SELECT DISTINCT * EXCLUDE (_warehouse_row_id) FROM '+table+
                   ' WHERE dot_number IN ('+','.join('?' for _ in ids)+')', ids)
        duplicate = db.execute(f"SELECT count(*) FROM (SELECT {key} FROM identity_events WHERE nullif(trim({key}),'') IS NOT NULL GROUP BY {key} HAVING count(*)>1)").fetchone()[0]
        db.execute(f'CREATE OR REPLACE TEMP VIEW identity_dated AS SELECT *,{date_sql(date)} AS event_day FROM identity_events')
        selected = f"nullif(trim({key}),'') IS NOT NULL AND event_day BETWEEN ? AND ?"
        for identifier in [None]+ids:
            clause = '' if identifier is None else ' WHERE dot_number=?'
            params = [] if identifier is None else [identifier]
            bad_key, bad_date, future, published = db.execute(
                f"SELECT count(*) FILTER (WHERE nullif(trim({key}),'') IS NULL),count(*) FILTER (WHERE event_day IS NULL),count(*) FILTER (WHERE event_day>?),count(*) FROM identity_dated"+clause,
                [end]+params).fetchone()
            count, latest = db.execute(f'SELECT count(*),max(event_day) FROM identity_dated WHERE {selected}'+('' if identifier is None else ' AND dot_number=?'), [start, end]+params).fetchone()
            issues = {'missing_event_id': bad_key, 'invalid_event_date': bad_date, 'future_event_date': future,
                      'conflicting_event_ids_in_group': duplicate}
            metric = {'count': count if not any(issues.values()) else None, 'known_window_rows': count,
                      'published_rows': published, 'latest_event_date': str(latest) if latest else None, 'issues': issues}
            if name == 'inspections':
                known, positive = db.execute("SELECT count(*) FILTER (WHERE regexp_full_match(oos_total,'[0-9]+') AND try_cast(oos_total AS BIGINT)>=0),count(*) FILTER (WHERE regexp_full_match(oos_total,'[0-9]+') AND try_cast(oos_total AS BIGINT)>0) FROM identity_dated WHERE "+selected+('' if identifier is None else ' AND dot_number=?'), [start, end]+params).fetchone()
                metric['oos'] = {'positive': positive if not duplicate else None, 'known': known, 'unknown': count-known,
                                 'rate_pct': round(100*positive/count, 2) if count and known == count and not any(issues.values()) else None}
            if identifier is None:
                result['metrics'][name] = metric
            else:
                result['by_dot'][identifier][name] = metric
        columns = f'{key} AS event_id,dot_number,event_day'
        records = db.execute('SELECT '+columns+' FROM identity_dated WHERE '+selected+' ORDER BY event_day DESC,dot_number,event_id LIMIT 25', [start, end]).fetchall()
        result['metrics'][name]['examples'] = [{'event_id': r[0], 'dot': r[1], 'date': str(r[2]), 'source_url': 'https://data.transportation.gov/resource/'+sid+'.json?'+urllib.parse.urlencode({key: r[0]})} for r in records]
    result['status'] = 'AVAILABLE' if all(m['count'] is not None for m in result['metrics'].values()) else 'PARTIAL_EVIDENCE'
    result['limitation'] = 'Counts describe published inspection records and crash vehicle reports, not unique crashes, fault, exposure-adjusted risk or complete operating history. No rows in a publication is not proof of no activity. Corporate membership is applied as reviewed now; ownership at the event date is not established. SMS scores are not added or averaged.'
    return result


def ghost_review(db, seed, days=365):
    seed = dot(seed)
    rows = census(db, [seed])
    activity = event_summary(db, [seed], days)
    row = rows[0] if rows else {}
    status = row.get('status_code')
    observed = any(m['known_window_rows'] for m in activity['metrics'].values())
    if activity['status'] != 'AVAILABLE':
        disposition = 'INCOMPLETE_ACTIVITY_EVIDENCE'
    elif not rows or status not in ('A', 'I', 'P'):
        disposition = 'REGISTRATION_UNRESOLVED'
    elif status in ('I', 'P') and observed:
        disposition = 'STATUS_ACTIVITY_REVIEW'
    elif status in ('I', 'P'):
        disposition = 'NO_RECENT_PUBLISHED_ACTIVITY'
    else:
        disposition = 'NO_STATUS_ACTIVITY_RULE_TRIGGER'
    return {'ruleset': VERSION, 'dot': seed, 'name': row.get('legal_name'), 'registration_status': status,
            'registration_added': row.get('add_date'), 'report_date': row.get('mcs150_date'),
            'status_effective_date': None, 'activity_while_inactive': 'NOT_ESTABLISHED', 'finding': disposition,
            'activity': activity, 'source': source(db, CENSUS),
            'limitation': 'Ghost DOT screening lead only. Current registration status is not operating-authority status. Historical activity can predate inactivation. Confirm status effective dates and carrier identity before any conclusion. Neither inactivity nor a missing record establishes fraudulent operation.'}


def ghost_queue(db, days=365, page=1):
    if type(page) is not int or page < 1 or page > 100000:
        raise ValueError('Invalid queue page')
    start, end, lineage = window(db, days)
    parts = []
    for name, (sid, key, field) in EVENTS.items():
        parts.append(f"SELECT dot_number,max({date_sql(field)}) AS latest FROM raw_{sid.replace('-', '_')} WHERE {date_sql(field)} BETWEEN ? AND ? AND nullif(trim({key}),'') IS NOT NULL GROUP BY dot_number")
    db.execute("CREATE OR REPLACE TEMP TABLE ghost_candidates AS SELECT c.dot_number,c.legal_name,c.status_code,c.mcs150_date,max(a.latest) AS latest_event FROM raw_az4n_8mr2 c JOIN ("+' UNION ALL '.join(parts)+") a ON a.dot_number=c.dot_number WHERE c.status_code IN ('I','P') GROUP BY c.dot_number,c.legal_name,c.status_code,c.mcs150_date", [start, end, start, end])
    total = db.execute('SELECT count(*) FROM ghost_candidates').fetchone()[0]
    rows = db.execute('SELECT * FROM ghost_candidates ORDER BY latest_event DESC,try_cast(dot_number AS BIGINT) LIMIT 50 OFFSET ?', [(page-1)*50]).fetchall()
    return {'ruleset': VERSION, 'page': page, 'page_size': 50, 'total': total, 'has_next': page*50 < total,
            'window': {'start': str(start), 'end': str(end)}, 'sources': lineage,
            'rows': [dict(zip(('dot', 'name', 'registration_status', 'report_date', 'latest_event_date'), [*r[:4], str(r[4])])) for r in rows],
            'limitation': 'Nationwide candidates: inactive or pending Census registrations with dated published activity in this window. Open a carrier to check record integrity and source evidence. This queue does not establish status at the event date, unlawful operation or fraud; it excludes unresolved Census identities and undated activity.'}


def normal_sql(field, mode='text'):
    if mode == 'digits':
        return f"regexp_replace(coalesce({field},''),'[^0-9]','','g')"
    if mode == 'email':
        return f"lower(trim(coalesce({field},'')))"
    # Preserve punctuation and unit numbers for conservative address/name matching.
    return f"upper(regexp_replace(trim(coalesce({field},'')),'\\s+',' ','g'))"


def identity_keys(row):
    keys = []
    placeholders = {'', 'NONE', 'UNKNOWN', 'N/A', 'NA', 'NOT PROVIDED', 'NOT AVAILABLE', 'NULL', 'NO EMAIL'}
    for category, fields, mode in [('phone', ['phone', 'cell_phone'], 'digits'), ('email', ['email_address'], 'email'),
                                   ('officer', ['company_officer_1', 'company_officer_2'], 'text'),
                                   ('duns', ['dun_bradstreet_no'], 'digits')]:
        for field in fields:
            raw = row.get(field) or ''
            value = re.sub(r'[^0-9]', '', raw) if mode == 'digits' else raw.strip().lower() if mode == 'email' else re.sub(r'\s+', ' ', raw.strip()).upper()
            if value.upper() in placeholders:
                continue
            if category == 'phone':
                if len(value) == 11 and value.startswith('1'):
                    value = value[1:]
                if len(value) != 10 or len(set(value)) <= 2 or value in ('1234567890', '0123456789'):
                    continue
            if category == 'duns' and (len(value) != 9 or len(set(value)) <= 1):
                continue
            if category == 'email' and (not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value) or value.split('@')[0] in ('none','noemail','unknown','na','test') or value.endswith(('@example.com','@example.org'))):
                continue
            if category == 'officer' and (len(value) < 5 or len(value.split()) < 2):
                continue
            if not any(k['category'] == category and k['value'] == value for k in keys):
                keys.append({'category': category, 'value': value, 'seed_field': field, 'fields': fields, 'mode': mode})
    address_fields = ['phy_street', 'phy_city', 'phy_state', 'phy_country', 'phy_zip']
    address = [re.sub(r'\s+', ' ', (row.get(f) or '').strip()).upper() for f in address_fields]
    if all(v not in placeholders for v in address) and len(address[0]) >= 5:
        keys.append({'category': 'address', 'value': ' | '.join(address), 'seed_field': 'physical address', 'fields': address_fields, 'mode': 'address'})
    return keys


def identity_screen(db, seed, page=1):
    seed = dot(seed)
    if type(page) is not int or not 1 <= page <= 100000:
        raise ValueError('Invalid candidate page')
    target = census(db, [seed])
    if len(target) != 1:
        raise ValueError('Unique Census registration required for identity screening')
    keys = identity_keys(target[0])
    fragments, params = [], []
    for index, key in enumerate(keys):
        expressions = []
        if key['mode'] == 'address':
            expressions = [' || \' | \' || '.join(normal_sql(f) for f in key['fields'])]
        else:
            for field in key['fields']:
                expr = normal_sql(field, key['mode'])
                if key['category'] == 'phone':
                    expr = f"CASE WHEN length({expr})=11 AND left({expr},1)='1' THEN substr({expr},2) ELSE {expr} END"
                expressions.append(expr)
        fragments.append(f"SELECT dot_number,{index} AS key_id,'{key['category']}' AS category FROM raw_az4n_8mr2 WHERE ("+' OR '.join(e+'=?' for e in expressions)+')')
        params.extend([key['value']]*len(expressions))
    # Published prior-revocation references are directional registration evidence, not our inference.
    prior = str(target[0].get('prior_revoke_dot_number') or '').strip()
    if prior.isdigit() and int(prior) > 0 and prior != seed:
        index = len(keys)
        keys.append({'category': 'prior_revocation_reference', 'value': prior, 'seed_field': 'prior_revoke_dot_number'})
        fragments.append(f"SELECT dot_number,{index} AS key_id,'prior_revocation_reference' AS category FROM raw_az4n_8mr2 WHERE dot_number=?");params.append(str(int(prior)))
    index = len(keys)
    keys.append({'category': 'reverse_prior_revocation_reference', 'value': seed, 'seed_field': 'dot_number'})
    fragments.append(f"SELECT dot_number,{index} AS key_id,'reverse_prior_revocation_reference' AS category FROM raw_az4n_8mr2 WHERE try_cast(prior_revoke_dot_number AS BIGINT)=?");params.append(int(seed))
    db.execute('CREATE OR REPLACE TEMP TABLE identity_matches AS SELECT DISTINCT * FROM ('+' UNION ALL '.join(fragments)+')', params)
    frequencies = dict(db.execute('SELECT key_id,count(DISTINCT dot_number) FROM identity_matches GROUP BY key_id').fetchall())
    for i, key in enumerate(keys):
        key['matching_registration_count'] = frequencies.get(i, 0)
        key['common_detail'] = key['category'] in ('phone','email','officer','address') and frequencies.get(i, 0) > 20
    db.execute('CREATE OR REPLACE TEMP TABLE identity_candidates AS SELECT dot_number,list(key_id ORDER BY key_id) AS keys,count(DISTINCT category) AS categories FROM identity_matches WHERE dot_number<>? GROUP BY dot_number', [seed])
    total = db.execute('SELECT count(*) FROM identity_candidates').fetchone()[0]
    # Category count orders a review queue only; it is not a fraud score or probability.
    rows = db.execute('SELECT dot_number,keys FROM identity_candidates ORDER BY categories DESC,try_cast(dot_number AS BIGINT) LIMIT 50 OFFSET ?', [(page-1)*50]).fetchall()
    carriers = {r['dot_number']: r for r in census(db, [r[0] for r in rows])} if rows else {}
    candidates = []
    for identifier, indices in rows:
        matches = [keys[i] for i in indices]
        categories = {k['category'] for k in matches}
        independent = categories-{'prior_revocation_reference','reverse_prior_revocation_reference'}
        row = carriers[identifier]
        candidates.append({'dot': identifier, 'name': row.get('legal_name'), 'registration_status': row.get('status_code'),
                           'added_date': row.get('add_date'), 'report_date': row.get('mcs150_date'), 'matches': matches,
                           'candidate_source_values': {f: row.get(f) for k in matches for f in k.get('fields', ['prior_revoke_dot_number'])},
                           'category_count': len(categories), 'review_reason': 'PUBLISHED_PRIOR_REVOCATION_REFERENCE' if categories != independent else 'MULTIPLE_SHARED_CATEGORIES' if len(independent) >= 2 else 'SINGLE_SHARED_CATEGORY',
                           'status_difference': row.get('status_code') != target[0].get('status_code')})
    return {'ruleset': VERSION, 'dot': seed, 'name': target[0].get('legal_name'), 'registration_status': target[0].get('status_code'),
            'added_date': target[0].get('add_date'), 'source': source(db, CENSUS), 'keys_checked': keys,
            'seed_source_values': {f: target[0].get(f) for k in keys for f in k.get('fields', ['prior_revoke_dot_number'])},
            'total': total, 'page': page, 'page_size': 50, 'has_next': page*50 < total, 'candidates': candidates,
            'limitation': 'Chameleon-carrier screening leads only. Exact normalized registration details can reflect legitimate affiliates, common names, shared offices or service providers. Multiple matches are not proof of evasion, ownership or fraud. No name similarity, invented history or automatic corporate membership. Common detail means more than 20 matching registrations, not a validated risk threshold.'}
