"""Tests for portfolio-analyzer/report.py"""
import importlib.util
import os
import pathlib
import tempfile
import unittest

_MOD_PATH = pathlib.Path(__file__).parent.parent / "report.py"
_spec = importlib.util.spec_from_file_location("report", _MOD_PATH)
report_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_mod)

SAMPLE_HOLDINGS = {
    "positions": [
        {"ticker": "NVDA", "weight": 0.12, "value": 17076.0, "cost_basis": 8000.0, "shares": None},
        {"ticker": "AAPL", "weight": 0.10, "value": 14230.0, "cost_basis": 10000.0, "shares": None},
    ],
    "total_value": 142300.0,
    "data_completeness": "full",
}

SAMPLE_MACRO = {
    "regime": "Rising Growth + Low Inflation",
    "vix": 14.2,
    "spread_3m10y_bps": 45.0,
    "spy_vs_200d_pct": 8.3,
    "inflation_expectations_pct": 2.1,
    "fed_rate": 4.75,
    "dxy": 102.3,
    "sector_leaders": ["XLK"],
    "sector_laggards": ["XLU"],
    "recommended_plan": "aggressive",
    "narrative": "Markets signal risk-on with low volatility.",
    "data_freshness": "live",
}

SAMPLE_METRICS = {
    "concentration": {"top_position_pct": 0.12, "top5_combined_pct": 0.45, "largest_sector_pct": 0.61, "hhi": 850, "num_positions": 2},
    "risk": {"portfolio_beta": 1.41, "annualized_vol": 0.22, "max_drawdown": -0.38, "var_95_1d": 3200.0, "avg_correlation": 0.62},
    "return_quality": {"sharpe": 1.24, "sortino": 1.68, "calmar": 0.75, "return_1y": 0.28, "alpha": 0.06},
    "income_style": {"weighted_yield": 0.008, "annual_income_est": 1138.0, "large_cap_pct": 0.78, "mid_cap_pct": 0.15, "small_cap_pct": 0.07, "domestic_pct": 0.92, "intl_pct": 0.08, "equity_pct": 0.95, "bond_pct": 0.0, "alt_pct": 0.03, "cash_pct": 0.02},
    "risk_parity": {"positions": [{"ticker": "NVDA", "capital_weight": 0.12, "risk_contribution": 0.22}], "sectors": [], "equity_risk_pct": 0.97, "implied_leverage": 1.02},
    "skipped_tickers": [],
}

SAMPLE_PICKS = {
    "aggressive": [{"ticker": "QQQ", "score": 5, "source": "ETF", "sector": "Technology", "reason": "Nasdaq100 core", "tag": "ETF"}],
    "balanced":   [{"ticker": "VTI", "score": 5, "source": "ETF", "sector": "Broad Market", "reason": "Total market", "tag": "ETF"}],
    "conservative": [{"ticker": "BND", "score": 5, "source": "ETF", "sector": "Bonds", "reason": "Broad bond", "tag": "ETF"}],
    "income":     [{"ticker": "SCHD", "score": 5, "source": "ETF", "sector": "Dividend", "reason": "Dividend", "tag": "ETF"}],
}

