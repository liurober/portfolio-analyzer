"""Monthly HTML report with 6 charts + MC optimization summary.

Charts:
  1. Equity curve ($100K)
  2. Win-rate by month
  3. Avg return by month
  4. Outcome breakdown (win/loss/neutral pie)
  5. PnL distribution histogram
  6. Composite-score Pareto for the top-20 MC parameter sets
"""
from __future__ import annotations

import base64
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "out"
OPTIMAL_PARAMS_PATH = HERE / "optimal_params.json"
PICKS_LOG = HERE / "picks_log.json"

BG = "#0f1419"
FG = "#e6edf3"
BULL = "#e53935"
BEAR = "#43a047"


def _png_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                facecolor=BG)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _style():
    plt.rcParams.update({"axes.facecolor": BG, "figure.facecolor": BG,
                         "axes.edgecolor": FG, "axes.labelcolor": FG,
                         "xtick.color": FG, "ytick.color": FG, "text.color": FG,
                         "axes.titlecolor": FG, "grid.color": "#1f2933"})


def chart_equity(equity_curve: list[tuple[str, float]]) -> str:
    _style()
    fig, ax = plt.subplots(figsize=(8, 3.5))
    if equity_curve:
        dates = [pd.to_datetime(d) for d, _ in equity_curve]
        navs = [v for _, v in equity_curve]
        ax.plot(dates, navs, color=BULL, linewidth=1.8)
        ax.fill_between(dates, navs, color=BULL, alpha=0.15)
    ax.set_title("投資組合資產曲線 (NT$ equivalent)", fontsize=12)
    ax.grid(True, alpha=0.25)
    return _png_b64(fig)


