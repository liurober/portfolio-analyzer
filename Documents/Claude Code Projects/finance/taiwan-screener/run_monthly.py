"""Monthly orchestrator: evaluate open picks, rebuild data cache,
run Monte Carlo optimizer, write report."""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import yfinance as yf
from tqdm import tqdm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from screener.universe_tw import load_universe
from backtest.evaluator import evaluate_open_picks
from backtest.optimizer import run_optimizer, write_optimal
from backtest.report import main as build_report_main


def build_data_cache() -> dict[str, pd.DataFrame]:
    cache: dict[str, pd.DataFrame] = {}
    for entry in tqdm(load_universe(), desc="cache"):
        try:
            df = yf.download(entry["symbol"], period="5y", interval="1wk",
                             auto_adjust=True, progress=False)
            if df is None or df.empty or len(df) < 80:
                continue
            cache[entry["symbol"]] = df.dropna()
        except Exception:
            continue
    return cache


def _load_market_df() -> "pd.DataFrame | None":
    """Download 0050.TW weekly bars for the market regime filter."""
    try:
        df = yf.download("0050.TW", period="5y", interval="1wk",
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        return df[["Close"]].dropna()
    except Exception:
        return None


def main() -> int:
    print(f"[monthly] start {datetime.utcnow().isoformat()}")
    closed_stats = evaluate_open_picks()
    print(f"[monthly] evaluator: {closed_stats}")
    cache = build_data_cache()
    print(f"[monthly] cache built: {len(cache)} tickers")
    market_df = _load_market_df()
    print(f"[monthly] market regime data: {'loaded' if market_df is not None else 'unavailable'}")
    top = run_optimizer(cache, n_samples=2000, seed=42, market_df=market_df)
    write_optimal(top)
    print(f"[monthly] MC produced {len(top)} quality sets")
    build_report_main()
    print("[monthly] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
