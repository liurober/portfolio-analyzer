"""Tests for portfolio_analyzer.obsidian.save_note."""

import importlib.util
import sys
import os
from pathlib import Path
import pytest

# Load obsidian module from file path (avoids hyphen-in-package-name issue)
_OBSIDIAN_PATH = Path(__file__).parent.parent / "obsidian.py"
_spec = importlib.util.spec_from_file_location("obsidian", _OBSIDIAN_PATH)
obsidian_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(obsidian_module)

save_note = obsidian_module.save_note


DATE_STR = "2026-05-18"

HOLDINGS = {
    "total_value": 125000.0,
    "positions": [
        {"ticker": "AAPL", "value": 50000},
        {"ticker": "MSFT", "value": 75000},
    ],
}

MACRO = {
    "regime": "Risk-On",
    "recommended_plan": "aggressive",
    "vix": 14.5,
    "spread_3m10y_bps": -35,
    "spy_vs_200d_pct": 4.2,
    "narrative": "Markets are trending above long-term averages with low volatility.",
}

METRICS = {
    "return_quality": {"sharpe": 1.23},
    "risk": {
        "portfolio_beta": 1.05,
        "max_drawdown": -0.124,
        "annualized_vol": 0.182,
    },
    "concentration": {"avg_pairwise_corr": 0.67},
    "income_style": {"weighted_yield": 0.0215},
}

ANALYSIS = {
    "implicit_bet": "Long duration tech with rate sensitivity.",
    "red_flags": [
        {"message": "High concentration in tech sector"},
        "Elevated correlation during drawdowns",
    ],
    "green_flags": [
        "Strong momentum across top holdings",
        "Above-average yield for growth portfolio",
    ],
}


@pytest.fixture
def tmp_vault(tmp_path, monkeypatch):
    """Patch VAULT_BASE to use pytest's tmp_path instead of the real vault."""
    monkeypatch.setattr(obsidian_module, "VAULT_BASE", str(tmp_path))
    return tmp_path


def test_save_note_file_exists(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    assert Path(path).exists(), f"Expected file at {path}"


def test_save_note_starts_with_frontmatter(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    content = Path(path).read_text(encoding="utf-8")
    assert content.startswith("---"), "File should start with YAML frontmatter '---'"


def test_save_note_recommended_plan_in_content(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    content = Path(path).read_text(encoding="utf-8")
    assert "aggressive" in content, "recommended_plan value should appear in file content"


def test_save_note_heading_present(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    content = Path(path).read_text(encoding="utf-8")
    assert "# Portfolio Review" in content, "Markdown heading should be present"


def test_save_note_red_flags_section(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    content = Path(path).read_text(encoding="utf-8")
    assert "## Red Flags" in content, "Red Flags section header should be present"


def test_save_note_returns_correct_path(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    expected = str(tmp_vault / obsidian_module.SUBFOLDER / f"{DATE_STR}-portfolio-review.md")
    assert path == expected, f"Expected {expected}, got {path}"


def test_save_note_analyze_filename(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR, mode="analyze")
    assert path.endswith(f"{DATE_STR}-portfolio-review.md")


def test_save_note_build_filename(tmp_vault):
    build_params = {"amount": 50000, "profile": "moderate", "horizon": 10, "goal": "retirement"}
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR, mode="build", build_params=build_params)
    assert path.endswith(f"{DATE_STR}-portfolio-build.md")


def test_save_note_build_frontmatter(tmp_vault):
    build_params = {"amount": 50000, "profile": "moderate", "horizon": 10, "goal": "retirement"}
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR, mode="build", build_params=build_params)
    content = Path(path).read_text(encoding="utf-8")
    assert "mode: build" in content
    assert "risk_profile: moderate" in content
    assert "time_horizon: 10y" in content
    assert "goal: retirement" in content


def test_save_note_none_values_graceful(tmp_vault):
    """None metric values should not crash — format as N/A."""
    sparse_metrics = {}
    path = save_note(HOLDINGS, MACRO, sparse_metrics, ANALYSIS, DATE_STR)
    content = Path(path).read_text(encoding="utf-8")
    assert "N/A" in content


def test_save_note_vault_missing(tmp_path):
    """If vault base does not exist, raise FileNotFoundError."""
    missing = str(tmp_path / "nonexistent_vault")
    orig = obsidian_module.VAULT_BASE
    obsidian_module.VAULT_BASE = missing
    try:
        with pytest.raises(FileNotFoundError, match="Obsidian vault not found"):
            save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    finally:
        obsidian_module.VAULT_BASE = orig


def test_save_note_red_flags_numbered(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    content = Path(path).read_text(encoding="utf-8")
    assert "1. High concentration in tech sector" in content
    assert "2. Elevated correlation during drawdowns" in content


def test_save_note_green_flags_bulleted(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    content = Path(path).read_text(encoding="utf-8")
    assert "- Strong momentum across top holdings" in content


def test_save_note_restructuring_plans_links(tmp_vault):
    path = save_note(HOLDINGS, MACRO, METRICS, ANALYSIS, DATE_STR)
    content = Path(path).read_text(encoding="utf-8")
    assert f"[[{DATE_STR}-aggressive-plan]]" in content
    assert f"[[{DATE_STR}-balanced-plan]]" in content
