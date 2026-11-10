"""API-level tests use synthetic NOAA records; never publish fixture data as official."""
import json
import pathlib
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from noaa_storm_events_ingest import build, BASE, KINDS
from noaa_storm_index import acceptance, event, locations
from test_noaa_storm_events import ROWS, make_sources
from test_nationwide_evidence import HAS_DUCKDB, NationwideEvidence

class NOAAIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        synthetic={k:list(v) for k,v in ROWS.items()}
        # >=5,000 events exercise real-world release completeness without bundling
        # or falsely attributing any real NOAA source records to the fixture.
        synthetic["details"]=[
            [str(i),"1000","2025","TEXAS","Flash Flood","01-JUN-25 00:00:00","01-JUN-25 00:30:00",
             "TEST COUNTY","48","201","0","0","29.8","-95.5"]
            for i in range(10001,15002)
        ]
        synthetic["locations"]=[
            [str(i),"1","29.8","-95.5","SIMULATED"] for i in range(10001,10005)
        ]+ [["9999","1","0","0","ORPHAN"]]
        synthetic["fatalities"]=[["10001","14999"],["9999","99999"]]
        self.files=make_sources(self.root,records=synthetic)
        self.release=self.root/"release"
        build(2025,self.release,self.files,min_details=5000)
        self.path=self.release/"events.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def simulated_official_receipt(self):
        """Only for tests; patches provenance flags in a local fake index and external receipt."""
        from noaa_storm_events_ingest import sha
        with sqlite3.connect(self.path) as db:
            data=json.loads(db.execute("SELECT value_json FROM source_receipt WHERE key='manifest'").fetchone()[0])
            data["status"]="SOURCE_ACCEPTED_YEAR_GRAIN"
            data["source_revision_stable"]=True
            for kind in KINDS:
                data["files"][kind]["origin_verified"]=True
                data["files"][kind]["url"]=BASE+data["files"][kind]["filename"]
            db.execute("UPDATE source_receipt SET value_json=? WHERE key='manifest'",(json.dumps(data),))
        external={**data,"index_sha256":sha(self.path)}
        (self.release/"manifest.json").write_text(json.dumps(external,indent=2)+"\n",encoding="utf-8")

    def test_unsigned_fixture_cannot_be_used_as_accepted_official_release(self):
        with self.assertRaisesRegex(ValueError,"publication"):
            acceptance(self.path)
        # Source-grain queries still work locally but public API refuses to install.
        value=event(self.path,"10001")
        self.assertEqual(value["status"],"SOURCE_EVENT_CONTEXT_ONLY")
        self.assertEqual(value["source_fatality_rows"],1)
        self.assertEqual(value["carrier_route_attribution"],"NOT_ESTABLISHED")

    def test_public_source_provenance_and_reported_point_pagination(self):
        self.simulated_official_receipt()
        report=acceptance(self.path)
        self.assertEqual(report["status"],"ACCEPTED_EVENT_SOURCE_INDEX")
        self.assertEqual(report["table_counts"]["details"],5001)
        self.assertEqual(report["unmatched_fatality_event_ids"],1)
        self.assertEqual(report["unmatched_location_event_ids"],1)
        self.assertTrue(report["reported_point_not_storm_footprint"])
        locs=locations(self.path,"TEXAS",limit=2)
        self.assertEqual(locs["total_reported_points"],4)
        self.assertEqual(locs["returned_points"],2)
        self.assertTrue(locs["partial"])
        self.assertEqual(locations(self.path,"TEXAS",limit=2,offset=2)["returned_points"],2)
        self.assertEqual(locations(self.path,"MAINE")["total_reported_points"],0)
        self.assertEqual(event(self.path,"10001")["source_fatality_rows"],1)
        self.assertNotIn("carrier_risk",event(self.path,"10001"))
        self.assertEqual(event(self.path,"99999999")["status"],"NOT_FOUND")

    def test_trusted_external_digest_is_required_for_public_installation(self):
        self.simulated_official_receipt()
        manifest=self.release/"manifest.json"
        report=acceptance(self.path,manifest)
        self.assertRegex(report["trusted_index_sha256"],r"^[a-f0-9]{64}$")
        altered=json.loads(manifest.read_text())
        altered["index_sha256"]="0"*64
        bad=self.release/"bad-manifest.json"
        bad.write_text(json.dumps(altered))
        with self.assertRaisesRegex(ValueError,"digest"):
            acceptance(self.path,bad)

    def test_wal_or_shm_sidecars_are_rejected_before_queries(self):
        self.simulated_official_receipt()
        manifest=self.release/"manifest.json"
        wal=pathlib.Path(str(self.path)+"-wal")
        wal.write_bytes(b"synthetic mutable sidecar")
        try:
            with self.assertRaisesRegex(ValueError,"sidecar"):
                acceptance(self.path,manifest)
        finally:
            wal.unlink(missing_ok=True)

    def test_invalid_identifiers_and_query_budgets(self):
        for raw in ["","0","1 OR 1=1","-2","101.0","1"*14]:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError,"EVENT_ID"):
                event(self.path,raw)
        for state,limit,offset in [("TX",0,0),("TEXAS",0,0),("TEXAS",501,0),
                                   ("TEXAS",50,-1),("TEXAS",50,100001),
                                   ("TEXAS'; DROP TABLE x",20,0)]:
            with self.subTest(state=state,limit=limit,offset=offset),self.assertRaises(ValueError):
                locations(self.path,state,limit,offset)

