from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.patterns import detect_pattern, detect_bull_flag


def _bull_flag_df():
    n = 30
    pole = np.linspace(20, 28, 22)
    flag = np.array([28, 27.6, 27.8, 27.5, 27.7, 27.9, 28.0, 28.1])
    close = np.concatenate([pole, flag])[:n]
    high = close + 0.3
    low = close - 0.3
    open_ = close - 0.05
    vol = np.full(n, 1_000_000.0)
    idx = pd.date_range("2025-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_bull_flag_detected():
    df = _bull_flag_df()
    r = detect_bull_flag(df)
    assert r is not None
    assert "旗形" in r["pattern"]
    assert 0 <= r["confidence"] <= 1


def test_detect_pattern_returns_one():
    df = _bull_flag_df()
    r = detect_pattern(df)
    assert r is not None
    assert "confidence" in r and "pattern" in r
