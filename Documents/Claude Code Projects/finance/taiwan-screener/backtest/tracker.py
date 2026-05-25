"""Live picks log reader/writer with per-trade PnL.

Schema (one entry):
{
  "date": "YYYY-MM-DD", "ticker": "2887.TW",
  "entry": 22.50, "stop": 19.80, "target": 29.25,
  "score": 6, "indicators_fired": [...],
  "pattern": "Bull Flag", "pattern_confidence": 0.7,
  "hold_weeks": 5,
  "status": "open" | "closed",
  "exit_price": null|float, "exit_date": null|str,
  "outcome": null|"win"|"loss"|"neutral",
  "pnl_pct": null|float, "pnl_nt": null|float,
  "lot_cost": 22500.0,
  "params_version": "2026-05-01"
}
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PICKS_LOG = HERE / "picks_log.json"


def load_log() -> dict:
    if not PICKS_LOG.exists():
        return {"version": 1, "picks": []}
    return json.loads(PICKS_LOG.read_text(encoding="utf-8"))


def save_log(data: dict) -> None:
    PICKS_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")


def add_pick(pick: dict[str, Any]) -> None:
    log = load_log()
    log["picks"].append(pick)
    save_log(log)


def open_picks() -> list[dict]:
    return [p for p in load_log()["picks"] if p.get("status") == "open"]


def closed_picks() -> list[dict]:
    return [p for p in load_log()["picks"] if p.get("status") == "closed"]


def close_pick(ticker: str, entry_date: str, exit_price: float,
               exit_date: str, outcome: str) -> bool:
    log = load_log()
    for p in log["picks"]:
        if (p["ticker"] == ticker and p["date"] == entry_date
                and p.get("status") == "open"):
            p["status"] = "closed"
            p["exit_price"] = float(exit_price)
            p["exit_date"] = exit_date
            p["outcome"] = outcome
            entry = float(p["entry"])
            pnl_pct = (exit_price - entry) / entry * 100.0
            p["pnl_pct"] = float(pnl_pct)
            p["pnl_nt"] = float(p.get("lot_cost", entry * 1000)) * pnl_pct / 100.0
            save_log(log)
            return True
    return False


def expired_picks(today: datetime | None = None) -> list[dict]:
    """Open picks whose hold_weeks have elapsed."""
    today = today or datetime.utcnow()
    out = []
    for p in open_picks():
        d = datetime.fromisoformat(p["date"])
        if today >= d + timedelta(weeks=int(p.get("hold_weeks", 5))):
            out.append(p)
    return out


def stats() -> dict:
    closed = closed_picks()
    if not closed:
        return {"closed": 0, "open": len(open_picks())}
    wins = [p for p in closed if p.get("outcome") == "win"]
    losses = [p for p in closed if p.get("outcome") == "loss"]
    rets = [p["pnl_pct"] for p in closed if p.get("pnl_pct") is not None]
    avg = sum(rets) / len(rets) if rets else 0.0
    return {
        "open": len(open_picks()),
        "closed": len(closed),
        "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / len(closed),
        "avg_return_pct": avg,
    }
