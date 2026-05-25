from finance_tw_path import ensure_path  # noqa: F401  (sys.path bootstrap)
from screener.universe_tw import load_universe, load_symbols


def test_universe_has_seed_tickers():
    u = load_universe()
    assert len(u) >= 20
    syms = {t["symbol"] for t in u}
    assert "2330.TW" in syms
    assert "2317.TW" in syms


def test_symbols_all_end_with_tw():
    for s in load_symbols():
        assert s.endswith(".TW"), s


def test_each_record_has_name_zh():
    for t in load_universe():
        assert t["name_zh"], t
