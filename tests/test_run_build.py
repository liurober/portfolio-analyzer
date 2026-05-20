"""Tests for run_build.py — Mode 2 Portfolio Builder orchestrator."""
import builtins
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKTREE = Path(__file__).parent.parent.parent  # portfolio-analyzer/tests -> worktree root
RUN_BUILD_PATH = WORKTREE / "portfolio-analyzer" / "run_build.py"
BASE_DIR = WORKTREE  # BASE_DIR inside run_build.py is Path(__file__).parent.parent
CONTEXT_PATH = BASE_DIR / "portfolio-analyzer" / ".build_context.json"

# ---------------------------------------------------------------------------
# Sample mock data
# ---------------------------------------------------------------------------
SAMPLE_MACRO = {
    "regime": "Rising Growth + Low Inflation",
    "recommended_plan": "aggressive",
    "fed_rate": 4.5,
    "vix": 15.2,
    "spread_3m10y_bps": 50.0,
    "spy_vs_200d_pct": 8.5,
    "narrative": "Goldilocks environment."
}


def make_mock_portfolios(amount):
    pos = [{"ticker": "AAPL", "weight": 1.0, "value": amount, "reason": "test", "tag": "screener"}]
    plan = {
        "positions": pos,
        "total_value": amount,
        "target_metrics": {"beta_est": 1.35, "yield_est": 0.007, "max_dd_est": -0.45, "equity_pct": 0.93},
        "macro_fit_score": 4.8,
        "rationale": "Test rationale"
    }
    return {"aggressive": plan, "balanced": plan, "conservative": plan, "income": plan}


# ---------------------------------------------------------------------------
# Module loader with pre-injected mocks
# ---------------------------------------------------------------------------

def _load_run_build():
    """Load run_build module with all sub-modules mocked in sys.modules."""

    # Build mock sub-modules
    macro_mod = types.ModuleType("portfolio_analyzer.macro_context")
    macro_mod.get_macro_context = MagicMock(return_value=SAMPLE_MACRO)

    builder_mod = types.ModuleType("portfolio_analyzer.builder")
    builder_mod.build_portfolios = MagicMock(side_effect=lambda amount, *a, **kw: make_mock_portfolios(amount))

    screener_mod = types.ModuleType("portfolio_analyzer.screener_picks")
    screener_mod.get_picks = MagicMock(return_value=[])

    report_mod = types.ModuleType("portfolio_analyzer.report")
    report_mod.generate_report = MagicMock(return_value="/tmp/report.html")

    obsidian_mod = types.ModuleType("portfolio_analyzer.obsidian")
    obsidian_mod.save_note = MagicMock(return_value="/tmp/note.md")

    # Also mock the parent package so import resolves cleanly
    pkg_mod = types.ModuleType("portfolio_analyzer")

    mocks = {
        "portfolio_analyzer": pkg_mod,
        "portfolio_analyzer.macro_context": macro_mod,
        "portfolio_analyzer.builder": builder_mod,
        "portfolio_analyzer.screener_picks": screener_mod,
        "portfolio_analyzer.report": report_mod,
        "portfolio_analyzer.obsidian": obsidian_mod,
    }

    # Stash originals and inject mocks
    originals = {k: sys.modules.get(k) for k in mocks}
    sys.modules.update(mocks)

    try:
        # Remove cached version if already loaded
        mod_name = "run_build"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        spec = importlib.util.spec_from_file_location(mod_name, RUN_BUILD_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    finally:
        # Restore originals (None means delete)
        for k, v in originals.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    return module


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_context_file():
    """Remove .build_context.json before and after each test."""
    CONTEXT_PATH.unlink(missing_ok=True)
    yield
    CONTEXT_PATH.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunBuild:
    def _invoke(self):
        module = _load_run_build()
        # Patch builtins.input to return "35" for the age prompt (loop requires non-empty)
        with patch("builtins.input", return_value="35"):
            return module.run_build(
                amount=50000,
                profile="aggressive",
                horizon=15,
                goal="growth",
                date_str="2026-05-18"
            )

    def test_context_file_written(self):
        self._invoke()
        assert CONTEXT_PATH.exists(), f".build_context.json not found at {CONTEXT_PATH}"

    def test_context_has_required_keys(self):
        ctx = self._invoke()
        for key in ("mode", "date", "params", "macro", "portfolios", "picks"):
            assert key in ctx, f"Missing key '{key}' in context"

    def test_mode_is_build(self):
        ctx = self._invoke()
        assert ctx["mode"] == "build"

    def test_portfolios_has_four_archetypes(self):
        ctx = self._invoke()
        assert set(ctx["portfolios"].keys()) == {"aggressive", "balanced", "conservative", "income"}

    def test_params_amount(self):
        ctx = self._invoke()
        assert ctx["params"]["amount"] == 50000

    def test_picks_has_four_keys(self):
        ctx = self._invoke()
        assert len(ctx["picks"]) == 4
        assert set(ctx["picks"].keys()) == {"aggressive", "balanced", "conservative", "income"}

    def test_context_file_is_valid_json(self):
        self._invoke()
        raw = CONTEXT_PATH.read_text()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_context_file_content_matches_return(self):
        ctx = self._invoke()
        parsed = json.loads(CONTEXT_PATH.read_text())
        assert parsed["mode"] == ctx["mode"]
        assert parsed["params"]["amount"] == ctx["params"]["amount"]
