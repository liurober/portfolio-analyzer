"""
parser.py — Parse portfolio holdings from PDF, Excel, or dict input.

Output contract: holdings dict with keys:
  positions: list of {ticker, weight, value, cost_basis, shares}
  total_value: float or None
  data_completeness: "full" | "partial" | "ticker_weight_only"
"""
from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Column header aliases (lowercase) → canonical field name
# ---------------------------------------------------------------------------
_TICKER_ALIASES = {"ticker", "symbol", "stock", "security", "name"}
_WEIGHT_ALIASES = {"weight", "allocation", "alloc", "%", "pct", "percent", "portfolio %", "port %"}
_VALUE_ALIASES  = {"value", "market value", "amount", "mkt value", "current value", "mkt val"}
_COST_ALIASES   = {"cost basis", "cost", "basis", "avg cost", "book value", "book val"}
_SHARES_ALIASES = {"shares", "quantity", "qty", "units", "position"}


def _match_col(header: str, aliases: set) -> bool:
    h = header.strip().lower()
    return h in aliases or any(a in h for a in aliases)


def _normalize_weight(raw: Any) -> float | None:
    """Convert '12%', 0.12, or 12.0 to a 0–1 float. Return None if unparseable."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip().replace(",", "")
    is_pct = s.endswith("%")
    s = s.rstrip("% ")
    try:
        val = float(s)
    except ValueError:
        return None
    if is_pct or val > 1.5:      # treat values > 1.5 as percentage points
        val = val / 100.0
    return val


def _normalize_float(raw: Any) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip().replace(",", "").replace("$", "")
    if s == "" or s == "-" or s.lower() == "none":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _determine_completeness(positions: list[dict]) -> str:
    """Infer data_completeness from position fields."""
    if not positions:
        return "ticker_weight_only"
    has_value = any(p.get("value") is not None for p in positions)
    has_cost  = any(p.get("cost_basis") is not None for p in positions)
    if has_value and has_cost:
        return "full"
    elif has_value or has_cost:
        return "partial"
    return "ticker_weight_only"


# ---------------------------------------------------------------------------
# Table → positions
# ---------------------------------------------------------------------------
def _table_to_positions(headers: list[str], rows: list[list]) -> list[dict]:
    """Map a 2-D table (headers + rows) to a list of position dicts."""
    hi = {}  # field → column index
    for i, h in enumerate(headers):
        if _match_col(h, _TICKER_ALIASES) and "ticker" not in hi:
            hi["ticker"] = i
        elif _match_col(h, _WEIGHT_ALIASES) and "weight" not in hi:
            hi["weight"] = i
        elif _match_col(h, _VALUE_ALIASES) and "value" not in hi:
            hi["value"] = i
        elif _match_col(h, _COST_ALIASES) and "cost_basis" not in hi:
            hi["cost_basis"] = i
        elif _match_col(h, _SHARES_ALIASES) and "shares" not in hi:
            hi["shares"] = i

    if "ticker" not in hi or "weight" not in hi:
        return []

    positions = []
    for row in rows:
        if not row:
            continue
        ticker_raw = row[hi["ticker"]] if hi["ticker"] < len(row) else None
        if not ticker_raw or str(ticker_raw).strip() == "":
            continue
        ticker = re.sub(r"[^A-Za-z0-9.\-]", "", str(ticker_raw)).upper()
        if not ticker:
            continue

        weight = _normalize_weight(row[hi["weight"]] if hi["weight"] < len(row) else None)
        if weight is None:
            continue

        value      = _normalize_float(row[hi["value"]]      if "value"      in hi and hi["value"]      < len(row) else None)
        cost_basis = _normalize_float(row[hi["cost_basis"]]  if "cost_basis" in hi and hi["cost_basis"] < len(row) else None)
        shares     = _normalize_float(row[hi["shares"]]      if "shares"     in hi and hi["shares"]     < len(row) else None)

        positions.append({
            "ticker":     ticker,
            "weight":     weight,
            "value":      value,
            "cost_basis": cost_basis,
            "shares":     shares,
        })
    return positions


# ---------------------------------------------------------------------------
# Source-specific parsers
# ---------------------------------------------------------------------------
def _parse_dict(data: dict) -> dict:
    """Pass-through for a dict that already matches the holdings schema."""
    positions = []
    for p in data.get("positions", []):
        positions.append({
            "ticker":     str(p.get("ticker", "")).upper(),
            "weight":     _normalize_weight(p.get("weight")),
            "value":      _normalize_float(p.get("value")),
            "cost_basis": _normalize_float(p.get("cost_basis")),
            "shares":     _normalize_float(p.get("shares")),
        })
    # Filter out positions with no weight
    positions = [p for p in positions if p["weight"] is not None]

    total_value = _normalize_float(data.get("total_value"))
    completeness = data.get("data_completeness") or _determine_completeness(positions)

    return {
        "positions":        positions,
        "total_value":      total_value,
        "data_completeness": completeness,
    }


def _parse_excel(path: str) -> dict:
    """Read first sheet of an Excel file; find header row heuristically."""
    df_raw = pd.read_excel(path, header=None, dtype=str)

    # Find the header row: first row where a cell matches ticker aliases
    header_row_idx = None
    for i, row in df_raw.iterrows():
        row_lower = [str(v).strip().lower() for v in row if pd.notna(v)]
        if any(cell in _TICKER_ALIASES for cell in row_lower):
            header_row_idx = i
            break

    if header_row_idx is None:
        header_row_idx = 0

    headers = [str(v) for v in df_raw.iloc[header_row_idx].tolist()]
    data_rows = df_raw.iloc[header_row_idx + 1:].values.tolist()

    positions = _table_to_positions(headers, data_rows)
    total_value: float | None = None
    if positions:
        vals = [p["value"] for p in positions if p["value"] is not None]
        if vals:
            total_value = sum(vals)

    return {
        "positions":        positions,
        "total_value":      total_value,
        "data_completeness": _determine_completeness(positions),
    }


def _parse_pdf(path: str) -> dict:
    """Extract tables from all pages of a PDF using pdfplumber."""
    import pdfplumber

    all_positions: list[dict] = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                headers = [str(c) if c is not None else "" for c in table[0]]
                rows = table[1:]
                positions = _table_to_positions(headers, rows)
                all_positions.extend(positions)

    # Deduplicate by ticker (keep first occurrence)
    seen = set()
    deduped = []
    for p in all_positions:
        if p["ticker"] not in seen:
            seen.add(p["ticker"])
            deduped.append(p)

    total_value: float | None = None
    vals = [p["value"] for p in deduped if p["value"] is not None]
    if vals:
        total_value = sum(vals)

    return {
        "positions":        deduped,
        "total_value":      total_value,
        "data_completeness": _determine_completeness(deduped),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse(source: Any) -> dict:
    """
    Parse portfolio holdings from various input types.

    Args:
        source: One of:
          - dict: already-structured holdings dict (pass-through)
          - str ending in .xlsx / .xls: Excel file path
          - str ending in .pdf: PDF file path

    Returns:
        Holdings dict with keys: positions, total_value, data_completeness
    """
    if isinstance(source, dict):
        return _parse_dict(source)

    if isinstance(source, str):
        ext = os.path.splitext(source)[1].lower()
        if ext in (".xlsx", ".xls"):
            return _parse_excel(source)
        elif ext == ".pdf":
            return _parse_pdf(source)
        else:
            raise ValueError(f"Unsupported file extension '{ext}'. Supported: .xlsx, .xls, .pdf")

    raise TypeError(f"parse() expects dict or file path str, got {type(source).__name__}")
