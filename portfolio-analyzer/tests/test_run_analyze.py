"""Tests for run_analyze.py — Mode 1 orchestrator."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Paths
WORKTREE = Path(__file__).parent.parent.parent
MODULE_PATH = WORKTREE / "portfolio-analyzer" / "run_analyze.py"
FIXTURE_PATH = WORKTREE / "portfolio-analyzer" / "tests" / "fixtures" / "sample_holdings.json"
CONTEXT_PATH = WORKTREE / "portfolio-analyzer" / ".analysis_context.json"

# --- Mock return values ---

MOCK_HOLDINGS = {
    "positions": [
        {"ticker": "NVDA", "weight": 0.12, "value": 17076.0, "sector": "Technology"},
        {"ticker": "AAPL", "weight": 0.10, "value": 14230.0, "sector": "Technology"},
    ],
    "total_value": 142300.0,
    "data_completeness": "full",
}

MOCK_MACRO = {
    "regime": "Risk-On",
    "recommended_plan": "aggressive",
    "fed_rate": 4.5,
    "vix": 18.2,
    "spread_3m10y_bps": 45.0,
}

MOCK_METRICS = {
    "return_quality": {"sharpe": 1.3},
    "risk": {"portfolio_beta": 1.1, "max_drawdown": -0.15},
    "income_style": {"weighted_yield": 0.012},
    "skipped_tickers": [],
}

MOCK_PICKS = [{"ticker": "AMZN", "score": 0.9}]


def _make_mock_submodules():
    """Return a dict of fake portfolio_analyzer sub-modules to inject into sys.modules."""
    parser_mod = MagicMock()
    parser_mod.parse = MagicMock(return_value=MOCK_HOLDINGS)

    macro_mod = MagicMock()
    # run_analyze.py imports: from portfolio_analyzer.macro_context import get_macro as get_macro_context
    # so the attribute on the module is "get_macro", not "get_macro_context"
    macro_mod.get_macro = MagicMock(return_value=MOCK_MACRO)

    metrics_mod = MagicMock()
    metrics_mod.compute_metrics = MagicMock(return_value=MOCK_METRICS)

    screener_mod = MagicMock()
    screener_mod.get_picks = MagicMock(return_value=MOCK_PICKS)

    report_mod = MagicMock()
    report_mod.generate_report = MagicMock(return_value="report.md")

    obsidian_mod = MagicMock()
    obsidian_mod.save_note = MagicMock(return_value="/vault/note.md")

    pkg = MagicMock()

    return {
        "portfolio_analyzer": pkg,
        "portfolio_analyzer.parser": parser_mod,
        "portfolio_analyzer.macro_context": macro_mod,
        "portfolio_analyzer.metrics": metrics_mod,
        "portfolio_analyzer.screener_picks": screener_mod,
        "portfolio_analyzer.report": report_mod,
        "portfolio_analyzer.obsidian": obsidian_mod,
    }


def load_module_with_mocks(name="run_analyze"):
    """
    Load run_analyze from its file path with portfolio_analyzer sub-modules
    pre-injected into sys.modules so the top-level imports succeed.
    """
    mocks = _make_mock_submodules()
    # Save any real modules so we can restore them
    saved = {k: sys.modules.get(k) for k in mocks}
    sys.modules.update(mocks)
    try:
        # Remove any cached version so exec_module runs fresh
        if name in sys.modules:
            del sys.modules[name]
        spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mocks
    finally:
        # Restore original sys.modules state
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class TestRunAnalyze(unittest.TestCase):

    def setUp(self):
        # Remove context file if it exists from a prior run
        if CONTEXT_PATH.exists():
            CONTEXT_PATH.unlink()

    def tearDown(self):
        # Clean up context file after each test
        if CONTEXT_PATH.exists():
            CONTEXT_PATH.unlink()

    def test_run_analyze_full_flow(self):
        """run_analyze() calls all sub-modules and writes .analysis_context.json."""
        mod, mocks = load_module_with_mocks()

        context = mod.run_analyze(str(FIXTURE_PATH), date_str="2026-05-18")

        # parse was called with the file path
        mocks["portfolio_analyzer.parser"].parse.assert_called_once_with(str(FIXTURE_PATH))
        # macro context was fetched (imported as: from macro_context import get_macro as get_macro_context)
        mocks["portfolio_analyzer.macro_context"].get_macro.assert_called_once()
        # metrics were computed
        mocks["portfolio_analyzer.metrics"].compute_metrics.assert_called_once()
        # picks were fetched (4 plan types)
        self.assertEqual(mocks["portfolio_analyzer.screener_picks"].get_picks.call_count, 4)

        # Context file was written
        self.assertTrue(CONTEXT_PATH.exists(), ".analysis_context.json was not created")

        # Context file content is valid JSON
        written = json.loads(CONTEXT_PATH.read_text())
        self.assertEqual(written["mode"], "analyze")
        self.assertEqual(written["date"], "2026-05-18")

    def test_context_dict_keys(self):
        """Returned context dict has all required keys."""
        mod, _ = load_module_with_mocks()
        context = mod.run_analyze(str(FIXTURE_PATH), date_str="2026-05-18")

        required_keys = {"holdings", "macro", "metrics", "picks", "mode", "date"}
        missing = required_keys - set(context.keys())
        self.assertEqual(missing, set(), f"Missing keys: {missing}")

    def test_context_mode_is_analyze(self):
        """context['mode'] must be 'analyze'."""
        mod, _ = load_module_with_mocks()
        context = mod.run_analyze(str(FIXTURE_PATH), date_str="2026-05-18")
        self.assertEqual(context["mode"], "analyze")

    def test_picks_has_four_plan_types(self):
        """context['picks'] must have keys: aggressive, balanced, conservative, income."""
        mod, _ = load_module_with_mocks()
        context = mod.run_analyze(str(FIXTURE_PATH), date_str="2026-05-18")

        self.assertIn("aggressive", context["picks"])
        self.assertIn("balanced", context["picks"])
        self.assertIn("conservative", context["picks"])
        self.assertIn("income", context["picks"])
        self.assertEqual(len(context["picks"]), 4)

    def test_context_file_written_with_correct_content(self):
        """The JSON file on disk matches the returned context dict."""
        mod, _ = load_module_with_mocks()
        context = mod.run_analyze(str(FIXTURE_PATH), date_str="2026-05-18")

        written = json.loads(CONTEXT_PATH.read_text())
        self.assertEqual(written["mode"], context["mode"])
        self.assertEqual(written["date"], context["date"])
        self.assertIn("holdings", written)
        self.assertIn("macro", written)
        self.assertIn("metrics", written)
        self.assertIn("picks", written)

    def test_default_date_is_today(self):
        """When date_str is None, context['date'] is set to today's ISO date."""
        from datetime import date as date_cls
        mod, _ = load_module_with_mocks()
        context = mod.run_analyze(str(FIXTURE_PATH))
        self.assertEqual(context["date"], date_cls.today().isoformat())


if __name__ == "__main__":
    unittest.main()
