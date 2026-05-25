from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from backtest.optimizer import (PARAM_SPACE, composite_score, sample_params,
                                run_optimizer)
import random


def test_param_space_keys():
    expected = {"min_score", "rsi_low", "rsi_high", "chandelier_mult",
                "chandelier_period", "target_mult", "hold_weeks",
                "min_price", "max_price", "min_vol_k", "bb_period",
                "ma_fast", "ma_slow", "adx_threshold", "min_rr",
                "require_macd", "require_ttm", "require_adx",
                "require_ma_stack", "require_index_regime"}
    assert set(PARAM_SPACE.keys()) == expected


def test_param_space_max_price_covers_large_caps():
    """max_price options must cover TSMC (~2255 NT$) and MediaTek (~3860 NT$)."""
    assert max(PARAM_SPACE["max_price"]) >= 2000


def test_composite_score_zero_when_few_trades():
    assert composite_score({"total_trades": 5, "win_rate": 0.9,
                            "avg_return_pct": 25, "sharpe": 2.0,
                            "max_drawdown": 5}) == 0.0


def test_composite_score_high_value():
    cs = composite_score({"total_trades": 50, "win_rate": 0.85,
                          "avg_win_return_pct": 18, "avg_return_pct": 14,
                          "sharpe": 2.5, "max_drawdown": 8})
    assert 0.7 < cs <= 1.0


def test_sample_params_keys_match_space():
    p = sample_params(random.Random(1))
    assert set(p.keys()) == set(PARAM_SPACE.keys())


def _df(n=180, seed=1):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.003, 0.02, n)
    close = 20 * np.cumprod(1 + rets)
    high = close * 1.01; low = close * 0.99
    open_ = close * (1 + rng.normal(0, 0.001, n))
    vol = rng.integers(700_000, 2_000_000, n).astype(float)
    idx = pd.date_range("2021-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_run_optimizer_smoke():
    cache = {f"T{i}.TW": _df(seed=i) for i in range(3)}
    top = run_optimizer(cache, n_samples=20, seed=1)
    assert isinstance(top, list)
    # Quality filter: win_rate (profitable_rate) >= 0.80, avg_win >= 10, overall > 0
    for r in top:
        assert r["metrics"]["win_rate"] >= 0.80
        assert r["metrics"]["total_trades"] >= 15
        assert r["metrics"]["avg_win_return_pct"] >= 10
        assert r["metrics"]["avg_return_pct"] > 0
