"""Taiwan chart generator — 3-panel weekly chart.

Color convention (Taiwan = OPPOSITE of US):
- RED   #e53935 = bull / up / 漲
- GREEN #43a047 = bear / down / 跌
- BLUE  #1e90ff = entry price line
- GOLD  #ffd740 = stop or cost basis line

Returns: PNG bytes for CID embedding.
"""
from __future__ import annotations

import io
from typing import Any

import matplotlib
matplotlib.use("Agg")

# CJK font detection — must run before any plt calls
def _set_cjk_font() -> None:
    import matplotlib.font_manager as fm
    candidates = [
        "PingFang SC",        # macOS (newer)
        "Heiti SC",           # macOS
        "STHeiti",            # macOS fallback
        "Arial Unicode MS",   # macOS bundled
        "Noto Sans CJK SC",   # Linux (Simplified)
        "Noto Sans CJK TC",   # Linux (Traditional)
        "Noto Sans CJK",
        "WenQuanYi Micro Hei",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            break
    # Prevent minus sign rendering as a missing glyph box
    matplotlib.rcParams["axes.unicode_minus"] = False

_set_cjk_font()

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

BULL = "#e53935"
BEAR = "#43a047"
ENTRY = "#1e90ff"
COST = "#ffd740"
BG = "#0f1419"
FG = "#e6edf3"


def _candles(ax, df: pd.DataFrame) -> None:
    """Draw Taiwan-colored candles. Width = 4 days (weekly bars)."""
    width = 4.0
    for ts, row in df.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        color = BULL if c >= o else BEAR
        x = mdates.date2num(ts)
        ax.vlines(x, l, h, color=color, linewidth=1)
        body_low = min(o, c)
        body_h = abs(c - o) if c != o else 0.01
        ax.add_patch(Rectangle((x - width / 2, body_low), width, body_h,
                               color=color, alpha=0.95))


def build_chart(df: pd.DataFrame, symbol: str, name_zh: str,
                entry: float, stop: float, target: float,
                indicators: dict[str, Any] | None = None) -> bytes:
    """Render 3-panel chart: price+MA / RSI / Volume. Returns PNG bytes."""
    plt.rcParams.update({
        "axes.facecolor": BG, "figure.facecolor": BG,
        "savefig.facecolor": BG, "axes.edgecolor": FG,
        "axes.labelcolor": FG, "xtick.color": FG, "ytick.color": FG,
        "text.color": FG, "axes.titlecolor": FG, "grid.color": "#1f2933",
        "axes.unicode_minus": False,
    })

    fig = plt.figure(figsize=(11, 8))
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 1, 1], hspace=0.05)
    ax_p = fig.add_subplot(gs[0])
    ax_r = fig.add_subplot(gs[1], sharex=ax_p)
    ax_v = fig.add_subplot(gs[2], sharex=ax_p)

    show = df.tail(60).copy()
    _candles(ax_p, show)

    for w, col in [(20, "#7fb3ff"), (50, "#ff9f43"), (120, "#a55eea")]:
        if len(show) >= w:
            sma = show["Close"].rolling(w).mean()
            ax_p.plot(show.index, sma, color=col, linewidth=1.2, label=f"MA{w}")

    ax_p.axhline(entry, color=ENTRY, linestyle="--", linewidth=1.4,
                 label=f"進場 NT${entry:.2f}")
    ax_p.axhline(stop, color=COST, linestyle=":", linewidth=1.4,
                 label=f"停損 NT${stop:.2f}")
    ax_p.axhline(target, color=BULL, linestyle="--", linewidth=1.4,
                 label=f"目標 NT${target:.2f}")
    ax_p.set_title(f"{symbol} {name_zh} — 週線", fontsize=13, fontweight="bold")
    ax_p.legend(loc="upper left", fontsize=8, framealpha=0.3)
    ax_p.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"NT${v:.0f}"))
    ax_p.grid(True, alpha=0.25)

    # RSI panel
    from ta.momentum import RSIIndicator
    rsi = RSIIndicator(close=df["Close"], window=14).rsi().tail(60)
    ax_r.plot(rsi.index, rsi.values, color=ENTRY, linewidth=1.2)
    ax_r.axhline(70, color=BEAR, linestyle=":", linewidth=0.8)
    ax_r.axhline(30, color=BULL, linestyle=":", linewidth=0.8)
    ax_r.set_ylabel("RSI(14)", fontsize=9)
    ax_r.set_ylim(0, 100)
    ax_r.grid(True, alpha=0.25)

    # Volume panel
    vol_colors = [BULL if c >= o else BEAR for o, c in
                  zip(show["Open"], show["Close"])]
    ax_v.bar(show.index, show["Volume"], color=vol_colors, width=4.0)
    ax_v.set_ylabel("成交量", fontsize=9)
    ax_v.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M"))
    ax_v.grid(True, alpha=0.25)

    for ax in (ax_p, ax_r, ax_v):
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax_p.get_xticklabels(), visible=False)
    plt.setp(ax_r.get_xticklabels(), visible=False)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
