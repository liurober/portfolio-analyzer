# Equity Analysis Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `/analyze <TICKER>` Claude Code skill that produces a commercial-grade equity analysis HTML report covering technical analysis, fundamentals, and GEX options positioning, with a weighted BUY/HOLD/SELL rating.

**Architecture:** A Python script (`analyze.py`) collects quantitative data (yfinance OHLCV + indicators + patterns + GEX from options chain + yfinance fundamentals), writes `analysis.json`, then Claude reads it, scores three pillars, writes analyst narrative, renders the HTML report via Jinja2, opens it in the browser, and saves an Obsidian note.

**Tech Stack:** Python 3.11+, yfinance, pandas, ta, matplotlib, jinja2, scipy (already installed). Skill definition in Markdown. No new pip dependencies required.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `stock-screener/screener/barchart_gex.py` | CREATE | Compute GEX from yfinance options chain |
| `stock-screener/screener/charts.py` | MODIFY | Add `generate_analysis_chart()` with delay label + pattern overlay |
| `stock-screener/analyze.py` | CREATE | Main orchestrator: fetch → score → write analysis.json |
| `stock-screener/screener/analysis_template.html` | CREATE | Jinja2 HTML report template |
| `financial-services/plugins/vertical-plugins/equity-research/skills/analyze/SKILL.md` | CREATE | Claude skill definition for `/analyze` |
| `stock-screener/tests/test_barchart_gex.py` | CREATE | Unit tests for GEX calculator |
| `stock-screener/tests/test_charts_analysis.py` | CREATE | Unit tests for analysis chart |
| `stock-screener/tests/test_analyze.py` | CREATE | Integration tests for orchestrator |

---

## Task 1: GEX Calculator

**Files:**
- Create: `stock-screener/screener/barchart_gex.py`
- Create: `stock-screener/tests/test_barchart_gex.py`

Note: GEX is calculated from yfinance options chain (not Barchart scraping — Barchart requires JS rendering). The math matches Barchart's GEX methodology: `GEX = Σ(Gamma × OI × 100 × Spot²)` where calls contribute positive GEX and puts contribute negative GEX.

- [ ] **Step 1: Create the tests directory and write the failing tests**

```bash
mkdir -p /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener/tests
touch /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener/tests/__init__.py
```

Create `stock-screener/tests/test_barchart_gex.py`:

```python
"""Tests for GEX calculator."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from screener.barchart_gex import fetch_gex, _compute_gex_from_chain


def _make_calls():
    return pd.DataFrame({
        "strike": [170.0, 175.0, 180.0, 185.0],
        "openInterest": [10000, 25000, 15000, 5000],
        "gamma": [0.05, 0.08, 0.06, 0.03],
    })


def _make_puts():
    return pd.DataFrame({
        "strike": [160.0, 165.0, 170.0, 175.0],
        "openInterest": [8000, 20000, 12000, 6000],
        "gamma": [0.03, 0.06, 0.07, 0.05],
    })


def test_compute_gex_returns_expected_keys():
    calls = _make_calls()
    puts = _make_puts()
    result = _compute_gex_from_chain(calls, puts, spot=175.0)
    assert "net_gex" in result
    assert "dealer_bias" in result
    assert "flip_level" in result
    assert "distance_to_flip_pct" in result
    assert "put_wall" in result
    assert "call_wall" in result


def test_call_wall_is_highest_oi_call_strike():
    calls = _make_calls()
    puts = _make_puts()
    result = _compute_gex_from_chain(calls, puts, spot=175.0)
    assert result["call_wall"] == 175.0  # highest call OI


def test_put_wall_is_highest_oi_put_strike():
    calls = _make_calls()
    puts = _make_puts()
    result = _compute_gex_from_chain(calls, puts, spot=175.0)
    assert result["put_wall"] == 165.0  # highest put OI


def test_dealer_bias_positive_net_gex():
    # Force large call GEX > put GEX → long gamma
    calls = pd.DataFrame({
        "strike": [175.0],
        "openInterest": [100000],
        "gamma": [0.10],
    })
    puts = pd.DataFrame({
        "strike": [175.0],
        "openInterest": [1000],
        "gamma": [0.01],
    })
    result = _compute_gex_from_chain(calls, puts, spot=175.0)
    assert result["dealer_bias"] == "long_gamma"
    assert result["net_gex"] > 0


def test_dealer_bias_negative_net_gex():
    calls = pd.DataFrame({
        "strike": [175.0],
        "openInterest": [1000],
        "gamma": [0.01],
    })
    puts = pd.DataFrame({
        "strike": [175.0],
        "openInterest": [100000],
        "gamma": [0.10],
    })
    result = _compute_gex_from_chain(calls, puts, spot=175.0)
    assert result["dealer_bias"] == "short_gamma"
    assert result["net_gex"] < 0


def test_fetch_gex_returns_null_dict_on_failure():
    """If yfinance fails, return null fields rather than crashing."""
    with patch("screener.barchart_gex.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = Exception("network error")
        result = fetch_gex("FAKE")
    assert result["net_gex"] is None
    assert result["dealer_bias"] is None
    assert "error" in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -m pytest tests/test_barchart_gex.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'screener.barchart_gex'`

- [ ] **Step 3: Implement `barchart_gex.py`**

Create `stock-screener/screener/barchart_gex.py`:

```python
"""
GEX (Gamma Exposure) calculator from yfinance options chain.

GEX per strike = Gamma × OI × 100 × Spot²
  Calls → positive GEX (dealers long gamma, dampening moves)
  Puts  → negative GEX (dealers short gamma, amplifying moves)

Net GEX > 0 → long gamma → price-dampening environment
Net GEX < 0 → short gamma → price-amplifying environment
"""
import datetime

import numpy as np
import pandas as pd
import yfinance as yf


def _compute_gex_from_chain(calls: pd.DataFrame, puts: pd.DataFrame, spot: float) -> dict:
    """
    Compute GEX metrics from calls/puts DataFrames with columns:
    strike, openInterest, gamma.
    """
    calls = calls.copy()
    puts = puts.copy()

    calls["gex"] = calls["gamma"] * calls["openInterest"] * 100 * spot ** 2
    puts["gex"] = -puts["gamma"] * puts["openInterest"] * 100 * spot ** 2

    merged = pd.merge(
        calls[["strike", "gex"]].rename(columns={"gex": "gex_call"}),
        puts[["strike", "gex"]].rename(columns={"gex": "gex_put"}),
        on="strike",
        how="outer",
    ).fillna(0)
    merged["net_gex"] = merged["gex_call"] + merged["gex_put"]

    net_gex_total = float(merged["net_gex"].sum())
    dealer_bias = "long_gamma" if net_gex_total >= 0 else "short_gamma"

    # Flip level: strike where cumulative GEX (sorted by strike) crosses zero
    sorted_strikes = merged.sort_values("strike").reset_index(drop=True)
    sorted_strikes["cumgex"] = sorted_strikes["net_gex"].cumsum()
    flip_idx = int(sorted_strikes["cumgex"].abs().idxmin())
    flip_level = float(sorted_strikes.loc[flip_idx, "strike"])
    distance_to_flip_pct = round((spot - flip_level) / flip_level * 100, 1)

    # Walls: strikes with highest OI
    call_wall = float(calls.loc[calls["openInterest"].idxmax(), "strike"])
    put_wall = float(puts.loc[puts["openInterest"].idxmax(), "strike"])

    return {
        "net_gex": round(net_gex_total, 0),
        "dealer_bias": dealer_bias,
        "flip_level": flip_level,
        "distance_to_flip_pct": distance_to_flip_pct,
        "put_wall": put_wall,
        "call_wall": call_wall,
    }


def fetch_gex(ticker: str) -> dict:
    """
    Fetch options chain for the nearest 2 expiries and compute GEX.
    Returns null-filled dict on any failure instead of raising.
    """
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        spot = float(fi.get("last_price") or fi.get("previous_close", 0))
        if spot <= 0:
            raise ValueError(f"Invalid spot price {spot} for {ticker}")

        exps = t.options[:2]
        if not exps:
            raise ValueError(f"No options expiries found for {ticker}")

        all_calls, all_puts = [], []
        for exp in exps:
            chain = t.option_chain(exp)
            c = chain.calls[["strike", "openInterest", "gamma"]].dropna()
            p = chain.puts[["strike", "openInterest", "gamma"]].dropna()
            all_calls.append(c)
            all_puts.append(p)

        calls = (
            pd.concat(all_calls)
            .groupby("strike", as_index=False)
            .sum()
        )
        puts = (
            pd.concat(all_puts)
            .groupby("strike", as_index=False)
            .sum()
        )

        result = _compute_gex_from_chain(calls, puts, spot)
        result["raw_scraped_at"] = datetime.datetime.now().isoformat()
        return result

    except Exception as e:
        return {
            "net_gex": None,
            "dealer_bias": None,
            "flip_level": None,
            "distance_to_flip_pct": None,
            "put_wall": None,
            "call_wall": None,
            "raw_scraped_at": None,
            "error": str(e),
        }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -m pytest tests/test_barchart_gex.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects
git add stock-screener/screener/barchart_gex.py stock-screener/tests/test_barchart_gex.py stock-screener/tests/__init__.py
git commit -m "feat: add GEX calculator from yfinance options chain"
```

