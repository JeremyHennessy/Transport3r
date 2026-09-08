#!/usr/bin/env python3
"""Bounded Census consistency audit; band agreement is not exposure accuracy."""
import json
import math
import urllib.parse
import urllib.request

BANDS = [
    ('A',1,1),('B',2,3),('C',4,6),('D',7,8),('E',9,11),('F',12,14),('G',15,17),('H',18,19),
    ('I',20,23),('J',24,28),('K',29,32),('L',33,38),('M',39,44),('N',45,55),('O',56,75),
    ('P',76,100),('Q',101,200),('R',201,300),('S',301,400),('T',401,550),('U',551,999),
    ('V',1000,2000),('W',2001,3000),('X',3001,4000),('Y',4001,5000),('Z',5001,math.inf),
]

def expected(n):
    return next((code for code, low, high in BANDS if low <= n <= high), None)

def audit(rows):
    matches, mismatches, unknown = 0, [], 0
    for row in rows:
        try:
            count = float(str(row.get('power_units', '')).replace(',', ''))
            if not math.isfinite(count) or not count.is_integer() or count < 1:
                raise ValueError('Invalid power-unit count')
        except (TypeError, ValueError):
            unknown += 1
            continue
        actual = str(row.get('fleetsize', '')).strip().upper()
        exp = expected(count)
        if actual not in {band[0] for band in BANDS}:
            unknown += 1
        elif actual == exp:
            matches += 1
        else:
            mismatches.append({'dot': row.get('dot_number'), 'power_units': int(count), 'actual': actual, 'expected': exp})
    comparable = matches + len(mismatches)
    return {'sample_rows': len(rows), 'comparable': comparable, 'matches': matches,
            'mismatches': len(mismatches), 'unknown': unknown,
            'match_rate': matches / comparable if comparable else None, 'mismatch_examples': mismatches[:20]}

def validate(result):
    if result['comparable'] < 100:
        raise ValueError('Fleet audit returned too few comparable rows')
    if result['mismatches']:
        raise ValueError(f"Fleet audit found {result['mismatches']} band mismatches")

def main():
    params = {'$select': 'dot_number,legal_name,power_units,fleetsize,mcs150_date,status_code',
              '$where': "power_units is not null AND power_units!='0' AND fleetsize is not null",
              '$limit': '1500', '$order': 'dot_number DESC'}
    url = 'https://data.transportation.gov/resource/az4n-8mr2.json?' + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={'User-Agent': 'Transport3r fleet audit', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=45) as response:
        result = audit(json.load(response))
    print(json.dumps(result, indent=2))
    validate(result)

if __name__ == '__main__':
    main()
