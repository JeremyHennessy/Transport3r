"""Install and query a provenance-validated FEMA county NRI SQLite source index.

FEMA county risk is community-level context, not a carrier, route, terminal,
policy, claim, or insured loss assessment. No transport linkage is performed.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import pathlib
import re
import sqlite3

from nri_county_ingest import hash_file

VERSION = "FEMA_NRI_COUNTY_SOURCE_INDEX_1"
SCHEMA = """
CREATE TABLE county_context (
  stcofips TEXT PRIMARY KEY, state TEXT NOT NULL, county TEXT NOT NULL,
  fema_risk_score REAL, fema_risk_rating TEXT NOT NULL,
  fema_expected_annual_loss_usd REAL,
  raw_risk_score TEXT, raw_eal_total TEXT, nri_ver TEXT NOT NULL
);
CREATE TABLE source_receipt (
  key TEXT PRIMARY KEY, value_json TEXT NOT NULL
);
CREATE INDEX county_context_state ON county_context(state, county);
"""


def _real(value: str, upper: float | None = None) -> float | None:
    if value == "":
        return None
    try:
        parsed = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid source numeric value in accepted file") from error
    if not math.isfinite(parsed) or parsed < 0 or upper is not None and parsed > upper:
        raise ValueError("Out-of-range source numeric value")
    return parsed


def verified_manifest(root: pathlib.Path) -> dict:
    root = pathlib.Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "SOURCE_ACCEPTED_COUNTY_GRAIN":
        raise ValueError("NRI source release was not accepted")
    if manifest.get("mode") != "FEMA_ARCGIS_PAGED_SOURCE":
        raise ValueError("Read-only index requires independently acquired official ArcGIS source")
    if manifest.get("source_distribution") != "FEMA_OFFICIAL_ARCGIS_FEATURESERVER":
        raise ValueError("Source distribution or provenance identity mismatch")
    if manifest.get("provenance_verified") is not True:
        raise ValueError("Unverified source archive cannot enter published county index")
    if manifest.get("source_versions") != ["December 2025"]:
        raise ValueError("FEMA NRI v1.20/December 2025 source vintage not confirmed")
    if manifest.get("archive_is_original_fema_zip") is not False:
        raise ValueError("ArcGIS reconstructed wrapper must not be represented as original ZIP")
    n = manifest.get("accepted_rows")
    if not isinstance(n, int) or not 3000 <= n <= 4000:
        raise ValueError("Accepted county source universe is incomplete")
    if any(manifest.get(key) != n for key in ("raw_rows", "fips_unique", "publisher_count")):
        raise ValueError("Published and accepted counts differ")
    if manifest.get("rejected_rows") != 0 or manifest.get("route_exposure_matched") is not False:
        raise ValueError("Rejected rows or unsupported carrier linkage found")
    for filename, key in (("counties.csv", "normalized_sha256"), ("source_table.zip", "archive_sha256")):
        if hash_file(root / filename) != manifest.get(key):
            raise ValueError("Source artifact SHA-256 mismatch: " + filename)
    publisher = root / "arcgis-original-responses"
    for source_name, digest_key in (
        ("metadata-before.json", "metadata_before_sha256"),
        ("metadata-after.json", "metadata_after_sha256"),
    ):
        if hash_file(publisher / source_name) != manifest.get(digest_key):
            raise ValueError("Original publisher metadata digest mismatch")
    pages = manifest.get("page_audit")
    if not isinstance(pages, list) or len(pages) < 2:
        raise ValueError("Original publisher page audit missing")
    if sum(page.get("rows", 0) for page in pages) != n:
        raise ValueError("Publisher page row totals do not match accepted counties")
    for page in pages:
        name = page.get("path")
        if not isinstance(name, str) or not re.fullmatch(r"page-[0-9]{5}\.json", name):
            raise ValueError("Invalid retained publisher page name")
        if hash_file(publisher / name) != page.get("sha256"):
            raise ValueError("Original publisher page digest mismatch")
    return manifest


def install(release: pathlib.Path, output: pathlib.Path) -> dict:
    source = pathlib.Path(release).resolve()
    destination = pathlib.Path(output).resolve()
    receipt = verified_manifest(source)
    if destination.exists() or destination.with_suffix(".partial.sqlite").exists():
        raise FileExistsError("Source index or pending build exists; use a new index path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_suffix(".partial.sqlite")
    db = sqlite3.connect(pending)
    db.executescript(SCHEMA)
    rows = 0
    known = 0
    seen = set()
    try:
        with (source / "counties.csv").open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            expected = {"stcofips", "state", "county", "risk_score", "risk_rating",
                        "eal_total_usd", "source_version"}
            if set(reader.fieldnames or []) != expected:
                raise ValueError("Normalized county schema differs from accepted contract")
            for row in reader:
                fips = row["stcofips"]
                if not re.fullmatch(r"[0-9]{5}", fips) or fips in seen:
                    raise ValueError("Duplicate or malformed county FIPS in normalized release")
                seen.add(fips)
                score = _real(row["risk_score"], 100)
                eal = _real(row["eal_total_usd"])
                if row["source_version"] != "December 2025":
                    raise ValueError("Unmatched source vintage in normalized county")
                if not re.fullmatch(r"[A-Z]{2}", row["state"]) or not row["county"]:
                    raise ValueError("Missing county identity")
                db.execute("INSERT INTO county_context VALUES (?,?,?,?,?,?,?,?,?)",
                    (fips, row["state"], row["county"], score, row["risk_rating"],
                     eal, row["risk_score"] or None, row["eal_total_usd"] or None,
                     row["source_version"]))
                rows += 1
                known += score is not None
        if rows != receipt["accepted_rows"] or known != receipt["scored_rows"]:
            raise ValueError("Index counts do not reconcile to source acceptance")
        meta = {
            "schema_version": VERSION,
            "source_id": receipt["source_id"], "source_version": "December 2025",
            "source_url": receipt["source_url"],
            "county_rows": rows, "known_scores": known, "unknown_scores": rows-known,
            "normalized_source_sha256": receipt["normalized_sha256"],
            "original_arcgis_archive_sha256": receipt["archive_sha256"],
            "publisher_data_last_edit_ms": receipt["publisher_data_last_edit_ms"],
            "evidence_grain": "COUNTY_STCOFIPS",
            "carrier_attribution": "NOT_ESTABLISHED",
            "route_attribution": "NOT_ESTABLISHED",
            "coverage_or_premium_determination": False,
        }
        with db:
            db.executemany("INSERT INTO source_receipt VALUES (?,?)",
                           [(key, json.dumps(value)) for key, value in meta.items()])
        checked = db.execute("PRAGMA integrity_check").fetchone()[0]
        if checked != "ok":
            raise ValueError("SQLite integrity check failed: " + checked)
    finally:
        db.close()
    os.replace(pending, destination)
    return meta


def read_only_status(index: pathlib.Path) -> dict:
    """Check installed source release metadata and indexed county row coverage."""
    path = pathlib.Path(index).resolve()
    if not path.is_file():
        raise ValueError("Installed county source index unavailable")
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as db:
        metadata = {key: json.loads(value) for key, value in db.execute(
            "SELECT key,value_json FROM source_receipt")}
        total, known = db.execute(
            "SELECT count(*),count(fema_risk_score) FROM county_context").fetchone()
        integrity = db.execute("PRAGMA quick_check").fetchone()[0]
    if metadata.get("schema_version") != VERSION or metadata.get("source_version") != "December 2025":
        raise ValueError("Source index version is not accepted")
    if metadata.get("source_id") != "FEMA_NRI_COUNTIES_V120":
        raise ValueError("Source identity is not accepted")
    if total != metadata.get("county_rows") or known != metadata.get("known_scores"):
        raise ValueError("Source index no longer reconciles to acceptance receipt")
    if not 3000 <= total <= 4000 or integrity != "ok":
        raise ValueError("Source index failed county universe/integrity gate")
    if metadata.get("carrier_attribution") != "NOT_ESTABLISHED":
        raise ValueError("County source cannot claim transport carrier attribution")
    return {
        "status": "ACCEPTED_SOURCE_INDEX",
        "source": metadata.get("source_id"), "version": metadata.get("source_version"),
        "county_rows": total, "known_scores": known, "unknown_scores": total-known,
        "normalized_source_sha256": metadata.get("normalized_source_sha256"),
        "source_vintage": metadata.get("publisher_data_last_edit_ms"),
        "scope": "COUNTY_SOURCE_CONTEXT_ONLY", "carrier_route_attribution": "NOT_ESTABLISHED",
        "limitations": "No independently verified operating terminals, route coordinates, H3 hazard bands or insured-loss calibration."
    }


def lookup(index: pathlib.Path, fips: str) -> dict:
    if not isinstance(fips, str) or not re.fullmatch(r"[0-9]{5}", fips):
        raise ValueError("Exact five-digit county FIPS required")
    path = pathlib.Path(index).resolve()
    if not path.is_file():
        raise ValueError("Verified county source index unavailable")
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM county_context WHERE stcofips=?", (fips,)).fetchone()
        metadata = {k: json.loads(v) for k, v in db.execute("SELECT key,value_json FROM source_receipt")}
    if row is None:
        return {"status": "NOT_FOUND", "stcofips": fips, "source": metadata.get("source_id")}
    return {
        "status": "COUNTY_SOURCE_CONTEXT_ONLY",
        "stcofips": row["stcofips"], "state": row["state"], "county": row["county"],
        "fema_nri_risk_score": row["fema_risk_score"],
        "fema_nri_risk_rating": row["fema_risk_rating"],
        "fema_expected_annual_loss_usd": row["fema_expected_annual_loss_usd"],
        "score_status": "OBSERVED" if row["fema_risk_score"] is not None else "INSUFFICIENT_DATA",
        "source": {key: metadata[key] for key in (
            "source_id", "source_version", "normalized_source_sha256",
            "publisher_data_last_edit_ms", "evidence_grain"
        )},
        "carrier_route_attribution": "NOT_ESTABLISHED",
        "limitation": "Official FEMA county-level community relative risk, not carrier route exposure or insurer expected loss.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=pathlib.Path, help="Verified immutable source release")
    parser.add_argument("--index", type=pathlib.Path, required=True, help="SQLite source index")
    parser.add_argument("--lookup", metavar="STCOFIPS", help="Read a county from an already installed index")
    args = parser.parse_args()
    try:
        report = lookup(args.index, args.lookup) if args.lookup else install(args.release, args.index)
        print(json.dumps(report, indent=2))
    except Exception as error:
        parser.exit(1, str(error) + "\n")
