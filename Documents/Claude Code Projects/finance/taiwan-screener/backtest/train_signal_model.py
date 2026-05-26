"""Train the per-signal win probability model from cached backtest data.

Usage:
    python -m backtest.train_signal_model              # uses /tmp/tw_full_cache.pkl
    python -m backtest.train_signal_model --cache PATH

Outputs:
    backtest/signal_model.json   (loaded by main.py at scan time)
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.engine import simulate, summarize
from backtest.signal_scorer import SignalScorer, MODEL_PATH

DEFAULT_CACHE = Path("/tmp/tw_full_cache.pkl")

TRAIN_PARAMS = {
    "min_score": 6, "rsi_low": 30, "rsi_high": 75, "bb_period": 20,
    "chandelier_period": 22, "chandelier_mult": 3.0,
    "ma_fast": 20, "ma_slow": 120, "adx_threshold": 20,
    "target_mult": 2.5, "hold_weeks": 5,
    "min_price": 10, "max_price": 5000, "min_vol_k": 500, "min_rr": 2.0,
    "require_macd": True, "require_ttm": False,
    "require_adx": False, "require_ma_stack": True,
    "require_index_regime": False, "max_atr_pct": None, "min_momentum_pct": None,
}


def train(cache_path: Path = DEFAULT_CACHE) -> SignalScorer:
    print(f"Loading cache from {cache_path} ...")
    with open(cache_path, "rb") as f:
        data_cache: dict = pickle.load(f)
    print(f"  {len(data_cache)} tickers loaded")

    print("Running simulate() with capture_features=True ...")
    all_trades = []
    for i, (tk, df) in enumerate(data_cache.items(), 1):
        try:
            trades = simulate(tk, df, TRAIN_PARAMS, capture_features=True)
            all_trades.extend(trades)
        except Exception:
            pass
        if i % 100 == 0:
            print(f"  [{i}/{len(data_cache)}] {len(all_trades)} trades collected...")

    print(f"\n  Total trades with features: {len(all_trades)}")
    labelled = [t for t in all_trades if t.entry_features is not None]
    print(f"  Labelled (have features):   {len(labelled)}")

    s = summarize(all_trades)
    print(f"  Overall profitable rate:    {s['win_rate']:.1%}")
    print(f"  Avg win return:             {s['avg_win_return_pct']:.1f}%")

    print("\nTraining SignalScorer ...")
    scorer = SignalScorer()
    scorer.train(labelled)
    path = scorer.save(MODEL_PATH)
    print(f"  Saved to {path}")
    print()
    print(scorer.summary())
    return scorer


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default=str(DEFAULT_CACHE),
                        help="Path to pickle cache of {ticker: DataFrame}")
    args = parser.parse_args(argv)
    train(Path(args.cache))


if __name__ == "__main__":
    raise SystemExit(main())