@unittest.skipUnless(HAS_DUCKDB,"DuckDB required for full public-source HTTP smoke")
class NOAAHTTPTests(unittest.TestCase):
    def setUp(self):
        NOAAIndexTests.setUp(self)
        self.warehouse=self.root/"warehouse.duckdb"
        NationwideEvidence.fixture(self,self.warehouse)
        NOAAIndexTests.simulated_official_receipt(self)
        from evidence_api import EvidenceServer,Handler
        self.EvidenceServer=EvidenceServer
        self.Handler=Handler

    def tearDown(self):
        NOAAIndexTests.tearDown(self)

    def launch(self,with_index=True):
        server=self.EvidenceServer(("127.0.0.1",0),self.Handler,self.warehouse,
                                   "https://insurer.example",
                                   noaa_index=self.path if with_index else None,
                                   noaa_manifest=(self.release/"manifest.json") if with_index else None)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join()))
        return "http://127.0.0.1:"+str(server.server_port)

    def get(self,url):
        with urllib.request.urlopen(url,timeout=7) as response:
            return response.status,json.load(response),response.headers

    def test_noaa_optional_source_endpoints_do_not_change_carrier_identity(self):
        base=self.launch()
        code,health,headers=self.get(base+"/healthz")
        self.assertEqual(health["noaa_storm_source"],"ACCEPTED_EVENT_SOURCE_INDEX")
        self.assertEqual(headers["Access-Control-Allow-Origin"],"https://insurer.example")
        code,status,_=self.get(base+"/v1/geography/noaa/status")
        self.assertEqual(status["table_counts"]["details"],5001)
        self.assertEqual(code,200)
        code,record,_=self.get(base+"/v1/geography/noaa/events/10001")
        self.assertEqual(record["carrier_route_attribution"],"NOT_ESTABLISHED")
        self.assertEqual(record["source_fatality_rows"],1)
        self.assertNotIn("risk_score",record)
        route=base+"/v1/geography/noaa/locations?state=TEXAS&limit=2"
        _,rows,_=self.get(route)
        self.assertTrue(rows["partial"])
        self.assertEqual(rows["returned_points"],2)
        # Installing NOAA source evidence must not bypass the independent FMCSA warehouse audit gate.
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(base+"/v1/carriers/3706/evidence",timeout=7)
        self.assertEqual(raised.exception.code,503)
        self.assertEqual(json.load(raised.exception)["status"],"NOT_AUDITED")
        for endpoint,expected in [
            ("/v1/geography/noaa/events/invalid",400),
            ("/v1/geography/noaa/events/99999999",404),
            ("/v1/geography/noaa/locations?state=TEXAS&limit=1000",400),
            ("/v1/geography/noaa/locations?state=TX&limit=0",400),
        ]:
            with self.subTest(endpoint=endpoint),self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(base+endpoint,timeout=7)
            self.assertEqual(raised.exception.code,expected)

    def test_installed_noaa_index_mutation_fails_closed(self):
        base=self.launch()
        code,status,_=self.get(base+"/v1/geography/noaa/status")
        self.assertEqual(code,200)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE source_receipt SET value_json=value_json WHERE key='manifest'")
            db.execute("CREATE TABLE mutation_probe(value INTEGER)")
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(base+"/v1/geography/noaa/status",timeout=7)
        self.assertEqual(raised.exception.code,503)
        value=json.load(raised.exception)
        self.assertEqual(value["status"],"SOURCE_CHANGED")
        self.assertEqual(value["carrier_route_attribution"],"NOT_ESTABLISHED")
        with self.assertRaises(urllib.error.HTTPError) as health_error:
            urllib.request.urlopen(base+"/healthz",timeout=7)
        self.assertEqual(health_error.exception.code,503)
        health=json.load(health_error.exception)
        self.assertEqual(health["status"],"degraded")
        self.assertEqual(health["noaa_storm_source"],"SOURCE_CHANGED")
        self.assertFalse(health["release_ready"])

    def test_trusted_manifest_mutation_after_startup_fails_closed(self):
        base=self.launch()
        _,status,_=self.get(base+"/v1/geography/noaa/status")
        self.assertEqual(status["status"],"ACCEPTED_EVENT_SOURCE_INDEX")
        manifest=self.release/"manifest.json"
        data=json.loads(manifest.read_text())
        data["test_mutation"]=True
        manifest.write_text(json.dumps(data))
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(base+"/v1/geography/noaa/status",timeout=7)
        self.assertEqual(raised.exception.code,503)
        self.assertEqual(json.load(raised.exception)["status"],"SOURCE_CHANGED")
        with self.assertRaises(urllib.error.HTTPError) as health_error:
            urllib.request.urlopen(base+"/healthz",timeout=7)
        self.assertEqual(health_error.exception.code,503)
        self.assertEqual(json.load(health_error.exception)["noaa_storm_source"],"SOURCE_CHANGED")

    def test_noaa_not_installed_stays_unavailable(self):
        base=self.launch(with_index=False)
        _,health,_=self.get(base+"/healthz")
        self.assertEqual(health["noaa_storm_source"],"NOT_INSTALLED")
        for endpoint in ["/v1/geography/noaa/status","/v1/geography/noaa/locations?state=TEXAS",
                         "/v1/geography/noaa/events/10001"]:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(base+endpoint,timeout=7)
            self.assertEqual(raised.exception.code,503)
            self.assertEqual(json.load(raised.exception)["status"],"NOT_INSTALLED")

if __name__=="__main__":unittest.main()
