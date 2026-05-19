"""
builder.py — Mode 2: Construct 4 portfolios from scratch given investment params.
"""
from __future__ import annotations
from typing import Optional

from screener_picks import get_picks

ARCHETYPE_RULES = {
    "aggressive":    {"equity": 0.93, "bonds": 0.02, "real_assets": 0.02, "cash": 0.03, "reit": 0.00, "max_single": 0.08, "min_positions": 8,  "yield_target": (0.0, 0.01)},
    "balanced":      {"equity": 0.55, "bonds": 0.30, "real_assets": 0.12, "cash": 0.03, "reit": 0.03, "max_single": 0.06, "min_positions": 12, "yield_target": (0.015, 0.025)},
    "conservative":  {"equity": 0.28, "bonds": 0.48, "real_assets": 0.08, "cash": 0.10, "reit": 0.03, "max_single": 0.05, "min_positions": 10, "yield_target": (0.025, 0.035)},
    "income":        {"equity": 0.47, "bonds": 0.20, "real_assets": 0.08, "cash": 0.05, "reit": 0.20, "max_single": 0.05, "min_positions": 10, "yield_target": (0.035, 0.055)},
}

REGIME_TILTS = {
    "Rising Growth + Low Inflation":      {"overweight": ["Technology", "Consumer Discretionary", "Industrials"], "underweight": ["Utilities", "Bonds"]},
    "Rising Growth + Rising Inflation":   {"overweight": ["Energy", "Materials", "Industrials"],                  "underweight": ["Bonds", "Real Estate"]},
    "Stagflation":                        {"overweight": ["Energy", "Utilities", "Real Assets"],                  "underweight": ["Technology", "Consumer Discretionary", "Bonds"]},
    "Deflation / Recession":              {"overweight": ["Utilities", "Healthcare", "Bonds"],                    "underweight": ["Energy", "Financials", "Technology"]},
}

BOND_ETFS = {
    "aggressive":   [],
    "balanced":     [("TLT", 0.15, "Long Treasury"), ("BND", 0.15, "Broad bond")],
    "conservative": [("BND", 0.25, "Broad bond"), ("SGOV", 0.15, "T-bills"), ("TLT", 0.08, "Long Treasury")],
    "income":       [("BND", 0.12, "Broad bond"), ("SGOV", 0.08, "T-bills")],
}

# REIT sleeve (income archetype only)
REIT_ETFS = [("O", 0.10, "Monthly dividend REIT"), ("VNQ", 0.10, "Diversified REIT basket")]

# Real assets sleeve
REAL_ASSETS_ETFS = [("GLD", 1.0, "Gold · inflation + tail hedge")]  # weight is proportion of real_assets allocation

# Cash sleeve
CASH_ETF = ("SGOV", "Cash buffer · deploy on pullbacks")


