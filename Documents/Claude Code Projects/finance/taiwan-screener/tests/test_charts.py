from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.charts import build_chart


def _df():
    n = 80
    rng = np.random.default_rng(1)
    close = np.linspace(20, 30, n) + rng.normal(0, 0.2, n)
    high = close + 0.4
    low = close - 0.4
    open_ = close - rng.normal(0, 0.1, n)
    vol = rng.integers(500_000, 2_000_000, n).astype(float)
    idx = pd.date_range("2025-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_build_chart_returns_png_bytes():
    png = build_chart(_df(), "2330.TW", "台積電", entry=28.0, stop=25.0,
                      target=35.0)
    assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 5000
