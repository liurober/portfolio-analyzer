"""Monte Carlo parameter optimizer for the Taiwan screener.

Procedure:
  1. Sample n_samples random parameter dicts from PARAM_SPACE.
  2. For each dict, run simulate() across every ticker in data_cache.
  3. Aggregate trades and summarize to {win_rate, avg_return_pct, sharpe, max_drawdown}.
  4. Score with composite_score().
  5. Filter quality: win_rate >= 0.70 AND total_trades >= 20 AND avg_return_pct >= 15.
  6. Return top-20 by composite score and write best -> optimal_params.json.

Targets:
  - Win rate >= 80%
  - Avg return per trade 20-30%
  - Hold period 5-6 weeks
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from backtest.engine import simulate, summarize

HERE = Path(__file__).resolve().parent
OPTIMAL_PARAMS_PATH = HERE / "optimal_params.json"

# ----- PARAMETER SPACE -------------------------------------------------------
PARAM_SPACE: dict[str, list] = {
    "min_score":         [4, 5, 6, 7, 8],
    "rsi_low":           [20, 25, 30, 35],
    "rsi_high":          [70, 75, 80, 85],
    "chandelier_mult":   [2.0, 2.5, 3.0, 3.5],
    "chandelier_period": [14, 18, 22, 26],
    "target_mult":       [1.5, 2.0, 2.5, 3.0, 3.5],
    "hold_weeks":        [3, 4, 5, 6],
    "min_price":         [5, 10, 15, 20],
    "max_price":         [80, 100, 150, 200],
    "min_vol_k":         [300, 500, 750, 1000],
    "bb_period":         [20, 25, 30],
    "ma_fast":           [20, 30],
    "ma_slow":           [90, 120],
    "adx_threshold":     [15, 20, 25],
    "min_rr":            [1.5, 2.0, 2.5, 3.0],
    "require_macd":      [True, False],
    "require_ttm":       [True, False],
    "require_adx":       [True, False],
    "require_ma_stack":  [True, False],
}


# ----- COMPOSITE SCORE -------------------------------------------------------
def composite_score(metrics: dict) -> float:
    if metrics.get("total_trades", 0) < 20:
        return 0.0
    win_rate = metrics.get("win_rate", 0)
    avg_ret  = metrics.get("avg_return_pct", 0)
    sharpe   = metrics.get("sharpe", 0)
    drawdown = abs(metrics.get("max_drawdown", 100))
    return (
        0.40 * win_rate
      + 0.25 * min(avg_ret / 30, 1.0)
      + 0.20 * min(sharpe / 3.0, 1.0)
      + 0.15 * (1 - drawdown / 30)
    )


def sample_params(rng: random.Random) -> dict[str, Any]:
    p = {k: rng.choice(v) for k, v in PARAM_SPACE.items()}
    if p["rsi_high"] <= p["rsi_low"] + 20:
        p["rsi_high"] = min(85, p["rsi_low"] + 25)
    if p["max_price"] <= p["min_price"] + 30:
        p["max_price"] = p["min_price"] + 50
    return p


def _backtest_all(data_cache: dict[str, pd.DataFrame],
                  params: dict[str, Any]) -> dict[str, Any]:
    all_trades = []
    for tk, df in data_cache.items():
        try:
            all_trades.extend(simulate(tk, df, params))
        except Exception:
            continue
    return summarize(all_trades)


def run_optimizer(
    data_cache: dict[str, pd.DataFrame],
    n_samples: int = 2000,
    seed: int = 42,
) -> list[dict]:
    """Sample n_samples random param sets, backtest each on data_cache,
    return top-20 quality results sorted by composite_score.

    Quality filter: win_rate >= 0.70 AND total_trades >= 20 AND avg_return_pct >= 15
    """
    rng = random.Random(seed)
    results: list[dict] = []
    for _ in tqdm(range(n_samples), desc="MC samples"):
        params = sample_params(rng)
        metrics = _backtest_all(data_cache, params)
        if (metrics.get("total_trades", 0) < 20
                or metrics.get("win_rate", 0) < 0.70
                or metrics.get("avg_return_pct", 0) < 15):
            continue
        cs = composite_score(metrics)
        results.append({"params": params, "metrics": metrics, "composite": cs})
    results.sort(key=lambda r: r["composite"], reverse=True)
    return results[:20]


def write_optimal(top: list[dict]) -> Path:
    if not top:
        # Keep existing best — do not overwrite with empty
        existing = json.loads(OPTIMAL_PARAMS_PATH.read_text(encoding="utf-8"))
        return OPTIMAL_PARAMS_PATH
    payload = {
        "generated": datetime.utcnow().isoformat(timespec="seconds"),
        "target": {"win_rate": 0.80, "avg_return_pct": 25, "hold_weeks": "5-6"},
        "best": top[0]["params"],
        "top20": top,
    }
    OPTIMAL_PARAMS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return OPTIMAL_PARAMS_PATH


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cache", type=str, required=True,
                        help="path to a pre-built parquet directory of weekly bars")
    args = parser.parse_args(argv)
    cache_dir = Path(args.cache)
    data_cache = {}
    for f in cache_dir.glob("*.parquet"):
        data_cache[f.stem] = pd.read_parquet(f)
    print(f"[optimizer] loaded {len(data_cache)} tickers from {cache_dir}")
    top = run_optimizer(data_cache, n_samples=args.samples, seed=args.seed)
    path = write_optimal(top)
    print(f"[optimizer] wrote {path}")
    if top:
        b = top[0]
        print(f"[optimizer] best composite={b['composite']:.3f} "
              f"win_rate={b['metrics']['win_rate']:.2%} "
              f"avg_ret={b['metrics']['avg_return_pct']:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
