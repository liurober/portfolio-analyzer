from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.screener_core import apply_liquidity_filter, select_top, Pick


def test_liquidity_passes():
    n = 30
    df = pd.DataFrame({"Volume": np.full(n, 1_000_000.0)},
                      index=pd.date_range("2025-01-01", periods=n, freq="W-FRI"))
    assert apply_liquidity_filter(
        df, 25.0, {"min_price": 10, "max_price": 100, "min_vol_k": 500}
    ) is True


def test_liquidity_blocks_low_volume():
    n = 30
    df = pd.DataFrame({"Volume": np.full(n, 50_000.0)},
                      index=pd.date_range("2025-01-01", periods=n, freq="W-FRI"))
    assert apply_liquidity_filter(
        df, 25.0, {"min_price": 10, "max_price": 100, "min_vol_k": 500}
    ) is False


def test_liquidity_blocks_out_of_band_price():
    n = 30
    df = pd.DataFrame({"Volume": np.full(n, 1_000_000.0)},
                      index=pd.date_range("2025-01-01", periods=n, freq="W-FRI"))
    assert apply_liquidity_filter(
        df, 250.0, {"min_price": 10, "max_price": 100, "min_vol_k": 500}
    ) is False


def _pick(symbol, score, rr):
    return Pick(symbol=symbol, name_zh="X", sector="半導體", last_close=20.0,
                score=score, indicators_fired=["rsi"], pattern=None,
                pattern_confidence=None, entry=20.0, stop=18.0, target=24.0,
                rr=rr, hold_weeks=5, params_version="t")


def test_select_top_orders_by_score():
    picks = [_pick("A.TW", 5, 3.0), _pick("B.TW", 8, 2.0), _pick("C.TW", 7, 4.0)]
    top = select_top(picks, n=2, cooldown_weeks=0)
    assert top[0].symbol == "B.TW"
    assert top[1].symbol == "C.TW"
