"""obsidian.py — Write YAML-frontmattered Obsidian notes for portfolio analysis."""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime

VAULT_BASE = (
    "/Users/robertliu/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
    "Rob's Valut/Rob's Personal Vault"
)

SUBFOLDER = "Trading/Portfolio Analysis"


def _fmt(value, multiplier=1, decimals=2, suffix="", prefix="", fallback="N/A"):
    """Format a numeric value with optional multiplier and rounding."""
    if value is None:
        return fallback
    try:
        result = round(float(value) * multiplier, decimals)
        return f"{prefix}{result}{suffix}"
    except (TypeError, ValueError):
        return fallback


def _fmt_currency(value, fallback="N/A"):
    if value is None:
        return fallback
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return fallback


def save_note(
    holdings: dict,
    macro: dict,
    metrics: dict,
    analysis: dict,
    date_str: str,
    mode: str = "analyze",
    build_params: dict = None,
) -> str:
    """Save a portfolio review note to the Obsidian vault.

    Args:
        holdings: Portfolio holdings dict (expects "total_value" key).
        macro: Macro context dict from macro_context.py.
        metrics: Portfolio metrics dict from metrics.py.
        analysis: Analysis dict with implicit_bet, red_flags, green_flags.
        date_str: ISO date string "YYYY-MM-DD".
        mode: "analyze" or "build".
        build_params: For build mode — dict with amount, profile, horizon, goal.

    Returns:
        Absolute path of the saved note.
    """
    vault_base = Path(VAULT_BASE)
    if not vault_base.exists():
        raise FileNotFoundError(
            f"Obsidian vault not found at {vault_base}. "
            "Ensure iCloud is running and the vault path is accessible."
        )

    save_dir = vault_base / SUBFOLDER
    save_dir.mkdir(parents=True, exist_ok=True)

    filename = (
        f"{date_str}-portfolio-review.md"
        if mode == "analyze"
        else f"{date_str}-portfolio-build.md"
    )
    note_path = save_dir / filename

    # --- Extract values ---
    total_value = _fmt_currency(holdings.get("total_value"))
    sharpe_raw = metrics.get("return_quality", {}).get("sharpe")
    sharpe = _fmt(sharpe_raw, decimals=2)
    beta_raw = metrics.get("risk", {}).get("portfolio_beta")
    beta = _fmt(beta_raw, decimals=2)
    max_dd_raw = metrics.get("risk", {}).get("max_drawdown")
    max_drawdown = _fmt(max_dd_raw, multiplier=100, decimals=1)
    vol_raw = metrics.get("risk", {}).get("annualized_vol")
    vol = _fmt(vol_raw, multiplier=100, decimals=1)
    avg_corr_raw = metrics.get("concentration", {}).get("avg_pairwise_corr")
    avg_corr = _fmt(avg_corr_raw, decimals=2)
    yield_raw = metrics.get("income_style", {}).get("weighted_yield")
    weighted_yield = _fmt(yield_raw, multiplier=100, decimals=2)

    regime = macro.get("regime", "Unknown")
    recommended_plan = macro.get("recommended_plan", "balanced")
    vix_raw = macro.get("vix", "N/A")
    vix = f"{vix_raw:.2f}" if isinstance(vix_raw, (int, float)) else vix_raw
    spread = macro.get("spread_3m10y_bps", "N/A")
    spy_vs_200d = macro.get("spy_vs_200d_pct", "N/A")
    narrative = macro.get("narrative", "")

    implicit_bet = analysis.get("implicit_bet", "")
    red_flags = analysis.get("red_flags", [])
    green_flags = analysis.get("green_flags", [])

    # --- Parse date for heading ---
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        month_year = dt.strftime("%B %Y")
    except ValueError:
        month_year = date_str

    # --- Build YAML frontmatter ---
    fm_lines = [
        "---",
        "tags:",
        "  - portfolio-analysis",
        "  - equity",
        "  - trading",
        "  - review",
        f"date: {date_str}",
        "stream: Trading / Finance",
        f"total_value: {total_value}",
        f"sharpe: {sharpe}",
        f"beta: {beta}",
        f"max_drawdown: {max_drawdown}%",
        f"current_regime: {regime}",
        f"recommended_plan: {recommended_plan}",
        f"report_html: ~/portfolio-reports/{date_str}-analysis.html",
    ]

    if mode == "build" and build_params:
        amount = _fmt_currency(build_params.get("amount"))
        profile = build_params.get("profile", "")
        horizon = build_params.get("horizon", "")
        goal = build_params.get("goal", "")
        fm_lines += [
            "mode: build",
            f"investment_amount: {amount}",
            f"risk_profile: {profile}",
            f"time_horizon: {horizon}y",
            f"goal: {goal}",
        ]

    fm_lines.append("---")
    frontmatter = "\n".join(fm_lines)

    # --- Build red flags section ---
    if red_flags:
        rf_lines = []
        for i, flag in enumerate(red_flags, 1):
            if isinstance(flag, dict):
                text = flag.get("flag") or flag.get("message") or flag.get("text") or str(flag)
                impact = flag.get("impact_est", "")
                impact_tag = f" `{impact}`" if impact else ""
            else:
                text = str(flag)
                impact_tag = ""
            rf_lines.append(f"{i}. {text}{impact_tag}")
        red_flags_text = "\n".join(rf_lines)
    else:
        red_flags_text = "_None identified._"

    # --- Build green flags section ---
    if green_flags:
        gf_lines = [f"- {str(flag)}" for flag in green_flags]
        green_flags_text = "\n".join(gf_lines)
    else:
        green_flags_text = "_None identified._"

    # --- Build restructuring plans section ---
    plans = analysis.get("plans", {})
    plans_lines = []
    plan_order = ["aggressive", "balanced", "conservative", "income"]
    for plan_name in plan_order:
        plan = plans.get(plan_name)
        if not plan:
            continue
        fit = plan.get("fit_grade", "")
        fit_str = f" · Fit: **{fit}**" if fit else ""
        plans_lines.append(f"\n### {plan_name.title()} Plan{fit_str}")
        if plan.get("rationale"):
            plans_lines.append(f"_{plan['rationale']}_\n")
        sells = plan.get("sell", [])
        if sells:
            plans_lines.append("**Sell / Reduce**\n")
            plans_lines.append("| Ticker | Action | Proceeds | Reason |")
            plans_lines.append("|--------|--------|----------|--------|")
            for s in sells:
                proceeds = s.get("proceeds", s.get("freed_dollars", 0))
                reason = s.get("reason", "").replace("|", "\\|")
                plans_lines.append(f"| **{s['ticker']}** | {s.get('action','')} | ${proceeds:,.0f} | {reason} |")
        buys = plan.get("buy", [])
        if buys:
            plans_lines.append("\n**Buy**\n")
            plans_lines.append("| Ticker | % Port | $ Amount | Reason |")
            plans_lines.append("|--------|--------|----------|--------|")
            for b in buys:
                pct = b.get("pct", b.get("target_pct", 0))
                if pct > 1:
                    pct = pct / 100
                reason = b.get("reason", "").replace("|", "\\|")
                plans_lines.append(f"| **{b['ticker']}** | {pct:.1%} | ${b.get('dollars',0):,.0f} | {reason} |")
        holds = plan.get("hold", [])
        if holds:
            plans_lines.append("\n**Hold**\n")
            for h in holds:
                reason = h.get("reason", "").replace("|", "\\|")
                plans_lines.append(f"- **{h['ticker']}** — {reason}")
        macro_grid = plan.get("macro_grid", {})
        if macro_grid:
            plans_lines.append("\n**Macro Grid (post-restructure)**\n")
            plans_lines.append("| Regime | Est. Impact |")
            plans_lines.append("|--------|-------------|")
            for regime_name, impact in macro_grid.items():
                plans_lines.append(f"| {regime_name} | {impact} |")
    plans_text = "\n".join(plans_lines) if plans_lines else "_No restructuring plans generated._"

    # --- Build markdown body ---
    body = f"""# Portfolio Review — {month_year}

## Market Context
**Regime:** {regime}
**VIX:** {vix} | **3M-10Y Spread:** {spread} bps | **SPY vs 200D:** {spy_vs_200d}%
{narrative}

## Implicit Bet
{implicit_bet}

## Key Metrics
| Metric | Value |
|--------|-------|
| Sharpe | {sharpe} |
| Beta | {beta} |
| Max Drawdown | {max_drawdown}% |
| Annualized Vol | {vol}% |
| Avg Correlation | {avg_corr} |
| Portfolio Yield | {weighted_yield}% |

## Red Flags
{red_flags_text}

## Green Flags
{green_flags_text}

## Restructuring Plans
{plans_text}
"""

    note_content = frontmatter + "\n" + body

    note_path.write_text(note_content, encoding="utf-8")
    return str(note_path)
