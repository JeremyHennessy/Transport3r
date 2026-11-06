"""Offline FEMA county ZIP contract tests; fixture is synthetic, never production evidence."""
import csv
import io
import json
import pathlib
import tempfile
import unittest
import zipfile

from nri_county_ingest import build, hash_file, normalize, ARCGIS_FIELDS, ARCGIS_LAYER, _arcgis_json
from unittest.mock import patch
import urllib.parse

HEADER = ["STCOFIPS", "STATEABBRV", "COUNTY", "RISK_SCORE", "RISK_RATNG", "EAL_VALT", "NRI_VER"]
ROWS = [
    ["01001", "AL", "Autauga", "40.1", "Relatively Moderate", "700000", "1.20"],
    ["01003", "AL", "Baldwin", "", "Insufficient Data", "", "1.20"],
    ["23001", "ME", "Androscoggin", "12.5", "Very Low", "50000", "1.20"],
]


def fixture(archive, rows=ROWS, header=HEADER, member="NRI_Table_Counties.csv"):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr(member, buffer.getvalue().encode("utf-8"))


class NriCountyIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.src = self.root / "official.zip"
    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_county_grain_acceptance_and_determinism(self):
        fixture(self.src)
        first = build(self.root / "release-a", self.src, min_rows=3)
        self.assertEqual(first["status"], "SOURCE_ACCEPTED_COUNTY_GRAIN")
        self.assertEqual(first["source_id"], "FEMA_NRI_COUNTIES_V120")
        self.assertEqual(first["raw_rows"], 3)
        self.assertEqual(first["accepted_rows"], 3)
        self.assertEqual(first["rejected_rows"], 0)
        self.assertEqual(first["unknown_scores"], 1)
        self.assertFalse(first["derived_carrier_risk"])
        self.assertFalse(first["route_exposure_matched"])
        self.assertEqual(first["archive_sha256"], hash_file(self.src))
        self.assertEqual(first["fips_unique"], 3)
        normalized = (self.root / "release-a" / "counties.csv").read_text()
        self.assertTrue(normalized.startswith("stcofips,state,county,"))
        self.assertLess(normalized.index("01003"), normalized.index("23001"))
        self.assertIn("01003,AL,Baldwin,,Insufficient Data,,1.20", normalized)
        second = build(self.root / "release-b", self.src, min_rows=3)
        self.assertEqual(first["normalized_sha256"], second["normalized_sha256"])
        self.assertEqual(first["archive_sha256"], second["archive_sha256"])
        with self.assertRaises(FileExistsError):
            build(self.root / "release-a", self.src, min_rows=3)

    def test_duplicate_fips_fails_closed_and_writes_receipt(self):
        fixture(self.src, rows=ROWS + [ROWS[0]])
        with self.assertRaisesRegex(ValueError, "Rejected"):
            build(self.root / "bad-duplicate", self.src, min_rows=3)
        receipt = json.loads((self.root / "bad-duplicate" / "manifest.json").read_text())
        self.assertEqual(receipt["status"], "REJECTED")
        self.assertIn("Duplicate county", receipt["error"])
        self.assertFalse((self.root / "bad-duplicate" / "counties.csv").exists())

    def test_unexpected_headers_and_bad_version_fail(self):
        fixture(self.src, header=HEADER[:-1], rows=[row[:-1] for row in ROWS])
        # Even an explicit archive must contain the exact pinned source vintage.
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            normalize(self.src, min_rows=3)
        fixture(self.src, header=HEADER[:-2], rows=[row[:-2] for row in ROWS])
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            normalize(self.src, min_rows=3)
        fixture(self.src, rows=[ROWS[0][:-1] + ["1.10"], *ROWS[1:]])
        with self.assertRaisesRegex(ValueError, "Rejected"):
            normalize(self.src, min_rows=3)

    def test_explicit_archive_requires_known_december_2025_vintage(self):
        fixture(self.src, rows=[r[:-1] + ["December 2025"] for r in ROWS])
        self.assertEqual(normalize(self.src, min_rows=3)["accepted_rows"], 3)
        fixture(self.src, rows=[r[:-1] + ["December 2024"] for r in ROWS])
        with self.assertRaisesRegex(ValueError, "Rejected"):
            normalize(self.src, min_rows=3)
        fixture(self.src, rows=[r[:-1] + [""] for r in ROWS])
        with self.assertRaisesRegex(ValueError, "Rejected"):
            normalize(self.src, min_rows=3)

    def test_bad_score_and_incomplete_archive_are_rejected(self):
        fixture(self.src, rows=[ROWS[0][:-4] + ["not-a-number", *ROWS[0][-3:]], *ROWS[1:]])
        with self.assertRaisesRegex(ValueError, "Rejected"):
            normalize(self.src, min_rows=3)
        fixture(self.src)
        with self.assertRaisesRegex(ValueError, "completeness gate"):
            normalize(self.src, min_rows=3000)

    def test_no_scores_does_not_pass_as_zero_risk(self):
        fixture(self.src, rows=[[r[0], r[1], r[2], "", "", "", r[6]] for r in ROWS])
        with self.assertRaisesRegex(ValueError, "No county"):
            normalize(self.src, min_rows=3)

    def _arcgis_response(self, url, destination, limit=8000000, mutate_count=False):
        metadata = {
            "name": "NRI_Counties_Prod", "objectIdField": "OBJECTID",
            "fields": [{"name": field} for field in ARCGIS_FIELDS],
            "editingInfo": {"dataLastEditDate": 1765870621340},
        }
        if "/query?" not in url:
            response = metadata
        else:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            if query.get("returnCountOnly") == ["true"]:
                value = 4 if mutate_count and destination.name=="count-after.json" else 3
                response = {"count": value}
            else:
                response = {
                    "features": [
                        {"attributes": {"OBJECTID": i + 1, **dict(zip(ARCGIS_FIELDS[1:], row))}}
                        for i, row in enumerate(ROWS)
                    ]
                }
        destination.write_text(json.dumps(response), encoding="utf-8")
        return response

    def test_official_arcgis_pages_keep_original_bytes_and_cut_identity(self):
        with patch("nri_county_ingest._arcgis_json", side_effect=self._arcgis_response):
            result = build(self.root / "arcgis", min_rows=3, arcgis=True)
        self.assertEqual(result["status"], "SOURCE_ACCEPTED_COUNTY_GRAIN")
        self.assertEqual(result["mode"], "FEMA_ARCGIS_PAGED_SOURCE")
        self.assertTrue(result["provenance_verified"])
        self.assertFalse(result["archive_is_original_fema_zip"])
        self.assertEqual(result["source_archive_kind"], "RECONSTRUCTED_FROM_ORIGINAL_ARCGIS_JSON")
        self.assertEqual(result["publisher_count"], 3)
        self.assertEqual(len(result["page_audit"]), 1)
        source_dir=self.root / "arcgis" / "arcgis-original-responses"
        self.assertEqual(result["page_audit"][0]["sha256"],hash_file(source_dir/"page-00000.json"))
        self.assertEqual(len(list(source_dir.glob("*.json"))),5)
        self.assertTrue((self.root/"arcgis"/"counties.csv").is_file())

    def test_arcgis_source_changes_fail_closed_and_preserve_raw_receipt(self):
        def changing(url, dest, limit=8000000):
            return self._arcgis_response(url,dest,limit,mutate_count=True)
        with patch("nri_county_ingest._arcgis_json",side_effect=changing):
            with self.assertRaisesRegex(ValueError,"changed during"):
                build(self.root/"arcgis-changed",min_rows=3,arcgis=True)
        receipt=json.loads((self.root/"arcgis-changed"/"manifest.json").read_text())
        self.assertEqual(receipt["status"],"REJECTED")
        self.assertFalse((self.root/"arcgis-changed"/"counties.csv").exists())
        self.assertTrue((self.root/"arcgis-changed"/"arcgis-original-responses"/"metadata-before.json").exists())

    def test_arcgis_redirect_must_remain_on_approved_publisher_host_and_layer(self):
        class Response:
            def __init__(self,url): self.url=url
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def geturl(self): return self.url
            def read(self,n): return b'{"name":"NRI_Counties_Prod"}'
        good=ARCGIS_LAYER+"?f=json"
        for redirect in [
            "https://attacker.example/nri?f=json",
            "https://services.arcgis.com/other-provider/ArcGIS/rest/services/fake/FeatureServer/0?f=json",
            "http://"+good[len("https://"):],
            "https://user:pass@"+good[len("https://"):],
        ]:
            with self.subTest(redirect=redirect),patch(
                "urllib.request.urlopen",return_value=Response(redirect)
            ),self.assertRaisesRegex(ValueError,"approved official source endpoint"):
                _arcgis_json(good,self.root/"unexpected.json")
        self.assertFalse((self.root/"unexpected.json").exists())
        with patch("urllib.request.urlopen",return_value=Response(good)):
            data=_arcgis_json(good,self.root/"approved.json")
            self.assertEqual(data["name"],"NRI_Counties_Prod")
            self.assertTrue((self.root/"approved.json").exists())

    def test_missing_or_duplicate_csv_archive_fails(self):
        fixture(self.src, member="wrong.csv")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            normalize(self.src, min_rows=3)
        with zipfile.ZipFile(self.src, "w", zipfile.ZIP_DEFLATED) as package:
            for name in ["folder/NRI_Table_Counties.csv", "NRI_Table_Counties.csv"]:
                package.writestr(name, "STCOFIPS\n")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            normalize(self.src, min_rows=3)


if __name__ == "__main__":
    unittest.main()
