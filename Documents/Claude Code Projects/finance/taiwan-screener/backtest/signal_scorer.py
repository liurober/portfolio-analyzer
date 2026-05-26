"""Per-signal win probability model for the Taiwan screener.

Uses logistic regression (numpy only, no sklearn) trained on historical
trade outcomes. Features are extracted at entry time from the same data
already computed by the screener.

Workflow
--------
1. Run simulate() with capture_features=True to collect TradeResult objects
   that carry an `entry_features` dict.
2. Call SignalScorer.train(trades).
3. Call SignalScorer.save(path) → writes signal_model.json.
4. At live signal time: load model, call scorer.predict(features) to get
   (win_probability, n_samples, confidence_label).

Features used
-------------
score        : 0–8  composite signal count (primary predictor)
rr_ratio     : 1–5  risk/reward (higher = better setup)
atr_pct      : 0–0.20  weekly ATR / price (lower = steadier stock)
rsi          : 20–80  RSI(14) at entry
momentum_13w : −0.30–0.50  13-week return fraction
ma_ratio     : 0.80–1.30  close / slow_MA (above 1 = uptrend)
vol_ratio    : 0.50–5.0   current week vol / 10-week avg vol
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "signal_model.json"

# Feature order — must be consistent across train/predict
FEATURE_NAMES = [
    "score",        # 0–8
    "rr_ratio",     # 1.0–5.0
    "atr_pct",      # 0.02–0.25 (as fraction, not %)
    "rsi",          # 20–80
    "momentum_13w", # −0.30–0.50 (fraction)
    "ma_ratio",     # 0.80–1.30
    "vol_ratio",    # 0.5–5.0
]

# Normalisation bounds [min, max] for each feature
_BOUNDS = {
    "score":        (0.0, 8.0),
    "rr_ratio":     (1.0, 5.0),
    "atr_pct":      (0.01, 0.25),
    "rsi":          (10.0, 85.0),
    "momentum_13w": (-0.40, 0.60),
    "ma_ratio":     (0.70, 1.40),
    "vol_ratio":    (0.3, 6.0),
}


def _norm(value: float, name: str) -> float:
    lo, hi = _BOUNDS[name]
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _feature_vector(features: dict[str, float]) -> np.ndarray:
    return np.array([_norm(features.get(f, 0.0), f) for f in FEATURE_NAMES],
                    dtype=np.float64)


def extract_features(df_so_far: "pd.DataFrame",
                     scored: dict[str, Any],
                     levels: dict[str, Any]) -> dict[str, float]:
    """Extract normalised features from already-computed screener output.

    Parameters match what _qualifies() already has in scope, so no extra
    indicator computation is needed.
    """
    import pandas as pd

    close = df_so_far["Close"]
    last_close = float(close.iloc[-1])
    sigs = scored.get("signals", {})
    params = scored.get("params", {})

    # score
    score = float(scored.get("score", 0))

    # R/R ratio from levels
    rr_ratio = float(levels.get("rr") or 2.0)

    # ATR (14-bar)
    atr_pct = 0.05  # default
    if len(df_so_far) >= 15:
        hi = df_so_far["High"].tail(14)
        lo = df_so_far["Low"].tail(14)
        cl = close.tail(15)
        prev_cl = cl.shift(1).tail(14)
        tr = (hi - lo).combine((hi - prev_cl).abs(), max).combine(
            (lo - prev_cl).abs(), max)
        atr_pct = float(tr.mean()) / last_close

    # RSI from signals dict (already computed)
    rsi = float(sigs.get("rsi", {}).get("value") or 50.0)

    # 13-week momentum
    momentum_13w = 0.0
    if len(df_so_far) >= 14:
        momentum_13w = last_close / float(close.iloc[-14]) - 1.0

    # MA ratio: close / slow_MA
    ma_ratio = 1.0
    ma_slow = int(params.get("ma_slow", 120))
    if len(df_so_far) >= ma_slow:
        slow_ma = float(close.tail(ma_slow).mean())
        if slow_ma > 0:
            ma_ratio = last_close / slow_ma

    # Volume ratio: latest bar vol / 10-bar avg vol
    vol_ratio = 1.0
    if len(df_so_far) >= 11 and "Volume" in df_so_far.columns:
        avg_vol = float(df_so_far["Volume"].tail(10).mean())
        if avg_vol > 0:
            vol_ratio = float(df_so_far["Volume"].iloc[-1]) / avg_vol

    return {
        "score":        score,
        "rr_ratio":     rr_ratio,
        "atr_pct":      atr_pct,
        "rsi":          rsi,
        "momentum_13w": momentum_13w,
        "ma_ratio":     ma_ratio,
        "vol_ratio":    vol_ratio,
    }


class SignalScorer:
    """Logistic regression model for per-signal win probability.

    Trained on historical (features, outcome) pairs from the walk-forward
    backtest.  Uses numpy gradient descent — no sklearn required.
    """

    def __init__(self) -> None:
        self.weights: np.ndarray | None = None   # shape: (n_features + 1,) incl. bias
        self.n_samples: int = 0
        self.base_rate: float = 0.5              # overall profitable_rate
        self.generated: str = ""
        # Binned lookup table (fallback + calibration reference)
        self._bins: dict[str, dict] = {}

    # ── Training ──────────────────────────────────────────────────────────────

    def train(self, trades: list, lr: float = 0.05, epochs: int = 2000) -> None:
        """Train on a list of TradeResult objects that have `entry_features`."""
        records = [(t.entry_features, t.pnl_pct > 0)
                   for t in trades
                   if getattr(t, "entry_features", None) is not None]
        if len(records) < 20:
            raise ValueError(f"Too few labelled trades ({len(records)}) to train.")

        feats, labels = zip(*records)
        X = np.array([_feature_vector(f) for f in feats])   # (n, k)
        y = np.array(labels, dtype=np.float64)               # (n,)

        self.n_samples = len(y)
        self.base_rate = float(y.mean())

        # Add bias column
        Xb = np.column_stack([np.ones(len(X)), X])           # (n, k+1)
        w = np.zeros(Xb.shape[1])

        for _ in range(epochs):
            z = Xb @ w
            pred = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
            grad = Xb.T @ (pred - y) / len(y)
            w -= lr * grad

        self.weights = w
        self.generated = datetime.utcnow().isoformat(timespec="seconds")
        self._build_bins(feats, labels)

    def _build_bins(self, feats: list, labels: list) -> None:
        """Build a binned lookup table for calibration display."""
        bins: dict[str, dict] = {}
        for feat, lab in zip(feats, labels):
            s = int(feat.get("score", 0))
            rr = feat.get("rr_ratio", 2.0)
            rr_bin = "1-2" if rr < 2 else ("2-3" if rr < 3 else "3+")
            key = f"s{s}_{rr_bin}"
            if key not in bins:
                bins[key] = {"n": 0, "wins": 0}
            bins[key]["n"] += 1
            if lab:
                bins[key]["wins"] += 1
        for k, v in bins.items():
            v["win_rate"] = round(v["wins"] / v["n"], 3) if v["n"] > 0 else self.base_rate
        self._bins = bins

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict(self, features: dict[str, float]) -> dict[str, Any]:
        """Predict win probability for a single signal.

        Returns
        -------
        dict with keys:
          win_probability : float  0–1
          confidence      : str    "HIGH" / "MEDIUM" / "LOW"
          n_similar       : int    samples in nearest bin
          max_loss_pct    : float  if 'entry' and 'stop' in features
          expected_value  : float  estimated EV (if avg_win_pct provided)
        """
        if self.weights is None:
            return {"win_probability": self.base_rate, "confidence": "LOW",
                    "n_similar": 0}

        xv = _feature_vector(features)
        xb = np.concatenate([[1.0], xv])
        z = float(xb @ self.weights)
        prob = 1.0 / (1.0 + math.exp(-max(-30, min(30, z))))

        # Confidence from nearest bin sample count
        s = int(features.get("score", 0))
        rr = features.get("rr_ratio", 2.0)
        rr_bin = "1-2" if rr < 2 else ("2-3" if rr < 3 else "3+")
        bin_key = f"s{s}_{rr_bin}"
        n_similar = self._bins.get(bin_key, {}).get("n", 0)
        confidence = "HIGH" if n_similar >= 20 else ("MEDIUM" if n_similar >= 8 else "LOW")

        result: dict[str, Any] = {
            "win_probability": round(prob, 3),
            "confidence": confidence,
            "n_similar": n_similar,
        }

        # Max loss % (if stop/entry provided in features dict)
        entry = features.get("entry")
        stop  = features.get("stop")
        if entry and stop and entry > 0:
            result["max_loss_pct"] = round((stop - entry) / entry * 100, 2)

        # Expected value = P(win) × avg_win − P(loss) × avg_loss
        avg_win = features.get("avg_win_pct", 17.0)   # default from historical
        avg_loss = abs(features.get("max_loss_pct", result.get("max_loss_pct", -7.0) or -7.0))
        ev = prob * avg_win - (1 - prob) * avg_loss
        result["expected_value_pct"] = round(ev, 2)

        return result

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: "Path | str" = MODEL_PATH) -> Path:
        path = Path(path)
        payload = {
            "generated": self.generated,
            "n_samples": self.n_samples,
            "base_rate": self.base_rate,
            "feature_names": FEATURE_NAMES,
            "weights": self.weights.tolist() if self.weights is not None else [],
            "bins": self._bins,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path

    def load(self, path: "Path | str" = MODEL_PATH) -> "SignalScorer":
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.generated   = payload.get("generated", "")
        self.n_samples   = payload.get("n_samples", 0)
        self.base_rate   = payload.get("base_rate", 0.5)
        self.weights     = np.array(payload["weights"]) if payload.get("weights") else None
        self._bins       = payload.get("bins", {})
        return self

    # ── Convenience ───────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: "Path | str" = MODEL_PATH) -> "SignalScorer":
        return cls().load(path)

    def summary(self) -> str:
        lines = [
            f"SignalScorer  trained={self.generated}  n={self.n_samples}",
            f"  base_rate={self.base_rate:.1%}",
            "  score×rr bins (n≥5):",
        ]
        for k, v in sorted(self._bins.items()):
            if v["n"] >= 5:
                lines.append(f"    {k:12s}  n={v['n']:4d}  win={v['win_rate']:.1%}")
        return "\n".join(lines)
