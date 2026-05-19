"""Tests for portfolio-analyzer/metrics.py"""
import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

_MOD_PATH = pathlib.Path(__file__).parent.parent / "metrics.py"
_spec = importlib.util.spec_from_file_location("metrics", _MOD_PATH)
metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metrics)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _make_price_series(start: float, end: float, n: int = 252) -> pd.Series:
    prices = np.linspace(start, end, n)
    dates = pd.date_range(end="2026-05-18", periods=n, freq="B")
    return pd.Series(prices, index=dates)


def _make_mock_download(tickers_prices: dict):
    def _download(tickers, period=None, auto_adjust=True):
        if isinstance(tickers, str):
            tickers = [tickers]
        n = 252
        frames = {}
        for t in tickers:
            if t in tickers_prices:
                s, e = tickers_prices[t]
            else:
                s, e = 100.0, 100.0
            frames[t] = _make_price_series(s, e, n)
        close_df = pd.DataFrame(frames)
        close_df.columns = pd.MultiIndex.from_tuples([("Close", t) for t in close_df.columns])
        return close_df
    return _download


def _make_mock_ticker_info(market_cap: float = 1e12, dividend_yield: float = 0.01):
    t = MagicMock()
    t.info = {"marketCap": market_cap, "dividendYield": dividend_yield}
    return t


class TestHHI(unittest.TestCase):

    def test_hhi_single_position_max(self):
        positions = [{"ticker": "NVDA", "weight": 1.0, "value": None, "cost_basis": None, "shares": None}]
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}
        prices = {"NVDA": (100, 120), "SPY": (400, 480)}
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)
        self.assertEqual(result["concentration"]["hhi"], 10000)

    def test_hhi_equal_weights_lower(self):
        positions = [
            {"ticker": t, "weight": 0.25, "value": None, "cost_basis": None, "shares": None}
            for t in ["NVDA", "AAPL", "MSFT", "JPM"]
        ]
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}
        prices = {t: (100, 120) for t in ["NVDA", "AAPL", "MSFT", "JPM", "SPY"]}
        prices["SPY"] = (400, 480)
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)
        self.assertLess(result["concentration"]["hhi"], 10000)
        self.assertGreater(result["concentration"]["hhi"], 0)


class TestConcentration(unittest.TestCase):

    def _compute(self, positions):
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}
        tickers = [p["ticker"] for p in positions] + ["SPY"]
        prices = {t: (100, 120) for t in tickers}
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                return metrics.compute_metrics(holdings)

    def test_top_position_pct(self):
        positions = [
            {"ticker": "NVDA", "weight": 0.30, "value": None, "cost_basis": None, "shares": None},
            {"ticker": "AAPL", "weight": 0.20, "value": None, "cost_basis": None, "shares": None},
        ]
        result = self._compute(positions)
        self.assertAlmostEqual(result["concentration"]["top_position_pct"], 0.30, places=4)

    def test_num_positions(self):
        positions = [
            {"ticker": t, "weight": 0.10, "value": None, "cost_basis": None, "shares": None}
            for t in ["A", "B", "C", "D", "E"]
        ]
        result = self._compute(positions)
        self.assertEqual(result["concentration"]["num_positions"], 5)


class TestSkippedTickers(unittest.TestCase):

    def test_skipped_tickers_excluded_from_metrics(self):
        positions = [
            {"ticker": "NVDA", "weight": 0.60, "value": None, "cost_basis": None, "shares": None},
            {"ticker": "UNKN_XYZ", "weight": 0.40, "value": None, "cost_basis": None, "shares": None},
        ]
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}

        def mock_download(tickers, period=None, auto_adjust=True):
            if isinstance(tickers, str):
                tickers = [tickers]
            frames = {}
            for t in tickers:
                if t == "UNKN_XYZ":
                    continue
                s, e = (100, 120) if t != "SPY" else (400, 480)
                frames[t] = _make_price_series(s, e)
            if not frames:
                return pd.DataFrame()
            df = pd.DataFrame(frames)
            df.columns = pd.MultiIndex.from_tuples([("Close", t) for t in df.columns])
            return df

        with patch("yfinance.download", side_effect=mock_download):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)

        self.assertIn("UNKN_XYZ", result["skipped_tickers"])


class TestRiskMetrics(unittest.TestCase):

    def test_annualized_vol_positive(self):
        positions = [{"ticker": "NVDA", "weight": 1.0, "value": None, "cost_basis": None, "shares": None}]
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}
        prices = {"NVDA": (100, 130), "SPY": (400, 480)}
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)
        self.assertGreater(result["risk"]["annualized_vol"], 0)

    def test_beta_uptrending_portfolio_positive(self):
        positions = [{"ticker": "NVDA", "weight": 1.0, "value": None, "cost_basis": None, "shares": None}]
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}
        prices = {"NVDA": (100, 130), "SPY": (400, 480)}
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)
        self.assertGreater(result["risk"]["portfolio_beta"], 0)


class TestReturnQuality(unittest.TestCase):

    def test_sharpe_positive_for_uptrending_portfolio(self):
        positions = [{"ticker": "NVDA", "weight": 1.0, "value": 10000.0, "cost_basis": 7000.0, "shares": None}]
        holdings = {"positions": positions, "total_value": 10000.0, "data_completeness": "full"}
        prices = {"NVDA": (100, 130), "SPY": (400, 480)}
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)
        self.assertGreater(result["return_quality"]["sharpe"], 0)

    def test_return_quality_none_when_no_total_value(self):
        positions = [{"ticker": "NVDA", "weight": 1.0, "value": None, "cost_basis": None, "shares": None}]
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}
        prices = {"NVDA": (100, 130), "SPY": (400, 480)}
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)
        self.assertIsNone(result["return_quality"]["sharpe"])
        self.assertIsNone(result["return_quality"]["sortino"])


class TestAssetClassification(unittest.TestCase):

    def test_bnd_classified_as_bond(self):
        positions = [{"ticker": "BND", "weight": 1.0, "value": None, "cost_basis": None, "shares": None}]
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}
        prices = {"BND": (75, 76), "SPY": (400, 480)}
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)
        self.assertGreater(result["income_style"]["bond_pct"], 0.5)

    def test_gld_classified_as_alt(self):
        positions = [{"ticker": "GLD", "weight": 1.0, "value": None, "cost_basis": None, "shares": None}]
        holdings = {"positions": positions, "total_value": None, "data_completeness": "ticker_weight_only"}
        prices = {"GLD": (180, 190), "SPY": (400, 480)}
        with patch("yfinance.download", side_effect=_make_mock_download(prices)):
            with patch("yfinance.Ticker", return_value=_make_mock_ticker_info()):
                result = metrics.compute_metrics(holdings)
        self.assertGreater(result["income_style"]["alt_pct"], 0.5)


if __name__ == "__main__":
    unittest.main()
