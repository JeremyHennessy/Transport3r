#!/usr/bin/env python3
import json
import urllib.parse
import urllib.request

BANDS = [
    ('A',1,1),('B',2,3),('C',4,6),('D',7,8),('E',9,11),('F',12,14),('G',15,17),('H',18,19),
    ('I',20,23),('J',24,28),('K',29,32),('L',33,38),('M',39,44),('N',45,55),('O',56,75),
    ('P',76,100),('Q',101,200),('R',201,300),('S',301,400),('T',401,550),('U',551,999),
    ('V',1000,2000),('W',2001,3000),('X',3001,4000),('Y',4001,5000),('Z',5001,10**12),
]

def expected(n):
    for code, low, high in BANDS:
        if low <= n <= high:
            return code
    return None

params = {
    '$select': 'dot_number,legal_name,power_units,fleetsize,mcs150_date,status_code',
    '$where': "power_units is not null AND power_units!='0' AND fleetsize is not null",
    '$limit': '1500',
    '$order': 'dot_number DESC',
}
url = 'https://data.transportation.gov/resource/az4n-8mr2.json?' + urllib.parse.urlencode(params)
request = urllib.request.Request(url, headers={'User-Agent': 'Transport3r fleet audit', 'Accept': 'application/json'})
with urllib.request.urlopen(request, timeout=45) as response:
    rows = json.load(response)

matches = 0
mismatches = []
unknown = []
for row in rows:
    try:
        pu = int(float(str(row.get('power_units','')).replace(',','')))
    except ValueError:
        continue
    actual = str(row.get('fleetsize','')).strip().upper()
    exp = expected(pu)
    if not exp or actual not in {b[0] for b in BANDS}:
        unknown.append({'dot': row.get('dot_number'), 'power_units': pu, 'actual': actual, 'expected': exp})
    elif actual == exp:
        matches += 1
    else:
        mismatches.append({'dot': row.get('dot_number'), 'name': row.get('legal_name'), 'power_units': pu, 'actual': actual, 'expected': exp, 'mcs150_date': row.get('mcs150_date')})

comparable = matches + len(mismatches)
print(json.dumps({
    'sample_rows': len(rows),
    'comparable': comparable,
    'matches': matches,
    'mismatches': len(mismatches),
    'match_rate': round(matches / comparable, 4) if comparable else None,
    'unknown': len(unknown),
    'mismatch_examples': mismatches[:20],
}, indent=2))
if comparable < 100:
    raise SystemExit('Fleet audit returned too few comparable rows')
