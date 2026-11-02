"""Immutable acquisition and county-grain QA for official FEMA NRI v1.20.

No FMCSA carrier matching, road-route inference, insurance score or expected
insured loss is produced. Output is not part of the public Pages build.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import pathlib
import re
import shutil
import sys
import urllib.request
import zipfile

SOURCE_URL = "https://www.fema.gov/about/reports-and-data/openfema/nri/v120/NRI_Table_Counties.zip"
SOURCE_ID = "FEMA_NRI_COUNTIES_V120"
EXPECTED_VERSION = "1.20"
REQUIRED_FIELDS = {"STCOFIPS", "STATEABBRV", "COUNTY", "RISK_SCORE", "RISK_RATNG", "EAL_VALT"}
NORMALIZED_FIELDS = ("stcofips", "state", "county", "risk_score", "risk_rating", "eal_total_usd", "source_version")
MAX_DOWNLOAD_BYTES = 85_000_000
MAX_CSV_BYTES = 150_000_000
MAX_ROWS = 4_000


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def hash_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire_official(dest: pathlib.Path) -> str:
    """Download only the pinned official URL; fail closed on size or transport error."""
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "Transport3r-NRI-Source-Audit/1.0", "Accept": "application/zip,*/*"}
    )
    partial = dest.with_suffix(".partial")
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("xb") as output:
        final_url = response.geturl()
        if not final_url.startswith("https://"):
            raise ValueError("Official download redirected to an insecure transport")
        size = 0
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > MAX_DOWNLOAD_BYTES:
                raise ValueError("Official FEMA archive exceeds the bounded download size")
            output.write(block)
    os.replace(partial, dest)
    return final_url


def _decimal(value: str, field: str, maximum: float | None = None) -> str:
    raw = str(value or "").strip()
    if not raw or raw.upper() in ("NULL", "N/A", "NA"):
        return ""
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as cause:
        raise ValueError(field + " has a nonnumeric value") from cause
    if not math.isfinite(parsed) or parsed < 0 or (maximum is not None and parsed > maximum):
        raise ValueError(field + " outside declared numeric range")
    return raw


def _csv_from_zip(archive: pathlib.Path) -> tuple[str, bytes]:
    with zipfile.ZipFile(archive) as package:
        candidates = [
            member for member in package.infolist()
            if pathlib.PurePosixPath(member.filename).name.lower() == "nri_table_counties.csv"
            and not member.is_dir()
        ]
        if len(candidates) != 1:
            raise ValueError("Expected exactly one FEMA NRI_Table_Counties.csv in the official archive")
        member = candidates[0]
        if member.file_size > MAX_CSV_BYTES:
            raise ValueError("County CSV exceeds decompressed size safety bound")
        with package.open(member) as stream:
            payload = stream.read(MAX_CSV_BYTES + 1)
        if len(payload) > MAX_CSV_BYTES:
            raise ValueError("County CSV exceeded decompressed read safety bound")
        return member.filename, payload


def normalize(archive: pathlib.Path, min_rows: int = 3000) -> dict:
    """Validate the complete county CSV before publishing anything."""
    if not 1 <= min_rows <= MAX_ROWS:
        raise ValueError("Expected minimum row count must be 1..4,000")
    name, payload = _csv_from_zip(archive)
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as cause:
        raise ValueError("Original FEMA CSV must decode as UTF-8") from cause
    csv.field_size_limit(2_000_000)
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    header = reader.fieldnames or []
    if len(set(header)) != len(header):
        raise ValueError("Duplicate source header names")
    missing = sorted(REQUIRED_FIELDS - set(header))
    if missing:
        raise ValueError("Official county CSV is missing required fields: " + ", ".join(missing))
    result, invalid, seen = [], [], set()
    invalid_count = 0
    input_rows = 0
    versions = set()
    scored_rows = 0
    for row in reader:
        input_rows += 1
        if input_rows > MAX_ROWS:
            raise ValueError("Source row count above bounded official county universe")
        try:
            if None in row:
                raise ValueError("Source CSV row has surplus fields")
            fips = str(row["STCOFIPS"] or "").strip()
            if not re.fullmatch(r"[0-9]{5}", fips):
                raise ValueError("STCOFIPS must be a five-character source identifier")
            if fips in seen:
                raise ValueError("Duplicate county STCOFIPS " + fips)
            seen.add(fips)
            state = str(row["STATEABBRV"] or "").strip()
            county = str(row["COUNTY"] or "").strip()
            if not re.fullmatch(r"[A-Z]{2}", state) or not county:
                raise ValueError("Missing or invalid county/state identity")
            score = _decimal(row["RISK_SCORE"], "RISK_SCORE", maximum=100)
            eal = _decimal(row["EAL_VALT"], "EAL_VALT")
            rating = str(row["RISK_RATNG"] or "").strip()
            if len(rating) > 80:
                raise ValueError("Unexpected risk rating length")
            version = str(row.get("NRI_VER") or "").strip()
            if version:
                versions.add(version)
                if not version.startswith(EXPECTED_VERSION):
                    raise ValueError("Source row NRI_VER does not match pinned v1.20 release")
            if score:
                scored_rows += 1
            result.append(dict(zip(NORMALIZED_FIELDS, (fips, state, county, score, rating, eal, version))))
        except ValueError as error:
            invalid_count += 1
            if len(invalid) < 25:
                invalid.append({"row": input_rows, "error": str(error)})
    if input_rows < min_rows:
        raise ValueError(f"County completeness gate: {input_rows} rows, minimum {min_rows}")
    if invalid_count:
        raise ValueError(f"Rejected {invalid_count} of {input_rows} rows (first 25): {json.dumps(invalid)}")
    if not scored_rows:
        raise ValueError("No county has an interpretable official NRI score")
    if len(versions) > 1:
        raise ValueError("Official archive mixes NRI publication vintages")
    result.sort(key=lambda row: row["stcofips"])
    return {
        "member": name, "source_csv_sha256": hashlib.sha256(payload).hexdigest(),
        "raw_rows": input_rows, "accepted_rows": len(result),
        "rejected_rows": 0, "scored_rows": scored_rows,
        "unknown_scores": input_rows - scored_rows,
        "fips_unique": len(seen), "source_versions": sorted(versions),
        "source_fields": header, "data": result,
    }


def build(output: pathlib.Path, archive: pathlib.Path | None = None, min_rows: int = 3000):
    if output.exists():
        raise FileExistsError("Release already exists; use a new versioned output directory")
    output.mkdir(parents=True)
    official = output / "official.zip"
    final_url = SOURCE_URL
    if archive:
        source = pathlib.Path(archive).resolve()
        if not source.is_file():
            raise FileNotFoundError("Explicit source archive not found")
        shutil.copyfile(source, official)
        source_mode = "EXPLICIT_ARCHIVE"
    else:
        final_url = acquire_official(official)
        source_mode = "OFFICIAL_LIVE_DOWNLOAD"
    manifest = {
        "source_id": SOURCE_ID, "source_url": SOURCE_URL, "resolved_url": final_url,
        "release": EXPECTED_VERSION, "ingested_at": timestamp(),
        "mode": source_mode, "archive_bytes": official.stat().st_size,
        "archive_sha256": hash_file(official), "status": "BLOCKED_PENDING_VALIDATION",
        "grain": "county STCOFIPS", "derived_carrier_risk": False,
        "route_exposure_matched": False,
    }
    try:
        normalized = normalize(official, min_rows)
        rows = normalized.pop("data")
        pending = output / "counties.partial.csv"
        with pending.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=NORMALIZED_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        dest = output / "counties.csv"
        os.replace(pending, dest)
        manifest.update(normalized)
        manifest.update(status="SOURCE_ACCEPTED_COUNTY_GRAIN", normalized_sha256=hash_file(dest))
    except Exception as error:
        manifest.update(status="REJECTED", error=f"{type(error).__name__}: {error}")
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        raise
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--archive", type=pathlib.Path, help="Explicit verified source ZIP (offline replay)")
    parser.add_argument("--min-rows", type=int, default=3000)
    args = parser.parse_args()
    try:
        report = build(args.output, args.archive, args.min_rows)
    except Exception as error:
        print(f"FEMA NRI acquisition failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({key: value for key, value in report.items() if key != "source_fields"}, indent=2))
