from finance_tw_path import ensure_path  # noqa: F401
import os
from screener.mailer import render_weekly_email, send_email


def _png_stub() -> bytes:
    # smallest valid PNG (1x1 transparent)
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00"
            b"\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00"
            b"\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00"
            b"\x00\x00\x00IEND\xaeB`\x82")


def _pick(sym):
    return {
        "symbol": sym, "name_zh": "測試", "sector": "半導體",
        "score": 7, "indicators_fired": ["rsi", "macd"],
        "pattern": "旗形 (Bull Flag)", "pattern_confidence": 0.7,
        "entry": 20.0, "stop": 18.0, "target": 26.0, "rr": 3.0,
        "hold_weeks": 5,
        "institution_label": "高度正相關", "soxx_corr": 0.91,
        "institution_score": 9.0,
        "chart_png": _png_stub(),
    }


def test_render_returns_html_and_cids():
    html, atts = render_weekly_email([_pick("2330.TW"), _pick("2317.TW")],
                                     universe_count=1045, date_zh="2026年5月25日",
                                     params_version="2026-05-01")
    assert "台股週報" in html
    assert len(atts) == 2
    for cid, png in atts:
        assert isinstance(cid, str) and "@" in cid
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_send_dry_run_size_under_cap(monkeypatch):
    monkeypatch.setenv("EMAIL_TO", "you@example.com")
    monkeypatch.setenv("GMAIL_USER", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x")
    html, atts = render_weekly_email([_pick("2330.TW")],
                                     universe_count=1045, date_zh="2026年5月25日",
                                     params_version="t")
    size = send_email("台股週報 — 交易機會 — 2026年5月25日",
                      html, atts, dry_run=True)
    assert size < 102_000
