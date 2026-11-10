"""Read-only, source-grain NOAA NCEI Storm Events index access.

No carrier-route, facility, insurer, H3, historical frequency, risk or loss
attribution is performed. Reported points are not complete storm footprints.
"""
import hashlib
import json
import pathlib
import re
import sqlite3

SOURCE_ID="NOAA_NCEI_STORM_EVENTS_V1"
SOURCE_VERSION=2025
STATUS="ACCEPTED_EVENT_SOURCE_INDEX"

def _sha(path):
    digest=hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1048576),b""):
            digest.update(chunk)
    return digest.hexdigest()

def _sidecars(path):
    source=pathlib.Path(path).resolve()
    return [pathlib.Path(str(source)+suffix) for suffix in ("-wal","-shm") if pathlib.Path(str(source)+suffix).exists()]

def _open(path):
    source=pathlib.Path(path).resolve()
    if not source.is_file():
        raise ValueError("NOAA source index is not installed")
    if _sidecars(source):
        raise ValueError("NOAA source index has mutable SQLite sidecar state")
    db=sqlite3.connect(f"{source.as_uri()}?mode=ro",uri=True,timeout=5)
    db.execute("PRAGMA query_only=ON")
    db.row_factory=sqlite3.Row
    return db

def _trusted_manifest(path,index_path):
    receipt=pathlib.Path(path).resolve()
    if not receipt.is_file():
        raise ValueError("Trusted NOAA acquisition manifest is not installed")
    try:
        external=json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError,UnicodeDecodeError,json.JSONDecodeError) as error:
        raise ValueError("Trusted NOAA acquisition manifest is invalid") from error
    expected=external.get("index_sha256")
    if (external.get("source_id")!=SOURCE_ID or external.get("year")!=SOURCE_VERSION
            or external.get("status")!="SOURCE_ACCEPTED_YEAR_GRAIN"
            or external.get("source_revision_stable") is not True
            or not re.fullmatch(r"[a-f0-9]{64}",str(expected or ""))
            or expected!=_sha(index_path)):
        raise ValueError("Trusted NOAA acquisition digest does not match installed index")
    return external,receipt

def acceptance(path,trusted_manifest=None):
    source=pathlib.Path(path).resolve()
    external=None
    manifest_path=None
    if trusted_manifest is not None:
        external,manifest_path=_trusted_manifest(trusted_manifest,source)
    with _open(source) as db:
        receipt=db.execute("SELECT value_json FROM source_receipt WHERE key='manifest'").fetchone()
        if receipt is None:
            raise ValueError("No embedded official-source manifest")
        m=json.loads(receipt["value_json"])
        if not (m.get("source_id")==SOURCE_ID
                and m.get("year")==SOURCE_VERSION
                and m.get("status")=="SOURCE_ACCEPTED_YEAR_GRAIN"
                and m.get("source_revision_stable") is True
                and m.get("carrier_route_attributed") is False
                and m.get("storm_footprint_intersection_verified") is False):
            raise ValueError("NOAA source cut failed publication, coverage or attribution acceptance")
        counts={}
        for kind,table in (("details","event_detail"),("locations","event_location"),("fatalities","event_fatality")):
            expected=m.get("tables",{}).get(kind,{})
            size=db.execute("SELECT count(*) FROM "+table).fetchone()[0]
            if (size<0 or size!=expected.get("raw_rows")
                    or size!=expected.get("indexed_rows")
                    or size!=expected.get("accepted_rows")
                    or expected.get("rejected_rows")!=0):
                raise ValueError(kind+" NOAA publisher counts do not match installed index")
            file=m.get("files",{}).get(kind,{})
            if (file.get("origin_verified") is not True
                    or not re.fullmatch(r"[a-f0-9]{64}",str(file.get("sha256") or ""))
                    or not str(file.get("url") or "").startswith("https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/")):
                raise ValueError("NOAA publisher bytes are not provenance verified: "+kind)
            counts[kind]=size
        if counts["details"]<5000:
            raise ValueError("NOAA 2025 source index has incomplete event universe")
        orphans=db.execute("SELECT count(*) FROM event_fatality WHERE linked_detail=0").fetchone()[0]
        if orphans!=m.get("unmatched_fatality_event_ids"):
            raise ValueError("Unmatched fatality source evidence was changed")
        orphan_locs=db.execute("SELECT count(*) FROM event_location WHERE linked_detail=0").fetchone()[0]
        if orphan_locs!=m.get("unmatched_location_event_ids"):
            raise ValueError("Unmatched location source evidence was changed")
        if external is not None:
            for key in ("tables","files","unmatched_location_event_ids","unmatched_fatality_event_ids",
                        "missing_coordinates","invalid_coordinates","source_revision_stable"):
                if external.get(key)!=m.get(key):
                    raise ValueError("Trusted NOAA acquisition manifest differs from embedded receipt: "+key)
        check=db.execute("PRAGMA quick_check").fetchone()[0]
        if check!="ok":
            raise ValueError("NOAA source SQLite integrity check failed")
        return {
            "status":STATUS,"source_id":SOURCE_ID,"year":SOURCE_VERSION,
            "source_status":"SOURCE_ACCEPTED_YEAR_GRAIN",
            "table_counts":counts,
            "unmatched_location_event_ids":orphan_locs,
            "unmatched_fatality_event_ids":orphans,
            "missing_coordinates":m.get("missing_coordinates"),
            "original_urls":{kind:m["files"][kind]["url"] for kind in counts},
            "original_sha256":{kind:m["files"][kind]["sha256"] for kind in counts},
            "source_revision_stable":True,
            "carrier_route_attribution":"NOT_ESTABLISHED",
            "reported_point_not_storm_footprint":True,
            "insurer_loss_attribution":"NOT_ESTABLISHED",
            "trusted_index_sha256":external.get("index_sha256") if external else None,
            "trusted_manifest_sha256":_sha(manifest_path) if manifest_path else None,
        }

