"""US-ETF correlation, institutional holders, and analyst consensus for TW tickers.

Scoring lookup:
- SOXX correlation > 0.85 AND has institutions  -> 9.0
- SOXX correlation 0.70 - 0.85                  -> 7.0
- SOXX correlation < 0.50                       -> 4.0
- No correlation data available                 -> 5.0 (neutral)
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yfinance as yf

US_BENCH = ["QQQ", "SOXX", "SPY", "AMAT"]


@dataclass
class InstitutionReport:
    correlations: dict[str, float | None]
    holders: list[dict]
    analyst: dict
    score: float
    label_zh: str


def _label(corr: float | None) -> str:
    if corr is None:
        return "資料不足"
    if corr > 0.80:
        return "高度正相關"
    if corr > 0.60:
        return "中度正相關"
    return "低度正相關"


def _weekly_returns(ticker: str, period: str = "2y") -> pd.Series | None:
    try:
        df = yf.download(ticker, period=period, interval="1wk",
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close.pct_change().dropna()
    except Exception:
        return None


def correlations_for(symbol: str) -> dict[str, float | None]:
    tw_ret = _weekly_returns(symbol)
    if tw_ret is None or len(tw_ret) < 30:
        return {b: None for b in US_BENCH}
    out: dict[str, float | None] = {}
    for b in US_BENCH:
        us_ret = _weekly_returns(b)
        if us_ret is None or len(us_ret) < 30:
            out[b] = None
            continue
        joined = pd.concat([tw_ret.rename("tw"), us_ret.rename("us")],
                           axis=1, join="inner").dropna()
        if len(joined) < 30:
            out[b] = None
            continue
        out[b] = float(joined["tw"].corr(joined["us"]))
    return out


def holders_for(symbol: str) -> list[dict]:
    try:
        tk = yf.Ticker(symbol)
        df = tk.institutional_holders
        if df is None or df.empty:
            return []
        rows = []
        for _, r in df.head(5).iterrows():
            rows.append({
                "holder": str(r.get("Holder", "")),
                "shares": int(r.get("Shares", 0) or 0),
                "pct": float(r.get("% Out", r.get("pctHeld", 0)) or 0),
            })
        return rows
    except Exception:
        return []


def analyst_for(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info or {}
        return {
            "recommendation": info.get("recommendationKey", "n/a"),
            "target_mean": info.get("targetMeanPrice"),
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "num_analysts": info.get("numberOfAnalystOpinions"),
        }
    except Exception:
        return {}


def score_institution(corrs: dict[str, float | None],
                      holders: list[dict]) -> tuple[float, str]:
    soxx = corrs.get("SOXX")
    has_holders = bool(holders)
    if soxx is None:
        return 5.0, _label(None)
    if soxx > 0.85 and has_holders:
        return 9.0, _label(soxx)
    if 0.70 <= soxx <= 0.85:
        return 7.0, _label(soxx)
    if soxx < 0.50:
        return 4.0, _label(soxx)
    return 6.0, _label(soxx)


def report_for(symbol: str) -> InstitutionReport:
    """Full institution report — makes live yfinance calls."""
    corrs = correlations_for(symbol)
    holders = holders_for(symbol)
    analyst = analyst_for(symbol)
    score, label = score_institution(corrs, holders)
    return InstitutionReport(
        correlations=corrs, holders=holders, analyst=analyst,
        score=score, label_zh=label,
    )
