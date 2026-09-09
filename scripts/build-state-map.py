"""Build local state symbols from the official Census 2025 20M boundary response."""
import json, pathlib, hashlib, zipfile, struct
# Download this public artifact separately, then rebuild offline with no dependencies.
# https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_20m.zip
p=pathlib.Path('outputs/census-state-20m.zip');z=zipfile.ZipFile(p)
dbf=z.read(next(n for n in z.namelist() if n.endswith('.dbf')))
shp=z.read(next(n for n in z.namelist() if n.endswith('.shp')))
n=struct.unpack_from('<I',dbf,4)[0];header,record=struct.unpack_from('<HH',dbf,8);fields=[];offset=1
for i in range(32,header-1,32):
    name=dbf[i:i+11].split(b'\0')[0].decode();length=dbf[i+16];fields.append((name,offset,length));offset+=length
field=next(f for f in fields if f[0]=='STUSPS');position=100;features=[]
for j in range(n):
    length=struct.unpack_from('>I',shp,position+4)[0]*2;body=shp[position+8:position+8+length];position+=8+length
    if struct.unpack_from('<I',body)[0]!=5:raise ValueError('Expected Polygon geometry')
    parts_count,point_count=struct.unpack_from('<II',body,36)
    parts=list(struct.unpack_from('<'+'I'*parts_count,body,44))+[point_count]
    points=[struct.unpack_from('<dd',body,44+4*parts_count+16*k) for k in range(point_count)]
    code=dbf[header+j*record+field[1]:header+j*record+field[1]+field[2]].decode().strip()
    features.append({'properties':{'STUSAB':code},'geometry':{'type':'Polygon','coordinates':[points[parts[k]:parts[k+1]] for k in range(parts_count)]}})
g={'features':features};out=[]
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
