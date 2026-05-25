"""Screener core: liquidity gate + scoring + pick selection + cooldown.

Loaded params shape mirrors backtest/optimal_params.json `best`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yfinance as yf

from screener.indicators_tw import score_signals_tw
from screener.patterns import detect_pattern
from screener.support_resistance import suggest_trade_levels

HERE = Path(__file__).resolve().parent
RECENT_PICKS_PATH = HERE / "recent_picks_tw.json"


def apply_liquidity_filter(df: pd.DataFrame, last_close: float,
                           params: dict[str, Any]) -> bool:
    """Return True if ticker passes price range and volume gates."""
    if last_close < params.get("min_price", 10):
        return False
    if last_close > params.get("max_price", 100):
        return False
    avg_vol_k = float(df["Volume"].tail(10).mean()) / 1000.0
    if avg_vol_k < params.get("min_vol_k", 500):
        return False
    return True


@dataclass
class Pick:
    symbol: str
    name_zh: str
    sector: str
    last_close: float
    score: int
    indicators_fired: list[str]
    pattern: str | None
    pattern_confidence: float | None
    entry: float
    stop: float
    target: float
    rr: float
    hold_weeks: int
    params_version: str


def _load_recent() -> dict:
    try:
        return json.loads(RECENT_PICKS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"picks": []}


def _save_recent(d: dict) -> None:
    RECENT_PICKS_PATH.write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_on_cooldown(symbol: str, weeks: int = 2) -> bool:
    data = _load_recent()
    cutoff = datetime.utcnow() - timedelta(weeks=weeks)
    for p in data.get("picks", []):
        if p["symbol"] == symbol:
            try:
                dt = datetime.fromisoformat(p["date"])
                if dt > cutoff:
                    return True
            except Exception:
                pass
    return False


def record_picks(picks: Iterable[Pick]) -> None:
    data = _load_recent()
    today = datetime.utcnow().date().isoformat()
    for p in picks:
        data["picks"].append({"symbol": p.symbol, "date": today,
                              "score": p.score})
    # prune anything older than 8 weeks
    cutoff = datetime.utcnow() - timedelta(weeks=8)
    data["picks"] = [
        x for x in data["picks"]
        if datetime.fromisoformat(x["date"]) > cutoff
    ]
    _save_recent(data)


def _fetch(symbol: str) -> pd.DataFrame | None:
    try:
        df = yf.download(symbol, period="3y", interval="1wk",
                         auto_adjust=True, progress=False)
        if df is None or df.empty or len(df) < 60:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception:
        return None


def evaluate_ticker(symbol: str, name_zh: str, sector: str,
                    params: dict[str, Any]) -> Pick | None:
    df = _fetch(symbol)
    if df is None:
        return None
    last_close = float(df["Close"].iloc[-1])
    if not apply_liquidity_filter(df, last_close, params):
        return None
    scored = score_signals_tw(df, params)
    if not scored["gates_ok"]:
        return None
    if scored["score"] < params.get("min_score", 6):
        return None
    levels = suggest_trade_levels(df,
                                  target_mult=params.get("target_mult", 2.5),
                                  min_rr=params.get("min_rr", 2.0))
    if levels["entry"] is None or levels["rr"] is None:
        return None
    if levels["rr"] < params.get("min_rr", 2.0):
        return None
    pat = detect_pattern(df) or {}
    fired = [k for k, v in scored["signals"].items() if v["fired"]]
    return Pick(
        symbol=symbol, name_zh=name_zh, sector=sector,
        last_close=last_close, score=scored["score"],
        indicators_fired=fired,
        pattern=pat.get("pattern"),
        pattern_confidence=pat.get("confidence"),
        entry=float(levels["entry"]),
        stop=float(levels["stop"]),
        target=float(levels["target"]),
        rr=float(levels["rr"]),
        hold_weeks=int(params.get("hold_weeks", 5)),
        params_version=params.get("params_version", "default"),
    )


def select_top(picks: list[Pick], n: int = 3,
               cooldown_weeks: int = 2) -> list[Pick]:
    candidates = [p for p in picks if not _is_on_cooldown(p.symbol, cooldown_weeks)]
    candidates.sort(key=lambda p: (p.score, p.rr,
                                    p.pattern_confidence or 0), reverse=True)
    return candidates[:n]
