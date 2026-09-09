# Raw acquisition cuts

The downloader creates a new current-source cut for every run. A date label cannot reconstruct historical data. Each cut records acquisition start/completion and per-source availability, SHA-256 hashes, CSV row counts, schema fingerprints, upstream update watermarks, and the full source metadata observed before and after download.

## Acquire and verify

For complete carrier-cohort JSON paging, expanded SMS/MOTUS evidence and local SQLite promotion, see the [verified evidence warehouse](evidence-warehouse.md). The verifier also accepts complete v3/v4 cohort cuts; the commands below describe the original full-source CSV pipeline.

Run from the repository root with Python 3.12 or newer:

```sh
python scripts/download_fmcsa.py --source p2mt-9ige --source xe5s-wca7 --max-bytes 50000000
python scripts/verify_snapshot.py warehouse/raw/REPORTED_SNAPSHOT_ID
python scripts/verify_snapshot.py warehouse/raw/REPORTED_SNAPSHOT_ID --as-of 2026-09-09T00:00:00Z
```

The byte ceiling applies separately to each source. Explicit source selection is recommended before a larger acquisition; `--tier all` can download substantially more data. Raw data remains ignored by Git. The printed manifest path identifies the exact cut.

The verifier rejects failed or partial cuts, changed raw/metadata artifacts, inconsistent row counts, and cuts acquired after the requested timezone-aware knowledge-time cutoff. A successful verification certifies stored artifact integrity and recorded availability, **not historical feature validity**.

## Retention and failure behavior

- Existing cut directories and source artifacts are never replaced by the writer. `--clean` fails before writing; `--date` accepts only the current UTC date and does not select historical data.
- Failed transfers retain partial bytes and failure records. Retry with a fresh cut ID. An interrupted run without a final complete manifest is ineligible.
- A CSV is accepted only after header, row width, row count, transfer length when supplied, and source metadata checks pass. A changed source watermark, schema, table identifier or row count during acquisition rejects the transfer.
- Promotion uses a same-filesystem hard link with no replacement. The `.csv.partial` and accepted `.csv` names then reference the same validated bytes. A filesystem without hard-link support fails closed.
- Immutability is enforced by the acquisition writer and checked through hashes; this is not WORM storage or protection against privileged filesystem edits. Preserve manifests separately when stronger provenance guarantees are required.

The before/after source checks are not a transactional guarantee: upstream content could change without a distinguishable watermark/count change. Sources are acquired at different times. A multi-source cut is conservatively available only after the last source completes.

## Verified initial acquisition

On September 8, 2026, cut `20260908T221456196420Z-78419d0c` completed at `2026-09-08T22:15:17.680029Z`. Offline verification passed for two sources, 399,144 rows and 42,636,088 bytes: 399,025 new-entrant order rows (`p2mt-9ige`) and 119 daily insurance-history rows (`xe5s-wca7`). These counts describe this cut, not future source sizes. This was not an acquisition of all 36 configured sources.

This establishes a current raw baseline only. It does not supply a historical carrier-month panel, justify backdating current Census/SMS attributes, or validate a forecast. MOTUS amount-unit discrepancies and unmapped filing codes such as `TERM/REPL` remain unresolved. Those rows retain uncertainty; no current coverage gap or order effect is inferred from an unexplained code.
