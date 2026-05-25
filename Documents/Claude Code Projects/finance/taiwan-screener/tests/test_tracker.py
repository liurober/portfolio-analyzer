from finance_tw_path import ensure_path  # noqa: F401
import json
from pathlib import Path

import backtest.tracker as T


def _redirect(tmp_path, monkeypatch):
    p = tmp_path / "picks_log.json"
    p.write_text('{"version":1,"picks":[]}', encoding="utf-8")
    monkeypatch.setattr(T, "PICKS_LOG", p)
    return p


def test_add_and_close(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    T.add_pick({
        "date": "2026-05-25", "ticker": "2330.TW",
        "entry": 600.0, "stop": 540.0, "target": 750.0,
        "score": 7, "indicators_fired": ["rsi"], "pattern": None,
        "pattern_confidence": None, "hold_weeks": 5, "status": "open",
        "exit_price": None, "exit_date": None, "outcome": None,
        "pnl_pct": None, "pnl_nt": None,
        "lot_cost": 600000.0, "params_version": "t"})
    assert len(T.open_picks()) == 1
    ok = T.close_pick("2330.TW", "2026-05-25", 750.0, "2026-06-29", "win")
    assert ok is True
    closed = T.closed_picks()
    assert closed[0]["outcome"] == "win"
    assert abs(closed[0]["pnl_pct"] - 25.0) < 1e-6


def test_stats_empty(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    s = T.stats()
    assert s["closed"] == 0
