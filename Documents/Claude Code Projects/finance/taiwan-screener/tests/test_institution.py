from finance_tw_path import ensure_path  # noqa: F401
from screener.institution import score_institution, _label


def test_score_high_corr_with_holders():
    score, label = score_institution(
        {"SOXX": 0.92, "QQQ": 0.88, "SPY": 0.70, "AMAT": 0.91},
        [{"holder": "BlackRock", "shares": 1000, "pct": 5.0}]
    )
    assert score == 9.0
    assert label == "高度正相關"


def test_score_mid_corr():
    score, _ = score_institution(
        {"SOXX": 0.75, "QQQ": 0.6, "SPY": 0.5, "AMAT": 0.7}, []
    )
    assert score == 7.0


def test_score_low_corr():
    score, _ = score_institution(
        {"SOXX": 0.30, "QQQ": 0.2, "SPY": 0.1, "AMAT": 0.2}, []
    )
    assert score == 4.0


def test_no_data_score():
    score, label = score_institution({"SOXX": None}, [])
    assert score == 5.0
    assert label == "資料不足"
