"""NOAA NCEI Storm Events year-cut acquisition, original-byte provenance and source index.

Storm Events observations are public reports, NOT known carrier routes or insured losses.
Three annual source tables (details, locations, fatalities) are retained separately.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.parse
import urllib.request

BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
KINDS = ("details", "locations", "fatalities")
PATTERN = re.compile(
    r"^StormEvents_(details|locations|fatalities)-ftp_v1\.0_d([0-9]{4})_c([0-9]{8})\.csv\.gz$")
MAX_COMPRESSED_BYTES = 55_000_000
MAX_SOURCE_ROWS = 200_000
MIN_DETAILS_ROWS = 5_000
COLUMNS = {
    "details": {"EVENT_ID", "EPISODE_ID", "YEAR", "STATE", "EVENT_TYPE", "BEGIN_DATE_TIME", "END_DATE_TIME"},
    "locations": {"EVENT_ID", "LOCATION_INDEX", "LATITUDE", "LONGITUDE"},
    "fatalities": {"EVENT_ID", "FATALITY_ID"},
}
SCHEMA = """
CREATE TABLE event_detail(
    event_id INTEGER PRIMARY KEY, episode_id INTEGER, source_year INTEGER NOT NULL,
    state TEXT, event_type TEXT, begin_time TEXT, end_time TEXT,
    cz_name TEXT, state_fips TEXT, cz_fips TEXT,
    damage_property_raw TEXT, damage_crops_raw TEXT, begin_lat REAL, begin_lon REAL,
    begin_coord_valid INTEGER NOT NULL
);
CREATE TABLE event_location(
    event_id INTEGER NOT NULL, location_index INTEGER NOT NULL,
    label TEXT, latitude REAL, longitude REAL,
    geo_status TEXT NOT NULL, linked_detail INTEGER NOT NULL,
    PRIMARY KEY(event_id,location_index)
);
CREATE TABLE event_fatality(
    event_id INTEGER NOT NULL, fatality_id INTEGER NOT NULL,
    linked_detail INTEGER NOT NULL,
    PRIMARY KEY(event_id,fatality_id)
);
CREATE TABLE source_receipt(key TEXT PRIMARY KEY,value_json TEXT NOT NULL);
CREATE INDEX event_detail_state ON event_detail(state,event_type);
CREATE INDEX event_location_detail ON event_location(event_id);
CREATE INDEX event_fatality_detail ON event_fatality(event_id);
"""

def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()

class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

def catalog(html: bytes, year: int) -> dict:
    if not 1950 <= year <= dt.datetime.now(dt.timezone.utc).year:
        raise ValueError("Outside NOAA supported annual range")
    try:
        parser=Anchors()
        parser.feed(html.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("NCEI catalog is not UTF-8") from error
    found={kind:[] for kind in KINDS}
    for link in parser.links:
        name=urllib.parse.urlsplit(link).path.split("/")[-1]
        match=PATTERN.fullmatch(name)
        if match and int(match.group(2))==year:
            found[match.group(1)].append((match.group(3),name))
    result={}
    for kind, candidates in found.items():
        if not candidates:
            raise ValueError(f"NOAA {kind} publication absent for year {year}")
        sorted_files=sorted(candidates)
        if len(set(name for _,name in sorted_files)) != len(sorted_files):
            raise ValueError("Duplicate NOAA index listing entries")
        result[kind]=sorted_files[-1][1]
    return result

def fetch(url:str,dest:Path,max_bytes:int):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!="https" or parsed.hostname!="www.ncei.noaa.gov" or not parsed.path.startswith("/pub/data/swdi/stormevents/csvfiles/"):
        raise ValueError("Unapproved NOAA source URL")
    request=urllib.request.Request(url,headers={"User-Agent":"Transport3r-NCEI-Source-Audit/1.0","Accept":"*/*"})
    pending=dest.with_suffix(dest.suffix+".partial")
    size=0
    with urllib.request.urlopen(request,timeout=100) as response, pending.open("xb") as out:
        final=urllib.parse.urlsplit(response.geturl())
        if final.scheme!="https" or final.hostname!="www.ncei.noaa.gov":
            raise ValueError("NOAA redirect left approved source host")
        while block:=response.read(1048576):
            size+=len(block)
            if size>max_bytes:
                raise ValueError("NOAA response exceeded bounded maximum")
            out.write(block)
    os.replace(pending,dest)
    return {"url":url,"resolved_url":response.geturl(),"sha256":sha(dest),"downloaded_bytes":size}

def number(value,field,allow_blank=False):
    v=str(value or "").strip()
    if not v and allow_blank:
        return None
    if not v.isascii() or not v.isdigit():
        raise ValueError("Invalid "+field+" source identifier")
    return int(v)

def coordinate(lat,lon):
    a,b=str(lat or "").strip(),str(lon or "").strip()
    if not a or not b:
        return None,None,"NOT_REPORTED"
    try:
        x,y=float(a),float(b)
    except ValueError:
        return None,None,"INVALID"
    if not (-90<=x<=90 and -180<=y<=180) or (x==0 and y==0):
        return None,None,"INVALID"
    # NOAA may report points outside CONUS (AK, HI, marine); keep valid worldwide coordinates.
    return x,y,"PUBLISHED_POINT"

def source_rows(gz_path:Path,kind:str):
    # Stream decompression; no arbitrary byte substitution or silent CSV truncation.
    with gzip.open(gz_path,"rt",encoding="utf-8-sig",errors="strict",newline="") as stream:
        csv.field_size_limit(1_500_000)
        reader=csv.DictReader(stream,strict=True)
        header=reader.fieldnames or []
        if len(header)!=len(set(header)) or not COLUMNS[kind].issubset(set(header)):
            raise ValueError("Unrecognized NOAA "+kind+" CSV contract "+str(sorted(COLUMNS[kind]-set(header))))
        for row_number,row in enumerate(reader,1):
            if row_number>MAX_SOURCE_ROWS:
                raise ValueError("NOAA year exceeds bounded parsed row count")
            if None in row:
                raise ValueError(f"NOAA {kind} row {row_number} has excess fields")
            yield row_number,row

def build(year:int,output:Path,archives:dict|None=None,min_details:int=MIN_DETAILS_ROWS):
    if not 1950 <= year <= dt.datetime.now(dt.timezone.utc).year:
        raise ValueError("NOAA annual source year outside allowed range")
    if output.exists():
        raise FileExistsError("Use a new immutable release directory")
    if not 1<=min_details<=MAX_SOURCE_ROWS:
        raise ValueError("Invalid minimum NOAA details rows")
    output.mkdir(parents=True)
    manifest={"source_id":"NOAA_NCEI_STORM_EVENTS_V1","year":year,
              "source_catalog_url":BASE,"ingested_at":utcnow(),"status":"ACQUISITION_PENDING",
              "private_insurer_data":False,"carrier_route_attributed":False,
              "storm_footprint_intersection_verified":False,
              "files":{},"tables":{},"source_revision_stable":False}
    db=None
    try:
        raw=output/"source"
        raw.mkdir()
        if archives is None:
            idx=raw/"directory.html"
            manifest["catalog"]=fetch(BASE,idx,3_000_000)
            names=catalog(idx.read_bytes(),year)
            manifest["catalog"]["selected_filenames"]=names
        else:
            names={kind:Path(archives[kind]).name for kind in KINDS}
            if any(not PATTERN.fullmatch(v) or int(PATTERN.fullmatch(v).group(2))!=year for v in names.values()):
                raise ValueError("Explicit source filenames must identify requested NOAA year/version")
            manifest["catalog"]={"mode":"EXPLICIT_ARCHIVES_UNVERIFIED_ORIGIN"}
        for kind in KINDS:
            name=names[kind]
            destination=raw/name
            if archives:
                source=Path(archives[kind]).resolve()
                if not source.is_file():
                    raise FileNotFoundError("Explicit source missing: "+str(source))
                import shutil
                shutil.copyfile(source,destination)
                file_receipt={"url":None,"origin_verified":False,"downloaded_bytes":destination.stat().st_size,"sha256":sha(destination)}
            else:
                file_receipt=fetch(BASE+name,destination,MAX_COMPRESSED_BYTES)
                file_receipt["origin_verified"]=True
            file_receipt["filename"]=name
            manifest["files"][kind]=file_receipt
        pending=output/"events.partial.sqlite"
        db=sqlite3.connect(pending)
        db.executescript(SCHEMA)
        loaded_ids=set()
        counts={kind:0 for kind in KINDS}
        invalid_coords=0
        missing_coords=0
        orphan_locations=0
        orphan_fatalities=0
        # Events establish the exact key universe; no association by approximate company name.
        for n,row in source_rows(raw/names["details"],"details"):
            event_id=number(row["EVENT_ID"],"EVENT_ID")
            if event_id in loaded_ids:
                raise ValueError("Duplicate NOAA detail EVENT_ID: "+str(event_id))
            loaded_ids.add(event_id)
            if number(row["YEAR"],"YEAR")!=year:
                raise ValueError("Detail YEAR does not match annual source file")
            a,b,state=coordinate(row.get("BEGIN_LAT"),row.get("BEGIN_LON"))
            if state=="INVALID":invalid_coords+=1
            if state=="NOT_REPORTED":missing_coords+=1
            db.execute("INSERT INTO event_detail VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (event_id,number(row.get("EPISODE_ID"),"EPISODE_ID",True),year,
                 row["STATE"],row["EVENT_TYPE"],row["BEGIN_DATE_TIME"],row["END_DATE_TIME"],
                 row.get("CZ_NAME"),row.get("STATE_FIPS"),row.get("CZ_FIPS"),
                 row.get("DAMAGE_PROPERTY"),row.get("DAMAGE_CROPS"),a,b,int(state=="PUBLISHED_POINT")))
            counts["details"]+=1
        if counts["details"]<min_details:
            raise ValueError(f"NOAA event universe incomplete: {counts['details']} expected >= {min_details}")
        for n,row in source_rows(raw/names["locations"],"locations"):
            event_id=number(row["EVENT_ID"],"EVENT_ID")
            loc_id=number(row["LOCATION_INDEX"],"LOCATION_INDEX")
            a,b,state=coordinate(row["LATITUDE"],row["LONGITUDE"])
            if state=="INVALID":invalid_coords+=1
            if state=="NOT_REPORTED":missing_coords+=1
            orphan=int(event_id not in loaded_ids)
            orphan_locations+=orphan
            db.execute("INSERT INTO event_location VALUES (?,?,?,?,?,?)",
                (event_id,loc_id,row.get("LOCATION"),a,b,state,int(not orphan)))
            counts["locations"]+=1
        for n,row in source_rows(raw/names["fatalities"],"fatalities"):
            event_id=number(row["EVENT_ID"],"EVENT_ID")
            fatality_id=number(row["FATALITY_ID"],"FATALITY_ID")
            orphan=int(event_id not in loaded_ids)
            orphan_fatalities+=orphan
            db.execute("INSERT INTO event_fatality VALUES (?,?,?)",
                       (event_id,fatality_id,int(not orphan)))
            counts["fatalities"]+=1
        manifest["tables"]={kind:{"raw_rows":cnt,"accepted_rows":cnt,"rejected_rows":0,"indexed_rows":cnt}
                            for kind,cnt in counts.items()}
        manifest.update(invalid_coordinates=invalid_coords,missing_coordinates=missing_coords,
                        unmatched_location_event_ids=orphan_locations,unmatched_fatality_event_ids=orphan_fatalities)
        manifest["source_revision_stable"]=False
        if not archives:
            # Fail closed if any revision advanced while the three source files were downloading.
            fresh=raw/"directory-after.html"
            manifest["catalog_after"]=fetch(BASE,fresh,3_000_000)
            latest=catalog(fresh.read_bytes(),year)
            if latest!=names:
                raise ValueError("NOAA annual file revisions changed during acquisition")
            manifest["source_revision_stable"]=True
        manifest["status"]="SOURCE_ACCEPTED_YEAR_GRAIN" if archives is None else "EXPLICIT_ARCHIVES_VERIFIED_SCHEMA_ONLY"
        with db:
            db.execute("INSERT INTO source_receipt VALUES (?,?)",("manifest",json.dumps(manifest,sort_keys=True)))
        check=db.execute("PRAGMA integrity_check").fetchone()[0]
        if check!="ok":
            raise ValueError("SQLite index integrity check failed")
        db.close();db=None
        os.replace(pending,output/"events.sqlite")
        manifest["index_sha256"]=sha(output/"events.sqlite")
    except Exception as error:
        manifest["status"]="REJECTED"
        manifest["error"]=type(error).__name__+": "+str(error)
        (output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        if db is not None:db.close()
        raise
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--year",type=int,default=2025)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--min-details",type=int,default=MIN_DETAILS_ROWS)
    args=p.parse_args()
    try:
        manifest=build(args.year,args.output,min_details=args.min_details)
        print(json.dumps({k:v for k,v in manifest.items() if k not in ("catalog","catalog_after")},indent=2))
    except Exception as e:
        print(f"NOAA Storm Events acquisition blocked: {e}",file=sys.stderr)
        sys.exit(1)
