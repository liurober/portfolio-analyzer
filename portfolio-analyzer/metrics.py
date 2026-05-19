"""
metrics.py — Compute portfolio risk/return/concentration metrics.

Public API:
    compute_metrics(holdings: dict, risk_free_rate: float = 0.045) -> dict
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Asset class membership
# ---------------------------------------------------------------------------
_BOND_TICKERS = {"BND", "AGG", "TLT", "IEF", "SHY", "SGOV", "BIL", "TIPS", "VTIP", "SCHP"}
_ALT_TICKERS  = {"GLD", "IAU", "SLV", "PDBC", "DJP", "REET", "VNQ", "IYR"}


def _asset_class(ticker: str) -> str:
    t = ticker.upper()
    if t in _BOND_TICKERS:
        return "bond"
    if t in _ALT_TICKERS:
        return "alt"
    return "equity"


def _cap_size(market_cap: float | None) -> str:
    if market_cap is None:
        return "large"
    if market_cap >= 10e9:
        return "large"
    if market_cap >= 2e9:
        return "mid"
    return "small"


# ---------------------------------------------------------------------------
# Price history download
# ---------------------------------------------------------------------------
def _download_prices(tickers: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """
    Download 1Y daily adjusted closing prices for tickers + SPY.
    Returns (close_df, skipped_tickers). close_df has flat ticker columns.
    """
    all_tickers = list(set(tickers + ["SPY"]))
    try:
        raw = yf.download(all_tickers, period="1y", auto_adjust=True)
    except Exception:
        return pd.DataFrame(), tickers[:]

    if raw is None or raw.empty:
        return pd.DataFrame(), tickers[:]

    # Normalize to flat columns of close prices
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            close = raw["Close"]
        else:
            close = raw.iloc[:, raw.columns.get_level_values(0) == raw.columns.get_level_values(0)[0]]
            close.columns = close.columns.droplevel(0)
    else:
        close = raw

    # Identify skipped tickers
    skipped: list[str] = []
    for t in tickers:
        if t not in close.columns or close[t].dropna().empty:
            skipped.append(t)

    return close, skipped


# ---------------------------------------------------------------------------
# Concentration metrics
# ---------------------------------------------------------------------------
def _compute_concentration(positions: list[dict]) -> dict:
    weights = [p["weight"] for p in positions if p.get("weight") is not None]
    if not weights:
        return {"top_position_pct": 0.0, "top5_combined_pct": 0.0, "largest_sector_pct": 0.0, "hhi": 0, "num_positions": 0}

    weights_sorted = sorted(weights, reverse=True)
    top5 = sum(weights_sorted[:5])
    hhi = int(sum((w * 100) ** 2 for w in weights))

    return {
        "top_position_pct":   weights_sorted[0],
        "top5_combined_pct":  min(top5, 1.0),
        "largest_sector_pct": 0.0,  # populated later after sector data
        "hhi":                hhi,
        "num_positions":      len(weights),
    }


# ---------------------------------------------------------------------------
# Risk metrics
# ---------------------------------------------------------------------------
def _compute_risk(positions: list[dict], close: pd.DataFrame, skipped: list[str], total_value: float | None) -> dict:
    valid = [p for p in positions if p["ticker"] not in skipped and p["ticker"] in close.columns]
    if not valid:
        return {"portfolio_beta": None, "annualized_vol": None, "max_drawdown": None, "var_95_1d": None, "avg_correlation": None}

    total_w = sum(p["weight"] for p in valid)
    norm_weights = np.array([p["weight"] / total_w for p in valid])
    tickers_valid = [p["ticker"] for p in valid]

    returns = close[tickers_valid].pct_change().dropna()
    spy_returns = close["SPY"].pct_change().dropna() if "SPY" in close.columns else None

    if spy_returns is not None:
        common_idx = returns.index.intersection(spy_returns.index)
        returns = returns.loc[common_idx]
        spy_returns = spy_returns.loc[common_idx]

    port_returns = returns.values @ norm_weights

    beta: float | None = None
    if spy_returns is not None and len(port_returns) > 10:
        spy_arr = spy_returns.values
        cov = np.cov(port_returns, spy_arr)
        if cov[1, 1] != 0:
            beta = float(cov[0, 1] / cov[1, 1])

    ann_vol = float(port_returns.std() * math.sqrt(252))

    cum = (1 + pd.Series(port_returns)).cumprod()
    rolling_max = cum.cummax()
    drawdown = (cum - rolling_max) / rolling_max
    max_dd = float(drawdown.min())

    var_95_1d: float | None = None
    if total_value is not None:
        daily_vol = ann_vol / math.sqrt(252)
        var_95_1d = round(total_value * daily_vol * 1.645, 2)

    avg_corr: float | None = None
    if returns.shape[1] > 1:
        corr_matrix = returns.corr().values
        upper = corr_matrix[np.triu_indices_from(corr_matrix, k=1)]
        avg_corr = float(upper.mean()) if len(upper) > 0 else None

    return {
        "portfolio_beta":  round(beta, 4) if beta is not None else None,
        "annualized_vol":  round(ann_vol, 4),
        "max_drawdown":    round(max_dd, 4),
        "var_95_1d":       var_95_1d,
        "avg_correlation": round(avg_corr, 4) if avg_corr is not None else None,
    }


# ---------------------------------------------------------------------------
# Return quality metrics
# ---------------------------------------------------------------------------
def _compute_return_quality(
    positions: list[dict],
    close: pd.DataFrame,
    skipped: list[str],
    total_value: float | None,
    risk_free_rate: float,
    risk_metrics: dict,
) -> dict:
    if total_value is None:
        return {"sharpe": None, "sortino": None, "calmar": None, "return_1y": None, "alpha": None}

    valid = [p for p in positions if p["ticker"] not in skipped and p["ticker"] in close.columns]
    if not valid:
        return {"sharpe": None, "sortino": None, "calmar": None, "return_1y": None, "alpha": None}

    total_w = sum(p["weight"] for p in valid)
    norm_weights = np.array([p["weight"] / total_w for p in valid])
    tickers_valid = [p["ticker"] for p in valid]

    returns = close[tickers_valid].pct_change().dropna()
    port_returns = pd.Series(returns.values @ norm_weights, index=returns.index)

    ann_return = float((1 + port_returns).prod() ** (252 / len(port_returns)) - 1)
    ann_vol = risk_metrics.get("annualized_vol") or float(port_returns.std() * math.sqrt(252))
    max_dd  = risk_metrics.get("max_drawdown") or -1e-6
    beta    = risk_metrics.get("portfolio_beta") or 1.0

    spy_ann = 0.0
    if "SPY" in close.columns:
        spy_r = close["SPY"].pct_change().dropna()
        common = port_returns.index.intersection(spy_r.index)
        spy_r = spy_r.loc[common]
        if len(spy_r) > 10:
            spy_ann = float((1 + spy_r).prod() ** (252 / len(spy_r)) - 1)

    sharpe = sortino = calmar = alpha = None

    if ann_vol > 0:
        sharpe = round((ann_return - risk_free_rate) / ann_vol, 4)

    downside = port_returns[port_returns < 0]
    if len(downside) > 1:
        down_vol = float(downside.std() * math.sqrt(252))
        if down_vol > 0:
            sortino = round((ann_return - risk_free_rate) / down_vol, 4)

    if max_dd != 0:
        calmar = round(ann_return / abs(max_dd), 4)

    alpha = round(ann_return - (risk_free_rate + beta * (spy_ann - risk_free_rate)), 4)

    return {
        "sharpe":    sharpe,
        "sortino":   sortino,
        "calmar":    calmar,
        "return_1y": round(ann_return, 4),
        "alpha":     alpha,
    }


# ---------------------------------------------------------------------------
# Income / style metrics
# ---------------------------------------------------------------------------
def _compute_income_style(positions: list[dict], total_value: float | None) -> dict:
    large_w = mid_w = small_w = 0.0
    equity_w = bond_w = alt_w = 0.0
    weighted_yield = 0.0
    total_w = sum(p["weight"] for p in positions) or 1.0

    for p in positions:
        w = p["weight"] / total_w
        ac = _asset_class(p["ticker"])
        if ac == "bond":
            bond_w += w
        elif ac == "alt":
            alt_w += w
        else:
            equity_w += w

        try:
            info = yf.Ticker(p["ticker"]).info
            mkt_cap   = info.get("marketCap")
            raw_yield = info.get("dividendYield") or 0.0
            # clamp: yfinance occasionally returns total-return or stale values > 20%
            div_yield = float(raw_yield) if 0.0 <= float(raw_yield) <= 0.20 else 0.0
            weighted_yield += w * div_yield
            cap = _cap_size(mkt_cap)
            if cap == "large":
                large_w += w
            elif cap == "mid":
                mid_w += w
            else:
                small_w += w
        except Exception:
            large_w += w

    annual_income: float | None = None
    if total_value is not None:
        annual_income = round(total_value * weighted_yield, 2)

    return {
        "weighted_yield":    round(weighted_yield, 4),
        "annual_income_est": annual_income,
        "large_cap_pct":     round(large_w, 4),
        "mid_cap_pct":       round(mid_w, 4),
        "small_cap_pct":     round(small_w, 4),
        "domestic_pct":      1.0,
        "intl_pct":          0.0,
        "equity_pct":        round(equity_w, 4),
        "bond_pct":          round(bond_w, 4),
        "alt_pct":           round(alt_w, 4),
        "cash_pct":          0.0,
    }


# ---------------------------------------------------------------------------
# Risk parity
# ---------------------------------------------------------------------------
def _compute_risk_parity(positions: list[dict], close: pd.DataFrame, skipped: list[str]) -> dict:
    valid = [p for p in positions if p["ticker"] not in skipped and p["ticker"] in close.columns]
    if not valid:
        return {"positions": [], "sectors": [], "equity_risk_pct": None, "implied_leverage": None}

    total_w = sum(p["weight"] for p in valid)
    weights = np.array([p["weight"] / total_w for p in valid])
    tickers_valid = [p["ticker"] for p in valid]

    returns = close[tickers_valid].pct_change().dropna()
    cov = returns.cov().values
    port_var = float(weights @ cov @ weights)

    if port_var == 0:
        risk_contribs = weights.copy()
    else:
        marginal = cov @ weights
        risk_contribs = weights * marginal / port_var

    total_rc = risk_contribs.sum()
    if total_rc > 0:
        risk_contribs = risk_contribs / total_rc

    pos_parity = [
        {
            "ticker":          p["ticker"],
            "capital_weight":  round(float(w), 4),
            "risk_contribution": round(float(rc), 4),
        }
        for p, w, rc in zip(valid, weights, risk_contribs)
    ]

    equity_rc = sum(
        rc for p, rc in zip(valid, risk_contribs)
        if _asset_class(p["ticker"]) == "equity"
    )

    return {
        "positions":       pos_parity,
        "sectors":         [],
        "equity_risk_pct": round(float(equity_rc), 4),
        "implied_leverage": 1.0,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_metrics(holdings: dict, risk_free_rate: float = 0.045) -> dict:
    """
    Compute full portfolio metrics from a holdings dict.

    Args:
        holdings: Holdings dict with 'positions', 'total_value', 'data_completeness'
        risk_free_rate: Annual risk-free rate (default 4.5%)

    Returns:
        Metrics dict with keys: concentration, risk, return_quality, income_style,
        risk_parity, skipped_tickers
    """
    positions = holdings.get("positions", [])
    total_value = holdings.get("total_value")

    _empty = {
        "concentration": {"top_position_pct": 0, "top5_combined_pct": 0, "largest_sector_pct": 0, "hhi": 0, "num_positions": 0},
        "risk": {"portfolio_beta": None, "annualized_vol": None, "max_drawdown": None, "var_95_1d": None, "avg_correlation": None},
        "return_quality": {"sharpe": None, "sortino": None, "calmar": None, "return_1y": None, "alpha": None},
        "income_style": {"weighted_yield": 0, "annual_income_est": None, "large_cap_pct": 0, "mid_cap_pct": 0, "small_cap_pct": 0, "domestic_pct": 0, "intl_pct": 0, "equity_pct": 0, "bond_pct": 0, "alt_pct": 0, "cash_pct": 0},
        "risk_parity": {"positions": [], "sectors": [], "equity_risk_pct": None, "implied_leverage": None},
        "skipped_tickers": [],
    }

    if not positions:
        return _empty

    tickers = [p["ticker"] for p in positions]
    close, skipped = _download_prices(tickers)

    concentration  = _compute_concentration(positions)
    risk           = _compute_risk(positions, close, skipped, total_value)
    return_quality = _compute_return_quality(positions, close, skipped, total_value, risk_free_rate, risk)
    income_style   = _compute_income_style(positions, total_value)
    risk_parity    = _compute_risk_parity(positions, close, skipped)

    return {
        "concentration":  concentration,
        "risk":           risk,
        "return_quality": return_quality,
        "income_style":   income_style,
        "risk_parity":    risk_parity,
        "skipped_tickers": skipped,
    }