---

## Task 2: Extend Chart Generator

**Files:**
- Modify: `stock-screener/screener/charts.py`
- Create: `stock-screener/tests/test_charts_analysis.py`

Add `generate_analysis_chart()` alongside the existing `generate_chart()`. The existing function is untouched — the weekly screener still calls it. The new function adds: pattern annotation box, "Prices delayed ~15 min" label, and accepts a `timeframe` param (`"weekly"` or `"daily"`).

- [ ] **Step 1: Write the failing tests**

Create `stock-screener/tests/test_charts_analysis.py`:

```python
"""Tests for generate_analysis_chart."""
import base64
import pytest
import numpy as np
import pandas as pd

from screener.charts import generate_analysis_chart


def _make_df(n=60):
    """Synthetic OHLCV DataFrame with DatetimeIndex."""
    idx = pd.date_range("2025-01-01", periods=n, freq="W")
    close = 100 + np.cumsum(np.random.randn(n))
    open_ = close - np.abs(np.random.randn(n))
    high = close + np.abs(np.random.randn(n))
    low = open_ - np.abs(np.random.randn(n))
    volume = np.random.randint(1_000_000, 50_000_000, n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def _make_trade(ticker="TEST", pattern="Cup & Handle"):
    return {
        "ticker": ticker,
        "direction": "LONG",
        "entry": 105.0,
        "stop": 98.0,
        "target": 122.5,
        "pattern": pattern,
        "score": 4,
        "squeeze_fired": False,
    }


def test_returns_valid_base64_string():
    df = _make_df()
    trade = _make_trade()
    result = generate_analysis_chart(df, trade)
    assert isinstance(result, str)
    # Must decode without error
    decoded = base64.b64decode(result)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes


def test_accepts_daily_timeframe():
    df = _make_df(n=120)
    trade = _make_trade()
    result = generate_analysis_chart(df, trade, timeframe="daily")
    assert isinstance(result, str)
    base64.b64decode(result)  # must not raise


def test_accepts_no_pattern():
    df = _make_df()
    trade = _make_trade(pattern=None)
    trade["pattern"] = None
    result = generate_analysis_chart(df, trade)
    assert isinstance(result, str)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -m pytest tests/test_charts_analysis.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'generate_analysis_chart' from 'screener.charts'`

- [ ] **Step 3: Add `generate_analysis_chart()` to `charts.py`**

Append the following to the bottom of `stock-screener/screener/charts.py` (after the existing `generate_chart` function):

```python
def generate_analysis_chart(df: pd.DataFrame, trade: dict,
                             timeframe: str = "weekly", bars: int = 52) -> str:
    """
    Analysis-grade chart variant. Adds:
    - Pattern annotation box
    - 'Prices delayed ~15 min' footer label
    - timeframe param ('weekly' or 'daily')

    The existing generate_chart() is unchanged — weekly screener still uses it.
    """
    d = _prep_df(df, bars)
    d = _add_indicators(d)

    direction = trade["direction"]
    entry     = trade["entry"]
    stop      = trade["stop"]
    target    = trade["target"]
    ticker    = trade["ticker"]
    pattern   = trade.get("pattern") or "Multi-indicator Confluence"
    score     = trade.get("score", "—")

    xs = np.arange(len(d))
    freq_label = "Daily" if timeframe == "daily" else "Weekly"
    dates = [dt.strftime("%b '%y") for dt in d.index]
    tick_step = max(1, len(xs) // 8)
    tick_xs   = xs[::tick_step]
    tick_lbls = [dates[i] for i in range(0, len(xs), tick_step)]

    fig = plt.figure(figsize=(14, 10), facecolor=DARK_BG)
    gs  = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.04)

    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor(CARD_BG)
        ax.tick_params(colors=DIM_COLOR, labelsize=8)
        ax.spines[:].set_color(GRID_COLOR)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.5, linestyle="--")
        ax.grid(axis="x", color=GRID_COLOR, linewidth=0.3, linestyle=":")

    # Panel 1: Candlesticks
    w = 0.6
    for i, (_, row) in enumerate(d.iterrows()):
        bull = row["Close"] >= row["Open"]
        color = GREEN if bull else RED
        ax1.bar(xs[i], abs(row["Close"] - row["Open"]),
                bottom=min(row["Open"], row["Close"]),
                width=w, color=color, alpha=0.9, linewidth=0)
        ax1.plot([xs[i], xs[i]], [row["Low"], row["High"]],
                 color=color, linewidth=0.8, alpha=0.7)

    ax1.plot(xs, d["bb_upper"], color=BLUE, linewidth=0.8, alpha=0.5, linestyle="--")
    ax1.plot(xs, d["bb_mid"],   color=BLUE, linewidth=0.8, alpha=0.8)
    ax1.plot(xs, d["bb_lower"], color=BLUE, linewidth=0.8, alpha=0.5, linestyle="--")
    ax1.fill_between(xs, d["bb_upper"], d["bb_lower"], alpha=0.04, color=BLUE)

    if direction == "LONG":
        ax1.plot(xs, d["ce_long"],  color=ORANGE, linewidth=1.2, linestyle="-.", alpha=0.8, label="CE Long")
    else:
        ax1.plot(xs, d["ce_short"], color=ORANGE, linewidth=1.2, linestyle="-.", alpha=0.8, label="CE Short")

    ax1.axhline(entry,  color=BLUE,  linewidth=1.2, linestyle="-",  alpha=0.9)
    ax1.axhline(stop,   color=RED,   linewidth=1.2, linestyle="--", alpha=0.9)
    ax1.axhline(target, color=GREEN, linewidth=1.2, linestyle="--", alpha=0.9)

    ax1_xmax = xs[-1] + 1.5
    ax1.text(ax1_xmax, entry,  f" Entry ${entry}",  color=BLUE,  fontsize=7.5, va="center")
    ax1.text(ax1_xmax, stop,   f" Stop  ${stop}",   color=RED,   fontsize=7.5, va="center")
    ax1.text(ax1_xmax, target, f" Target ${target}", color=GREEN, fontsize=7.5, va="center")

    ax1.fill_between(xs[-15:], stop,   entry,  alpha=0.06, color=RED)
    ax1.fill_between(xs[-15:], entry,  target, alpha=0.06, color=GREEN)

    dir_color = GREEN if direction == "LONG" else RED
    ax1.set_title(
        f"{ticker}  ·  {direction}  ·  {freq_label}  ·  Score {score}/5",
        color=TEXT_COLOR, fontsize=12, fontweight="bold", loc="left", pad=10,
    )

    # Pattern annotation box
    if pattern:
        ax1.text(
            0.01, 0.97, f"Pattern: {pattern}",
            transform=ax1.transAxes,
            fontsize=9, color=YELLOW,
            va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=CARD_BG,
                      edgecolor=YELLOW, alpha=0.85),
        )

    legend_patches = [
        mpatches.Patch(color=BLUE,   label="Bollinger Bands"),
        mpatches.Patch(color=ORANGE, label="Chandelier Exit"),
        mpatches.Patch(color=BLUE,   label=f"Entry ${entry}"),
        mpatches.Patch(color=RED,    label=f"Stop ${stop}"),
        mpatches.Patch(color=GREEN,  label=f"Target ${target}"),
    ]
    ax1.legend(handles=legend_patches, loc="upper right",
               facecolor=DARK_BG, edgecolor=GRID_COLOR,
               labelcolor=TEXT_COLOR, fontsize=7.5, ncol=3)

    vol_ax = ax1.twinx()
    vol_ax.set_facecolor(CARD_BG)
    vol_ax.tick_params(right=False, labelright=False)
    vol_ax.spines[:].set_visible(False)
    vol_colors = [GREEN if d["Close"].iloc[i] >= d["Open"].iloc[i] else RED for i in range(len(d))]
    vol_ax.bar(xs, d["Volume"], width=w, color=vol_colors, alpha=0.12)
    vol_ax.set_ylim(0, d["Volume"].max() * 6)

    plt.setp(ax1.get_xticklabels(), visible=False)

    # Panel 2: RSI
    ax2.plot(xs, d["rsi"], color=PURPLE, linewidth=1.2)
    ax2.axhline(70, color=RED,      linewidth=0.6, linestyle="--", alpha=0.6)
    ax2.axhline(50, color=DIM_COLOR, linewidth=0.5, linestyle=":")
    ax2.axhline(30, color=GREEN,    linewidth=0.6, linestyle="--", alpha=0.6)
    ax2.fill_between(xs, d["rsi"], 70, where=(d["rsi"] >= 70), alpha=0.15, color=RED)
    ax2.fill_between(xs, d["rsi"], 30, where=(d["rsi"] <= 30), alpha=0.15, color=GREEN)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI", color=DIM_COLOR, fontsize=8)
    ax2.text(xs[-1] + 0.5, d["rsi"].iloc[-1], f" {d['rsi'].iloc[-1]:.0f}",
             color=PURPLE, fontsize=7.5, va="center")
    plt.setp(ax2.get_xticklabels(), visible=False)

    # Panel 3: MACD + TTM Squeeze dots
    hist = d["macd_hist"]
    hist_colors = [GREEN if v >= 0 else RED for v in hist]
    ax3.bar(xs, hist, width=w, color=hist_colors, alpha=0.7)
    ax3.plot(xs, d["macd"],        color=BLUE,   linewidth=1.0)
    ax3.plot(xs, d["macd_signal"], color=ORANGE, linewidth=1.0)
    ax3.axhline(0, color=GRID_COLOR, linewidth=0.5)
    ax3.set_ylabel("MACD", color=DIM_COLOR, fontsize=8)

    squeeze_y = ax3.get_ylim()[0]
    for i, (_, row) in enumerate(d.iterrows()):
        dot_color = RED if row["squeeze_on"] else GREEN
        ax3.plot(xs[i], squeeze_y, "o", color=dot_color, markersize=4, alpha=0.9, zorder=5)

    sq_legend = [
        mpatches.Patch(color=RED,    label="Squeeze ON"),
        mpatches.Patch(color=GREEN,  label="Squeeze OFF"),
        mpatches.Patch(color=BLUE,   label="MACD"),
        mpatches.Patch(color=ORANGE, label="Signal"),
    ]
    ax3.legend(handles=sq_legend, loc="upper left",
               facecolor=DARK_BG, edgecolor=GRID_COLOR,
               labelcolor=TEXT_COLOR, fontsize=7, ncol=2)

    ax3.set_xticks(tick_xs)
    ax3.set_xticklabels(tick_lbls, color=DIM_COLOR, fontsize=7.5)

    # "Prices delayed ~15 min" footer
    fig.text(
        0.99, 0.005,
        "Prices delayed ~15 min  |  Chart: yfinance",
        ha="right", va="bottom",
        fontsize=6.5, color=DIM_COLOR, style="italic",
    )

    plt.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=DARK_BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -m pytest tests/test_charts_analysis.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Confirm existing screener chart test still works**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -c "
import yfinance as yf
from screener.charts import generate_chart
df = yf.download('AAPL', period='1y', interval='1wk', progress=False, auto_adjust=True)
trade = {'ticker':'AAPL','direction':'LONG','entry':190.0,'stop':178.0,'target':214.0,'pattern':'Bull Flag','score':4,'squeeze_fired':False}
b64 = generate_chart(df, trade)
print('generate_chart OK, length:', len(b64))
"
```

