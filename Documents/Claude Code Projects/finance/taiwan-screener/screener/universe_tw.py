"""TWSE universe loader and refresher.

Phase 1: ships with 20 seed tickers in tickers_tw.json. The `refresh` CLI
pulls the full TWSE listed-companies feed from TWSE OpenAPI and rewrites
tickers_tw.json with ~1,045 entries.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

import requests

HERE = Path(__file__).resolve().parent
TICKERS_PATH = HERE / "tickers_tw.json"

# TWSE OpenAPI — daily listed company list
TWSE_LIST_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"


def load_universe() -> list[dict]:
    """Return the list of ticker dicts from tickers_tw.json."""
    data = json.loads(TICKERS_PATH.read_text(encoding="utf-8"))
    return data["tickers"]


def load_symbols() -> list[str]:
    """Return only the .TW symbol strings."""
    return [t["symbol"] for t in load_universe()]


def _fetch_twse_list() -> list[dict]:
    resp = requests.get(TWSE_LIST_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _normalize(row: dict) -> dict | None:
    code = (row.get("公司代號") or "").strip()
    name_zh = (row.get("公司簡稱") or row.get("公司名稱") or "").strip()
    sector = (row.get("產業別") or "其他").strip()
    if not code or not code.isdigit():
        return None
    return {
        "symbol": f"{code}.TW",
        "name_zh": name_zh,
        "name_en": "",
        "sector": sector,
    }


def refresh_universe(verbose: bool = True) -> int:
    """Refresh tickers_tw.json from TWSE OpenAPI. Returns count written."""
    rows = _fetch_twse_list()
    if verbose:
        print(f"[refresh] TWSE returned {len(rows)} rows")
    tickers: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        norm = _normalize(row)
        if norm is None or norm["symbol"] in seen:
            continue
        seen.add(norm["symbol"])
        tickers.append(norm)
    tickers.sort(key=lambda t: t["symbol"])
    payload = {
        "as_of": date.today().isoformat(),
        "exchange": "TWSE",
        "count": len(tickers),
        "tickers": tickers,
    }
    TICKERS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if verbose:
        print(f"[refresh] wrote {len(tickers)} tickers to {TICKERS_PATH}")
    return len(tickers)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TWSE universe loader/refresher")
    parser.add_argument("--refresh", action="store_true",
                        help="Fetch full TWSE listed company list and overwrite tickers_tw.json")
    parser.add_argument("--show", action="store_true",
                        help="Print the current universe count and first 10 symbols")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.refresh:
        count = refresh_universe()
        print(f"Refreshed {count} TWSE tickers.")
    if args.show or not args.refresh:
        symbols = load_symbols()
        print(f"Universe size: {len(symbols)}")
        for s in symbols[:10]:
            print(f"  {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
