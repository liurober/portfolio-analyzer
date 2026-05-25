#!/bin/bash
# Runs automatically after Taiwan/Spain/Barcelona scan finishes.
# Collects + scans all remaining collections for new posts, then builds Excel.

set -e
cd "$(dirname "$0")"

echo ""
echo "============================================================"
echo "  Post-Taiwan chain: collecting all other collections"
echo "  $(date)"
echo "============================================================"

# 1. Collect URLs for all collections (skips already-processed)
echo ""
echo "[1/3] Collecting new post URLs for all collections..."
python3 collect_collection_urls.py > /tmp/collect-all.log 2>&1
cat /tmp/collect-all.log

# 2. Scan new posts across all collections
echo ""
echo "[2/3] Scanning new posts (Japan, Korea, Bangkok, Vancouver, LA, Recipes, AI, etc.)..."
python3 scan_from_urls.py \
    --only Japan Korea Bangkok Vancouver LA Recipes "AI prompt" AI Seattle Vegas London Paris "New York" Italy Iceland \
    > /tmp/scan-all.log 2>&1
cat /tmp/scan-all.log

# 3. Build Excel
echo ""
echo "[3/3] Building travel Excel sheet..."
python3 build_travel_sheet.py > /tmp/build-sheet.log 2>&1
cat /tmp/build-sheet.log

echo ""
echo "============================================================"
echo "  ALL DONE. Check Obsidian + Excel."
echo "  $(date)"
echo "============================================================"
