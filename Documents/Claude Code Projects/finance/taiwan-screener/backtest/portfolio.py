"""Portfolio simulator — $100K starting capital, $10K per pick, max 3 concurrent.

Inputs: list of TradeResult-like dicts (entry_date, exit_date, pnl_pct, ticker).
Output: equity curve (date -> nav), summary stats.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import pandas as pd


def simulate_portfolio(trades: Iterable[dict[str, Any]],
                       starting_cash: float = 100_000.0,
                       per_pick: float = 10_000.0,
                       max_concurrent: int = 3) -> dict[str, Any]:
    sorted_trades = sorted(trades, key=lambda t: t["entry_date"])
    open_book: list[dict] = []  # active positions
    cash = starting_cash
    nav_history: list[tuple[str, float]] = []
    closed_trades = []

    def _value_open(today: str) -> float:
        # MVP: assume positions revalue linearly to exit price by exit_date.
        # For NAV between entry and exit we use entry value (no MTM here).
        return sum(p["cost"] for p in open_book)

    for t in sorted_trades:
        # First, close anything that has exited on/before this trade's entry
        new_open = []
        for p in open_book:
            if p["exit_date"] <= t["entry_date"]:
                cash += p["cost"] * (1 + p["pnl_pct"] / 100.0)
                closed_trades.append(p)
            else:
                new_open.append(p)
        open_book = new_open

        if len(open_book) >= max_concurrent:
            continue   # cannot take this trade
        if cash < per_pick:
            continue
        cash -= per_pick
        open_book.append({"entry_date": t["entry_date"],
                          "exit_date": t["exit_date"] or t["entry_date"],
                          "ticker": t["ticker"],
                          "cost": per_pick,
                          "pnl_pct": float(t["pnl_pct"])})
        nav_history.append((t["entry_date"], cash + _value_open(t["entry_date"])))

    # Finally drain everything still open
    final_exit_dates = sorted(p["exit_date"] for p in open_book)
    for d in final_exit_dates:
        still = []
        for p in open_book:
            if p["exit_date"] == d:
                cash += p["cost"] * (1 + p["pnl_pct"] / 100.0)
                closed_trades.append(p)
            else:
                still.append(p)
        open_book = still
        nav_history.append((d, cash))

    final_nav = cash
    starting = starting_cash
    total_return = (final_nav - starting) / starting * 100
    return {
        "final_nav": float(final_nav),
        "total_return_pct": float(total_return),
        "trades_taken": len(closed_trades),
        "trades_skipped": len(sorted_trades) - len(closed_trades),
        "equity_curve": nav_history,
    }
