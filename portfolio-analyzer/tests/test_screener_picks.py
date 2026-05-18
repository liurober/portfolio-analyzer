"""Tests for portfolio-analyzer/screener_picks.py"""
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

_MOD_PATH = pathlib.Path(__file__).parent.parent / "screener_picks.py"
_spec = importlib.util.spec_from_file_location("screener_picks", _MOD_PATH)
screener_picks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(screener_picks)


def _make_analysis_json(ticker, sector, direction, score, days_old=0):
    as_of = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return {
        "ticker": ticker,
        "as_of": as_of,
        "sector": sector,
        "technicals": {"score_long": score, "direction": direction},
        "price": {"current": 150.0},
    }


def _make_yf_price_series(trend="up", n=35):
    prices = np.linspace(100, 115, n) if trend == "up" else np.linspace(115, 100, n)
    dates = pd.date_range(end="2026-05-18", periods=n, freq="B")
    df = pd.DataFrame({"Close": prices}, index=dates)
    df.columns = pd.MultiIndex.from_tuples([("Close", "TICKER")])
    return df


class TestScreenerPicksFromAnalysisJson(unittest.TestCase):

    def test_fresh_analysis_json_included_as_screener_source(self):
        analysis = _make_analysis_json("NVDA", "Technology", "long", "6", days_old=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_path = os.path.join(tmpdir, "analysis.json")
            with open(analysis_path, "w") as f:
                json.dump(analysis, f)
            with patch.object(screener_picks, "ANALYSIS_JSON_PATH", analysis_path):
                with patch("yfinance.download") as mock_dl:
                    mock_dl.return_value = _make_yf_price_series("up")
                    picks = screener_picks.get_picks(sectors_needed=["Technology"], plan_type="aggressive", n_per_sector=3)

        screener_source = [p for p in picks if p["source"] == "screener"]
        self.assertGreaterEqual(len(screener_source), 1)
        nvda = next((p for p in screener_source if p["ticker"] == "NVDA"), None)
        self.assertIsNotNone(nvda)
        self.assertEqual(nvda["score"], 6)

    def test_stale_analysis_json_not_used_as_screener(self):
        analysis = _make_analysis_json("NVDA", "Technology", "long", "6", days_old=8)
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_path = os.path.join(tmpdir, "analysis.json")
            with open(analysis_path, "w") as f:
                json.dump(analysis, f)
            with patch.object(screener_picks, "ANALYSIS_JSON_PATH", analysis_path):
                with patch("yfinance.download") as mock_dl:
                    mock_dl.return_value = _make_yf_price_series("up")
                    picks = screener_picks.get_picks(sectors_needed=["Technology"], plan_type="aggressive", n_per_sector=3)

        self.assertEqual(len([p for p in picks if p["source"] == "screener"]), 0)

    def test_wrong_direction_analysis_json_not_used(self):
        analysis = _make_analysis_json("NVDA", "Technology", "short", "6", days_old=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_path = os.path.join(tmpdir, "analysis.json")
            with open(analysis_path, "w") as f:
                json.dump(analysis, f)
            with patch.object(screener_picks, "ANALYSIS_JSON_PATH", analysis_path):
                with patch("yfinance.download") as mock_dl:
                    mock_dl.return_value = _make_yf_price_series("up")
                    picks = screener_picks.get_picks(sectors_needed=["Technology"], plan_type="aggressive", n_per_sector=3)

        self.assertEqual(len([p for p in picks if p["source"] == "screener"]), 0)


class TestScreenerPicksETFFallbacks(unittest.TestCase):

    def _get_picks_no_analysis(self, plan_type):
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_path = os.path.join(tmpdir, "analysis.json")
            with patch.object(screener_picks, "ANALYSIS_JSON_PATH", analysis_path):
                with patch("yfinance.download") as mock_dl:
                    mock_dl.return_value = _make_yf_price_series("up")
                    return screener_picks.get_picks(sectors_needed=["Technology"], plan_type=plan_type, n_per_sector=3)

    def test_etf_fallbacks_aggressive(self):
        picks = self._get_picks_no_analysis("aggressive")
        etf_tickers = [p["ticker"] for p in picks if p["source"] == "ETF"]
        self.assertIn("QQQ", etf_tickers)
        self.assertIn("SPY", etf_tickers)

    def test_etf_fallbacks_balanced(self):
        picks = self._get_picks_no_analysis("balanced")
        etf_tickers = [p["ticker"] for p in picks if p["source"] == "ETF"]
        self.assertIn("TLT", etf_tickers)
        self.assertIn("GLD", etf_tickers)

    def test_etf_fallbacks_conservative(self):
        picks = self._get_picks_no_analysis("conservative")
        etf_tickers = [p["ticker"] for p in picks if p["source"] == "ETF"]
        self.assertIn("BND", etf_tickers)
        self.assertIn("SGOV", etf_tickers)

    def test_etf_fallbacks_income(self):
        picks = self._get_picks_no_analysis("income")
        etf_tickers = [p["ticker"] for p in picks if p["source"] == "ETF"]
        self.assertIn("SCHD", etf_tickers)
        self.assertIn("JEPI", etf_tickers)


class TestScreenerPicksLiveScoring(unittest.TestCase):

    def test_pick_dict_has_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_path = os.path.join(tmpdir, "analysis.json")
            with patch.object(screener_picks, "ANALYSIS_JSON_PATH", analysis_path):
                with patch("yfinance.download") as mock_dl:
                    mock_dl.return_value = _make_yf_price_series("up")
                    picks = screener_picks.get_picks(sectors_needed=["Technology"], plan_type="aggressive", n_per_sector=1)

        for p in picks:
            self.assertIn("ticker", p)
            self.assertIn("score", p)
            self.assertIn("source", p)
            self.assertIn("sector", p)
            self.assertIn("reason", p)
            self.assertIn("tag", p)


if __name__ == "__main__":
    unittest.main()
