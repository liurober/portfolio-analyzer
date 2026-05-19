#!/usr/bin/env python3
"""
Mode 1 — Portfolio Analyzer
Usage: python run_analyze.py <portfolio_file> [--date YYYY-MM-DD]
"""
import argparse
import sys
import json
from datetime import date
from pathlib import Path

# Add parent dir to sys.path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from portfolio_analyzer.parser import parse
from portfolio_analyzer.macro_context import get_macro as get_macro_context
from portfolio_analyzer.metrics import compute_metrics
from portfolio_analyzer.screener_picks import get_picks
from portfolio_analyzer.report import generate_report
from portfolio_analyzer.obsidian import save_note

BASE_DIR = Path(__file__).parent.parent

def run_analyze(file_path: str, date_str: str = None) -> dict:
    """Run full Mode 1 analysis. Returns context dict."""
    if date_str is None:
        date_str = date.today().isoformat()

    print("📊 Parsing portfolio...", flush=True)
    holdings = parse(file_path)
    n = len(holdings["positions"])
    total = holdings.get("total_value")
    total_str = f"${total:,.0f}" if total else "unknown value"
    print(f"   {n} positions · {total_str}", flush=True)

    print("🌐 Fetching market context...", flush=True)
    macro = get_macro_context()
    print(f"   Regime: {macro['regime']} · Recommended plan: {macro['recommended_plan']}", flush=True)

    print("📐 Computing metrics...", flush=True)
    rf = macro.get("fed_rate", 4.5) / 100
    metrics = compute_metrics(holdings, risk_free_rate=rf)
    if metrics.get("skipped_tickers"):
        print(f"   ⚠️  Skipped (no data): {', '.join(metrics['skipped_tickers'])}", flush=True)

    print("🔍 Fetching screener picks...", flush=True)
    sectors = list({p.get("sector", "Technology") for p in holdings["positions"]})
    picks = {
        "aggressive":   get_picks(sectors, "aggressive"),
        "balanced":     get_picks(sectors, "balanced"),
        "conservative": get_picks(sectors, "conservative"),
        "income":       get_picks(sectors, "income"),
    }

    print("🧠 Preparing Claude analysis context...", flush=True)
    context = {
        "mode": "analyze",
        "date": date_str,
        "holdings": holdings,
        "macro": macro,
        "metrics": metrics,
        "picks": picks,
    }
    context_path = BASE_DIR / "portfolio-analyzer" / ".analysis_context.json"
    context_path.write_text(json.dumps(context, indent=2))
    print(f"   Context saved → {context_path}", flush=True)

    return context


def render_terminal_summary(holdings, macro, metrics, analysis):
    """Print the in-session terminal summary."""
    total = holdings.get("total_value")
    n = len(holdings["positions"])
    total_str = f"${total:,.0f}" if total else "N/A"

    print()
    print(f"\033[95m\033[1m📊 PORTFOLIO ANALYSIS — {total_str} · {n} positions · {macro.get('regime', 'Unknown regime')}\033[0m")
    vix_val = macro.get('vix', '?')
    vix_str = f"{vix_val:.2f}" if isinstance(vix_val, (int, float)) else str(vix_val)
    print(f"\033[90m  VIX {vix_str} · 3M-10Y {macro.get('spread_3m10y_bps','?'):+.0f}bps · data as of {date.today().isoformat()}\033[0m")
    print()

    print(f"\033[93m\033[1mIMPLICIT BET\033[0m")
    print(f"\033[37m  {analysis.get('implicit_bet','')}\033[0m")
    print()

    rq = metrics.get("return_quality", {})
    risk = metrics.get("risk", {})
    inc = metrics.get("income_style", {})
    sharpe = rq.get("sharpe")
    beta   = risk.get("portfolio_beta")
    mdd    = risk.get("max_drawdown")
    yld    = inc.get("weighted_yield")

    def fmt(v, fmt_str, good_fn):
        if v is None: return ("N/A", "\033[90m")
        color = "\033[92m" if good_fn(v) else "\033[91m"
        return (fmt_str.format(v), color)

    sharpe_s, sc = fmt(sharpe, "{:.2f}", lambda x: x > 1.0)
    beta_s,   bc = fmt(beta,   "{:.2f}", lambda x: x < 1.2)
    mdd_s,    mc = fmt(mdd,    "{:.0%}", lambda x: x > -0.3)
    yld_s,    yc = fmt(yld,    "{:.1%}", lambda x: x > 0.01)

    print(f"  {sc}Sharpe {sharpe_s}\033[0m  {bc}Beta {beta_s}\033[0m  {mc}Max DD {mdd_s}\033[0m  {yc}Yield {yld_s}\033[0m")
    print()

    red_flags = analysis.get("red_flags", [])[:3]
    if red_flags:
        print(f"\033[91m\033[1m🚨 RED FLAGS\033[0m")
        for f in red_flags:
            flag_text = f["flag"] if isinstance(f, dict) else str(f)
            print(f"\033[37m  · {flag_text}\033[0m")
        print()

    green_flags = analysis.get("green_flags", [])[:2]
    if green_flags:
        print(f"\033[92m\033[1m✅ GREEN FLAGS\033[0m")
        for f in green_flags:
            print(f"\033[37m  · {f}\033[0m")
        print()

    rec = macro.get("recommended_plan", "balanced").title()
    print(f"\033[96m  ★ Recommended plan for today's market: {rec}\033[0m")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Portfolio file (PDF, Excel, JSON)")
    parser.add_argument("--date", default=None, help="Analysis date YYYY-MM-DD")
    args = parser.parse_args()

    context = run_analyze(args.file, args.date)
    print("\n✅ Context ready. Claude will now perform analysis...")
    print(f"   Context: portfolio-analyzer/.analysis_context.json")
