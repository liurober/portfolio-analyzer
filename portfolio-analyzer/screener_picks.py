"""
screener_picks.py — Select stock picks for portfolio restructuring plans.

Priority:
  1. analysis.json (fresh screener output, if < 7 days old + direction='long')
  2. Live yfinance scoring (price > 30D SMA, RSI 40-70, 1M return > 0)
  3. ETF fallbacks (always appended, curated per plan_type)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Path to analysis.json — patchable in tests
# ---------------------------------------------------------------------------
ANALYSIS_JSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "stock-screener", "analysis.json"
)

# ---------------------------------------------------------------------------
# ETF fallbacks by plan type
# ---------------------------------------------------------------------------
ETF_FALLBACKS: dict[str, list[dict]] = {
    "aggressive": [
        {"ticker": "QQQ",  "score": 5, "source": "ETF", "sector": "Technology",   "reason": "Nasdaq100 core · diversified mega-cap",         "tag": "ETF"},
        {"ticker": "SOXX", "score": 5, "source": "ETF", "sector": "Technology",   "reason": "Semiconductor basket · sector breadth",          "tag": "ETF"},
        {"ticker": "SPY",  "score": 5, "source": "ETF", "sector": "Broad Market", "reason": "S&P500 base layer · market beta",                "tag": "ETF"},
    ],
    "balanced": [
        {"ticker": "VTI",  "score": 5, "source": "ETF", "sector": "Broad Market", "reason": "Total market · core equity sleeve",             "tag": "ETF"},
        {"ticker": "TLT",  "score": 5, "source": "ETF", "sector": "Bonds",        "reason": "Long-duration Treasury · deflation hedge",      "tag": "ETF"},
        {"ticker": "GLD",  "score": 5, "source": "ETF", "sector": "Real Assets",  "reason": "Gold · stagflation + tail hedge",               "tag": "ETF"},
        {"ticker": "PDBC", "score": 5, "source": "ETF", "sector": "Real Assets",  "reason": "Diversified commodities · inflation hedge",     "tag": "ETF"},
    ],
    "conservative": [
        {"ticker": "BND",  "score": 5, "source": "ETF", "sector": "Bonds",        "reason": "Broad bond market · capital preservation",      "tag": "ETF"},
        {"ticker": "SGOV", "score": 5, "source": "ETF", "sector": "Cash",         "reason": "0-3M T-bills · max liquidity",                  "tag": "ETF"},
        {"ticker": "USMV", "score": 5, "source": "ETF", "sector": "Broad Market", "reason": "Min volatility equity · low drawdown",          "tag": "ETF"},
        {"ticker": "GLD",  "score": 5, "source": "ETF", "sector": "Real Assets",  "reason": "Gold hedge",                                    "tag": "ETF"},
    ],
    "income": [
        {"ticker": "SCHD", "score": 5, "source": "ETF", "sector": "Dividend",     "reason": "High-quality dividend · 3.5% yield",            "tag": "ETF"},
        {"ticker": "JEPI", "score": 5, "source": "ETF", "sector": "Dividend",     "reason": "Covered call income · 7%+ yield",               "tag": "ETF"},
        {"ticker": "O",    "score": 5, "source": "ETF", "sector": "REITs",        "reason": "Monthly dividend REIT · 5.5% yield",            "tag": "REIT"},
        {"ticker": "VNQ",  "score": 5, "source": "ETF", "sector": "REITs",        "reason": "Diversified REIT basket",                       "tag": "REIT"},
    ],
}

# ---------------------------------------------------------------------------
# Sector → candidate tickers for live scoring
# ---------------------------------------------------------------------------
SECTOR_TICKERS: dict[str, list[str]] = {
    "Technology":             ["NVDA", "AVGO", "MSFT", "AAPL", "META", "GOOGL", "AMD", "AMAT", "KLAC", "RBRK"],
    "Financial Services":     ["JPM",  "BAC",  "GS",   "MS",   "V",    "MA",    "BLK", "SCHW", "WFC",  "COF"],
    "Healthcare":             ["UNH",  "LLY",  "JNJ",  "ABBV", "MRK",  "TMO",   "ABT", "DHR",  "ISRG", "REGN"],
    "Energy":                 ["XOM",  "CVX",  "COP",  "SLB",  "EOG",  "MPC",   "PSX", "VLO",  "OXY",  "HAL"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD",   "MCD",  "NKE",  "SBUX",  "TJX", "BKNG", "LOW",  "ROST"],
    "Industrials":            ["CAT",  "DE",   "HON",  "UPS",  "LMT",  "RTX",   "BA",  "GE",   "EMR",  "ITW"],
    "Utilities":              ["NEE",  "DUK",  "SO",   "D",    "AEP",  "EXC",   "SRE", "ED",   "XEL",  "PEG"],
    "Real Estate":            ["PLD",  "AMT",  "EQIX", "PSA",  "SPG",  "O",     "DLR", "AVB",  "VTR",  "EQR"],
}


# ---------------------------------------------------------------------------
# Step 1: Check analysis.json
# ---------------------------------------------------------------------------
def _check_analysis_json(sectors_needed: list[str]) -> list[dict]:
    try:
        if not os.path.exists(ANALYSIS_JSON_PATH):
            return []
        with open(ANALYSIS_JSON_PATH) as f:
            data = json.load(f)

        ticker    = data.get("ticker", "")
        as_of_str = data.get("as_of", "")
        sector    = data.get("sector", "")
        direction = data.get("technicals", {}).get("direction", "")
        score_raw = data.get("technicals", {}).get("score_long", "0")

        try:
            as_of = datetime.fromisoformat(as_of_str)
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return []

        age_days = (datetime.now(timezone.utc) - as_of).total_seconds() / 86400

        if age_days > 7:
            return []
        if direction.lower() != "long":
            return []
        if sector not in sectors_needed:
            return []

        score = int(score_raw) if str(score_raw).isdigit() else 0

        return [{
            "ticker": ticker.upper(),
            "score":  score,
            "source": "screener",
            "sector": sector,
            "reason": f"Score {score}/6 · screener pick",
            "tag":    "screener",
        }]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Step 2: Live yfinance scoring
# ---------------------------------------------------------------------------
def _rsi(series: pd.Series, period: int = 14) -> float:
    delta    = series.diff().dropna()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    return float(100 - (100 / (1 + avg_gain / avg_loss)))


def _score_ticker_live(ticker: str) -> int | None:
    """Score 0-3: +1 price>30D SMA, +1 RSI 40-70, +1 1M return>0."""
    try:
        df = yf.download(ticker, period="3mo", auto_adjust=True)
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            if "Close" in df.columns.get_level_values(0):
                close = df["Close"].squeeze()
            else:
                return None
        else:
            close = df["Close"]

        close = close.dropna()
        if len(close) < 31:
            return None

        score = 0
        sma30  = close.rolling(30).mean().iloc[-1]
        last   = close.iloc[-1]
        ret_1m = (close.iloc[-1] - close.iloc[-22]) / close.iloc[-22] if len(close) >= 22 else 0

        if last > sma30:
            score += 1
        if 40 <= _rsi(close) <= 70:
            score += 1
        if ret_1m > 0:
            score += 1

        return score
    except Exception:
        return None


def _get_live_picks(sectors_needed: list[str], existing_tickers: set[str], n_per_sector: int) -> list[dict]:
    picks: list[dict] = []
    for sector in sectors_needed:
        candidates = SECTOR_TICKERS.get(sector, [])
        scored: list[tuple[str, int]] = []
        for ticker in candidates:
            if ticker in existing_tickers:
                continue
            s = _score_ticker_live(ticker)
            if s is not None:
                scored.append((ticker, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        for ticker, score in scored[:n_per_sector]:
            picks.append({
                "ticker": ticker,
                "score":  score,
                "source": "live",
                "sector": sector,
                "reason": f"Live score {score}/3 · {sector}",
                "tag":    "live",
            })
    return picks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_picks(sectors_needed: list[str], plan_type: str, n_per_sector: int = 3) -> list[dict]:
    """
    Return stock picks for the given sectors and plan type.

    Returns: list of {ticker, score, source, sector, reason, tag}
    """
    picks: list[dict] = []

    # Step 1: screener (analysis.json)
    screener = _check_analysis_json(sectors_needed)
    picks.extend(screener)
    existing_tickers = {p["ticker"] for p in picks}

    # Step 2: live scoring
    live = _get_live_picks(sectors_needed, existing_tickers, n_per_sector)
    picks.extend(live)

    # Step 3: ETF fallbacks — always appended
    fallbacks = ETF_FALLBACKS.get(plan_type, ETF_FALLBACKS["balanced"])
    picks.extend(fallbacks)

    return picks
