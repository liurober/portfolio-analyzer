#!/usr/bin/env python3
"""
Mode 2 — Portfolio Builder (from scratch)
Usage: python run_build.py [--amount 50000] [--profile aggressive] [--horizon 15] [--goal growth] [--age 35] [--avoid "TSLA,crypto"]
"""
import argparse
import sys
import json
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from portfolio_analyzer.macro_context import get_macro_context
from portfolio_analyzer.builder import build_portfolios
from portfolio_analyzer.screener_picks import get_picks
from portfolio_analyzer.report import generate_report
from portfolio_analyzer.obsidian import save_note

BASE_DIR = Path(__file__).parent.parent

PROFILES = ["aggressive", "balanced", "conservative", "income"]
GOALS = ["growth", "income", "capital preservation", "retirement", "FIRE"]


def _prompt_if_missing(value, prompt_text, valid=None):
    if value is not None:
        return value
    while True:
        v = input(f"  {prompt_text}: ").strip()
        if not v:
            continue
        if valid and v not in valid:
            print(f"    Must be one of: {', '.join(valid)}")
            continue
        return v


def run_build(amount=None, profile=None, horizon=None, goal=None, age=None, avoid_str=None, date_str=None):
    if date_str is None:
        date_str = date.today().isoformat()

    print("\n💼 PORTFOLIO BUILDER — Build From Scratch\n", flush=True)

    # Collect params interactively if not provided
    amount  = float(_prompt_if_missing(amount,  "Total amount to invest ($)"))
    profile = _prompt_if_missing(profile, f"Risk profile ({'/'.join(PROFILES)})", valid=PROFILES)
    horizon = int(_prompt_if_missing(horizon, "Time horizon (years)"))
    goal    = _prompt_if_missing(goal, f"Primary goal ({'/'.join(GOALS)})", valid=GOALS)
    age_raw = _prompt_if_missing(age, "Age (optional, press Enter to skip)")
    age     = int(age_raw) if age_raw and str(age_raw).isdigit() else None
    avoid   = [t.strip().upper() for t in (avoid_str or "").split(",") if t.strip()]

    print(f"\n  Amount: ${amount:,.0f}  ·  Profile: {profile}  ·  Horizon: {horizon}Y  ·  Goal: {goal}", flush=True)
    if age:
        print(f"  Age: {age}  →  120-age equity guideline: {120-age}%", flush=True)
    if avoid:
        print(f"  Avoiding: {', '.join(avoid)}", flush=True)

    print("\n🌐 Fetching market context...", flush=True)
    macro = get_macro_context()
    print(f"   Regime: {macro['regime']} · Best fit today: {macro['recommended_plan']}", flush=True)

    print("🏗️  Building 4 portfolios...", flush=True)
    portfolios = build_portfolios(amount, profile, horizon, goal, macro, age=age, avoid=avoid)

    # Build picks dict (for report compatibility)
    picks = {
        arch: [
            {"ticker": p["ticker"], "score": 5, "source": p["tag"], "sector": "Various", "reason": p["reason"], "tag": p["tag"]}
            for p in port["positions"]
        ]
        for arch, port in portfolios.items()
    }

    # Save context for Claude
    context = {
        "mode": "build",
        "date": date_str,
        "params": {"amount": amount, "profile": profile, "horizon": horizon, "goal": goal, "age": age, "avoid": avoid},
        "macro": macro,
        "portfolios": portfolios,
        "picks": picks,
    }
    context_path = BASE_DIR / "portfolio-analyzer" / ".build_context.json"
    context_path.write_text(json.dumps(context, indent=2))

    _render_build_summary(portfolios, macro, amount, profile, horizon)

    print(f"\n✅ Build context ready → {context_path}")
    print("   Claude will add narrative rationale and render the full report.")
    return context


