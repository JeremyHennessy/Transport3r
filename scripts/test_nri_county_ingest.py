"""Offline FEMA county ZIP contract tests; fixture is synthetic, never production evidence."""
import csv
import io
import json
import pathlib
import tempfile
import unittest
import zipfile

from nri_county_ingest import build, hash_file, normalize

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
        # A missing version column is legal; provenance remains pinned to download URL.
        self.assertEqual(normalize(self.src, min_rows=3)["accepted_rows"], 3)
        fixture(self.src, header=HEADER[:-2], rows=[row[:-2] for row in ROWS])
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            normalize(self.src, min_rows=3)
        fixture(self.src, rows=[ROWS[0][:-1] + ["1.10"], *ROWS[1:]])
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
