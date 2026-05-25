"""Monthly outcome checker for open picks.

For every open pick:
  * Pull daily bars from entry_date to today.
  * If High >= target on any bar     -> close as win @ target
  * Else if Low <= stop on any bar   -> close as loss @ stop
  * Else if hold_weeks elapsed       -> close as neutral @ last close
  * Else                              -> leave open
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from backtest.tracker import open_picks, close_pick


def evaluate_open_picks(today: datetime | None = None) -> dict[str, int]:
    today = today or datetime.utcnow()
    wins = losses = neutrals = unchanged = 0
    for p in open_picks():
        entry_date = datetime.fromisoformat(p["date"])
        hold_w = int(p.get("hold_weeks", 5))
        expire = entry_date + timedelta(weeks=hold_w)
        try:
            df = yf.download(p["ticker"],
                             start=entry_date.date(),
                             end=min(today, expire + timedelta(days=2)).date(),
                             interval="1d", auto_adjust=True, progress=False)
        except Exception:
            unchanged += 1
            continue
        if df is None or df.empty:
            unchanged += 1
            continue
        outcome = None; exit_price = None; exit_date = None
        for ts, row in df.iterrows():
            if float(row["High"]) >= float(p["target"]):
                outcome = "win"; exit_price = float(p["target"])
                exit_date = str(ts.date()); break
            if float(row["Low"]) <= float(p["stop"]):
                outcome = "loss"; exit_price = float(p["stop"])
                exit_date = str(ts.date()); break
        if outcome is None and today >= expire:
            outcome = "neutral"
            exit_price = float(df["Close"].iloc[-1])
            exit_date = str(df.index[-1].date())
        if outcome is None:
            unchanged += 1
            continue
        close_pick(p["ticker"], p["date"], exit_price, exit_date, outcome)
        if outcome == "win": wins += 1
        elif outcome == "loss": losses += 1
        else: neutrals += 1
    return {"wins": wins, "losses": losses, "neutrals": neutrals,
            "still_open": unchanged}


def main() -> int:
    out = evaluate_open_picks()
    print(f"[evaluator] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