def _build_one_portfolio(archetype: str, rules: dict, amount: float, regime: str, avoid: list[str]) -> list[dict]:
    """Build a single portfolio's positions list."""
    avoid_set = set(avoid or [])
    positions: dict[str, dict] = {}  # ticker -> {weight, reason, tag}

    # --- Equity sleeve ---
    overweighted_sectors = REGIME_TILTS.get(regime, {}).get("overweight", ["Technology", "Healthcare"])
    raw_picks = get_picks(overweighted_sectors, archetype)

    # Filter avoid tickers
    equity_picks = [p for p in raw_picks if p["ticker"] not in avoid_set]

    # Deduplicate by ticker (keep first occurrence)
    seen: set[str] = set()
    deduped_picks: list[dict] = []
    for p in equity_picks:
        if p["ticker"] not in seen:
            seen.add(p["ticker"])
            deduped_picks.append(p)
    equity_picks = deduped_picks

    if not equity_picks:
        equity_picks = [
            {"ticker": "SPY", "reason": "Core equity ETF", "tag": "screener"},
            {"ticker": "QQQ", "reason": "Core equity ETF", "tag": "screener"},
        ]

    # Equal-weight within equity sleeve, capped at max_single
    max_single = rules["max_single"]
    equity_total = rules["equity"]

    # Fallback equity ETFs to pad when we don't have enough picks
    EQUITY_PADDING = [
        {"ticker": "SPY",  "reason": "Core equity ETF · S&P 500",        "tag": "screener"},
        {"ticker": "QQQ",  "reason": "Core equity ETF · Nasdaq 100",      "tag": "screener"},
        {"ticker": "VTI",  "reason": "Total market ETF",                   "tag": "screener"},
        {"ticker": "IWM",  "reason": "Small cap ETF",                      "tag": "screener"},
        {"ticker": "VEA",  "reason": "Developed markets ETF",              "tag": "screener"},
        {"ticker": "VWO",  "reason": "Emerging markets ETF",               "tag": "screener"},
        {"ticker": "VIG",  "reason": "Dividend growth ETF",                "tag": "screener"},
        {"ticker": "SCHD", "reason": "High-quality dividend ETF",          "tag": "screener"},
        {"ticker": "VUG",  "reason": "Growth ETF",                         "tag": "screener"},
        {"ticker": "VTV",  "reason": "Value ETF",                          "tag": "screener"},
        {"ticker": "MTUM", "reason": "Momentum factor ETF",                "tag": "screener"},
        {"ticker": "QUAL", "reason": "Quality factor ETF",                 "tag": "screener"},
        {"ticker": "MGK",  "reason": "Mega-cap growth ETF",                "tag": "screener"},
        {"ticker": "VO",   "reason": "Mid-cap ETF",                        "tag": "screener"},
        {"ticker": "IJH",  "reason": "S&P 400 mid-cap ETF",               "tag": "screener"},
    ]

    # Ensure we have enough unique picks to fill equity sleeve at max_single
    import math
    min_positions_needed = max(1, math.ceil(equity_total / max_single))
    if len(equity_picks) < min_positions_needed:
        existing_in_picks = {p["ticker"] for p in equity_picks}
        for pad in EQUITY_PADDING:
            if pad["ticker"] not in existing_in_picks and pad["ticker"] not in avoid_set:
                equity_picks.append(pad)
                existing_in_picks.add(pad["ticker"])
            if len(equity_picks) >= min_positions_needed:
                break

    # Compute equal weight per pick, respecting max_single
    n_picks = len(equity_picks)
    equal_w = min(max_single, equity_total / n_picks)

    # Build equity positions
    allocated_equity = 0.0
    for i, p in enumerate(equity_picks):
        remaining_equity = equity_total - allocated_equity
        if remaining_equity < 1e-9:
            break
        w = min(equal_w, remaining_equity, max_single)
        ticker = p["ticker"]
        if ticker not in positions:
            positions[ticker] = {"weight": 0.0, "reason": p.get("reason", "Equity pick"), "tag": p.get("tag", "screener")}
        positions[ticker]["weight"] += w
        allocated_equity += w

    # --- Bond sleeve ---
    for (ticker, w, reason) in BOND_ETFS.get(archetype, []):
        if ticker in avoid_set:
            continue
        if ticker not in positions:
            positions[ticker] = {"weight": 0.0, "reason": reason, "tag": "bond"}
        positions[ticker]["weight"] += w

    # --- Real assets sleeve ---
    real_assets_total = rules["real_assets"]
    for (ticker, proportion, reason) in REAL_ASSETS_ETFS:
        if ticker in avoid_set:
            continue
        w = real_assets_total * proportion
        if ticker not in positions:
            positions[ticker] = {"weight": 0.0, "reason": reason, "tag": "real_asset"}
        positions[ticker]["weight"] += w

    # --- REIT sleeve (income only) ---
    if archetype == "income":
        reit_total = rules["reit"]
        reit_raw_sum = sum(w for _, w, _ in REIT_ETFS)
        for (ticker, raw_w, reason) in REIT_ETFS:
            if ticker in avoid_set:
                continue
            w = (raw_w / reit_raw_sum) * reit_total
            if ticker not in positions:
                positions[ticker] = {"weight": 0.0, "reason": reason, "tag": "reit"}
            positions[ticker]["weight"] += w

    # --- Cash sleeve ---
    cash_ticker, cash_reason = CASH_ETF
    if cash_ticker not in avoid_set:
        if cash_ticker not in positions:
            positions[cash_ticker] = {"weight": 0.0, "reason": cash_reason, "tag": "cash"}
        positions[cash_ticker]["weight"] += rules["cash"]

    # --- Normalize to 1.0, then enforce max_single via redistribution ---
    tickers_list = list(positions.keys())
    total_weight = sum(p["weight"] for p in positions.values())
    if total_weight <= 0:
        total_weight = 1.0

    weights: dict[str, float] = {t: positions[t]["weight"] / total_weight for t in tickers_list}

    # Iteratively cap at max_single and redistribute excess to equity padding positions
    # that are not yet at max_single.
    # We keep a pool of "absorber" tickers that can receive redistributed weight.
    absorber_pool = [
        {"ticker": "SPY",  "reason": "Core equity ETF · S&P 500",   "tag": "screener"},
        {"ticker": "QQQ",  "reason": "Core equity ETF · Nasdaq 100", "tag": "screener"},
        {"ticker": "VTI",  "reason": "Total market ETF",              "tag": "screener"},
        {"ticker": "IWM",  "reason": "Small cap ETF",                 "tag": "screener"},
        {"ticker": "VEA",  "reason": "Developed markets ETF",         "tag": "screener"},
        {"ticker": "VWO",  "reason": "Emerging markets ETF",          "tag": "screener"},
        {"ticker": "VIG",  "reason": "Dividend growth ETF",           "tag": "screener"},
        {"ticker": "SCHD", "reason": "High-quality dividend ETF",     "tag": "screener"},
        {"ticker": "VUG",  "reason": "Growth ETF",                    "tag": "screener"},
        {"ticker": "VTV",  "reason": "Value ETF",                     "tag": "screener"},
        {"ticker": "MTUM", "reason": "Momentum factor ETF",           "tag": "screener"},
        {"ticker": "QUAL", "reason": "Quality factor ETF",            "tag": "screener"},
        {"ticker": "MGK",  "reason": "Mega-cap growth ETF",           "tag": "screener"},
        {"ticker": "VO",   "reason": "Mid-cap ETF",                   "tag": "screener"},
        {"ticker": "IJH",  "reason": "S&P 400 mid-cap ETF",          "tag": "screener"},
        {"ticker": "VNQ",  "reason": "Real estate ETF",               "tag": "screener"},
        {"ticker": "XLF",  "reason": "Financials ETF",                "tag": "screener"},
        {"ticker": "XLV",  "reason": "Healthcare ETF",                "tag": "screener"},
        {"ticker": "XLE",  "reason": "Energy ETF",                    "tag": "screener"},
        {"ticker": "XLI",  "reason": "Industrials ETF",               "tag": "screener"},
    ]

    for _ in range(50):
        excess = sum(max(0.0, w - max_single) for w in weights.values())
        if excess < 1e-9:
            break

        # Cap over-max positions
        new_weights: dict[str, float] = {t: min(w, max_single) for t, w in weights.items()}

        # Find positions below cap that can absorb more
        under_cap = {t: w for t, w in new_weights.items() if w < max_single - 1e-9}

        if not under_cap:
            # Need to add new positions from the absorber pool
            added = False
            for ap in absorber_pool:
                t = ap["ticker"]
                if t not in new_weights and t not in avoid_set:
                    new_weights[t] = 0.0
                    tickers_list.append(t)
                    positions[t] = {"weight": 0.0, "reason": ap["reason"], "tag": ap["tag"]}
                    under_cap[t] = 0.0
                    added = True
                    break
            if not added:
                break

        # Distribute excess proportionally to under-cap positions
        under_total = sum(under_cap.values()) if sum(under_cap.values()) > 0 else len(under_cap)
        if sum(under_cap.values()) > 0:
            for t in under_cap:
                new_weights[t] += excess * (under_cap[t] / under_total)
        else:
            share = excess / len(under_cap)
            for t in under_cap:
                new_weights[t] += share

        weights = new_weights

    # Final normalization to handle floating-point drift
    w_sum = sum(weights.values())
    if w_sum > 0:
        weights = {t: w / w_sum for t, w in weights.items()}

    result: list[dict] = []
    for ticker in tickers_list:
        if ticker not in weights:
            continue
        w = weights[ticker]
        result.append({
            "ticker": ticker,
            "weight": w,
            "value": w * amount,
            "reason": positions[ticker]["reason"],
            "tag": positions[ticker]["tag"],
        })

    return result


