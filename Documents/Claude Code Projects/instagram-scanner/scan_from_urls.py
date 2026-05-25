#!/usr/bin/env python3
"""
Process pre-collected Instagram post URLs without Playwright.
Reads URLs from /tmp/collection_urls.json (created by collect_collection_urls.py)
and processes each through the full scan pipeline (API fetch → Claude vision → Obsidian).

Usage:
    python3 scan_from_urls.py                   # process all collections in file
    python3 scan_from_urls.py --only Taiwan     # process one collection
    python3 scan_from_urls.py --start 50        # skip first N posts (resume)
"""

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────────
import os
_env_file = Path.home() / ".instagram-scanner.env"
if _env_file.exists() and not os.environ.get("ANTHROPIC_API_KEY"):
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

sys.path.insert(0, str(Path(__file__).parent))

from scan import (
    process_post,
    load_state, save_state, is_processed,
    export_travel_csv, export_to_google_sheets,
    load_session, COLLECTIONS, OBSIDIAN_BASE,
    POST_DELAY,
)

URLS_FILE = Path("/tmp/collection_urls.json")


def main():
    parser = argparse.ArgumentParser(description="Process pre-collected Instagram URLs")
    parser.add_argument("--only", nargs="+", metavar="COLLECTION",
                        help="Process only these collections (e.g. --only Taiwan Spain)")
    parser.add_argument("--start", type=int, default=0,
                        help="Skip the first N posts (for resuming mid-collection)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after processing N posts total (0 = no limit)")
    args = parser.parse_args()

    if not URLS_FILE.exists():
        print(f"ERROR: {URLS_FILE} not found. Run collect_collection_urls.py first.")
        sys.exit(1)

    data = json.loads(URLS_FILE.read_text())

    print("\n" + "="*60)
    print("  Instagram Scanner — API Mode (no Playwright)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")

    state  = load_state()
    cookies, _ = load_session()
    print(f"State: {len(state['processed_posts'])} processed, {len(state.get('failed_posts', []))} failed\n")

    only_filter = {c.lower() for c in args.only} if args.only else None

    total_saved   = 0
    total_skipped = 0
    total_failed  = 0
    grand_total   = 0

    for coll_name, coll_data in data.items():
        if only_filter and coll_name.lower() not in only_filter:
            continue

        config = COLLECTIONS.get(coll_name)
        if config is None:
            print(f"[SKIP] {coll_name} (not in COLLECTIONS or explicitly skipped)")
            continue

        new_urls = coll_data.get("new", [])
        all_urls = coll_data.get("all", [])

        # Re-check against current state (may have processed some since collection)
        truly_new = [u for u in all_urls if not is_processed(state, u)]
        skip_count = len(all_urls) - len(truly_new)

        if args.start:
            truly_new = truly_new[args.start:]
            print(f"\n{'─'*50}")
            print(f"[COLLECTION] {coll_name}  (resuming from post {args.start+1})")
        else:
            print(f"\n{'─'*50}")
            print(f"[COLLECTION] {coll_name}")
        print(f"{'─'*50}")
        print(f"  Total in collection: {len(all_urls)} | New to process: {len(truly_new)} | Already done: {skip_count}")

        # Ensure output folder exists
        folder = config["folder"]
        (OBSIDIAN_BASE / folder).mkdir(parents=True, exist_ok=True)

        saved = 0
        failed = 0
        for i, url in enumerate(truly_new, 1):
            if args.limit and total_saved >= args.limit:
                print(f"\n  --limit {args.limit} reached, stopping.")
                break

            print(f"  [{i}/{len(truly_new)}] {url.split('/p/')[-1].strip('/')} ", end="", flush=True)
            try:
                ok = process_post(url, coll_name, config, state, cookies)
                if ok:
                    saved += 1
                    total_saved += 1
                else:
                    failed += 1
                    total_failed += 1
            except Exception as e:
                print(f"\n      EXCEPTION: {e}")
                traceback.print_exc()
                failed += 1
                total_failed += 1

            grand_total += 1
            time.sleep(POST_DELAY)

        total_skipped += skip_count
        print(f"\n  {coll_name} done: {saved} saved, {failed} failed, {skip_count} skipped")

    # ── Export ──────────────────────────────────────────────────────────────────
    print("\n" + "─"*60)
    export_travel_csv(state)

    travel_rows = state.get("travel_rows", [])
    if travel_rows:
        print(f"\nPushing {len(travel_rows)} travel rows to Google Sheets...")
        export_to_google_sheets(travel_rows)

    # ── Summary ─────────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  Scan complete (API mode)")
    print("─"*60)
    print(f"  Posts processed: {grand_total}")
    print(f"  Saved to Obsidian: {total_saved}")
    print(f"  Failed:            {total_failed}")
    print(f"  Skipped (dupes):   {total_skipped}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
