"""Walk-forward weekly backtest with no look-ahead.

For each weekly bar T from `start` to len(df)-hold_weeks:
  1. Slice df[:T+1] (information available at close of bar T).
  2. Score signals + liquidity gate.
  3. If qualifies, simulate the trade across bars [T+1 .. T+hold_weeks].
  4. Outcome:
       WIN     -> first bar after entry where High >= target
       LOSS    -> first bar after entry where Low  <= stop
       NEUTRAL -> neither hit within hold_weeks
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from screener.indicators_tw import score_signals_tw
from screener.support_resistance import suggest_trade_levels


@dataclass
class TradeResult:
    ticker: str
    entry_date: str
    entry: float
    stop: float
    target: float
    exit_date: str | None
    exit_price: float | None
    outcome: str       # "win" | "loss" | "neutral"
    pnl_pct: float
    hold_weeks_actual: int
    score: int


def _qualifies(df_so_far: pd.DataFrame, params: dict[str, Any]
               ) -> tuple[bool, dict, dict]:
    last_close = float(df_so_far["Close"].iloc[-1])
    if last_close < params.get("min_price", 10) or last_close > params.get("max_price", 100):
        return False, {}, {}
    avg_vol_k = float(df_so_far["Volume"].tail(10).mean()) / 1000.0
    if avg_vol_k < params.get("min_vol_k", 500):
        return False, {}, {}
    scored = score_signals_tw(df_so_far, params)
    if not scored["gates_ok"] or scored["score"] < params.get("min_score", 6):
        return False, scored, {}
    levels = suggest_trade_levels(df_so_far,
                                  target_mult=params.get("target_mult", 2.5),
                                  min_rr=params.get("min_rr", 2.0))
    if levels["entry"] is None or (levels["rr"] or 0) < params.get("min_rr", 2.0):
        return False, scored, levels
    return True, scored, levels


def simulate(ticker: str, df: pd.DataFrame, params: dict[str, Any],
             start: int = 60) -> list[TradeResult]:
    hold = int(params.get("hold_weeks", 5))
    results: list[TradeResult] = []
    last_exit_idx = -1
    for t in range(start, len(df) - hold):
        if t <= last_exit_idx:
            continue
        slice_ = df.iloc[: t + 1]
        ok, scored, levels = _qualifies(slice_, params)
        if not ok:
            continue
        entry = float(levels["entry"]); stop = float(levels["stop"])
        target = float(levels["target"])
        window = df.iloc[t + 1: t + 1 + hold]
        outcome = "neutral"; exit_price = None; exit_date = None
        hold_actual = hold
        for k, (ts, row) in enumerate(window.iterrows(), start=1):
            hit_stop = float(row["Low"]) <= stop
            hit_tgt = float(row["High"]) >= target
            if hit_stop and hit_tgt:
                # both hit same bar - conservative: assume stop first
                outcome = "loss"; exit_price = stop
                exit_date = str(ts.date()); hold_actual = k; break
            if hit_stop:
                outcome = "loss"; exit_price = stop
                exit_date = str(ts.date()); hold_actual = k; break
            if hit_tgt:
                outcome = "win"; exit_price = target
                exit_date = str(ts.date()); hold_actual = k; break
        if outcome == "neutral":
            exit_price = float(window["Close"].iloc[-1])
            exit_date = str(window.index[-1].date())
        pnl_pct = (exit_price - entry) / entry * 100.0
        results.append(TradeResult(
            ticker=ticker, entry_date=str(df.index[t].date()),
            entry=entry, stop=stop, target=target,
            exit_date=exit_date, exit_price=exit_price,
            outcome=outcome, pnl_pct=float(pnl_pct),
            hold_weeks_actual=hold_actual, score=int(scored["score"]),
        ))
        last_exit_idx = t + hold_actual
    return results


def summarize(trades: list[TradeResult]) -> dict[str, Any]:
    if not trades:
        return {"total_trades": 0}
    wins = sum(1 for t in trades if t.outcome == "win")
    losses = sum(1 for t in trades if t.outcome == "loss")
    neut = sum(1 for t in trades if t.outcome == "neutral")
    rets = [t.pnl_pct for t in trades]
    avg_ret = sum(rets) / len(rets)
    import statistics as st
    sd = st.pstdev(rets) if len(rets) > 1 else 0.0
    sharpe = (avg_ret / sd) if sd > 0 else 0.0  # weekly Sharpe proxy
    cum = []
    eq = 1.0
    for r in rets:
        eq *= (1 + r / 100)
        cum.append(eq)
    peak = cum[0]; max_dd = 0.0
    for x in cum:
        peak = max(peak, x)
        max_dd = max(max_dd, (peak - x) / peak * 100)
    return {
        "total_trades": len(trades),
        "wins": wins, "losses": losses, "neutral": neut,
        "win_rate": wins / len(trades),
        "avg_return_pct": avg_ret,
        "median_return_pct": st.median(rets),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
        "best": max(rets), "worst": min(rets),
    }