SAMPLE_ANALYSIS = {
    "implicit_bet": "This portfolio bets on continued AI capex with no recession.",
    "red_flags": [
        {"rank": 1, "flag": "Tech sector = 61% capital, 78% risk contribution", "impact_est": "High"},
    ],
    "green_flags": ["No single position exceeds 8%"],
    "grades": {"diversification": "C", "risk_adjusted_return": "B+", "macro_resilience": "D", "income_quality": "D", "market_alignment": "B"},
    "plans": {
        "aggressive": {
            "rationale": "High growth environment favors equities.",
            "sell": [{"ticker": "MSFT", "action": "Reduce 50%", "proceeds": 6000.0, "reason": "Overweight"}],
            "buy": [{"ticker": "NVDA", "reason": "Momentum", "pct": 0.08, "dollars": 11384.0, "tag": "screener"}],
            "hold": [{"ticker": "AAPL", "yield_pct": 0.005, "value": 14230.0}],
            "target_metrics": {"beta": 1.3, "sharpe_est": 1.4, "max_dd_est": -0.42, "equity_pct": 0.92, "yield_pct": 0.007},
            "macro_grid": {"rising_growth_low_inflation": "+18-25%", "rising_growth_rising_inflation": "+8-14%", "stagflation": "-25-35%", "deflation_recession": "-35-45%"},
            "fit_grade": "A",
        },
        "balanced": {"rationale": "...", "sell": [], "buy": [], "hold": [], "target_metrics": {"beta": 0.8, "sharpe_est": 1.1, "max_dd_est": -0.22, "equity_pct": 0.55, "yield_pct": 0.02}, "macro_grid": {"rising_growth_low_inflation": "+10-15%", "rising_growth_rising_inflation": "+5-10%", "stagflation": "-10-18%", "deflation_recession": "-12-20%"}, "fit_grade": "B"},
        "conservative": {"rationale": "...", "sell": [], "buy": [], "hold": [], "target_metrics": {"beta": 0.45, "sharpe_est": 0.8, "max_dd_est": -0.12, "equity_pct": 0.28, "yield_pct": 0.03}, "macro_grid": {"rising_growth_low_inflation": "+4-8%", "rising_growth_rising_inflation": "+2-5%", "stagflation": "-5-10%", "deflation_recession": "-5-8%"}, "fit_grade": "C"},
        "income": {"rationale": "...", "sell": [], "buy": [], "hold": [], "target_metrics": {"beta": 0.65, "sharpe_est": 0.9, "max_dd_est": -0.18, "equity_pct": 0.47, "yield_pct": 0.045}, "macro_grid": {"rising_growth_low_inflation": "+8-12%", "rising_growth_rising_inflation": "+4-8%", "stagflation": "-8-15%", "deflation_recession": "-8-12%"}, "fit_grade": "B-"},
    },
    "construction_rationale": None,
}


class TestGenerateReport(unittest.TestCase):

    def test_report_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test-report.html")
            result = report_mod.generate_report(
                holdings=SAMPLE_HOLDINGS,
                macro=SAMPLE_MACRO,
                metrics=SAMPLE_METRICS,
                picks=SAMPLE_PICKS,
                analysis=SAMPLE_ANALYSIS,
                output_path=out_path,
            )
            self.assertTrue(os.path.exists(result))

    def test_report_contains_key_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test-report.html")
            report_mod.generate_report(
                holdings=SAMPLE_HOLDINGS,
                macro=SAMPLE_MACRO,
                metrics=SAMPLE_METRICS,
                picks=SAMPLE_PICKS,
                analysis=SAMPLE_ANALYSIS,
                output_path=out_path,
            )
            content = open(out_path).read()
            self.assertIn("Restructuring Plans", content)
            self.assertIn("Bridgewater", content)
            self.assertIn("Metrics Dashboard", content)
            self.assertIn("aggressive", content.lower())

    def test_report_contains_recommended_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test-report.html")
            report_mod.generate_report(
                holdings=SAMPLE_HOLDINGS,
                macro=SAMPLE_MACRO,
                metrics=SAMPLE_METRICS,
                picks=SAMPLE_PICKS,
                analysis=SAMPLE_ANALYSIS,
                output_path=out_path,
            )
            content = open(out_path).read()
            self.assertIn("aggressive", content)

    def test_report_build_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test-build-report.html")
            report_mod.generate_report(
                holdings=SAMPLE_HOLDINGS,
                macro=SAMPLE_MACRO,
                metrics=SAMPLE_METRICS,
                picks=SAMPLE_PICKS,
                analysis=SAMPLE_ANALYSIS,
                output_path=out_path,
                mode="build",
            )
            content = open(out_path).read()
            self.assertIn("Blueprint", content)

    def test_report_returns_path_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test-report.html")
            result = report_mod.generate_report(
                holdings=SAMPLE_HOLDINGS,
                macro=SAMPLE_MACRO,
                metrics=SAMPLE_METRICS,
                picks=SAMPLE_PICKS,
                analysis=SAMPLE_ANALYSIS,
                output_path=out_path,
            )
            self.assertIsInstance(result, str)
            self.assertTrue(result.endswith(".html"))


if __name__ == "__main__":
    unittest.main()
