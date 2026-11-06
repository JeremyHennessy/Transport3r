"""API-level validation of optional FEMA county NRI evidence path.

Test source pages are synthetic and are never evidence of a real insured risk.
"""
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from test_nri_county_index import source_response
from nri_county_ingest import build
from nri_county_index import install
from test_nationwide_evidence import NationwideEvidence, HAS_DUCKDB

@unittest.skipUnless(HAS_DUCKDB, 'DuckDB required for source+warehouse API test')
class NriApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        self.warehouse=self.root/'warehouse.duckdb'
        NationwideEvidence.fixture(self,self.warehouse)
        from evidence_api import EvidenceServer,Handler
        self.EvidenceServer=EvidenceServer
        self.Handler=Handler

    def tearDown(self):
        self.temp.cleanup()

    def start(self, index=None):
        server=self.EvidenceServer(('127.0.0.1',0),self.Handler,self.warehouse,
                                   'https://insurer.example',nri_index=index)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(),server.server_close(),thread.join()))
        return 'http://127.0.0.1:'+str(server.server_port)

    def fetch(self,url):
        with urllib.request.urlopen(url,timeout=10) as response:
            return response.status,json.load(response),response.headers

    def test_source_absence_is_not_a_clean_zero(self):
        base=self.start()
        code,health,_=self.fetch(base+'/healthz')
        self.assertEqual(code,200)
        self.assertEqual(health['nri_county_source'],'NOT_INSTALLED')
        for route in ['/v1/geography/nri/status','/v1/geography/nri/counties/01001']:
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base+route,timeout=10)
            self.assertEqual(err.exception.code,503)
            self.assertEqual(json.load(err.exception)['status'],'NOT_INSTALLED')
        _,carrier,_=self.fetch(base+'/v1/carriers/3706/evidence')
        self.assertEqual(carrier['carrier_rows'],2)

    def test_validated_index_serves_county_only_without_carrier_score(self):
        release=self.root/'release'
        with patch('nri_county_ingest._arcgis_json',side_effect=source_response):
            build(release,arcgis=True)
        path=self.root/'index.sqlite'
        install(release,path)
        base=self.start(path)
        code,status,headers=self.fetch(base+'/v1/geography/nri/status')
        self.assertEqual(code,200)
        self.assertEqual(status['county_rows'],3232)
        self.assertEqual(status['unknown_scores'],88)
        self.assertEqual(status['carrier_route_attribution'],'NOT_ESTABLISHED')
        self.assertEqual(headers['Access-Control-Allow-Origin'],'https://insurer.example')
        _,first,_=self.fetch(base+'/v1/geography/nri/counties/00001')
        self.assertEqual(first['score_status'],'INSUFFICIENT_DATA')
        self.assertIsNone(first['fema_nri_risk_score'])
        self.assertEqual(first['carrier_route_attribution'],'NOT_ESTABLISHED')
        _,rated,_=self.fetch(base+'/v1/geography/nri/counties/03000')
        self.assertEqual(rated['fema_nri_risk_score'],10.25)
        self.assertNotIn('carrier_risk',rated)
        for route,expected in [('/v1/geography/nri/counties/1%20OR%201=1',400),
                               ('/v1/geography/nri/counties/99999',404)]:
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base+route,timeout=10)
            self.assertEqual(err.exception.code,expected)
        code,health,_=self.fetch(base+'/healthz')
        self.assertEqual(health['nri_county_source'],'ACCEPTED_SOURCE_INDEX')

if __name__=='__main__':
    unittest.main()
