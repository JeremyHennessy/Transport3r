"""Build local state symbols from the official Census 2025 20M boundary response."""
import json, pathlib, hashlib
p=pathlib.Path('outputs/census-states-2025.geojson');g=json.loads(p.read_text());out=[]
for feature in g['features']:
    code=feature['properties']['STUSAB'];geometry=feature['geometry']
    if not geometry: raise ValueError('State geometry unavailable')
    coords=geometry['coordinates'];rings=[r for poly in coords for r in poly] if geometry['type']=='MultiPolygon' else coords
    if code not in ['AK','HI','PR']: project=lambda x,y:((x+125)*12,(50-y)*19)
    elif code=='AK': project=lambda x,y:((x+180)*3,420+(72-y)*4)
    elif code=='HI': project=lambda x,y:(200+(x+161)*10,440+(23-y)*10)
    else: project=lambda x,y:(650+(x+68)*14,450+(19-y)*14)
    paths=[];points=[]
    for ring in rings:
        xy=[project(x,y) for x,y,*_ in ring if x<0]
        if not xy: continue
        points+=xy;paths.append('M'+'L'.join(f'{x:.1f},{y:.1f}' for x,y in xy)+'Z')
    if not points: continue
    x=(min(x for x,y in points)+max(x for x,y in points))/2;y=(min(y for x,y in points)+max(y for x,y in points))/2
    out.append({'code':code,'path':''.join(paths),'x':round(x,1),'y':round(y,1)})
if len(out)!=52: raise ValueError('Expected 50 states, DC and Puerto Rico')
pathlib.Path('src/stateBoundaries.json').write_text(json.dumps({'source':'https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_20m.zip','vintage':'2025','scale':'1:20,000,000','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'states':out},separators=(',',':')))
