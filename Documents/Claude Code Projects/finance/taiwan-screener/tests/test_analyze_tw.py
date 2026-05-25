from finance_tw_path import ensure_path  # noqa: F401
from analyze_tw import _rate, _fmt


def test_rate_bands():
    assert _rate(9.5) == "強力買進"
    assert _rate(8.0) == "買進"
    assert _rate(6.5) == "觀望"
    assert _rate(5.0) == "謹慎"
    assert _rate(2.0) == "避開"


def test_fmt_handles_none():
    assert _fmt(None) == "n/a"
    assert _fmt(0.123, pct=True) == "12.3%"
    assert _fmt(1.50) == "1.50"
