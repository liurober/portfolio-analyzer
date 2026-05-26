"""`/analyze_tw <TICKER>` — single-stock institutional-grade report.

Pillars: 技術 55% / 基本面 30% / 機構相關性 15%

Outputs HTML and (if weasyprint available) PDF into ./out/.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yfinance as yf
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from screener.indicators_tw import score_signals_tw
from screener.patterns import detect_pattern
from screener.support_resistance import suggest_trade_levels
from screener.charts import build_chart
from screener.institution import report_for
from screener.universe_tw import load_universe
from backtest.signal_scorer import SignalScorer, extract_features, MODEL_PATH

OUT_DIR = HERE / "out"
OPTIMAL = HERE / "backtest" / "optimal_params.json"


def _params() -> tuple[dict, str]:
    data = json.loads(OPTIMAL.read_text(encoding="utf-8"))
    p = dict(data["best"])
    return p, data.get("generated", "default")[:10]


def _name_for(symbol: str) -> tuple[str, str]:
    for t in load_universe():
        if t["symbol"] == symbol:
            return t["name_zh"], t["sector"]
    return symbol.replace(".TW", ""), "未分類"


def _rate(total: float) -> str:
    if total >= 9.0: return "強力買進"
    if total >= 7.5: return "買進"
    if total >= 6.0: return "觀望"
    if total >= 4.0: return "謹慎"
    return "避開"


def _fmt(v: Any, suffix: str = "", pct: bool = False) -> str:
    if v is None or v == "":
        return "n/a"
    try:
        f = float(v)
    except Exception:
        return str(v)
    if pct:
        return f"{f * 100:.1f}%"
    return f"{f:.2f}{suffix}"


def _fundamentals(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}

    score = 5.0
    # forward P/E sweet spot 8-25 -> +1.5
    fwd = info.get("forwardPE")
    if fwd and 8 < fwd < 25: score += 1.5
    eps_g = info.get("earningsQuarterlyGrowth")
    if eps_g and eps_g > 0.10: score += 1.0
    rev_g = info.get("revenueGrowth")
    if rev_g and rev_g > 0.05: score += 0.5
    gm = info.get("grossMargins")
    if gm and gm > 0.30: score += 0.5
    fcf = info.get("freeCashflow")
    if fcf and fcf > 0: score += 0.5
    de = info.get("debtToEquity")
    if de is not None and de < 100: score += 0.5
    score = max(0.0, min(10.0, score))

    next_earn = info.get("earningsTimestamp") or info.get("earningsDate")
    if isinstance(next_earn, (int, float)):
        try:
            next_earn = datetime.utcfromtimestamp(next_earn).date().isoformat()
        except Exception:
            next_earn = "n/a"
    return {
        "fwd_pe": _fmt(fwd),
        "ttm_pe": _fmt(info.get("trailingPE")),
        "ev_ebitda": _fmt(info.get("enterpriseToEbitda")),
        "eps_growth": _fmt(eps_g, pct=True),
        "rev_growth": _fmt(rev_g, pct=True),
        "gross_margin": _fmt(gm, pct=True),
        "op_margin": _fmt(info.get("operatingMargins"), pct=True),
        "fcf": _fmt(fcf),
        "de_ratio": _fmt(de),
        "next_earnings": next_earn or "n/a",
        "score": score,
    }


def analyze(symbol: str) -> dict:
    OUT_DIR.mkdir(exist_ok=True)
    params, params_version = _params()
    name_zh, sector = _name_for(symbol)

    df = yf.download(symbol, period="3y", interval="1wk",
                     auto_adjust=True, progress=False).dropna()
    if df.empty or len(df) < 60:
        raise RuntimeError(f"insufficient data for {symbol}")

    last_close = float(df["Close"].iloc[-1])
    scored = score_signals_tw(df, params)
    fired = [k for k, v in scored["signals"].items() if v["fired"]]
    levels = suggest_trade_levels(df, target_mult=params.get("target_mult", 2.5),
                                  min_rr=params.get("min_rr", 2.0))
    pat = detect_pattern(df) or {}

    # Technical score 0-10
    tech_score = (scored["score"] / 8.0) * 10.0
    if levels.get("rr") and levels["rr"] >= 2.5:
        tech_score = min(10.0, tech_score + 0.5)
    if pat.get("confidence"):
        tech_score = min(10.0, tech_score + 0.5 * pat["confidence"])

    fund = _fundamentals(symbol)
    inst = report_for(symbol)

    total = 0.55 * tech_score + 0.30 * fund["score"] + 0.15 * inst.score
    rating = _rate(total)

    png = build_chart(df, symbol, name_zh,
                      entry=levels.get("entry") or last_close,
                      stop=levels.get("stop") or last_close * 0.9,
                      target=levels.get("target") or last_close * 1.2)
    chart_file = OUT_DIR / f"{symbol.replace('.', '_')}_chart.png"
    chart_file.write_bytes(png)

    # ── Per-signal win probability ─────────────────────────────────────────────
    _entry = levels.get("entry") or last_close
    _stop  = levels.get("stop")  or last_close * 0.90
    _fallback_loss = round((_stop - _entry) / _entry * 100, 2)
    win_probability   = 0.5
    win_confidence    = "LOW"
    n_similar_setups  = 0
    max_loss_pct      = _fallback_loss
    expected_value_pct: float | None = None
    if MODEL_PATH.exists():
        try:
            scorer = SignalScorer.from_file(MODEL_PATH)
            _feat = extract_features(df, scored, levels)
            _feat["entry"] = _entry
            _feat["stop"]  = _stop
            _pred = scorer.predict(_feat)
            win_probability   = _pred.get("win_probability", 0.5)
            win_confidence    = _pred.get("confidence", "LOW")
            n_similar_setups  = _pred.get("n_similar", 0)
            max_loss_pct      = _pred.get("max_loss_pct") or _fallback_loss
            expected_value_pct = _pred.get("expected_value_pct")
        except Exception as e:
            print(f"[analyze_tw] ⚠️  signal model predict failed: {e}")

    env = Environment(loader=FileSystemLoader(str(HERE / "screener")),
                      autoescape=select_autoescape(["html"]))
    tpl = env.get_template("analyze_template_tw.html")
    now = datetime.utcnow()
    ctx = {
        "symbol": symbol, "name_zh": name_zh, "sector": sector,
        "date_zh": f"{now.year}年{now.month}月{now.day}日",
        "params_version": params_version,
        "last_close": last_close,
        "total_score": total, "rating": rating,
        "tech_score": tech_score, "fund_score": fund["score"],
        "inst_score": inst.score,
        "indicator_score": scored["score"],
        "indicators_fired": fired,
        "entry": levels.get("entry") or last_close,
        "stop": levels.get("stop") or last_close * 0.9,
        "target": levels.get("target") or last_close * 1.2,
        "rr": levels.get("rr") or 0.0,
        "pattern": pat.get("pattern"),
        "pattern_confidence": pat.get("confidence") or 0.0,
        "chart_path": chart_file.as_uri(),
        "fwd_pe": fund["fwd_pe"], "ttm_pe": fund["ttm_pe"],
        "ev_ebitda": fund["ev_ebitda"],
        "eps_growth": fund["eps_growth"], "rev_growth": fund["rev_growth"],
        "gross_margin": fund["gross_margin"], "op_margin": fund["op_margin"],
        "fcf": fund["fcf"], "de_ratio": fund["de_ratio"],
        "next_earnings": fund["next_earnings"],
        "corr_qqq": inst.correlations.get("QQQ") or 0.0,
        "corr_soxx": inst.correlations.get("SOXX") or 0.0,
        "corr_spy": inst.correlations.get("SPY") or 0.0,
        "corr_amat": inst.correlations.get("AMAT") or 0.0,
        "inst_label": inst.label_zh,
        "holders": inst.holders,
        "analyst_recommendation": inst.analyst.get("recommendation", "n/a"),
        "analyst_target_mean": _fmt(inst.analyst.get("target_mean")),
        "analyst_count": inst.analyst.get("num_analysts") or "n/a",
        # ── ML probability metrics ────────────────────────────────────────────
        "win_probability":    win_probability,
        "win_confidence":     win_confidence,
        "n_similar_setups":   n_similar_setups,
        "max_loss_pct":       max_loss_pct,
        "expected_value_pct": expected_value_pct,
    }
    html = tpl.render(**ctx)
    out_html = OUT_DIR / f"{symbol.replace('.', '_')}_analyze.html"
    out_html.write_text(html, encoding="utf-8")

    pdf_path: Path | None = None
    try:
        from weasyprint import HTML
        pdf_path = OUT_DIR / f"{symbol.replace('.', '_')}_analyze.pdf"
        HTML(string=html, base_url=str(HERE)).write_pdf(str(pdf_path))
    except Exception as e:
        print(f"[analyze_tw] PDF skipped: {e}")

    print(f"[analyze_tw] {symbol}: total={total:.2f} ({rating})")
    print(f"[analyze_tw] HTML -> {out_html}")
    if pdf_path:
        print(f"[analyze_tw] PDF  -> {pdf_path}")
    return ctx


def main(argv=None):
    parser = argparse.ArgumentParser(description="/analyze_tw <TICKER>")
    parser.add_argument("symbol", help="e.g. 2330.TW")
    args = parser.parse_args(argv)
    analyze(args.symbol)
    return 0


if __name__ == "__main__":
    sys.exit(main())
