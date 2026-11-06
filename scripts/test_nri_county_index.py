"""Reconcile real-grain source receipts with a read-only county SQLite index."""
import json
import pathlib
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch

from nri_county_ingest import ARCGIS_FIELDS, build
from nri_county_index import install, lookup, verified_manifest, VERSION

COUNT = 3232
def source_response(url, path, limit=8000000):
    if "/query?" not in url:
        response = {
            "name":"NRI_Counties_Prod", "objectIdField":"OBJECTID",
            "fields":[{"name":name} for name in ARCGIS_FIELDS],
            "editingInfo":{"dataLastEditDate":1765870621340},
        }
    else:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if query.get("returnCountOnly") == ["true"]:
            response = {"count":COUNT}
        else:
            offset=int(query["resultOffset"][0])
            limit_count=int(query["resultRecordCount"][0])
            features=[]
            for n in range(offset,offset+limit_count):
                attributes={
                  "OBJECTID":n+1, "STCOFIPS":str(n+1).zfill(5),
                  "STATEABBRV":"AL", "COUNTY":"Synthetic County "+str(n+1),
                  "RISK_SCORE":None if n<88 else 10.25,
                  "RISK_RATNG":"Insufficient Data" if n<88 else "Very Low",
                  "EAL_VALT":None if n<88 else 25.50,
                  "NRI_VER":"December 2025"
                }
                features.append({"attributes":attributes})
            response={"features":features}
    path.write_text(json.dumps(response),encoding="utf-8")
    return response


class CountyIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.tmp.name)
        self.release=self.root/"source"
        with patch("nri_county_ingest._arcgis_json",side_effect=source_response):
            report=build(self.release,arcgis=True)
        self.assertEqual(report["accepted_rows"],COUNT)
        self.index=self.root/"index.sqlite"
    def tearDown(self):
        self.tmp.cleanup()

    def test_verified_release_installs_and_retains_unknowns(self):
        meta=install(self.release,self.index)
        self.assertEqual(meta["schema_version"],VERSION)
        self.assertEqual(meta["county_rows"],COUNT)
        self.assertEqual(meta["unknown_scores"],88)
        self.assertEqual(meta["known_scores"],COUNT-88)
        self.assertEqual(meta["carrier_attribution"],"NOT_ESTABLISHED")
        self.assertEqual(lookup(self.index,"00001")["score_status"],"INSUFFICIENT_DATA")
        self.assertIsNone(lookup(self.index,"00001")["fema_nri_risk_score"])
        rated=lookup(self.index,"03000")
        self.assertEqual(rated["status"],"COUNTY_SOURCE_CONTEXT_ONLY")
        self.assertEqual(rated["fema_nri_risk_score"],10.25)
        self.assertEqual(rated["fema_expected_annual_loss_usd"],25.5)
        self.assertEqual(rated["carrier_route_attribution"],"NOT_ESTABLISHED")
        self.assertEqual(lookup(self.index,"99999")["status"],"NOT_FOUND")
        with self.assertRaisesRegex(ValueError,"five-digit"):
            lookup(self.index,"1 OR 1=1")
        with self.assertRaises(FileExistsError):
            install(self.release,self.index)

    def test_mutated_publisher_pages_or_counties_are_rejected(self):
        verified_manifest(self.release)
        p=self.release/"arcgis-original-responses"/"page-00000.json"
        p.write_text(p.read_text()+" ",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"publisher page digest"):
            install(self.release,self.index)
        self.assertFalse(self.index.exists())

    def test_mutated_normalized_csv_rejected(self):
        p=self.release/"counties.csv"
        p.write_text(p.read_text().replace("Synthetic County 1","Other County 1"),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            install(self.release,self.index)

    def test_unverified_source_mode_rejected(self):
        p=self.release/"manifest.json"
        data=json.loads(p.read_text())
        data["mode"]="UNVERIFIED_EXPLICIT_ARCHIVE"
        p.write_text(json.dumps(data),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"official ArcGIS"):
            install(self.release,self.index)


if __name__=="__main__":
    unittest.main()