Expected: `generate_chart OK, length: <some large number>`

- [ ] **Step 6: Commit**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects
git add stock-screener/screener/charts.py stock-screener/tests/test_charts_analysis.py
git commit -m "feat: add generate_analysis_chart with pattern overlay and delay label"
```

---

## Task 3: Main Orchestrator

**Files:**
- Create: `stock-screener/analyze.py`
- Create: `stock-screener/tests/test_analyze.py`

- [ ] **Step 1: Write the failing tests**

Create `stock-screener/tests/test_analyze.py`:

```python
"""Tests for analyze.py orchestrator."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import pandas as pd
import pytest

# Add stock-screener to path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze


def _make_weekly_df(n=60):
    idx = pd.date_range("2024-01-01", periods=n, freq="W")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "Open":   close - 0.5,
        "High":   close + 1.0,
        "Low":    close - 1.0,
        "Close":  close,
        "Volume": np.full(n, 10_000_000.0),
    }, index=idx)


def test_score_technical_pillar_maps_correctly():
    assert analyze.score_technical_pillar(5, True, 0.8, 3.2) == 10.0
    assert analyze.score_technical_pillar(4, False, 0.0, 2.0) == 8.0
    assert analyze.score_technical_pillar(3, False, 0.0, 2.0) == 6.0
    assert analyze.score_technical_pillar(2, False, 0.0, 2.0) == 3.0
    assert analyze.score_technical_pillar(0, False, 0.0, 0.0) == 0.0


def test_score_technical_pillar_bonuses_capped_at_10():
    result = analyze.score_technical_pillar(5, True, 0.9, 4.0)
    assert result == 10.0


def test_score_gex_pillar_long_gamma_above_flip():
    gex = {
        "dealer_bias": "long_gamma",
        "distance_to_flip_pct": 5.0,
        "net_gex": 1_000_000_000,
    }
    score = analyze.score_gex_pillar(gex)
    assert 9 <= score <= 10


def test_score_gex_pillar_short_gamma_below_flip():
    gex = {
        "dealer_bias": "short_gamma",
        "distance_to_flip_pct": -5.0,
        "net_gex": -1_000_000_000,
    }
    score = analyze.score_gex_pillar(gex)
    assert 0 <= score <= 2


def test_score_gex_pillar_returns_5_when_gex_null():
    gex = {"dealer_bias": None, "distance_to_flip_pct": None, "net_gex": None}
    score = analyze.score_gex_pillar(gex)
    assert score == 5.0


def test_compute_final_score_and_rating():
    score, rating = analyze.compute_final_score_and_rating(
        tech_score=9.0, fund_score=8.5, gex_score=8.0
    )
    assert score >= 8.0
    assert "BUY" in rating
    assert "High" in rating


def test_compute_final_score_hold_range():
    score, rating = analyze.compute_final_score_and_rating(
        tech_score=5.0, fund_score=5.0, gex_score=5.0
    )
    assert 4.5 <= score <= 6.4
    assert rating == "HOLD"


def test_entry_stop_target_long():
    entry, stop, target, rr = analyze.calc_entry_stop_target(
        close=100.0, direction="long", ce_long=93.0, ce_short=None
    )
    assert entry == 100.0
    assert stop == 93.0
    assert target == pytest.approx(100.0 + (100.0 - 93.0) * 2.5, abs=0.01)
    assert rr == pytest.approx(2.5, abs=0.1)


def test_entry_stop_target_short():
    entry, stop, target, rr = analyze.calc_entry_stop_target(
        close=100.0, direction="short", ce_long=None, ce_short=107.0
    )
    assert entry == 100.0
    assert stop == 107.0
    assert target == pytest.approx(100.0 - (107.0 - 100.0) * 2.5, abs=0.01)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -m pytest tests/test_analyze.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'analyze'`

- [ ] **Step 3: Implement `analyze.py`**

Create `stock-screener/analyze.py`:

```python
"""
On-demand single-stock equity analysis orchestrator.
Usage: python analyze.py <TICKER>
Outputs: analysis.json in the stock-screener directory.
"""
import datetime
import json
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

from screener.barchart_gex import fetch_gex
from screener.charts import generate_analysis_chart
from screener.indicators import score_signals
from screener.patterns import detect_all_patterns


# ── Scoring helpers ──────────────────────────────────────────────────────────

def score_technical_pillar(
    ind_score: int,
    squeeze_fired: bool,
    pattern_confidence: float,
    rr_ratio: float,
) -> float:
    """Map indicator score + bonuses to 0–10. Capped at 10."""
    base = {5: 10, 4: 8, 3: 6, 2: 3, 1: 0, 0: 0}.get(ind_score, 0)
    bonus = 0.0
    if pattern_confidence > 0:
        bonus += 1.0
    if pattern_confidence > 0.7:
        bonus += 0.5
    if rr_ratio >= 3.0:
        bonus += 0.5
    if squeeze_fired:
        bonus += 0.5
    return min(float(base) + bonus, 10.0)


def score_gex_pillar(gex: dict) -> float:
    """Return 0–10 GEX score. Returns 5.0 (neutral) when GEX data unavailable."""
    if gex.get("dealer_bias") is None:
        return 5.0
    bias = gex["dealer_bias"]
    dist = gex.get("distance_to_flip_pct") or 0.0
    if bias == "long_gamma":
        if dist > 3:
            return 9.5
        elif dist > 0:
            return 7.5
        else:
            return 6.0
    else:  # short_gamma
        if dist < -3:
            return 1.0
        elif dist < 0:
            return 3.5
        else:
            return 5.5


def compute_final_score_and_rating(
    tech_score: float,
    fund_score: float,
    gex_score: float,
    gex_available: bool = True,
) -> tuple[float, str]:
    """Weighted average → rating string."""
    if gex_available:
        weighted = tech_score * 0.45 + fund_score * 0.40 + gex_score * 0.15
    else:
        weighted = tech_score * 0.55 + fund_score * 0.45

    weighted = round(weighted, 2)

    if weighted >= 8.0:
        rating = "BUY — High Conviction"
    elif weighted >= 6.5:
        rating = "BUY — Moderate Conviction"
    elif weighted >= 4.5:
        rating = "HOLD"
    elif weighted >= 3.0:
        rating = "SELL — Moderate Conviction"
    else:
        rating = "SELL — High Conviction"

    return weighted, rating


def calc_entry_stop_target(
    close: float,
    direction: str,
    ce_long: float | None,
    ce_short: float | None,
) -> tuple[float, float, float, float]:
    """Return (entry, stop, target, rr_ratio)."""
    if direction == "long":
        stop = ce_long if ce_long else close * 0.93
        risk = close - stop
        target = close + risk * 2.5
    else:
        stop = ce_short if ce_short else close * 1.07
        risk = stop - close
        target = close - risk * 2.5

    rr = round(abs(target - close) / abs(close - stop), 1) if abs(close - stop) > 0 else 0.0
    return round(close, 2), round(stop, 2), round(target, 2), rr


# ── Data fetchers ────────────────────────────────────────────────────────────

def fetch_price_data(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    fi = t.fast_info
    info = t.info
    return {
        "current":      round(float(fi.get("last_price") or fi.get("previous_close") or 0), 2),
        "open":         round(float(fi.get("open") or 0), 2),
        "day_high":     round(float(fi.get("day_high") or 0), 2),
        "day_low":      round(float(fi.get("day_low") or 0), 2),
        "week_52_high": round(float(fi.get("year_high") or 0), 2),
        "week_52_low":  round(float(fi.get("year_low") or 0), 2),
        "volume":       int(fi.get("three_month_average_volume") or 0),
        "avg_volume":   int(info.get("averageVolume") or 0),
        "float_shares": int(info.get("floatShares") or 0),
        "company_name": info.get("longName") or ticker,
        "sector":       info.get("sector") or "Unknown",
        "industry":     info.get("industry") or "Unknown",
    }


def fetch_fundamentals(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info
    next_earnings = None
    try:
        cal = t.calendar
        if cal is not None and not cal.empty:
            next_earnings = str(list(cal.get("Earnings Date", [None]))[0].date())
    except Exception:
        pass

    return {
        "market_cap":           info.get("marketCap"),
        "enterprise_value":     info.get("enterpriseValue"),
        "pe_ttm":               info.get("trailingPE"),
        "pe_forward":           info.get("forwardPE"),
        "ps_ttm":               info.get("priceToSalesTrailing12Months"),
        "ev_ebitda":            info.get("enterpriseToEbitda"),
        "peg_ratio":            info.get("pegRatio"),
        "eps_ttm":              info.get("trailingEps"),
        "eps_growth_yoy":       info.get("earningsGrowth"),
        "revenue_growth_yoy":   info.get("revenueGrowth"),
        "gross_margin":         info.get("grossMargins"),
        "operating_margin":     info.get("operatingMargins"),
        "net_margin":           info.get("profitMargins"),
        "free_cash_flow":       info.get("freeCashflow"),
        "debt_to_equity":       info.get("debtToEquity"),
        "next_earnings_date":   next_earnings,
        "analyst_consensus":    info.get("recommendationKey"),
        "analyst_price_target": info.get("targetMeanPrice"),
        "insider_ownership_pct": info.get("heldPercentInsiders"),
    }


# ── Main run ─────────────────────────────────────────────────────────────────

def run(ticker: str) -> Path:
    ticker = ticker.upper().strip()
    print(f"\n[analyze] Starting analysis for {ticker}")

    # 1. Download OHLCV
    print("  Downloading OHLCV history (2yr weekly)...")
    df = yf.download(ticker, period="2y", interval="1wk", progress=False, auto_adjust=True)
    if df is None or len(df) < 30:
        raise ValueError(f"Insufficient weekly data for {ticker} (got {len(df) if df is not None else 0} bars)")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

    # 2. Score indicators
    print("  Scoring technical indicators...")
    sig_long  = score_signals(df, direction="long")
    sig_short = score_signals(df, direction="short")
    direction = "long" if sig_long["score"] >= sig_short["score"] else "short"
    sig = sig_long if direction == "long" else sig_short

    # 3. Detect patterns
    patterns = detect_all_patterns(df)
    top_pattern = next((p for p in patterns if p["direction"] == direction), None)

    # 4. Entry / stop / target
    entry, stop, target, rr = calc_entry_stop_target(
        close=sig["close"],
        direction=direction,
        ce_long=sig.get("ce_long"),
        ce_short=sig.get("ce_short"),
    )

    # 5. Technical score
    tech_score = score_technical_pillar(
        ind_score=sig["score"],
        squeeze_fired=sig["squeeze_fired"],
        pattern_confidence=top_pattern["confidence"] if top_pattern else 0.0,
        rr_ratio=rr,
    )

    # 6. Generate chart
    print("  Generating chart...")
    trade_meta = {
        "ticker":    ticker,
        "direction": direction.upper(),
        "entry":     entry,
        "stop":      stop,
        "target":    target,
        "pattern":   top_pattern["pattern"] if top_pattern else "Multi-indicator Confluence",
        "score":     sig["score"],
        "squeeze_fired": sig["squeeze_fired"],
    }
    chart_b64 = generate_analysis_chart(df, trade_meta)

    # 7. Price + fundamentals
    print("  Fetching price data and fundamentals...")
    price_data    = fetch_price_data(ticker)
    fundamentals  = fetch_fundamentals(ticker)

    # 8. GEX
    print("  Computing GEX from options chain...")
    gex = fetch_gex(ticker)
    gex_available = gex.get("net_gex") is not None

    # 9. GEX score (Claude will re-score fundamentals — this is the quantitative GEX score only)
    gex_score = score_gex_pillar(gex)

    # 10. Preliminary scores written to JSON (Claude computes fund_score + final narrative)
    output = {
        "ticker":        ticker,
        "as_of":         datetime.datetime.now().isoformat(),
        "company_name":  price_data.pop("company_name"),
        "sector":        price_data.pop("sector"),
        "industry":      price_data.pop("industry"),
        "price":         price_data,
        "technicals": {
            "score_long":          sig_long["score"],
            "score_short":         sig_short["score"],
            "direction":           direction,
            "rsi":                 sig["rsi"],
            "sig_rsi":             sig["sig_rsi"],
            "sig_bb":              sig["sig_bb"],
            "sig_macd":            sig["sig_macd"],
            "sig_chandelier":      sig["sig_chandelier"],
            "sig_ttm":             sig["sig_ttm"],
            "squeeze_fired":       sig["squeeze_fired"],
            "squeeze_on":          sig["squeeze_on"],
            "bb_upper":            sig["bb_upper"],
            "bb_lower":            sig["bb_lower"],
            "ce_long":             sig.get("ce_long"),
            "atr":                 sig.get("atr"),
            "entry":               entry,
            "stop":                stop,
            "target":              target,
            "rr_ratio":            rr,
            "pattern":             top_pattern["pattern"] if top_pattern else None,
            "pattern_confidence":  top_pattern["confidence"] if top_pattern else None,
            "pattern_confirmed":   top_pattern.get("confirmed", False) if top_pattern else False,
        },
        "chart_b64":     chart_b64,
        "gex":           gex,
        "fundamentals":  fundamentals,
        "scores": {
            "tech_score":      tech_score,
            "gex_score":       gex_score,
            "gex_available":   gex_available,
        },
    }

    out_path = Path(__file__).parent / "analysis.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"  analysis.json → {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <TICKER>")
        sys.exit(1)
    run(sys.argv[1])
```

- [ ] **Step 4: Run unit tests**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -m pytest tests/test_analyze.py -v
```

Expected: `10 passed`

- [ ] **Step 5: Smoke test with a real ticker**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python analyze.py AAPL
```

Expected output (approximately):
```
[analyze] Starting analysis for AAPL
  Downloading OHLCV history (2yr weekly)...
  Scoring technical indicators...
  Generating chart...
  Fetching price data and fundamentals...
  Computing GEX from options chain...
  analysis.json → .../stock-screener/analysis.json
```

Then verify JSON:
```bash
python -c "import json; d=json.load(open('analysis.json')); print(d['ticker'], d['price']['current'], d['technicals']['direction'], d['scores'])"
```

Expected: `AAPL <price> long {'tech_score': ..., 'gex_score': ..., 'gex_available': True}`

- [ ] **Step 6: Commit**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects
git add stock-screener/analyze.py stock-screener/tests/test_analyze.py
git commit -m "feat: add analyze.py orchestrator with technical scoring and GEX"
```

---

## Task 4: HTML Report Template

**Files:**
- Create: `stock-screener/screener/analysis_template.html`

This is a Jinja2 template. Claude renders it after scoring fundamentals and writing narratives. All values passed in via a `report` dict.

- [ ] **Step 1: Create the template**

Create `stock-screener/screener/analysis_template.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ report.ticker }} — Equity Analysis</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d0d0d; color: #cccccc; font-family: -apple-system, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.6; padding: 24px; }
  .container { max-width: 1100px; margin: 0 auto; }

  /* Header */
  .header { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; padding: 24px 28px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
  .header-left h1 { font-size: 26px; color: #fff; font-weight: 700; }
  .header-left .subtitle { color: #888; font-size: 13px; margin-top: 4px; }
  .header-left .price-row { margin-top: 10px; display: flex; align-items: baseline; gap: 12px; }
  .price-live { font-size: 36px; font-weight: 700; color: #fff; }
  .price-change { font-size: 16px; }
  .price-delayed { font-size: 11px; color: #555; font-style: italic; margin-top: 4px; }
  .header-right { text-align: right; }
  .rating-badge { display: inline-block; padding: 10px 20px; border-radius: 6px; font-size: 18px; font-weight: 700; letter-spacing: 0.5px; }
  .rating-buy-high   { background: #003d1a; color: #00c853; border: 1px solid #00c853; }
  .rating-buy-mod    { background: #1a3300; color: #76ff03; border: 1px solid #76ff03; }
  .rating-hold       { background: #2a2200; color: #ffd740; border: 1px solid #ffd740; }
  .rating-sell-mod   { background: #3d0011; color: #ff4081; border: 1px solid #ff4081; }
  .rating-sell-high  { background: #3d0000; color: #ff1744; border: 1px solid #ff1744; }
  .final-score { font-size: 13px; color: #888; margin-top: 8px; }
  .as-of { font-size: 11px; color: #444; margin-top: 4px; }

  /* Score cards */
  .pillar-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }
  .pillar-card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; padding: 20px; text-align: center; }
  .pillar-name { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #666; margin-bottom: 8px; }
  .pillar-score { font-size: 38px; font-weight: 700; }
  .pillar-weight { font-size: 11px; color: #444; margin-top: 4px; }
  .score-high { color: #00c853; }
  .score-mid  { color: #ffd740; }
  .score-low  { color: #ff1744; }

  /* Chart */
  .chart-section { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
  .chart-section img { width: 100%; border-radius: 4px; }
  .section-title { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: #555; margin-bottom: 14px; font-weight: 600; }

  /* Analysis sections */
  .analysis-section { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; padding: 22px 24px; margin-bottom: 16px; }
  .analysis-section h2 { font-size: 15px; font-weight: 700; color: #fff; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 16px; border-bottom: 1px solid #2a2a2a; padding-bottom: 10px; }
  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .metric { background: #111; border-radius: 6px; padding: 12px 14px; }
  .metric-label { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .metric-value { font-size: 16px; font-weight: 600; color: #ddd; }
  .metric-sub { font-size: 11px; color: #444; margin-top: 2px; }
  .sig-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
  .sig-badge { padding: 5px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }
  .sig-on  { background: #003d1a; color: #00c853; border: 1px solid #00c853; }
  .sig-off { background: #1a1a1a; color: #444; border: 1px solid #333; }
  .narrative { color: #aaa; font-size: 13.5px; line-height: 1.75; margin-top: 14px; }
  .narrative p + p { margin-top: 10px; }

  /* Trade box */
  .trade-box { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
  .trade-item { background: #111; border-radius: 6px; padding: 12px; text-align: center; }
  .trade-label { font-size: 10px; text-transform: uppercase; color: #555; margin-bottom: 4px; }
  .trade-val { font-size: 18px; font-weight: 700; }
  .entry-val  { color: #1e90ff; }
  .stop-val   { color: #ff1744; }
  .target-val { color: #00c853; }
  .rr-val     { color: #ffd740; }

  /* Verdict */
  .verdict-section { background: #1a1a1a; border: 2px solid #2a2a2a; border-radius: 8px; padding: 24px; margin-bottom: 16px; }
  .verdict-header { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: #555; margin-bottom: 12px; }
  .verdict-rating { font-size: 28px; font-weight: 700; margin-bottom: 6px; }
  .verdict-target { color: #888; font-size: 14px; margin-bottom: 16px; }
  .verdict-thesis { color: #aaa; font-size: 14px; line-height: 1.75; }

  /* GEX */
  .gex-bias-long  { color: #00c853; }
  .gex-bias-short { color: #ff1744; }
  .gex-na { color: #444; font-style: italic; }

  /* Footer */
  .footer { text-align: center; color: #333; font-size: 11px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #1a1a1a; }
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <h1>{{ report.ticker }} — {{ report.company_name }}</h1>
      <div class="subtitle">{{ report.sector }} · {{ report.industry }}</div>
      <div class="price-row">
        <span class="price-live">${{ "%.2f"|format(report.price.current) }}</span>
        {% if report.price.day_high and report.price.day_low %}
        <span class="price-change" style="color:#888">H: ${{ "%.2f"|format(report.price.day_high) }} · L: ${{ "%.2f"|format(report.price.day_low) }}</span>
        {% endif %}
      </div>
      <div class="price-delayed">Live price: FactSet/S&P · Chart data: yfinance (~15 min delayed)</div>
    </div>
    <div class="header-right">
      <div class="rating-badge rating-{{ report.rating_class }}">{{ report.rating }}</div>
      <div class="final-score">Score: {{ "%.1f"|format(report.final_score) }} / 10.0</div>
      <div class="as-of">As of {{ report.as_of_fmt }}</div>
    </div>
  </div>

  <!-- Pillar scores -->
  <div class="pillar-row">
    <div class="pillar-card">
      <div class="pillar-name">Technical</div>
      <div class="pillar-score {{ 'score-high' if report.scores.tech_score >= 7 else ('score-mid' if report.scores.tech_score >= 5 else 'score-low') }}">{{ "%.1f"|format(report.scores.tech_score) }}</div>
      <div class="pillar-weight">45% weight</div>
    </div>
    <div class="pillar-card">
      <div class="pillar-name">Fundamental</div>
      <div class="pillar-score {{ 'score-high' if report.scores.fund_score >= 7 else ('score-mid' if report.scores.fund_score >= 5 else 'score-low') }}">{{ "%.1f"|format(report.scores.fund_score) }}</div>
      <div class="pillar-weight">40% weight</div>
    </div>
    <div class="pillar-card">
      <div class="pillar-name">GEX / Options</div>
      {% if report.gex.net_gex is not none %}
      <div class="pillar-score {{ 'score-high' if report.scores.gex_score >= 7 else ('score-mid' if report.scores.gex_score >= 5 else 'score-low') }}">{{ "%.1f"|format(report.scores.gex_score) }}</div>
      {% else %}
      <div class="pillar-score score-mid">N/A</div>
      {% endif %}
      <div class="pillar-weight">15% weight</div>
    </div>
  </div>

  <!-- Chart -->
  <div class="chart-section">
    <div class="section-title">Technical Chart — Weekly</div>
    <img src="data:image/png;base64,{{ report.chart_b64 }}" alt="{{ report.ticker }} chart">
  </div>

  <!-- Technical Analysis -->
  <div class="analysis-section">
    <h2>Technical Analysis</h2>
    <div class="sig-row">
      <span class="sig-badge {{ 'sig-on' if report.technicals.sig_rsi else 'sig-off' }}">RSI {% if report.technicals.sig_rsi %}✓{% else %}✗{% endif %}</span>
      <span class="sig-badge {{ 'sig-on' if report.technicals.sig_bb else 'sig-off' }}">BB {% if report.technicals.sig_bb %}✓{% else %}✗{% endif %}</span>
      <span class="sig-badge {{ 'sig-on' if report.technicals.sig_macd else 'sig-off' }}">MACD {% if report.technicals.sig_macd %}✓{% else %}✗{% endif %}</span>
      <span class="sig-badge {{ 'sig-on' if report.technicals.sig_chandelier else 'sig-off' }}">Chandelier {% if report.technicals.sig_chandelier %}✓{% else %}✗{% endif %}</span>
      <span class="sig-badge {{ 'sig-on' if report.technicals.sig_ttm else 'sig-off' }}">TTM {% if report.technicals.sig_ttm %}✓{% else %}✗{% endif %}</span>
      {% if report.technicals.squeeze_fired %}<span class="sig-badge sig-on">🔥 Squeeze Fired</span>{% endif %}
    </div>
    <div class="trade-box">
      <div class="trade-item"><div class="trade-label">Entry</div><div class="trade-val entry-val">${{ "%.2f"|format(report.technicals.entry) }}</div></div>
      <div class="trade-item"><div class="trade-label">Stop Loss</div><div class="trade-val stop-val">${{ "%.2f"|format(report.technicals.stop) }}</div></div>
      <div class="trade-item"><div class="trade-label">Target</div><div class="trade-val target-val">${{ "%.2f"|format(report.technicals.target) }}</div></div>
      <div class="trade-item"><div class="trade-label">R:R Ratio</div><div class="trade-val rr-val">{{ report.technicals.rr_ratio }}:1</div></div>
    </div>
    {% if report.technicals.pattern %}
    <div class="metrics-grid">
      <div class="metric"><div class="metric-label">Chart Pattern</div><div class="metric-value">{{ report.technicals.pattern }}</div><div class="metric-sub">Confidence: {{ "%.0f"|format(report.technicals.pattern_confidence * 100) }}% · {% if report.technicals.pattern_confirmed %}Confirmed{% else %}Forming{% endif %}</div></div>
      <div class="metric"><div class="metric-label">RSI (14)</div><div class="metric-value">{{ "%.1f"|format(report.technicals.rsi) }}</div></div>
      <div class="metric"><div class="metric-label">Direction Bias</div><div class="metric-value">{{ report.technicals.direction | upper }}</div><div class="metric-sub">Long score {{ report.technicals.score_long }}/5 · Short {{ report.technicals.score_short }}/5</div></div>
      <div class="metric"><div class="metric-label">ATR</div><div class="metric-value">${{ "%.2f"|format(report.technicals.atr) if report.technicals.atr else 'N/A' }}</div></div>
    </div>
    {% endif %}
    <div class="narrative">{{ report.narratives.technical | safe }}</div>
  </div>

  <!-- Fundamental Analysis -->
  <div class="analysis-section">
    <h2>Fundamental Analysis</h2>
    <div class="metrics-grid">
      <div class="metric"><div class="metric-label">Market Cap</div><div class="metric-value">{{ report.fundamentals.market_cap_fmt }}</div></div>
      <div class="metric"><div class="metric-label">P/E (TTM / Fwd)</div><div class="metric-value">{{ "%.1f"|format(report.fundamentals.pe_ttm) if report.fundamentals.pe_ttm else 'N/A' }}x / {{ "%.1f"|format(report.fundamentals.pe_forward) if report.fundamentals.pe_forward else 'N/A' }}x</div></div>
      <div class="metric"><div class="metric-label">EV/EBITDA</div><div class="metric-value">{{ "%.1f"|format(report.fundamentals.ev_ebitda) if report.fundamentals.ev_ebitda else 'N/A' }}x</div></div>
      <div class="metric"><div class="metric-label">P/S (TTM)</div><div class="metric-value">{{ "%.1f"|format(report.fundamentals.ps_ttm) if report.fundamentals.ps_ttm else 'N/A' }}x</div></div>
      <div class="metric"><div class="metric-label">EPS Growth YoY</div><div class="metric-value">{{ "+%.0f"|format(report.fundamentals.eps_growth_yoy * 100) if report.fundamentals.eps_growth_yoy else 'N/A' }}%</div></div>
      <div class="metric"><div class="metric-label">Revenue Growth YoY</div><div class="metric-value">{{ "+%.0f"|format(report.fundamentals.revenue_growth_yoy * 100) if report.fundamentals.revenue_growth_yoy else 'N/A' }}%</div></div>
      <div class="metric"><div class="metric-label">Gross Margin</div><div class="metric-value">{{ "%.1f"|format(report.fundamentals.gross_margin * 100) if report.fundamentals.gross_margin else 'N/A' }}%</div></div>
      <div class="metric"><div class="metric-label">Net Margin</div><div class="metric-value">{{ "%.1f"|format(report.fundamentals.net_margin * 100) if report.fundamentals.net_margin else 'N/A' }}%</div></div>
      <div class="metric"><div class="metric-label">Free Cash Flow</div><div class="metric-value">{{ report.fundamentals.fcf_fmt }}</div></div>
      <div class="metric"><div class="metric-label">Debt / Equity</div><div class="metric-value">{{ "%.2f"|format(report.fundamentals.debt_to_equity / 100) if report.fundamentals.debt_to_equity else 'N/A' }}</div></div>
      <div class="metric"><div class="metric-label">Insider Ownership</div><div class="metric-value">{{ "%.1f"|format(report.fundamentals.insider_ownership_pct * 100) if report.fundamentals.insider_ownership_pct else 'N/A' }}%</div></div>
      <div class="metric"><div class="metric-label">Next Earnings</div><div class="metric-value">{{ report.fundamentals.next_earnings_date or 'N/A' }}</div><div class="metric-sub">Analyst target: ${{ "%.0f"|format(report.fundamentals.analyst_price_target) if report.fundamentals.analyst_price_target else 'N/A' }}</div></div>
    </div>
    <div class="narrative">{{ report.narratives.fundamental | safe }}</div>
  </div>

  <!-- GEX -->
  <div class="analysis-section">
    <h2>GEX / Options Positioning</h2>
    {% if report.gex.net_gex is not none %}
    <div class="metrics-grid">
      <div class="metric">
        <div class="metric-label">Net GEX</div>
        <div class="metric-value {{ 'gex-bias-long' if report.gex.dealer_bias == 'long_gamma' else 'gex-bias-short' }}">${{ report.gex.net_gex_fmt }}</div>
        <div class="metric-sub">{{ 'Long Gamma — dampening' if report.gex.dealer_bias == 'long_gamma' else 'Short Gamma — amplifying' }}</div>
      </div>
      <div class="metric"><div class="metric-label">GEX Flip Level</div><div class="metric-value">${{ "%.2f"|format(report.gex.flip_level) }}</div><div class="metric-sub">Distance: {{ report.gex.distance_to_flip_pct }}%</div></div>
      <div class="metric"><div class="metric-label">Put Wall</div><div class="metric-value">${{ "%.0f"|format(report.gex.put_wall) }}</div><div class="metric-sub">Max put OI strike</div></div>
      <div class="metric"><div class="metric-label">Call Wall</div><div class="metric-value">${{ "%.0f"|format(report.gex.call_wall) }}</div><div class="metric-sub">Max call OI strike</div></div>
    </div>
    <div class="metric-sub" style="margin-bottom:10px">Options data as of {{ report.gex.raw_scraped_at or 'N/A' }}</div>
    {% else %}
    <p class="gex-na">GEX data unavailable for {{ report.ticker }}. Scores redistributed: Technical 55%, Fundamental 45%.</p>
    {% endif %}
    <div class="narrative">{{ report.narratives.gex | safe }}</div>
  </div>

  <!-- Final Verdict -->
  <div class="verdict-section">
    <div class="verdict-header">Final Verdict</div>
    <div class="verdict-rating rating-{{ report.rating_class }}">{{ report.rating }}</div>
    <div class="verdict-target">
      Score: {{ "%.1f"|format(report.final_score) }} / 10.0 &nbsp;·&nbsp;
      12-Month Price Target: ${{ "%.0f"|format(report.price_target_12m) }} &nbsp;·&nbsp;
      Upside: {{ "+%.1f"|format(report.upside_pct) }}%
    </div>
    <div class="verdict-thesis">{{ report.narratives.thesis | safe }}</div>
  </div>

  <div class="footer">
    Generated {{ report.as_of_fmt }} &nbsp;·&nbsp;
    Price: FactSet/S&P Global &nbsp;·&nbsp;
    OHLCV: yfinance (15-min delayed) &nbsp;·&nbsp;
    GEX: yfinance options chain &nbsp;·&nbsp;
    Fundamentals: yfinance &nbsp;·&nbsp;
    For informational purposes only — not investment advice.
  </div>

</div>
</body>
</html>
```

- [ ] **Step 2: Smoke test the template renders**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -c "
from jinja2 import Template
from pathlib import Path
tmpl = Template(Path('screener/analysis_template.html').read_text())
# Minimal render to verify no syntax errors
html = tmpl.render(report={
  'ticker':'TEST','company_name':'Test Co','sector':'Tech','industry':'Software',
  'price':{'current':100.0,'day_high':102.0,'day_low':98.0},
  'rating':'BUY — High Conviction','rating_class':'buy-high','final_score':8.5,
  'as_of_fmt':'2026-05-15 09:30 ET',
  'scores':{'tech_score':8.0,'fund_score':8.5,'gex_score':8.0},
  'technicals':{'sig_rsi':True,'sig_bb':True,'sig_macd':True,'sig_chandelier':True,'sig_ttm':False,
    'squeeze_fired':False,'entry':100.0,'stop':93.0,'target':117.5,'rr_ratio':2.5,
    'pattern':'Cup & Handle','pattern_confidence':0.72,'pattern_confirmed':True,
    'rsi':58.0,'direction':'long','score_long':4,'score_short':1,'atr':3.5},
  'chart_b64':'',
  'gex':{'net_gex':1e9,'dealer_bias':'long_gamma','flip_level':95.0,
    'distance_to_flip_pct':5.3,'put_wall':90.0,'call_wall':105.0,
    'raw_scraped_at':'2026-05-15T09:30:00','net_gex_fmt':'1.0B'},
  'fundamentals':{'market_cap_fmt':'500B','pe_ttm':25.0,'pe_forward':22.0,
    'ev_ebitda':18.0,'ps_ttm':5.0,'eps_growth_yoy':0.25,'revenue_growth_yoy':0.15,
    'gross_margin':0.45,'net_margin':0.20,'fcf_fmt':'10B','debt_to_equity':50.0,
    'insider_ownership_pct':0.05,'next_earnings_date':'2026-07-20','analyst_price_target':115.0},
  'narratives':{'technical':'<p>Technical narrative here.</p>',
    'fundamental':'<p>Fundamental narrative here.</p>',
    'gex':'<p>GEX narrative here.</p>',
    'thesis':'<p>Investment thesis here.</p>'},
  'price_target_12m':117.5,'upside_pct':17.5,
})
print('Template OK, length:', len(html))
"
```

Expected: `Template OK, length: <large number>`

- [ ] **Step 3: Commit**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects
git add stock-screener/screener/analysis_template.html
git commit -m "feat: add Jinja2 HTML analysis report template"
```

---

## Task 5: Skill File

**Files:**
- Create: `financial-services/plugins/vertical-plugins/equity-research/skills/analyze/SKILL.md`

This is the Claude skill definition. When the user types `/analyze TSLA`, Claude reads this file and follows it exactly.

- [ ] **Step 1: Create the skills directory**

```bash
mkdir -p /Users/robertliu/Documents/Claude\ Code\ Projects/financial-services/plugins/vertical-plugins/equity-research/skills/analyze
```

- [ ] **Step 2: Create the skill file**

Create `financial-services/plugins/vertical-plugins/equity-research/skills/analyze/SKILL.md`:

````markdown
---
name: analyze
description: On-demand single-stock equity analysis. Produces a commercial-grade HTML report with technical analysis, Goldman/Morgan-style fundamentals, GEX options positioning, and a weighted BUY/HOLD/SELL rating. Invoked as /analyze <TICKER>.
triggers:
  - /analyze
---

# Equity Analysis Skill

Triggered by `/analyze <TICKER>`. Produces a full equity analysis report and opens it in the browser.

## Step 1 — Validate ticker

Extract the ticker from the command. If no ticker is provided or it contains invalid characters, respond with:
> "Please provide a valid ticker symbol. Example: `/analyze TSLA`"

Then stop.

## Step 2 — Run the data collector

Run the Python orchestrator from the project root:

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python analyze.py <TICKER>
```

If the script exits with an error, report the error message to the user and stop.

## Step 3 — Read analysis.json and optionally refresh live price

Read `stock-screener/analysis.json`. This contains all quantitative data.

**If FactSet or S&P Global MCP is authenticated and available:** use it to fetch the current spot price for the ticker and overwrite `analysis.json`'s `price.current` field before scoring. This gives a truly real-time header price. If the MCP is not available, the yfinance price (from `fast_info.last_price`) is used — label it "~15 min delayed" in the header instead of "Live".

## Step 4 — Score fundamentals (0–10)

Using the fundamentals data in analysis.json, score the fundamental pillar 0–10:

**Scoring rubric:**
- Start at 5.0 (neutral baseline)
- EPS growth YoY > 30%: +1.5 | 10–30%: +0.75 | < 0%: −1.5
- Revenue growth YoY > 20%: +1.0 | 5–20%: +0.5 | < 0%: −1.0
- Forward P/E below sector median (use judgment based on sector): +0.5 | above 2× median: −1.0
- Gross margin > 40%: +0.5 | < 10%: −0.5
- FCF positive and growing: +0.75 | FCF negative: −0.75
- D/E < 0.5: +0.5 | D/E > 2.0: −0.5
- Insider ownership > 10%: +0.25

Cap result between 0 and 10.

## Step 5 — Compute final score and rating

Use the weights and thresholds from the spec:

```
final_score = tech_score × 0.45 + fund_score × 0.40 + gex_score × 0.15
```

If GEX is unavailable (net_gex is null):
```
final_score = tech_score × 0.55 + fund_score × 0.45
```

Rating thresholds:
- ≥ 8.0 → BUY — High Conviction
- ≥ 6.5 → BUY — Moderate Conviction
- ≥ 4.5 → HOLD
- ≥ 3.0 → SELL — Moderate Conviction
- < 3.0 → SELL — High Conviction

rating_class mapping (for HTML CSS):
- "BUY — High Conviction" → "buy-high"
- "BUY — Moderate Conviction" → "buy-mod"
- "HOLD" → "hold"
- "SELL — Moderate Conviction" → "sell-mod"
- "SELL — High Conviction" → "sell-high"

## Step 6 — Write analyst narratives

Write the following four narrative sections. Each should be 2–4 sentences, Goldman/Morgan style: direct, data-driven, no fluff.

Format each as HTML paragraphs (use `<p>` tags).

**Technical narrative:** Reference the specific indicators that fired, the pattern detected (if any), the entry/stop/target levels, and what the weekly setup implies about near-term price action.

**Fundamental narrative:** Comment on earnings growth trajectory, valuation vs. sector norms, balance sheet strength, and any notable upcoming catalysts (next earnings date, analyst consensus).

**GEX narrative:** Explain what the dealer gamma positioning means for the stock's near-term volatility and directional tendency. Reference the flip level and put/call walls. If GEX is unavailable, write one sentence noting it.

**Investment thesis:** One paragraph synthesizing all three pillars into a clear trade rationale. State the primary risk to the thesis.

## Step 7 — Format numbers for display

Prepare display-formatted values for the template:

- `market_cap_fmt`: format as "$XXX.XB" or "$X.XXB" (billions) or "$XXX.XM" (millions)
- `fcf_fmt`: same format as market cap
- `net_gex_fmt`: format as "$X.XB" or "$XXX.XM" with sign
- `as_of_fmt`: format analysis.json `as_of` as "YYYY-MM-DD HH:MM ET"
- `price_target_12m`: technicals.target (use as 12-month implied target)
- `upside_pct`: (price_target_12m - price.current) / price.current × 100

## Step 8 — Render HTML report

Use the Jinja2 template at `stock-screener/screener/analysis_template.html`.

Run this Python snippet to render and save the report:

```python
import json
from pathlib import Path
from jinja2 import Template

data = json.loads(Path("stock-screener/analysis.json").read_text())
tmpl = Template(Path("stock-screener/screener/analysis_template.html").read_text())

report = {
    "ticker":        data["ticker"],
    "company_name":  data["company_name"],
    "sector":        data["sector"],
    "industry":      data["industry"],
    "price":         data["price"],
    "technicals":    data["technicals"],
    "gex":           data["gex"],
    "fundamentals":  data["fundamentals"],
    "chart_b64":     data["chart_b64"],
    "rating":        <computed_rating>,
    "rating_class":  <computed_rating_class>,
    "final_score":   <computed_final_score>,
    "as_of_fmt":     <formatted_as_of>,
    "scores": {
        "tech_score":  data["scores"]["tech_score"],
        "fund_score":  <computed_fund_score>,
        "gex_score":   data["scores"]["gex_score"],
    },
    "narratives": {
        "technical":   <technical_narrative_html>,
        "fundamental": <fundamental_narrative_html>,
        "gex":         <gex_narrative_html>,
        "thesis":      <thesis_html>,
    },
    "price_target_12m": <price_target_12m>,
    "upside_pct":       <upside_pct>,
}

# Add formatted display fields to fundamentals
report["fundamentals"]["market_cap_fmt"] = <market_cap_fmt>
report["fundamentals"]["fcf_fmt"] = <fcf_fmt>
report["gex"]["net_gex_fmt"] = <net_gex_fmt>

html = tmpl.render(report=report)
out = Path(f"stock-screener/{data['ticker']}_analysis.html")
out.write_text(html)
print(f"Report saved to {out}")
```

Fill in all `<computed_...>` values using the scores and narratives from Steps 4–7.

## Step 9 — Open report in browser

```bash
open stock-screener/<TICKER>_analysis.html
```

## Step 10 — Save to Obsidian

Save a summary note to:
`/Users/robertliu/Library/Mobile Documents/iCloud~md~obsidian/Documents/Rob's Valut/Trading/<TICKER>/<TICKER>-<YYYY-MM-DD>.md`

Create the directory if it does not exist.

Note format:

```markdown
---
tags: [trading, equity-analysis, <ticker>]
date: <YYYY-MM-DD>
rating: <rating>
conviction: <final_score>/10
---

# <TICKER> — <company_name> | <rating>

**Date:** <YYYY-MM-DD HH:MM ET>
**Price:** $<current> · **Score:** <final_score>/10

## Scores
| Pillar | Score | Weight |
|---|---|---|
| Technical | <tech_score>/10 | 45% |
| Fundamental | <fund_score>/10 | 40% |
| GEX / Options | <gex_score>/10 | 15% |

## Trade Setup
- **Direction:** <direction>
- **Entry:** $<entry> · **Stop:** $<stop> · **Target:** $<target>
- **R:R:** <rr_ratio>:1
- **Pattern:** <pattern or "None detected">

## Key Fundamentals
- EPS Growth YoY: <eps_growth_yoy>%
- Revenue Growth YoY: <revenue_growth_yoy>%
- P/E Fwd: <pe_forward>x · EV/EBITDA: <ev_ebitda>x
- FCF: <fcf_fmt> · D/E: <debt_to_equity>
- Next Earnings: <next_earnings_date>

## GEX
- Net GEX: <net_gex_fmt> (<dealer_bias>)
- Flip Level: $<flip_level> · Distance: <distance_to_flip_pct>%
- Put Wall: $<put_wall> · Call Wall: $<call_wall>

## Investment Thesis
<thesis — plain text version, no HTML>

---
*Report: [[<TICKER>_analysis.html]]*
*Source: yfinance · FactSet/S&P Global · yfinance options chain*
```

## Step 11 — Confirm to user

Reply with a brief summary:

```
**<TICKER> Analysis Complete**

Rating: <rating> (Score: <final_score>/10)

| Pillar | Score |
|---|---|
| Technical | <tech_score>/10 |
| Fundamental | <fund_score>/10 |
| GEX | <gex_score>/10 |

Entry: $<entry> · Stop: $<stop> · Target: $<target> · R:R: <rr_ratio>:1

Report opened in browser. Saved to Obsidian.
```
````

- [ ] **Step 3: Verify the skill file is discoverable**

```bash
ls /Users/robertliu/Documents/Claude\ Code\ Projects/financial-services/plugins/vertical-plugins/equity-research/skills/analyze/
```

Expected: `SKILL.md`

- [ ] **Step 4: Commit**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects
git add financial-services/plugins/vertical-plugins/equity-research/skills/analyze/SKILL.md
git commit -m "feat: add /analyze equity analysis skill definition"
```

---

## Task 6: End-to-End Test

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects/stock-screener
python -m pytest tests/ -v
```

Expected: All tests pass. Note any failures and fix before proceeding.

- [ ] **Step 2: Live end-to-end smoke test with AAPL**

In a Claude Code session:
```
/analyze AAPL
```

Verify:
1. Python script runs and prints progress lines
2. `analysis.json` is written with valid JSON
3. HTML report opens in the browser showing:
   - Live price in header
   - Three pillar score cards
   - Annotated weekly chart with pattern annotation box and delay label
   - Technical indicators with checkmarks
   - Trade setup (entry/stop/target)
   - Fundamental metrics table
   - GEX section (or "unavailable" notice if options data missing)
   - Final verdict with rating badge
4. Obsidian note is created at the correct vault path

- [ ] **Step 3: Test error path — invalid ticker**

```
/analyze XXXXFAKE999
```

Expected: Skill returns an error message immediately without crashing.

- [ ] **Step 4: Test GEX fallback — ETF with no options**

```
/analyze SPY
```

SPY has options so GEX should work. If you want to test the null path, temporarily patch `fetch_gex` to return a null dict and verify the report renders correctly with the fallback weighting notice.

- [ ] **Step 5: Final commit**

```bash
cd /Users/robertliu/Documents/Claude\ Code\ Projects
git add -A
git commit -m "feat: equity analysis skill — full end-to-end verified"
```
