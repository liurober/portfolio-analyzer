from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd
from dataclasses import asdict

from backtest.engine import simulate, summarize, TradeResult


def _df(n=200, drift=0.005, seed=3):
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.02, n)
    close = 20 * np.cumprod(1 + rets)
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    vol = rng.integers(700_000, 2_000_000, n).astype(float)
    idx = pd.date_range("2021-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_simulate_returns_trade_results():
    params = {"min_score": 4, "rsi_low": 25, "rsi_high": 85, "bb_period": 20,
              "chandelier_period": 22, "chandelier_mult": 3.0,
              "ma_fast": 20, "ma_slow": 120, "adx_threshold": 15,
              "target_mult": 2.0, "hold_weeks": 5,
              "min_price": 10, "max_price": 100, "min_vol_k": 500,
              "min_rr": 1.5,
              "require_macd": False, "require_ttm": False,
              "require_adx": False, "require_ma_stack": False}
    trades = simulate("TEST.TW", _df(), params)
    for t in trades:
        assert isinstance(t, TradeResult)
        assert t.outcome in ("win", "loss", "neutral")


def test_summarize_empty():
    out = summarize([])
    assert out["total_trades"] == 0


def test_summarize_basic():
    t = [TradeResult("X.TW", "2024-01-01", 20, 18, 25, "2024-02-01", 25,
                     "win", 25.0, 4, 6),
         TradeResult("X.TW", "2024-03-01", 20, 18, 25, "2024-04-01", 18,
                     "loss", -10.0, 4, 6)]
    s = summarize(t)
    assert s["total_trades"] == 2
    assert s["wins"] == 1
    assert s["win_rate"] == 0.5
