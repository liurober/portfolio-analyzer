"""Pivot-based support / resistance level detection.

Returns up to N support levels (below last close) and N resistance
levels (above last close), sorted by proximity. Used for entry/stop/target
suggestions and chart overlays.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


@dataclass
class SRLevel:
    price: float
    strength: int   # number of times the level was touched
    last_touch_bar: int


def _cluster(levels: list[float], tol: float = 0.015) -> list[tuple[float, int]]:
    if not levels:
        return []
    levels = sorted(levels)
    clusters: list[list[float]] = [[levels[0]]]
    for x in levels[1:]:
        if abs(x - clusters[-1][-1]) / clusters[-1][-1] < tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [(float(np.mean(c)), len(c)) for c in clusters]


def find_levels(df: pd.DataFrame, lookback: int = 80, n: int = 3
                ) -> dict[str, list[SRLevel]]:
    sub = df.tail(lookback).copy().reset_index(drop=True)
    highs = sub["High"].to_numpy()
    lows = sub["Low"].to_numpy()

    peak_idx, _ = find_peaks(highs, distance=3)
    trough_idx, _ = find_peaks(-lows, distance=3)

    peak_levels = [float(highs[i]) for i in peak_idx]
    trough_levels = [float(lows[i]) for i in trough_idx]

    resistance_clusters = _cluster(peak_levels)
    support_clusters = _cluster(trough_levels)

    last_close = float(sub["Close"].iloc[-1])

    resistances = sorted(
        [SRLevel(p, s, int(peak_idx[-1]) if len(peak_idx) else 0)
         for p, s in resistance_clusters if p > last_close],
        key=lambda x: x.price,
    )[:n]
    supports = sorted(
        [SRLevel(p, s, int(trough_idx[-1]) if len(trough_idx) else 0)
         for p, s in support_clusters if p < last_close],
        key=lambda x: x.price, reverse=True,
    )[:n]
    return {"support": supports, "resistance": resistances}


def suggest_trade_levels(df: pd.DataFrame, target_mult: float = 2.5,
                         min_rr: float = 2.0
                         ) -> dict[str, float | None]:
    """Pick entry = last close, stop = nearest support, target = entry + R*target_mult.

    Returns {"entry","stop","target","rr"} or None values when no valid setup.
    """
    levels = find_levels(df)
    last_close = float(df["Close"].iloc[-1])
    if not levels["support"]:
        return {"entry": None, "stop": None, "target": None, "rr": None}
    stop = levels["support"][0].price
    risk = last_close - stop
    if risk <= 0:
        return {"entry": None, "stop": None, "target": None, "rr": None}
    target = last_close + target_mult * risk
    rr = (target - last_close) / risk
    return {"entry": last_close, "stop": stop, "target": target, "rr": float(rr)}
