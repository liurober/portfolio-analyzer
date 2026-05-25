from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd
import pytest
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
    # trade 1: strict win (target hit), PnL +25%
    # trade 2: strict loss (stop hit), PnL -10%
    t = [TradeResult("X.TW", "2024-01-01", 20, 18, 25, "2024-02-01", 25,
                     "win", 25.0, 4, 6),
         TradeResult("X.TW", "2024-03-01", 20, 18, 25, "2024-04-01", 18,
                     "loss", -10.0, 4, 6)]
    s = summarize(t)
    assert s["total_trades"] == 2
    assert s["wins"] == 1
    assert s["losses"] == 1
    assert s["strict_win_rate"] == 0.5          # target actually hit
    assert s["win_rate"] == 0.5                  # profitable (PnL > 0) = 1/2
    assert s["profitable"] == 1
    assert s["avg_win_return_pct"] == 25.0       # only profitable trade avg


def test_summarize_profitable_rate():
    """Three neutral trades: 2 profitable (+5%, +3%), 1 unprofitable (-1%)."""
    t = [TradeResult("X.TW", "2024-01-01", 20, 18, 25, "2024-02-01", 21,
                     "neutral", 5.0, 5, 6),
         TradeResult("X.TW", "2024-03-01", 20, 18, 25, "2024-04-01", 20.6,
                     "neutral", 3.0, 5, 6),
         TradeResult("X.TW", "2024-05-01", 20, 18, 25, "2024-06-01", 19.8,
                     "neutral", -1.0, 5, 6)]
    s = summarize(t)
    assert s["strict_win_rate"] == 0.0           # no target hit
    assert s["win_rate"] == pytest.approx(2/3)   # 2 of 3 profitable
    assert s["avg_win_return_pct"] == pytest.approx(4.0)  # (5+3)/2