def chart_winrate_by_month(closed: list[dict]) -> str:
    _style()
    fig, ax = plt.subplots(figsize=(8, 3.0))
    if closed:
        df = pd.DataFrame(closed)
        df["m"] = pd.to_datetime(df["exit_date"]).dt.to_period("M").astype(str)
        wr = df.groupby("m").apply(
            lambda g: (g["outcome"] == "win").sum() / len(g) * 100
        )
        ax.bar(wr.index, wr.values, color=BULL)
        ax.axhline(80, color=BEAR, linestyle="--", linewidth=1,
                   label="目標 80%")
        ax.set_ylabel("勝率 %"); ax.legend()
    ax.set_title("月度勝率", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    return _png_b64(fig)


def chart_avg_return_by_month(closed: list[dict]) -> str:
    _style()
    fig, ax = plt.subplots(figsize=(8, 3.0))
    if closed:
        df = pd.DataFrame(closed)
        df["m"] = pd.to_datetime(df["exit_date"]).dt.to_period("M").astype(str)
        avg = df.groupby("m")["pnl_pct"].mean()
        ax.bar(avg.index, avg.values,
               color=[BULL if v >= 0 else BEAR for v in avg.values])
        ax.axhline(25, color="#ffd740", linestyle="--", linewidth=1,
                   label="目標 25%")
        ax.set_ylabel("平均報酬 %"); ax.legend()
    ax.set_title("月度平均報酬", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    return _png_b64(fig)


def chart_outcome_pie(closed: list[dict]) -> str:
    _style()
    fig, ax = plt.subplots(figsize=(5, 5))
    if closed:
        cnt = pd.Series([p["outcome"] for p in closed]).value_counts()
        labels = {"win": "勝", "loss": "負", "neutral": "平"}
        ax.pie(cnt.values,
               labels=[labels.get(k, k) for k in cnt.index],
               colors=[BULL if k == "win" else BEAR if k == "loss"
                       else "#ffd740" for k in cnt.index],
               autopct="%1.1f%%", startangle=90)
    ax.set_title("勝負分布", fontsize=12)
    return _png_b64(fig)


def chart_pnl_hist(closed: list[dict]) -> str:
    _style()
    fig, ax = plt.subplots(figsize=(8, 3.0))
    if closed:
        pnl = [p["pnl_pct"] for p in closed if p.get("pnl_pct") is not None]
        ax.hist(pnl, bins=20, color=BULL, alpha=0.85)
        ax.axvline(0, color=FG, linewidth=1)
    ax.set_title("單筆報酬分布", fontsize=12)
    ax.set_xlabel("PnL %")
    return _png_b64(fig)


def chart_mc_pareto(top20: list[dict]) -> str:
    _style()
    fig, ax = plt.subplots(figsize=(8, 3.5))
    if top20:
        xs = [r["metrics"]["win_rate"] * 100 for r in top20]
        ys = [r["metrics"]["avg_return_pct"] for r in top20]
        cs = [r["composite"] for r in top20]
        sc = ax.scatter(xs, ys, c=cs, cmap="plasma", s=80, edgecolor=FG)
        fig.colorbar(sc, ax=ax, label="composite")
        ax.set_xlabel("勝率 %"); ax.set_ylabel("平均報酬 %")
        ax.axhline(25, color=BEAR, linestyle="--", linewidth=0.8)
        ax.axvline(80, color=BEAR, linestyle="--", linewidth=0.8)
    ax.set_title("Monte Carlo Top-20 Pareto", fontsize=12)
    ax.grid(True, alpha=0.25)
    return _png_b64(fig)


def build_report(equity_curve: list[tuple[str, float]],
                 closed: list[dict], top20: list[dict]) -> str:
    imgs = {
        "equity": chart_equity(equity_curve),
        "winrate": chart_winrate_by_month(closed),
        "avgret": chart_avg_return_by_month(closed),
        "pie": chart_outcome_pie(closed),
        "hist": chart_pnl_hist(closed),
        "mc": chart_mc_pareto(top20),
    }
    best = top20[0] if top20 else None
    now = datetime.utcnow()
    html = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>台股回測月報 — {now:%Y-%m}</title></head>
<body style="background:{BG};color:{FG};font-family:'Noto Sans TC',Arial,sans-serif;margin:0;padding:24px;">
<div style="max-width:900px;margin:0 auto;">
<h1 style="margin:0 0 4px 0;">台股回測月報 — {now:%Y年%m月}</h1>
<div style="color:#8b949e;font-size:13px;margin-bottom:18px;">
產生時間 {now:%Y-%m-%d %H:%M} UTC ｜ 已平倉 {len(closed)} 筆
</div>

<h2>1. 資產曲線</h2>
<img src="data:image/png;base64,{imgs['equity']}" style="width:100%;border-radius:8px;">

<h2>2. 月度勝率</h2>
<img src="data:image/png;base64,{imgs['winrate']}" style="width:100%;border-radius:8px;">

<h2>3. 月度平均報酬</h2>
<img src="data:image/png;base64,{imgs['avgret']}" style="width:100%;border-radius:8px;">

<h2>4. 勝負分布</h2>
<img src="data:image/png;base64,{imgs['pie']}" style="width:50%;border-radius:8px;">

<h2>5. 單筆報酬分布</h2>
<img src="data:image/png;base64,{imgs['hist']}" style="width:100%;border-radius:8px;">

<h2>6. Monte Carlo 優化結果</h2>
<img src="data:image/png;base64,{imgs['mc']}" style="width:100%;border-radius:8px;">
"""
    if best:
        html += f"""<h3>本月最佳參數</h3>
<pre style="background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:12px;color:#e6edf3;font-size:12px;overflow-x:auto;">{json.dumps(best['params'], ensure_ascii=False, indent=2)}</pre>
<div style="color:#8b949e;font-size:12px;">composite={best['composite']:.3f} ｜ win_rate={best['metrics']['win_rate']:.2%} ｜ avg_return={best['metrics']['avg_return_pct']:.1f}% ｜ trades={best['metrics']['total_trades']}</div>
"""
    html += "</div></body></html>"
    return html


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    log = json.loads(PICKS_LOG.read_text(encoding="utf-8"))
    closed = [p for p in log["picks"] if p.get("status") == "closed"]
    opt = json.loads(OPTIMAL_PARAMS_PATH.read_text(encoding="utf-8"))
    top20 = opt.get("top20", [])
    # equity curve from portfolio simulator
    from backtest.portfolio import simulate_portfolio
    sim = simulate_portfolio([{
        "ticker": p["ticker"], "entry_date": p["date"],
        "exit_date": p["exit_date"] or p["date"],
        "pnl_pct": p["pnl_pct"] or 0.0,
    } for p in closed])
    html = build_report(sim["equity_curve"], closed, top20)
    out = OUT_DIR / f"backtest_monthly_{datetime.utcnow():%Y%m}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[report] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
