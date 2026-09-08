#!/usr/bin/env python3
"""Acquire new, immutable current-source cuts; never reconstruct history by naming a date."""
from __future__ import annotations
import argparse
import json
import pathlib
from snapshot_store import acquire, download

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / 'data' / 'fmcsa_sources.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tier', choices=('core', 'all'), default='core')
    parser.add_argument('--source', action='append', default=[], help='Explicit DataHub ID; may be repeated')
    parser.add_argument('--output-root', default='warehouse/raw')
    parser.add_argument('--snapshot-id', help='Unique cut identifier; existing directories are never overwritten')
    parser.add_argument('--date', help='Deprecated current-UTC-date assertion; does not retrieve historical data')
    parser.add_argument('--max-bytes', type=int, help='Maximum transfer size per dataset; over-limit downloads fail')
    parser.add_argument('--clean', action='store_true', help='Disabled: existing cuts must be retained')
    args = parser.parse_args(argv)
    catalog = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    ids = set(args.source)
    if ids:
        sources = [source for source in catalog if source['id'] in ids]
        missing = ids - {source['id'] for source in sources}
        if missing:
            parser.error(f'Unknown dataset IDs: {", ".join(sorted(missing))}')
    else:
        sources = [source for source in catalog if args.tier == 'all' or source.get('tier') == 'core']
    try:
        _, manifest = acquire(sources, ROOT / args.output_root, date_label=args.date,
                              snapshot_id=args.snapshot_id, clean=args.clean, max_bytes=args.max_bytes)
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))
    return 0 if manifest['failure_count'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
