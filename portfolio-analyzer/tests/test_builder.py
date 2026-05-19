import sys
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock

# Load builder module
WORKTREE = Path("/Users/robertliu/Documents/Claude Code Projects/.claude/worktrees/confident-dubinsky-e68028")

def load_builder():
    # Pre-inject mock for screener_picks before loading builder
    mock_screener = MagicMock()
    mock_screener.get_picks.return_value = [
        {"ticker": "AAPL", "score": 5, "source": "screener", "sector": "Technology", "reason": "Strong momentum", "tag": "screener"},
        {"ticker": "MSFT", "score": 4, "source": "screener", "sector": "Technology", "reason": "Quality growth", "tag": "screener"},
        {"ticker": "NVDA", "score": 4, "source": "screener", "sector": "Technology", "reason": "AI leader", "tag": "screener"},
    ]
    sys.modules["portfolio_analyzer"] = MagicMock()
    sys.modules["portfolio_analyzer.screener_picks"] = mock_screener
    sys.modules["screener_picks"] = mock_screener

    spec = importlib.util.spec_from_file_location(
        "portfolio_analyzer.builder",
        WORKTREE / "portfolio-analyzer" / "builder.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, mock_screener

BUILDER, MOCK_SCREENER = load_builder()

SAMPLE_MACRO = {
    "regime": "Rising Growth + Low Inflation",
    "recommended_plan": "aggressive",
    "fed_rate": 4.5,
    "vix": 15.2,
    "spread_3m10y_bps": 50,
    "spy_vs_200d_pct": 8.5,
    "narrative": "Goldilocks environment."
}

def test_returns_four_archetypes():
    result = BUILDER.build_portfolios(50000, "aggressive", 15, "growth", SAMPLE_MACRO)
    assert set(result.keys()) == {"aggressive", "balanced", "conservative", "income"}

def test_positions_sum_to_one():
    result = BUILDER.build_portfolios(50000, "aggressive", 15, "growth", SAMPLE_MACRO)
    for arch, port in result.items():
        total_weight = sum(p["weight"] for p in port["positions"])
        assert abs(total_weight - 1.0) < 0.01, f"{arch} weights sum to {total_weight}"

def test_no_position_exceeds_max_single():
    result = BUILDER.build_portfolios(50000, "aggressive", 15, "growth", SAMPLE_MACRO)
    rules = BUILDER.ARCHETYPE_RULES
    for arch, port in result.items():
        max_w = rules[arch]["max_single"]
        for p in port["positions"]:
            assert p["weight"] <= max_w + 0.001, f"{arch}/{p['ticker']} weight {p['weight']} exceeds max {max_w}"

def test_aggressive_has_higher_macro_fit_than_conservative():
    result = BUILDER.build_portfolios(50000, "aggressive", 15, "growth", SAMPLE_MACRO)
    assert result["aggressive"]["macro_fit_score"] > result["conservative"]["macro_fit_score"]

def test_total_value_is_amount():
    result = BUILDER.build_portfolios(50000, "balanced", 10, "income", SAMPLE_MACRO)
    assert result["balanced"]["total_value"] == 50000

def test_position_values_sum_to_amount():
    result = BUILDER.build_portfolios(50000, "balanced", 10, "income", SAMPLE_MACRO)
    for arch, port in result.items():
        total_val = sum(p["value"] for p in port["positions"])
        assert abs(total_val - 50000) < 1.0, f"{arch} values sum to {total_val}"

def test_rationale_contains_goal_and_horizon():
    result = BUILDER.build_portfolios(50000, "aggressive", 15, "growth", SAMPLE_MACRO)
    for arch, port in result.items():
        assert "growth" in port["rationale"]
        assert "15" in port["rationale"]

def test_avoid_tickers_excluded():
    result = BUILDER.build_portfolios(50000, "aggressive", 15, "growth", SAMPLE_MACRO, avoid=["AAPL"])
    for arch, port in result.items():
        tickers = [p["ticker"] for p in port["positions"]]
        assert "AAPL" not in tickers, f"AAPL should be excluded from {arch}"

def test_target_metrics_present():
    result = BUILDER.build_portfolios(50000, "aggressive", 15, "growth", SAMPLE_MACRO)
    for arch, port in result.items():
        tm = port["target_metrics"]
        assert "beta_est" in tm
        assert "yield_est" in tm
        assert "max_dd_est" in tm
        assert "equity_pct" in tm
