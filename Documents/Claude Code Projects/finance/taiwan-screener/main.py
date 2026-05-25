"""Weekly Taiwan screener orchestrator.

Workflow:
  1. Load optimal_params.json (last MC-tuned parameter set).
  2. Iterate the TWSE universe, evaluate each ticker.
  3. Select top 3 by score, R:R, pattern confidence (with 2-week cooldown).
  4. Build chart PNG + institution overlay for each.
  5. Render email + send via Gmail SMTP.
  6. Append picks to backtest/picks_log.json (status=open).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from screener.universe_tw import load_universe
from screener.screener_core import evaluate_ticker, select_top, record_picks
from screener.charts import build_chart
from screener.institution import report_for
from screener.mailer import render_weekly_email, send_email
import yfinance as yf

OPTIMAL_PARAMS = HERE / "backtest" / "optimal_params.json"
PICKS_LOG = HERE / "backtest" / "picks_log.json"


def _zh_date(dt: datetime) -> str:
    return f"{dt.year}年{dt.month}月{dt.day}日"


def load_params() -> tuple[dict, str]:
    data = json.loads(OPTIMAL_PARAMS.read_text(encoding="utf-8"))
    params = dict(data["best"])
    params["params_version"] = data.get("generated", "default")[:10]
    return params, params["params_version"]


def append_to_picks_log(picks: list, params_version: str) -> None:
    log = json.loads(PICKS_LOG.read_text(encoding="utf-8"))
    today = datetime.utcnow().date().isoformat()
    for p in picks:
        log["picks"].append({
            "date": today,
            "ticker": p.symbol,
            "entry": p.entry,
            "stop": p.stop,
            "target": p.target,
            "score": p.score,
            "indicators_fired": p.indicators_fired,
            "pattern": p.pattern,
            "pattern_confidence": p.pattern_confidence,
            "hold_weeks": p.hold_weeks,
            "status": "open",
            "exit_price": None,
            "exit_date": None,
            "outcome": None,
            "pnl_pct": None,
            "pnl_nt": None,
            "lot_cost": round(p.entry * 1000, 2),
            "params_version": params_version,
        })
    PICKS_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2),
                         encoding="utf-8")


def _market_in_uptrend() -> bool:
    """Return True if 0050.TW (Taiwan 50 ETF) is above its 52-week MA.

    Used as a market-regime gate: when the market is in a downtrend, even
    valid signals have a lower profitable rate.  If data cannot be fetched,
    returns True so the screener continues rather than silently skipping.
    """
    try:
        df = yf.download("0050.TW", period="2y", interval="1wk",
                         auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return True
        if isinstance(df.columns, __import__("pandas").MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        if len(close) < 52:
            return True
        return float(close.iloc[-1]) >= float(close.tail(52).mean())
    except Exception:
        return True


def main() -> int:
    params, params_version = load_params()

    # ── Market regime gate ────────────────────────────────────────────────────
    if params.get("require_index_regime", False):
        if not _market_in_uptrend():
            print("[main] ⚠️  market regime: 0050.TW below 52w MA — skipping scan")
            return 0
        print("[main] ✅ market regime: uptrend confirmed")

    universe = load_universe()
    print(f"[main] universe={len(universe)}  params_version={params_version}")

    candidates = []
    for entry in tqdm(universe, desc="掃描"):
        pk = evaluate_ticker(entry["symbol"], entry["name_zh"],
                             entry["sector"], params)
        if pk is not None:
            candidates.append(pk)

    print(f"[main] candidates={len(candidates)}")
    top = select_top(candidates, n=3, cooldown_weeks=2)
    print(f"[main] selected={len(top)}")
    if not top:
        print("[main] no qualifying picks this week")
        return 0

    picks_for_email: list[dict] = []
    for p in top:
        try:
            df = yf.download(p.symbol, period="2y", interval="1wk",
                             auto_adjust=True, progress=False).dropna()
            png = build_chart(df, p.symbol, p.name_zh,
                              p.entry, p.stop, p.target)
        except Exception:
            png = b""
        inst = report_for(p.symbol)
        picks_for_email.append({
            "symbol": p.symbol, "name_zh": p.name_zh, "sector": p.sector,
            "score": p.score, "indicators_fired": p.indicators_fired,
            "pattern": p.pattern or "", "pattern_confidence": p.pattern_confidence or 0,
            "entry": p.entry, "stop": p.stop, "target": p.target,
            "rr": p.rr, "hold_weeks": p.hold_weeks,
            "institution_label": inst.label_zh,
            "soxx_corr": inst.correlations.get("SOXX") or 0,
            "institution_score": inst.score,
            "chart_png": png,
        })

    today = datetime.utcnow()
    html, atts = render_weekly_email(
        picks_for_email, universe_count=len(universe),
        date_zh=_zh_date(today), params_version=params_version)
    subject = f"台股週報 — 交易機會 — {_zh_date(today)}"
    size = send_email(subject, html, atts)
    print(f"[main] email sent: {size} bytes")

    record_picks(top)
    append_to_picks_log(top, params_version)
    print(f"[main] logged {len(top)} picks to picks_log.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
