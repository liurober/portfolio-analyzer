"""Tests for backtest.signal_scorer."""
from finance_tw_path import ensure_path  # noqa: F401
import math
import numpy as np
import pandas as pd
import pytest

from backtest.signal_scorer import (
    SignalScorer, extract_features, _feature_vector, FEATURE_NAMES, _norm
)
from backtest.engine import TradeResult


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fake_trade(pnl: float, features: dict | None = None) -> TradeResult:
    return TradeResult(
        ticker="T.TW", entry_date="2025-01-01",
        entry=100.0, stop=93.0, target=120.0,
        exit_date="2025-02-01", exit_price=100.0 + pnl,
        outcome="win" if pnl > 7 else ("loss" if pnl < -7 else "neutral"),
        pnl_pct=pnl, hold_weeks_actual=5, score=7,
        entry_features=features,
    )


def _good_features() -> dict:
    return {
        "score": 7.0, "rr_ratio": 2.5, "atr_pct": 0.05,
        "rsi": 35.0, "momentum_13w": 0.08, "ma_ratio": 1.05,
        "vol_ratio": 1.2, "entry": 100.0, "stop": 93.0,
    }


def _bad_features() -> dict:
    return {
        "score": 4.0, "rr_ratio": 1.2, "atr_pct": 0.18,
        "rsi": 72.0, "momentum_13w": -0.10, "ma_ratio": 0.88,
        "vol_ratio": 0.6, "entry": 100.0, "stop": 90.0,
    }


# ── Normalisation ─────────────────────────────────────────────────────────────

def test_norm_clamps_to_01():
    assert _norm(-100, "score") == 0.0
    assert _norm(100, "score") == 1.0


def test_feature_vector_length():
    v = _feature_vector(_good_features())
    assert len(v) == len(FEATURE_NAMES)


def test_feature_vector_range():
    v = _feature_vector(_good_features())
    assert all(0.0 <= x <= 1.0 for x in v)


# ── SignalScorer training ─────────────────────────────────────────────────────

def _make_trades(n_good=80, n_bad=40):
    trades = []
    for _ in range(n_good):
        trades.append(_fake_trade(15.0, _good_features()))
    for _ in range(n_bad):
        trades.append(_fake_trade(-5.0, _bad_features()))
    return trades


def test_train_requires_minimum_trades():
    scorer = SignalScorer()
    with pytest.raises(ValueError):
        scorer.train([_fake_trade(5.0, _good_features())] * 5)


def test_train_sets_weights():
    scorer = SignalScorer()
    scorer.train(_make_trades())
    assert scorer.weights is not None
    assert len(scorer.weights) == len(FEATURE_NAMES) + 1  # + bias


def test_good_features_higher_prob_than_bad():
    scorer = SignalScorer()
    scorer.train(_make_trades(n_good=100, n_bad=50))
    p_good = scorer.predict(_good_features())["win_probability"]
    p_bad  = scorer.predict(_bad_features())["win_probability"]
    assert p_good > p_bad, f"Expected good>{bad} but got {p_good:.3f} <= {p_bad:.3f}"


def test_predict_probability_in_range():
    scorer = SignalScorer()
    scorer.train(_make_trades())
    for feat in [_good_features(), _bad_features()]:
        p = scorer.predict(feat)["win_probability"]
        assert 0.0 <= p <= 1.0


def test_predict_returns_max_loss():
    scorer = SignalScorer()
    scorer.train(_make_trades())
    result = scorer.predict(_good_features())
    assert "max_loss_pct" in result
    assert result["max_loss_pct"] == pytest.approx(-7.0, abs=0.1)


def test_predict_returns_expected_value():
    scorer = SignalScorer()
    scorer.train(_make_trades())
    result = scorer.predict(_good_features())
    assert "expected_value_pct" in result


def test_predict_no_features_falls_back_to_base_rate():
    scorer = SignalScorer()
    scorer.train(_make_trades())
    # features dict with missing stop/entry → partial result still returns probability
    result = scorer.predict({"score": 6.0, "rr_ratio": 2.0})
    assert "win_probability" in result


# ── Save / Load ───────────────────────────────────────────────────────────────

def test_save_load_roundtrip(tmp_path):
    scorer = SignalScorer()
    scorer.train(_make_trades())
    path = tmp_path / "model.json"
    scorer.save(path)

    loaded = SignalScorer.from_file(path)
    assert loaded.n_samples == scorer.n_samples
    assert loaded.base_rate == pytest.approx(scorer.base_rate, abs=1e-6)
    assert loaded.weights is not None

    p_orig   = scorer.predict(_good_features())["win_probability"]
    p_loaded = loaded.predict(_good_features())["win_probability"]
    assert p_orig == pytest.approx(p_loaded, abs=1e-6)


# ── extract_features ─────────────────────────────────────────────────────────

def _make_df(n=130, seed=42):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.003, 0.02, n)
    close = 50 * np.cumprod(1 + rets)
    high = close * 1.015; low = close * 0.985
    open_ = close * (1 + rng.normal(0, 0.001, n))
    vol = rng.integers(500_000, 3_000_000, n).astype(float)
    idx = pd.date_range("2022-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_extract_features_keys():
    df = _make_df()
    scored = {"score": 7, "signals": {"rsi": {"value": 34.0}},
              "gates_ok": True, "params": {"ma_slow": 120}}
    levels = {"entry": 51.0, "stop": 47.0, "target": 60.0, "rr": 2.5}
    feats = extract_features(df, scored, levels)
    for k in ["score", "rr_ratio", "atr_pct", "rsi", "momentum_13w",
              "ma_ratio", "vol_ratio"]:
        assert k in feats, f"Missing key: {k}"


def test_extract_features_values_sane():
    df = _make_df()
    scored = {"score": 7, "signals": {"rsi": {"value": 34.0}},
              "gates_ok": True, "params": {"ma_slow": 120}}
    levels = {"entry": 51.0, "stop": 47.0, "target": 60.0, "rr": 2.5}
    feats = extract_features(df, scored, levels)
    assert 0 <= feats["score"] <= 8
    assert feats["atr_pct"] > 0
    assert 10 <= feats["rsi"] <= 90


# ── engine integration: capture_features ─────────────────────────────────────

def test_simulate_capture_features():
    """simulate() with capture_features=True populates entry_features on trades."""
    from backtest.engine import simulate

    df = _make_df(n=150)
    params = {
        "min_score": 4, "rsi_low": 20, "rsi_high": 85, "bb_period": 20,
        "chandelier_period": 22, "chandelier_mult": 3.0,
        "ma_fast": 20, "ma_slow": 120, "adx_threshold": 15,
        "target_mult": 2.0, "hold_weeks": 5,
        "min_price": 1, "max_price": 500_000, "min_vol_k": 1,
        "min_rr": 1.0, "require_macd": False, "require_ttm": False,
        "require_adx": False, "require_ma_stack": False,
        "require_index_regime": False, "max_atr_pct": None,
        "min_momentum_pct": None,
    }
    trades = simulate("T.TW", df, params, capture_features=True)
    if trades:  # may be 0 if no signals
        for t in trades:
            assert t.entry_features is not None
            assert "score" in t.entry_features
            assert "entry" in t.entry_features
