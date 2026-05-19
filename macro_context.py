"""
macro_context.py — Fetch 7 macro signals via yfinance + FRED, classify into
Dalio regime, return macro dict.

Public API: get_macro() -> dict
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import requests
import yfinance as yf

SECTOR_ETFS = ["XLK", "XLE", "XLU", "XLF", "XLY"]

_REGIME_PLAN = {
    "Rising Growth + Low Inflation": "aggressive",
    "Rising Growth + Rising Inflation": "balanced",
    "Stagflation": "conservative",
    "Deflation / Recession": "conservative",
}

_REGIME_NARRATIVES = {
    "Rising Growth + Low Inflation": (
        "Markets signal risk-on with low volatility and positive yield curve. "
        "Favor growth and cyclicals."
    ),
    "Rising Growth + Rising Inflation": (
        "Growth continues but inflation is heating up. "
        "Tilt toward inflation hedges and real assets alongside equities."
    ),
    "Stagflation": (
        "Slowing growth with elevated inflation — the worst macro mix. "
        "Defensive positioning, commodities, and short duration preferred."
    ),
    "Deflation / Recession": (
        "Risk-off environment with declining growth and low inflation. "
        "Long-duration bonds, cash, and defensive equities are favored."
    ),
}


# ---------------------------------------------------------------------------
# Pure classification helpers (testable without I/O)
# ---------------------------------------------------------------------------
def _classify_regime(
    vix: float,
    spread_3m10y_bps: float,
    spy_vs_200d_pct: float,
    inflation_pct: float,
) -> str:
    spy_bull = spy_vs_200d_pct > 0
    inflation_high = inflation_pct > 2.5

    if spy_bull and not inflation_high:
        return "Rising Growth + Low Inflation"
    elif spy_bull and inflation_high:
        return "Rising Growth + Rising Inflation"
    elif not spy_bull and inflation_high:
        return "Stagflation"
    else:
        return "Deflation / Recession"


def _plan_for_regime(regime: str) -> str:
    return _REGIME_PLAN.get(regime, "balanced")


# ---------------------------------------------------------------------------
# Signal fetchers — each returns (value, success: bool)
# ---------------------------------------------------------------------------
def _fetch_fast_info(sym: str) -> tuple[float | None, bool]:
    try:
        price = yf.Ticker(sym).fast_info["lastPrice"]
        return float(price), True
    except Exception:
        return None, False


def _fetch_spy_vs_200d() -> tuple[float | None, bool]:
    try:
        df = yf.download("SPY", period="1y", auto_adjust=True)
        if df is None or df.empty or len(df) < 200:
            return None, False
        close = df["Close"].squeeze()
        sma200 = close.rolling(200).mean().iloc[-1]
        last_close = close.iloc[-1]
        pct = float((last_close - sma200) / sma200 * 100)
        return pct, True
    except Exception:
        return None, False


def _fetch_sector_leaders_laggards(spy_1m_ret: float | None) -> tuple[list, list, bool]:
    try:
        tickers = SECTOR_ETFS + ["SPY"]
        df = yf.download(tickers, period="1mo", auto_adjust=True)
        if df is None or df.empty:
            return [], [], False

        if isinstance(df.columns, pd.MultiIndex):
            close = df["Close"]
        else:
            close = df[["Close"]].rename(columns={"Close": "SPY"})

        returns_1m: dict[str, float] = {}
        for t in tickers:
            if t in close.columns:
                col = close[t].dropna()
                if len(col) >= 2:
                    returns_1m[t] = float((col.iloc[-1] - col.iloc[0]) / col.iloc[0])

        spy_ret = returns_1m.get("SPY", spy_1m_ret or 0.0)
        leaders  = [t for t in SECTOR_ETFS if returns_1m.get(t, -999) > spy_ret]
        laggards = [t for t in SECTOR_ETFS if returns_1m.get(t, 999)  < spy_ret]
        return leaders, laggards, True
    except Exception:
        return [], [], False


def _fetch_fed_rate() -> tuple[float | None, bool]:
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        rate = float(df.iloc[-1, 1])
        return rate, True
    except Exception:
        return None, False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_macro() -> dict:
    """
    Fetch all macro signals and return a macro dict.
    On full failure returns safe defaults with data_freshness='stale'.
    On partial failure returns data_freshness='partial'.
    """
    successes: list[bool] = []

    vix,         ok_vix  = _fetch_fast_info("^VIX")
    successes.append(ok_vix)

    tnx,         ok_tnx  = _fetch_fast_info("^TNX")
    successes.append(ok_tnx)

    irx,         ok_irx  = _fetch_fast_info("^IRX")
    successes.append(ok_irx)

    rinf,        ok_rinf = _fetch_fast_info("RINF")
    successes.append(ok_rinf)

    dxy,         ok_dxy  = _fetch_fast_info("DX-Y.NYB")
    successes.append(ok_dxy)

    spy_vs_200d, ok_spy  = _fetch_spy_vs_200d()
    successes.append(ok_spy)

    fed_rate,    ok_fed  = _fetch_fed_rate()
    successes.append(ok_fed)

    # 3M-10Y spread in basis points
    spread_bps: float | None = None
    if ok_tnx and ok_irx and tnx is not None and irx is not None:
        spread_bps = (tnx - irx) * 100

    # Sector leaders/laggards
    leaders, laggards, ok_sectors = _fetch_sector_leaders_laggards(None)
    successes.append(ok_sectors)

    # Data freshness
    n_ok    = sum(successes)
    n_total = len(successes)
    if n_ok == 0:
        freshness = "stale"
    elif n_ok == n_total:
        freshness = "live"
    else:
        freshness = "partial"

    # Safe defaults for missing values
    vix_val         = vix         if vix         is not None else 20.0
    spread_val      = spread_bps  if spread_bps  is not None else 0.0
    spy_vs_200d_val = spy_vs_200d if spy_vs_200d is not None else 0.0
    inflation_val   = rinf        if rinf        is not None else 2.0
    fed_rate_val    = fed_rate    if fed_rate    is not None else 4.75
    dxy_val         = dxy         if dxy         is not None else 100.0

    regime = _classify_regime(vix_val, spread_val, spy_vs_200d_val, inflation_val)

    if freshness == "stale":
        regime = "Rising Growth + Low Inflation"
        plan   = "balanced"
    else:
        plan = _plan_for_regime(regime)

    return {
        "regime":                    regime,
        "vix":                       vix_val,
        "spread_3m10y_bps":          round(spread_val, 2),
        "spy_vs_200d_pct":           round(spy_vs_200d_val, 2),
        "inflation_expectations_pct": round(inflation_val, 2),
        "fed_rate":                  fed_rate_val,
        "dxy":                       round(dxy_val, 2),
        "sector_leaders":            leaders,
        "sector_laggards":           laggards,
        "recommended_plan":          plan,
        "narrative":                 _REGIME_NARRATIVES.get(regime, ""),
        "data_freshness":            freshness,
    }
