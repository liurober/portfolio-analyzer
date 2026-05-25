"""Taiwan technical indicators — long-only, parameter-configurable.

Every threshold here is overridable via the `params` dict so the Monte Carlo
optimizer can re-tune the screener without code changes.

DEFAULTS mirror backtest/optimal_params.json `best` block.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

DEFAULT_PARAMS: dict[str, Any] = {
    "rsi_low": 30,
    "rsi_high": 75,
    "bb_period": 20,
    "chandelier_period": 22,
    "chandelier_mult": 3.0,
    "ma_fast": 20,
    "ma_slow": 120,
    "adx_threshold": 20,
    "require_macd": True,
    "require_ttm": False,
    "require_adx": True,
    "require_ma_stack": True,
}


@dataclass
class Signal:
    name: str
    fired: bool
    value: float | None = None
    note: str = ""


def _merge(params: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(DEFAULT_PARAMS)
    if params:
        merged.update(params)
    return merged


def rsi_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    rsi = RSIIndicator(close=df["Close"], window=14).rsi()
    last = float(rsi.iloc[-1])
    fired = params["rsi_low"] < last < params["rsi_high"]
    return Signal("rsi", fired, last, f"RSI(14)={last:.1f}")


def bb_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    bb = BollingerBands(close=df["Close"], window=params["bb_period"], window_dev=2)
    mid = bb.bollinger_mavg()
    last_close = float(df["Close"].iloc[-1])
    last_mid = float(mid.iloc[-1])
    fired = last_close > last_mid
    return Signal("bb", fired, last_mid, f"Close>{last_mid:.2f}")


def macd_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    macd = MACD(close=df["Close"], window_slow=26, window_fast=12, window_sign=9)
    line = macd.macd()
    sig = macd.macd_signal()
    hist = macd.macd_diff()
    above = float(line.iloc[-1]) > float(sig.iloc[-1])
    rising = float(hist.iloc[-1]) > float(hist.iloc[-2])
    fired = bool(above and rising)
    return Signal("macd", fired, float(hist.iloc[-1]),
                  f"hist={float(hist.iloc[-1]):.3f}")


def chandelier_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    period = int(params["chandelier_period"])
    mult = float(params["chandelier_mult"])
    atr = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"],
                           window=period).average_true_range()
    hh = df["High"].rolling(period).max()
    ce_long = hh - mult * atr
    last_close = float(df["Close"].iloc[-1])
    last_ce = float(ce_long.iloc[-1])
    fired = last_close > last_ce
    return Signal("chandelier", fired, last_ce, f"CE={last_ce:.2f}")


def ttm_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    """TTM Squeeze: BB inside Keltner = squeeze ON. Fired when squeeze releases
    OR momentum oscillator is rising."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    bb = BollingerBands(close=close, window=20, window_dev=2)
    bb_up = bb.bollinger_hband()
    bb_dn = bb.bollinger_lband()
    atr = AverageTrueRange(high=high, low=low, close=close, window=20).average_true_range()
    ema = close.ewm(span=20, adjust=False).mean()
    kc_up = ema + 1.5 * atr
    kc_dn = ema - 1.5 * atr
    squeeze_on = (bb_up < kc_up) & (bb_dn > kc_dn)
    fired_release = bool(squeeze_on.iloc[-2] and not squeeze_on.iloc[-1])
    midpoint = (high.rolling(20).max() + low.rolling(20).min()) / 2
    avg = (midpoint + close.rolling(20).mean()) / 2
    momo = (close - avg).rolling(20).apply(
        lambda x: np.polyfit(np.arange(len(x)), x, 1)[0], raw=False
    )
    momo_rising = bool(momo.iloc[-1] > momo.iloc[-2])
    fired = bool(fired_release or momo_rising)
    return Signal("ttm", fired, float(momo.iloc[-1]),
                  f"release={fired_release} rising={momo_rising}")


def ma_stack_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    fast = SMAIndicator(close=df["Close"], window=int(params["ma_fast"])).sma_indicator()
    mid = SMAIndicator(close=df["Close"], window=50).sma_indicator()
    slow = SMAIndicator(close=df["Close"], window=int(params["ma_slow"])).sma_indicator()
    c = float(df["Close"].iloc[-1])
    f = float(fast.iloc[-1])
    m = float(mid.iloc[-1])
    s = float(slow.iloc[-1])
    fired = (c > f) and (f > m) and (m > s)
    return Signal("ma_stack", fired, f,
                  f"C={c:.2f}>F={f:.2f}>M={m:.2f}>S={s:.2f}")


def adx_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    adx = ADXIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=14)
    last_adx = float(adx.adx().iloc[-1])
    last_pos = float(adx.adx_pos().iloc[-1])
    last_neg = float(adx.adx_neg().iloc[-1])
    fired = (last_adx >= float(params["adx_threshold"])) and (last_pos > last_neg)
    return Signal("adx", fired, last_adx,
                  f"ADX={last_adx:.1f} +DI={last_pos:.1f} -DI={last_neg:.1f}")


def volume_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    """Up-week avg volume > down-week avg volume over last 10 bars."""
    sub = df.tail(10)
    up = sub[sub["Close"] >= sub["Open"]]["Volume"].mean()
    dn = sub[sub["Close"] < sub["Open"]]["Volume"].mean()
    up = 0.0 if pd.isna(up) else float(up)
    dn = 0.0 if pd.isna(dn) else float(dn)
    fired = up > dn
    return Signal("volume", fired, up, f"upV={up:.0f} dnV={dn:.0f}")


SIGNAL_FUNCS = [
    rsi_signal, bb_signal, macd_signal, chandelier_signal,
    ttm_signal, ma_stack_signal, adx_signal, volume_signal,
]


def score_signals_tw(df: pd.DataFrame, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run all 8 signals on a weekly DataFrame. Returns score + per-signal results."""
    p = _merge(params)
    results: list[Signal] = []
    for fn in SIGNAL_FUNCS:
        try:
            results.append(fn(df, p))
        except Exception as exc:
            results.append(Signal(fn.__name__.replace("_signal", ""), False, None,
                                  f"ERR:{exc}"))

    # Required gates (long-only): respect params toggles
    name_to = {r.name: r for r in results}

    def gate(name: str, required_key: str) -> bool:
        if not p.get(required_key, False):
            return True
        return name_to[name].fired

    gates_ok = (
        gate("macd", "require_macd")
        and gate("ttm", "require_ttm")
        and gate("adx", "require_adx")
        and gate("ma_stack", "require_ma_stack")
    )

    score = sum(1 for r in results if r.fired)
    return {
        "score": int(score),
        "signals": {r.name: {"fired": r.fired, "value": r.value, "note": r.note}
                    for r in results},
        "gates_ok": bool(gates_ok),
        "params": p,
    }
