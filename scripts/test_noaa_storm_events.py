"""NOAA Storm Events source ingestion tests use wholly synthetic fixtures."""
import csv
import gzip
import io
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

from noaa_storm_events_ingest import build, catalog, sha, coordinate, fetch, KINDS

DETAIL_HEADER = ["EVENT_ID","EPISODE_ID","YEAR","STATE","EVENT_TYPE",
                 "BEGIN_DATE_TIME","END_DATE_TIME","CZ_NAME","STATE_FIPS","CZ_FIPS",
                 "DAMAGE_PROPERTY","DAMAGE_CROPS","BEGIN_LAT","BEGIN_LON"]
LOCATION_HEADER = ["EVENT_ID","LOCATION_INDEX","LATITUDE","LONGITUDE","LOCATION"]
FATAL_HEADER = ["EVENT_ID","FATALITY_ID"]
ROWS = {
    "details":[
        ["101","1001","2025","TEXAS","Flash Flood","01-JUN-25 05:20:00","01-JUN-25 06:20:00","HARRIS","48","201","20K","0K","29.8","-95.5"],
        ["102","1002","2025","MAINE","Winter Storm","17-DEC-25 11:00:00","17-DEC-25 13:20:00","YORK","23","031","","","", ""],
        ["103","1002","2025","ALASKA","High Wind","19-DEC-25 08:30:00","19-DEC-25 08:40:00","NORTH SLOPE","02","185","","","bad","-150.5"],
    ],
    "locations":[
        ["101","1","29.8","-95.5","HOUSTON"],
        ["102","1","","","NO COORD"],
        ["103","1","0","0","BAD COORD"],
        ["9999","1","29.6","-95.3","UNMATCHED"],
    ],
    "fatalities":[["101","140001"],["9999","149999"]],
}
HEADERS = {"details":DETAIL_HEADER,"locations":LOCATION_HEADER,"fatalities":FATAL_HEADER}

def make_sources(root,year=2025,records=None):
    sources={}
    for kind in KINDS:
        archive=root/f"StormEvents_{kind}-ftp_v1.0_d{year}_c20260819.csv.gz"
        with gzip.open(archive,"wt",encoding="utf-8",newline="") as output:
            writer=csv.writer(output,lineterminator="\n")
            writer.writerow(HEADERS[kind])
            writer.writerows((records or ROWS)[kind])
        sources[kind]=archive
    return sources

class NOAAEventsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        self.files=make_sources(self.root)
    def tearDown(self):
        self.temp.cleanup()

    def test_catalog_selects_latest_revision_for_each_family(self):
        names=["StormEvents_details-ftp_v1.0_d2025_c20260505.csv.gz",
               *[p.name for p in self.files.values()],
               "StormEvents_details-ftp_v1.0_d2024_c20261001.csv.gz"]
        html=("<html>"+''.join('<a href="'+n+'">'+n+'</a>' for n in names)+"</html>").encode()
        picked=catalog(html,2025)
        self.assertEqual(picked["details"],self.files["details"].name)
        self.assertEqual(len(picked),3)
        with self.assertRaisesRegex(ValueError,"absent"):
            catalog(html,2023)

    def test_offline_replay_keeps_raw_tables_and_missing_geometry(self):
        release=self.root/"ncei-pilot"
        manifest=build(2025,release,self.files,min_details=3)
        self.assertEqual(manifest["status"],"EXPLICIT_ARCHIVES_VERIFIED_SCHEMA_ONLY")
        self.assertFalse(manifest["source_revision_stable"])
        self.assertFalse(manifest["carrier_route_attributed"])
        self.assertEqual(manifest["tables"]["details"]["raw_rows"],3)
        self.assertEqual(manifest["tables"]["locations"]["indexed_rows"],4)
        self.assertEqual(manifest["tables"]["fatalities"]["indexed_rows"],2)
        self.assertEqual(manifest["unmatched_location_event_ids"],1)
        self.assertEqual(manifest["unmatched_fatality_event_ids"],1)
        self.assertEqual(manifest["missing_coordinates"],2)
        self.assertEqual(manifest["invalid_coordinates"],2)
        for kind in KINDS:
            entry=manifest["files"][kind]
            self.assertFalse(entry["origin_verified"])
            self.assertIsNone(entry["url"])
            self.assertEqual(entry["sha256"],sha(self.files[kind]))
        db=sqlite3.connect(release/"events.sqlite")
        self.assertEqual(db.execute("SELECT count(*) FROM event_detail").fetchone()[0],3)
        self.assertEqual(db.execute("SELECT count(*) FROM event_location").fetchone()[0],4)
        self.assertEqual(db.execute("SELECT count(*) FROM event_fatality").fetchone()[0],2)
        self.assertEqual(db.execute("SELECT count(*) FROM event_location WHERE geo_status='PUBLISHED_POINT'").fetchone()[0],2)
        self.assertEqual(db.execute("SELECT count(*) FROM event_location WHERE linked_detail=0").fetchone()[0],1)
        self.assertEqual(db.execute("SELECT count(*) FROM event_fatality WHERE linked_detail=0").fetchone()[0],1)
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        internal=json.loads(db.execute("SELECT value_json FROM source_receipt WHERE key='manifest'").fetchone()[0])
        self.assertEqual(internal["status"],"EXPLICIT_ARCHIVES_VERIFIED_SCHEMA_ONLY")
        db.close()
        with self.assertRaises(FileExistsError):
            build(2025,release,self.files,min_details=3)

    def test_duplicate_detail_fails_closed(self):
        rows={key:list(value) for key,value in ROWS.items()}
        rows["details"]=[*rows["details"],rows["details"][0]]
        make_sources(self.root,records=rows)
        release=self.root/"rejected"
        with self.assertRaisesRegex(ValueError,"Duplicate NOAA"):
            build(2025,release,self.files,min_details=3)
        manifest=json.loads((release/"manifest.json").read_text())
        self.assertEqual(manifest["status"],"REJECTED")
        self.assertFalse((release/"events.sqlite").exists())

    def test_source_year_and_minimum_rows_gate(self):
        rows={key:list(value) for key,value in ROWS.items()}
        rows["details"]=[[v if i!=2 else "2024" for i,v in enumerate(row)]
                         for row in rows["details"]]
        make_sources(self.root,records=rows)
        with self.assertRaisesRegex(ValueError,"annual source file"):
            build(2025,self.root/"wrong-year",self.files,min_details=3)
        make_sources(self.root)
        with self.assertRaisesRegex(ValueError,"incomplete"):
            build(2025,self.root/"not-complete",self.files,min_details=4)

    def test_missing_required_columns_and_invalid_key(self):
        path=self.files["locations"]
        with gzip.open(path,"wt",encoding="utf-8") as output:
            output.write("EVENT_ID,LATITUDE,LONGITUDE\n101,29.8,-95.5\n")
        with self.assertRaisesRegex(ValueError,"Unrecognized NOAA locations"):
            build(2025,self.root/"bad-header",self.files,min_details=3)

    def test_orphan_metrics_count_distinct_event_ids_not_child_rows(self):
        rows={key:list(value) for key,value in ROWS.items()}
        rows["locations"]=[*rows["locations"],["9999","2","29.7","-95.2","SECOND UNMATCHED ROW"]]
        rows["fatalities"]=[*rows["fatalities"],["9999","150000"]]
        files=make_sources(self.root,records=rows)
        manifest=build(2025,self.root/"distinct-orphans",files,min_details=3)
        self.assertEqual(manifest["tables"]["locations"]["raw_rows"],5)
        self.assertEqual(manifest["tables"]["fatalities"]["raw_rows"],3)
        self.assertEqual(manifest["unmatched_location_event_ids"],1)
        self.assertEqual(manifest["unmatched_fatality_event_ids"],1)

    def test_same_host_redirect_to_different_noaa_file_is_rejected(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*args): self.close()
            def geturl(self): return "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_locations-ftp_v1.0_d2024_c20260819.csv.gz"
        expected="https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_locations-ftp_v1.0_d2025_c20260819.csv.gz"
        with mock.patch("urllib.request.urlopen",return_value=Response(b"not-used")):
            with self.assertRaisesRegex(ValueError,"changed approved source path"):
                fetch(expected,self.root/"redirect.gz",1000)

    def test_coordinates_do_not_invent_position(self):
        self.assertEqual(coordinate("","-95.5"),(None,None,"NOT_REPORTED"))
        self.assertEqual(coordinate("0","0"),(None,None,"INVALID"))
        self.assertEqual(coordinate("99","-95"),(None,None,"INVALID"))
        self.assertEqual(coordinate("NaN","-95.5"),(None,None,"INVALID"))
        self.assertEqual(coordinate("29.8","Infinity"),(None,None,"INVALID"))
        self.assertEqual(coordinate("-Infinity","-95.5"),(None,None,"INVALID"))
        self.assertEqual(coordinate("29.8","-95.5"),(29.8,-95.5,"PUBLISHED_POINT"))

if __name__=="__main__":unittest.main()
