"""Tests for portfolio-analyzer/macro_context.py"""
import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

_MOD_PATH = pathlib.Path(__file__).parent.parent / "macro_context.py"
_spec = importlib.util.spec_from_file_location("macro_context", _MOD_PATH)
macro_context = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(macro_context)


def _make_spy_prices(trend: str = "up", n: int = 260) -> pd.DataFrame:
    if trend == "up":
        prices = np.linspace(400, 520, n)
    else:
        prices = np.linspace(520, 380, n)
    dates = pd.date_range(end="2026-05-18", periods=n, freq="B")
    return pd.DataFrame({"Close": prices}, index=dates)


def _make_sector_prices(spy_return: float = 0.05) -> dict:
    sectors = ["XLK", "XLE", "XLU", "XLF", "XLY", "SPY"]
    result = {}
    for s in sectors:
        if s in ("XLK", "XLY"):
            end_price = 100 * (1 + spy_return + 0.02)
        elif s == "SPY":
            end_price = 100 * (1 + spy_return)
        else:
            end_price = 100 * (1 - 0.01)
        prices = np.linspace(100, end_price, 23)
        dates = pd.date_range(end="2026-05-18", periods=23, freq="B")
        result[s] = pd.DataFrame({"Close": prices}, index=dates)
    return result


class TestMacroContextRegimes(unittest.TestCase):

    def test_rising_growth_low_inflation(self):
        regime = macro_context._classify_regime(vix=14, spread_3m10y_bps=50, spy_vs_200d_pct=5.0, inflation_pct=2.0)
        self.assertEqual(regime, "Rising Growth + Low Inflation")

    def test_rising_growth_rising_inflation(self):
        regime = macro_context._classify_regime(vix=14, spread_3m10y_bps=50, spy_vs_200d_pct=5.0, inflation_pct=3.0)
        self.assertEqual(regime, "Rising Growth + Rising Inflation")

    def test_stagflation(self):
        regime = macro_context._classify_regime(vix=25, spread_3m10y_bps=-30, spy_vs_200d_pct=-5.0, inflation_pct=3.5)
        self.assertEqual(regime, "Stagflation")

    def test_deflation_recession(self):
        regime = macro_context._classify_regime(vix=28, spread_3m10y_bps=-20, spy_vs_200d_pct=-8.0, inflation_pct=1.5)
        self.assertEqual(regime, "Deflation / Recession")


class TestMacroContextRecommendedPlan(unittest.TestCase):

    def test_aggressive_plan_for_low_inflation(self):
        self.assertEqual(macro_context._plan_for_regime("Rising Growth + Low Inflation"), "aggressive")

    def test_balanced_plan_for_rising_inflation(self):
        self.assertEqual(macro_context._plan_for_regime("Rising Growth + Rising Inflation"), "balanced")

    def test_conservative_plan_for_stagflation(self):
        self.assertEqual(macro_context._plan_for_regime("Stagflation"), "conservative")

    def test_conservative_plan_for_recession(self):
        self.assertEqual(macro_context._plan_for_regime("Deflation / Recession"), "conservative")


class TestMacroContextGetMacro(unittest.TestCase):

    @patch("yfinance.download")
    @patch("yfinance.Ticker")
    @patch("requests.get")
    def test_get_macro_live_returns_full_dict(self, mock_requests, mock_ticker, mock_download):
        def ticker_side_effect(sym):
            prices = {"^VIX": 14.2, "^TNX": 4.3, "^IRX": 3.85, "RINF": 2.1, "DX-Y.NYB": 102.3}
            t = MagicMock()
            t.fast_info = {"lastPrice": prices.get(sym, 50.0)}
            return t

        mock_ticker.side_effect = ticker_side_effect

        spy_df = _make_spy_prices("up", n=260)
        sector_dfs = _make_sector_prices(spy_return=0.05)

        def download_side_effect(tickers, period=None, auto_adjust=True):
            if isinstance(tickers, str):
                tickers = [tickers]
            if tickers == ["SPY"] or tickers == "SPY":
                return spy_df
            dfs = {t: sector_dfs.get(t, sector_dfs["SPY"]) for t in tickers}
            combined = pd.concat({t: df["Close"] for t, df in dfs.items()}, axis=1)
            combined.columns = pd.MultiIndex.from_tuples([("Close", t) for t in tickers])
            return combined

        mock_download.side_effect = download_side_effect

        fred_csv = "DATE,FEDFUNDS\n2026-04-01,4.75\n"
        mock_resp = MagicMock()
        mock_resp.text = fred_csv
        mock_resp.raise_for_status = MagicMock()
        mock_requests.return_value = mock_resp

        result = macro_context.get_macro()

        required_keys = [
            "regime", "vix", "spread_3m10y_bps", "spy_vs_200d_pct",
            "inflation_expectations_pct", "fed_rate", "dxy",
            "sector_leaders", "sector_laggards", "recommended_plan",
            "narrative", "data_freshness"
        ]
        for k in required_keys:
            self.assertIn(k, result, f"Missing key: {k}")

        self.assertAlmostEqual(result["vix"], 14.2, places=1)
        self.assertIn(result["data_freshness"], ("live", "partial"))
        self.assertIsInstance(result["sector_leaders"], list)
        self.assertIsInstance(result["sector_laggards"], list)

    @patch("yfinance.download")
    @patch("yfinance.Ticker")
    @patch("requests.get")
    def test_get_macro_all_failures_returns_safe_defaults(self, mock_requests, mock_ticker, mock_download):
        mock_ticker.side_effect = Exception("network error")
        mock_download.side_effect = Exception("network error")
        mock_requests.side_effect = Exception("network error")

        result = macro_context.get_macro()

        self.assertIn("regime", result)
        self.assertEqual(result["data_freshness"], "stale")
        self.assertEqual(result["recommended_plan"], "balanced")

    @patch("yfinance.download")
    @patch("yfinance.Ticker")
    @patch("requests.get")
    def test_get_macro_partial_failure_sets_partial_freshness(self, mock_requests, mock_ticker, mock_download):
        call_count = {"n": 0}

        def ticker_side_effect(sym):
            call_count["n"] += 1
            if sym == "^VIX" and call_count["n"] == 1:
                t = MagicMock()
                t.fast_info = {"lastPrice": 14.2}
                return t
            raise Exception("timeout")

        mock_ticker.side_effect = ticker_side_effect
        mock_download.side_effect = Exception("timeout")
        mock_requests.side_effect = Exception("timeout")

        result = macro_context.get_macro()
        self.assertEqual(result["data_freshness"], "partial")


if __name__ == "__main__":
    unittest.main()
