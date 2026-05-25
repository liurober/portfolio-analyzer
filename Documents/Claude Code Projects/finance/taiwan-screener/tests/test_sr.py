from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.support_resistance import find_levels, suggest_trade_levels


def _df():
    n = 100
    rng = np.random.default_rng(7)
    close = 25 + 5 * np.sin(np.linspace(0, 6, n)) + rng.normal(0, 0.2, n)
    high = close + 0.5
    low = close - 0.5
    open_ = close.copy()
    vol = np.full(n, 1_000_000.0)
    idx = pd.date_range("2024-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_find_levels_returns_lists():
    out = find_levels(_df())
    assert "support" in out and "resistance" in out


def test_trade_levels_have_positive_rr_when_set():
    out = suggest_trade_levels(_df())
    if out["entry"] is not None:
        assert out["rr"] > 0
        assert out["target"] > out["entry"] > out["stop"]