def _estimate_metrics(archetype: str) -> dict:
    estimates = {
        "aggressive":   {"beta_est": 1.35, "yield_est": 0.007, "max_dd_est": -0.45, "equity_pct": 0.93},
        "balanced":     {"beta_est": 0.80, "yield_est": 0.020, "max_dd_est": -0.22, "equity_pct": 0.55},
        "conservative": {"beta_est": 0.45, "yield_est": 0.030, "max_dd_est": -0.12, "equity_pct": 0.28},
        "income":       {"beta_est": 0.65, "yield_est": 0.045, "max_dd_est": -0.18, "equity_pct": 0.47},
    }
    return estimates.get(archetype, estimates["balanced"])


def _score_macro_fit(archetype: str, regime: str) -> float:
    fit_matrix = {
        "Rising Growth + Low Inflation":    {"aggressive": 4.8, "balanced": 3.5, "conservative": 2.0, "income": 3.0},
        "Rising Growth + Rising Inflation": {"aggressive": 3.5, "balanced": 4.2, "conservative": 2.5, "income": 3.2},
        "Stagflation":                      {"aggressive": 1.5, "balanced": 3.0, "conservative": 4.5, "income": 3.5},
        "Deflation / Recession":            {"aggressive": 1.0, "balanced": 3.5, "conservative": 4.8, "income": 3.8},
    }
    return fit_matrix.get(regime, {}).get(archetype, 3.0)


