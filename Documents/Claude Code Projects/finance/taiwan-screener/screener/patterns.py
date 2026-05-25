"""Three weekly chart patterns: Reverse H&S, Cup & Handle, Bull Flag.

Each detector returns a dict:
    {"pattern": "<name>", "confidence": 0.0-1.0, "neckline": float|None, "notes": str}

detect_pattern() runs all three and returns the highest-confidence match, or None.

Pattern names in Traditional Chinese: 反向頭肩底 / 杯柄 / 旗形.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


def _troughs(close: np.ndarray, distance: int = 4) -> np.ndarray:
    idx, _ = find_peaks(-close, distance=distance)
    return idx


def _peaks(close: np.ndarray, distance: int = 4) -> np.ndarray:
    idx, _ = find_peaks(close, distance=distance)
    return idx


def detect_reverse_hns(df: pd.DataFrame) -> dict[str, Any] | None:
    closes = df["Close"].to_numpy()
    if len(closes) < 40:
        return None
    troughs = _troughs(closes[-40:], distance=3)
    if len(troughs) < 3:
        return None
    t = troughs[-3:]
    left = closes[-40:][t[0]]
    head = closes[-40:][t[1]]
    right = closes[-40:][t[2]]
    if head < left and head < right and abs(left - right) / left < 0.10:
        neckline = max(closes[-40:][t[0]:t[2]])
        depth = (left + right) / 2 - head
        conf = max(0.0, min(1.0, 1 - abs(left - right) / left * 4))
        return {
            "pattern": "反向頭肩底 (Reverse H&S)",
            "confidence": float(round(conf, 2)),
            "neckline": float(neckline),
            "notes": f"頭部={head:.2f} 左肩={left:.2f} 右肩={right:.2f} 深度={depth:.2f}",
        }
    return None


def detect_cup_and_handle(df: pd.DataFrame) -> dict[str, Any] | None:
    closes = df["Close"].to_numpy()
    if len(closes) < 50:
        return None
    window = closes[-50:]
    left_peak_idx = int(np.argmax(window[:20]))
    right_window = window[20:]
    right_peak_idx = 20 + int(np.argmax(right_window))
    if right_peak_idx <= left_peak_idx + 10:
        return None
    cup_low = float(np.min(window[left_peak_idx:right_peak_idx]))
    left_peak = float(window[left_peak_idx])
    right_peak = float(window[right_peak_idx])
    if abs(left_peak - right_peak) / left_peak > 0.08:
        return None
    handle = window[right_peak_idx:]
    if len(handle) < 4:
        return None
    handle_pullback = (right_peak - float(np.min(handle))) / right_peak
    if not (0.02 < handle_pullback < 0.18):
        return None
    depth = (left_peak - cup_low) / left_peak
    conf = max(0.0, min(1.0, 0.5 + (0.5 - abs(0.30 - depth))))
    return {
        "pattern": "杯柄 (Cup & Handle)",
        "confidence": float(round(conf, 2)),
        "neckline": float(max(left_peak, right_peak)),
        "notes": f"杯深={depth*100:.1f}% 柄回檔={handle_pullback*100:.1f}%",
    }


def detect_bull_flag(df: pd.DataFrame) -> dict[str, Any] | None:
    closes = df["Close"].to_numpy()
    if len(closes) < 20:
        return None
    pole = closes[-20:-8]
    flag = closes[-8:]
    pole_gain = (pole[-1] - pole[0]) / pole[0]
    if pole_gain < 0.10:
        return None
    flag_range = (float(np.max(flag)) - float(np.min(flag))) / float(np.mean(flag))
    if flag_range > 0.08:
        return None
    last = float(closes[-1])
    flag_top = float(np.max(flag))
    breakout_ready = last >= flag_top * 0.97
    conf = float(round(
        min(1.0, pole_gain * 3 + (0.05 - flag_range) + (0.1 if breakout_ready else 0)),
        2,
    ))
    return {
        "pattern": "旗形 (Bull Flag)",
        "confidence": max(0.0, conf),
        "neckline": flag_top,
        "notes": f"旗杆漲幅={pole_gain*100:.1f}% 旗區間={flag_range*100:.1f}%",
    }


def detect_pattern(df: pd.DataFrame) -> dict[str, Any] | None:
    """Run all three pattern detectors. Return highest-confidence match, or None."""
    candidates = []
    for fn in (detect_reverse_hns, detect_cup_and_handle, detect_bull_flag):
        try:
            r = fn(df)
            if r is not None:
                candidates.append(r)
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return candidates[0]
