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
    print(f"\n\033[95m\033[1m💼 PORTFOLIO BUILD — ${amount:,.0f} · {profile.title()} · {horizon}Y horizon\033[0m")
    print(f"\033[96m  Regime: {macro['regime']} · ★ Recommended today: {rec.title()} (fit {portfolios[rec]['macro_fit_score']:.1f}/5)\033[0m\n")

    for arch, port in portfolios.items():
        star = " ★" if arch == rec else ""
        m = port["target_metrics"]
        print(f"\033[1m  {arch.upper()}{star}\033[0m  beta ~{m['beta_est']}  yield ~{m['yield_est']:.1%}  max DD ~{m['max_dd_est']:.0%}")
        for p in port["positions"][:5]:
            print(f"    {p['ticker']:<6}  {p['weight']:.1%}  ${p['value']:,.0f}  {p['reason'][:45]}")
        if len(port["positions"]) > 5:
            print(f"    ... +{len(port['positions'])-5} more positions")
        print()


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
