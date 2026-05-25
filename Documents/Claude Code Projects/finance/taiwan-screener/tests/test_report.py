from finance_tw_path import ensure_path  # noqa: F401
from backtest.report import build_report


def test_build_report_contains_required_sections():
    html = build_report([("2024-01-01", 100_000)],
                        [{"date": "2024-01-01", "ticker": "X.TW",
                          "exit_date": "2024-02-01", "status": "closed",
                          "outcome": "win", "pnl_pct": 22.0}],
                        [{"params": {"min_score": 6}, "composite": 0.85,
                          "metrics": {"win_rate": 0.82, "avg_return_pct": 24,
                                      "total_trades": 30}}])
    assert "台股回測月報" in html
    assert "資產曲線" in html
    assert "Monte Carlo" in html
    assert "本月最佳參數" in html
