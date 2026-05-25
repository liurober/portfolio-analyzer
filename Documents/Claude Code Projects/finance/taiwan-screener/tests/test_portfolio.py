from finance_tw_path import ensure_path  # noqa: F401
from backtest.portfolio import simulate_portfolio


def _t(ticker, d_in, d_out, pnl):
    return {"ticker": ticker, "entry_date": d_in, "exit_date": d_out,
            "pnl_pct": pnl}


def test_basic_growth():
    trades = [_t("A.TW", "2024-01-05", "2024-02-09", 25.0),
              _t("B.TW", "2024-01-12", "2024-02-16", 20.0),
              _t("C.TW", "2024-01-19", "2024-02-23", -10.0)]
    out = simulate_portfolio(trades)
    assert out["trades_taken"] == 3
    # gross = 10000*(1.25 + 1.20 + 0.90) + 70_000 unused = 103_500
    assert abs(out["final_nav"] - 103_500.0) < 1.0


def test_skips_when_full():
    # 4 overlapping trades — only 3 should be taken (max_concurrent=3)
    trades = [_t("A.TW", "2024-01-05", "2024-03-01", 20.0),
              _t("B.TW", "2024-01-05", "2024-03-01", 20.0),
              _t("C.TW", "2024-01-05", "2024-03-01", 20.0),
              _t("D.TW", "2024-01-05", "2024-03-01", 20.0)]
    out = simulate_portfolio(trades)
    assert out["trades_taken"] == 3
    assert out["trades_skipped"] == 1