def _build_rationale(archetype: str, regime: str, goal: str, horizon_years: int, age: Optional[int]) -> str:
    age_note = f" At age {age}, the 120-minus-age rule suggests {120-age}% equity." if age else ""
    return (
        f"{archetype.title()} portfolio constructed for {goal} goal with {horizon_years}Y horizon. "
        f"Current regime ({regime}) drives sector tilts.{age_note}"
    )


def build_portfolios(
    amount: float,
    profile: str,
    horizon_years: int,
    goal: str,
    macro: dict,
    age: int = None,
    avoid: list[str] = None,
) -> dict:
    """
    Build 4 portfolios (aggressive, balanced, conservative, income) from scratch.

    Returns dict keyed by archetype, each containing positions, total_value,
    target_metrics, macro_fit_score, and rationale.
    """
    regime = macro.get("regime", "Rising Growth + Low Inflation")
    avoid = avoid or []

    result: dict = {}
    for archetype, rules in ARCHETYPE_RULES.items():
        positions = _build_one_portfolio(archetype, rules, amount, regime, avoid)
        result[archetype] = {
            "positions": positions,
            "total_value": amount,
            "target_metrics": _estimate_metrics(archetype),
            "macro_fit_score": _score_macro_fit(archetype, regime),
            "rationale": _build_rationale(archetype, regime, goal, horizon_years, age),
        }

    return result
