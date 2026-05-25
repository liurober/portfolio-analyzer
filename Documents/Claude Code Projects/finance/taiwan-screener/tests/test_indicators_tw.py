from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.indicators_tw import score_signals_tw, DEFAULT_PARAMS


def _make_bull_df(n: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = np.linspace(20, 60, n)  # strong uptrend
    noise = rng.normal(0, 0.3, n)
    close = base + noise
    high = close + 0.5
    low = close - 0.5
    open_ = close - rng.normal(0, 0.1, n)
    vol = rng.integers(800_000, 2_000_000, n).astype(float)
    idx = pd.date_range("2024-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_score_returns_int_and_signals():
    df = _make_bull_df()
    out = score_signals_tw(df)
    assert isinstance(out["score"], int)
    assert 0 <= out["score"] <= 8
    assert set(out["signals"].keys()) == {
        "rsi", "bb", "macd", "chandelier", "ttm", "ma_stack", "adx", "volume"
    }


def test_bull_trend_scores_high():
    df = _make_bull_df()
    out = score_signals_tw(df)
    assert out["score"] >= 5, out


def test_params_override_rsi_band():
    df = _make_bull_df()
    out_narrow = score_signals_tw(df, {"rsi_low": 95, "rsi_high": 99})
    assert out_narrow["signals"]["rsi"]["fired"] is False


def test_default_params_keys_present():
    for k in ["rsi_low", "rsi_high", "bb_period", "chandelier_period",
              "chandelier_mult", "ma_fast", "ma_slow", "adx_threshold"]:
        assert k in DEFAULT_PARAMS
