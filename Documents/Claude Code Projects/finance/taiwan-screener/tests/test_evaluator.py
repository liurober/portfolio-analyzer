from finance_tw_path import ensure_path  # noqa: F401
import json
import pandas as pd
from datetime import datetime

import backtest.evaluator as E
import backtest.tracker as T


def test_evaluator_uses_open_picks(tmp_path, monkeypatch):
    log_path = tmp_path / "picks_log.json"
    log_path.write_text(json.dumps({"version": 1, "picks": [{
        "date": "2026-04-01", "ticker": "2330.TW",
        "entry": 600.0, "stop": 540.0, "target": 750.0,
        "score": 7, "indicators_fired": [], "pattern": None,
        "pattern_confidence": None, "hold_weeks": 5, "status": "open",
        "exit_price": None, "exit_date": None, "outcome": None,
        "pnl_pct": None, "pnl_nt": None,
        "lot_cost": 600000.0, "params_version": "t"
    }]}), encoding="utf-8")
    monkeypatch.setattr(T, "PICKS_LOG", log_path)
    monkeypatch.setattr(E, "open_picks", T.open_picks)
    monkeypatch.setattr(E, "close_pick", T.close_pick)

    # Stub yfinance.download to return a frame where the target hits
    import yfinance
    def fake_download(*a, **k):
        idx = pd.date_range("2026-04-02", periods=5, freq="D")
        return pd.DataFrame({
            "Open": [600, 610, 620, 700, 760],
            "High": [605, 615, 630, 720, 780],
            "Low": [598, 605, 615, 690, 750],
            "Close": [604, 612, 625, 715, 770],
            "Volume": [1e6] * 5}, index=idx)
    monkeypatch.setattr(yfinance, "download", fake_download)

    result = E.evaluate_open_picks(today=datetime(2026, 5, 10))
    assert result["wins"] == 1