def _render_build_summary(portfolios, macro, amount, profile, horizon):
    rec = macro.get("recommended_plan", "balanced")
    BOLD = "\033[1m"; DIM = "\033[2m"; RESET = "\033[0m"
    PURPLE = "\033[95m"; CYAN = "\033[96m"; YELLOW = "\033[93m"
    GREEN = "\033[92m"; RED = "\033[91m"; GREY = "\033[90m"
    BLUE = "\033[94m"

    SLEEVE_COLORS = {
        "screener":    PURPLE,
        "bond":        BLUE,
        "real_asset":  YELLOW,
        "reit":        GREEN,
        "cash":        GREY,
    }
    SLEEVE_LABELS = {
        "screener":    "EQUITY / SCREENER",
        "bond":        "FIXED INCOME",
        "real_asset":  "REAL ASSETS",
        "reit":        "REITs",
        "cash":        "CASH",
    }

    print(f"\n{PURPLE}{BOLD}💼 PORTFOLIO BUILD — ${amount:,.0f} · {profile.title()} · {horizon}Y horizon{RESET}")
    print(f"{CYAN}  Regime: {macro['regime']} · ★ Recommended today: {rec.title()} "
          f"(macro fit {portfolios[rec]['macro_fit_score']:.1f}/5){RESET}")
    print(f"{GREY}  VIX {macro.get('vix','?')} · 3M-10Y {macro.get('spread_3m10y_bps',0):+.0f}bps · "
          f"Fed rate {macro.get('fed_rate','?')}%{RESET}\n")

    for arch, port in portfolios.items():
        star = " ★ RECOMMENDED" if arch == rec else ""
        m = port["target_metrics"]
        annual_income = amount * m["yield_est"]

        # Header bar
        print(f"{'─'*72}")
        print(f"{BOLD}  {arch.upper()}{RESET}{YELLOW}{star}{RESET}")
        print(f"  Macro fit: {m.get('macro_fit_score', port.get('macro_fit_score', '?')):.1f}/5  "
              f"│  Beta ~{m['beta_est']}  │  Max DD ~{m['max_dd_est']:.0%}  │  "
              f"Yield ~{m['yield_est']:.1%}  │  Equity {m['equity_pct']:.0%}"
              .replace("│", f"{GREY}│{RESET}"))
        print(f"  {GREEN}Est. Annual Income: ${annual_income:,.0f}{RESET}  "
              f"({GREY}${annual_income/12:,.0f}/mo{RESET})")
        print(f"  {port['rationale'][:90]}")
        print()

        # Group positions by sleeve
        from collections import defaultdict
        sleeves = defaultdict(list)
        for p in port["positions"]:
            sleeves[p.get("tag", "screener")].append(p)

        sleeve_order = ["screener", "bond", "real_asset", "reit", "cash"]
        for sleeve in sleeve_order:
            positions = sleeves.get(sleeve, [])
            if not positions:
                continue
            sleeve_weight = sum(p["weight"] for p in positions)
            sleeve_value  = sum(p["value"]  for p in positions)
            color = SLEEVE_COLORS.get(sleeve, RESET)
            label = SLEEVE_LABELS.get(sleeve, sleeve.upper())
            print(f"  {color}{BOLD}{label}{RESET}  "
                  f"{GREY}({sleeve_weight:.1%} · ${sleeve_value:,.0f}){RESET}")
            print(f"  {'Ticker':<7}  {'Weight':>7}  {'Value':>10}  Reason")
            print(f"  {'─'*65}")
            for p in positions:
                reason = p.get("reason", "")[:50]
                print(f"  {color}{p['ticker']:<7}{RESET}  "
                      f"{p['weight']:>7.1%}  "
                      f"${p['value']:>9,.0f}  "
                      f"{GREY}{reason}{RESET}")
            print()

        # Portfolio totals
        total_weight = sum(p["weight"] for p in port["positions"])
        total_value  = sum(p["value"]  for p in port["positions"])
        n = len(port["positions"])
        print(f"  {BOLD}TOTAL{RESET}  {total_weight:.1%}  ${total_value:,.0f}  ({n} positions)\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--amount",  type=float)
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--horizon", type=int)
    parser.add_argument("--goal",    choices=GOALS)
    parser.add_argument("--age",     type=int)
    parser.add_argument("--avoid",   default="")
    parser.add_argument("--date",    default=None)
    args = parser.parse_args()

    run_build(args.amount, args.profile, args.horizon, args.goal, args.age, args.avoid, args.date)