def event(path,event_id):
    if not isinstance(event_id,str) or not re.fullmatch(r"[1-9][0-9]{0,12}",event_id):
        raise ValueError("Positive numeric NCEI EVENT_ID required")
    with _open(path) as db:
        row=db.execute(
            "SELECT event_id,episode_id,source_year,state,event_type,begin_time,end_time,"
            "cz_name,state_fips,cz_fips,damage_property_raw,damage_crops_raw,"
            "begin_lat,begin_lon,begin_coord_valid FROM event_detail WHERE event_id=?",
            (int(event_id),)).fetchone()
        if row is None:
            return {"status":"NOT_FOUND","event_id":event_id,"source_id":SOURCE_ID}
        point_total=db.execute("SELECT count(*) FROM event_location WHERE event_id=?",(int(event_id),)).fetchone()[0]
        points=[dict(x) for x in db.execute(
            "SELECT location_index,label,latitude,longitude,geo_status "
            "FROM event_location WHERE event_id=? ORDER BY location_index LIMIT 101",
            (int(event_id),))]
        death_count=db.execute("SELECT count(*) FROM event_fatality WHERE event_id=? AND linked_detail=1",
                               (int(event_id),)).fetchone()[0]
        return {"status":"SOURCE_EVENT_CONTEXT_ONLY",**dict(row),
                "locations":points[:100],"location_count":point_total,"locations_truncated":point_total>100,
                "source_fatality_rows":death_count,
                "location_interpretation":"Reported locations are points, not hazard extent or insured exposure.",
                "carrier_route_attribution":"NOT_ESTABLISHED","source_id":SOURCE_ID}

def locations(path,state,limit=200,offset=0):
    if not isinstance(state,str) or not re.fullmatch(r"[A-Z][A-Z .-]{1,78}[A-Z]",state):
        raise ValueError("Official uppercase full state name required")
    if not isinstance(limit,int) or not 1<=limit<=500:
        raise ValueError("limit must be 1..500")
    if not isinstance(offset,int) or not 0<=offset<=100000:
        raise ValueError("offset must be 0..100000")
    with _open(path) as db:
        count=db.execute(
            "SELECT count(*) FROM event_location l JOIN event_detail d ON d.event_id=l.event_id "
            "WHERE d.state=? AND l.geo_status='PUBLISHED_POINT'",(state,)).fetchone()[0]
        rows=[dict(x) for x in db.execute(
            "SELECT l.event_id,l.location_index,l.label,l.latitude,l.longitude,"
            "d.event_type,d.state,d.begin_time "
            "FROM event_location l JOIN event_detail d ON d.event_id=l.event_id "
            "WHERE d.state=? AND l.geo_status='PUBLISHED_POINT' "
            "ORDER BY l.event_id,l.location_index LIMIT ? OFFSET ?",
            (state,limit,offset))]
    return {"status":"SOURCE_REPORTED_POINTS","source_id":SOURCE_ID,
            "year":SOURCE_VERSION,"state":state,"total_reported_points":count,
            "returned_points":len(rows),"offset":offset,"limit":limit,
            "partial":offset+len(rows)<count,"items":rows,
            "reported_points_not_hazard_footprints":True,
            "carrier_route_attribution":"NOT_ESTABLISHED",
            "insurer_loss_attribution":"NOT_ESTABLISHED"}
