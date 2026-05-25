# Taiwan Screener & Analyze Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Taiwan equity screener (`finance/taiwan-screener/`) that emails the top 3 TWSE picks weekly in Traditional Chinese, provides deep single-stock `/analyze_tw` analysis, runs a monthly backtest engine with portfolio simulation, and uses a Monte Carlo parameter optimizer to continuously find the combination of technical + fundamental triggers that maximizes win rate (target: >80%) and average return (target: 20–30%) within a 5–6 week hold period.

**Architecture:** Mirror `finance/stock-screener/` structure but fully isolated (no shared code in Phase 1). Core screener, analyze tool, and backtest engine share `taiwan-screener/screener/` infrastructure. A Monte Carlo optimizer in `backtest/optimizer.py` samples the parameter space, runs vectorized historical simulations, and writes winning parameters to `backtest/optimal_params.json` — which `main.py` loads at runtime. Every pick is tracked with per-trade return data.

**Tech Stack:** Python 3.11+, yfinance (.TW suffix), pandas, numpy, scipy, matplotlib, weasyprint (HTML→PDF), ta (technical-analysis library), smtplib (Gmail SMTP), GitHub Actions

---

## Table of Contents

1. [Project scaffold](#task-1-project-scaffold)
2. [TWSE universe](#task-2-twse-universe)
3. [Technical indicators](#task-3-technical-indicators)
4. [Chart generator](#task-4-chart-generator)
5. [Pattern detection](#task-5-pattern-detection)
6. [Support/resistance](#task-6-supportresistance)
7. [Institution correlation](#task-7-institution-correlation)
8. [Screener core](#task-8-screener-core)
9. [Email template](#task-9-email-template)
10. [Mailer](#task-10-mailer)
11. [Weekly orchestrator](#task-11-weekly-orchestrator)
12. [Analyze HTML template](#task-12-analyze-html-template)
13. [Analyze tool](#task-13-analyze-tool)
14. [Backtest engine](#task-14-backtest-engine)
15. [Live pick tracker](#task-15-live-pick-tracker)
16. [Backtest evaluator](#task-16-backtest-evaluator)
17. [Monte Carlo optimizer](#task-17-monte-carlo-optimizer)
18. [Portfolio simulator](#task-18-portfolio-simulator)
19. [Monthly backtest report](#task-19-monthly-backtest-report)
20. [GitHub Actions](#task-20-github-actions)

---

## Task 1: Project scaffold

**Files:**
- Create: `finance/taiwan-screener/CLAUDE.md`
- Create: `finance/taiwan-screener/requirements.txt`
- Create: `finance/taiwan-screener/screener/__init__.py`
- Create: `finance/taiwan-screener/backtest/__init__.py`
- Create: `finance/taiwan-screener/tests/__init__.py`
- Create: `finance/taiwan-screener/screener/recent_picks_tw.json`
- Create: `finance/taiwan-screener/backtest/picks_log.json`
- Create: `finance/taiwan-screener/backtest/backtest_results.json`
- Create: `finance/taiwan-screener/backtest/optimal_params.json`
- Create: `finance/taiwan-screener/.gitignore`

**Steps:**

- [ ] Create directory tree:

```bash
mkdir -p "finance/taiwan-screener/screener"
mkdir -p "finance/taiwan-screener/backtest"
mkdir -p "finance/taiwan-screener/tests"
mkdir -p "finance/taiwan-screener/.github/workflows"
```

- [ ] Write `finance/taiwan-screener/CLAUDE.md` with these exact contents:

```markdown
# Taiwan Screener — Project Notes

This project is fully isolated from `finance/stock-screener/`. Do NOT import across the two.

## Conventions (Taiwan)
- Ticker format: `NNNN.TW` (TWSE), `NNNN.TWO` (TPEx) — Phase 1 is TWSE only
- 1 lot = 1,000 shares
- Currency display: `NT${value:.2f}`
- Candle colors are SWAPPED from US: RED `#e53935` = bull/up, GREEN `#43a047` = bear/down
- All user-facing strings: Traditional Chinese (繁體中文)
- All long-only trades. No short side.

## Workflow
- `main.py` runs weekly (Sun 7am PT via GitHub Actions). Loads `backtest/optimal_params.json` for live parameters.
- `analyze_tw.py <TICKER>` produces a single-stock HTML+PDF report.
- `backtest/engine.py` runs monthly (1st @ 6am PT) — re-runs walk-forward + Monte Carlo + writes new `optimal_params.json`.

## Email rules (Gmail-safe)
- HTML `<table>` layout only — no grid/flex
- Inline styles only — no `<style>` block
- Charts as CID inline attachments — no `data:` URIs
- Total payload < 102KB

## Optimizer targets
- Win rate ≥ 80%
- Avg return per trade: 20–30%
- Hold period: 5–6 weeks
```

- [ ] Write `finance/taiwan-screener/requirements.txt` with this exact content:

```
yfinance==0.2.40
pandas==2.2.2
numpy==1.26.4
scipy==1.13.1
matplotlib==3.9.0
ta==0.11.0
weasyprint==62.3
jinja2==3.1.4
beautifulsoup4==4.12.3
requests==2.32.3
python-dateutil==2.9.0
pytest==8.2.2
pytest-cov==5.0.0
tqdm==4.66.4
```

- [ ] Write `finance/taiwan-screener/screener/__init__.py`:

```python
"""Taiwan screener package — TWSE-only, long-only, Traditional Chinese output."""
__version__ = "0.1.0"
```

- [ ] Write `finance/taiwan-screener/backtest/__init__.py`:

```python
"""Taiwan backtest + Monte Carlo optimizer package."""
__version__ = "0.1.0"
```

- [ ] Write `finance/taiwan-screener/tests/__init__.py`:

```python
# pytest discovery root for taiwan-screener
```

- [ ] Write `finance/taiwan-screener/screener/recent_picks_tw.json`:

```json
{"picks": []}
```

- [ ] Write `finance/taiwan-screener/backtest/picks_log.json`:

```json
{"version": 1, "picks": []}
```

- [ ] Write `finance/taiwan-screener/backtest/backtest_results.json`:

```json
{"runs": []}
```

- [ ] Write `finance/taiwan-screener/backtest/optimal_params.json` (seed with safe defaults so the first weekly run works even before the optimizer has ever fired):

```json
{
  "generated": "2026-05-25T00:00:00",
  "target": {"win_rate": 0.80, "avg_return_pct": 25, "hold_weeks": "5-6"},
  "best": {
    "min_score": 6,
    "rsi_low": 30,
    "rsi_high": 75,
    "chandelier_mult": 3.0,
    "chandelier_period": 22,
    "target_mult": 2.5,
    "hold_weeks": 5,
    "min_price": 10,
    "max_price": 100,
    "min_vol_k": 500,
    "bb_period": 20,
    "ma_fast": 20,
    "ma_slow": 120,
    "adx_threshold": 20,
    "min_rr": 2.0,
    "require_macd": true,
    "require_ttm": false,
    "require_adx": true,
    "require_ma_stack": true
  },
  "top20": []
}
```

- [ ] Write `finance/taiwan-screener/.gitignore`:

```
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
*.log
*.pdf
out/
.env
credentials.json
token.json
```

- [ ] Verify install:

```bash
cd "finance/taiwan-screener"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "import yfinance, pandas, numpy, scipy, matplotlib, ta, weasyprint, jinja2; print('OK')"
```

Expected output: `OK`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 1: taiwan-screener scaffold (CLAUDE.md, requirements, json stubs)"
```

---

## Task 2: TWSE universe

**Files:**
- Create: `finance/taiwan-screener/screener/universe_tw.py`
- Create: `finance/taiwan-screener/screener/tickers_tw.json`
- Create: `finance/taiwan-screener/tests/test_universe_tw.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/tickers_tw.json` with 20 seed tickers (the full ~1,045 list is refreshed via the CLI in this task):

```json
{
  "as_of": "2026-05-25",
  "exchange": "TWSE",
  "count": 20,
  "tickers": [
    {"symbol": "2330.TW", "name_zh": "台積電",       "name_en": "TSMC",                       "sector": "半導體"},
    {"symbol": "2317.TW", "name_zh": "鴻海",         "name_en": "Hon Hai Precision Industry", "sector": "電子"},
    {"symbol": "2454.TW", "name_zh": "聯發科",       "name_en": "MediaTek",                   "sector": "半導體"},
    {"symbol": "2308.TW", "name_zh": "台達電",       "name_en": "Delta Electronics",          "sector": "電子"},
    {"symbol": "2382.TW", "name_zh": "廣達",         "name_en": "Quanta Computer",            "sector": "電腦"},
    {"symbol": "2881.TW", "name_zh": "富邦金",       "name_en": "Fubon Financial",            "sector": "金融"},
    {"symbol": "2882.TW", "name_zh": "國泰金",       "name_en": "Cathay Financial",           "sector": "金融"},
    {"symbol": "2884.TW", "name_zh": "玉山金",       "name_en": "E.Sun Financial",            "sector": "金融"},
    {"symbol": "2885.TW", "name_zh": "元大金",       "name_en": "Yuanta Financial",           "sector": "金融"},
    {"symbol": "2886.TW", "name_zh": "兆豐金",       "name_en": "Mega Financial",             "sector": "金融"},
    {"symbol": "2887.TW", "name_zh": "台新金",       "name_en": "Taishin Financial",          "sector": "金融"},
    {"symbol": "2891.TW", "name_zh": "中信金",       "name_en": "CTBC Financial",             "sector": "金融"},
    {"symbol": "3711.TW", "name_zh": "日月光投控",   "name_en": "ASE Technology",             "sector": "半導體"},
    {"symbol": "2303.TW", "name_zh": "聯電",         "name_en": "UMC",                        "sector": "半導體"},
    {"symbol": "3034.TW", "name_zh": "聯詠",         "name_en": "Novatek",                    "sector": "半導體"},
    {"symbol": "2412.TW", "name_zh": "中華電",       "name_en": "Chunghwa Telecom",           "sector": "電信"},
    {"symbol": "1303.TW", "name_zh": "南亞",         "name_en": "Nan Ya Plastics",            "sector": "塑膠"},
    {"symbol": "1301.TW", "name_zh": "台塑",         "name_en": "Formosa Plastics",           "sector": "塑膠"},
    {"symbol": "2002.TW", "name_zh": "中鋼",         "name_en": "China Steel",                "sector": "鋼鐵"},
    {"symbol": "2603.TW", "name_zh": "長榮",         "name_en": "Evergreen Marine",           "sector": "航運"}
  ]
}
```

- [ ] Write `finance/taiwan-screener/screener/universe_tw.py`:

```python
"""TWSE universe loader and refresher.

Phase 1: ships with 20 seed tickers in tickers_tw.json. The `refresh` CLI
pulls the full TWSE listed-companies feed from TWSE OpenAPI and rewrites
tickers_tw.json with ~1,045 entries.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

import requests

HERE = Path(__file__).resolve().parent
TICKERS_PATH = HERE / "tickers_tw.json"

# TWSE OpenAPI — daily listed company list
TWSE_LIST_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"


def load_universe() -> list[dict]:
    """Return the list of ticker dicts from tickers_tw.json."""
    data = json.loads(TICKERS_PATH.read_text(encoding="utf-8"))
    return data["tickers"]


def load_symbols() -> list[str]:
    """Return only the .TW symbol strings."""
    return [t["symbol"] for t in load_universe()]


def _fetch_twse_list() -> list[dict]:
    resp = requests.get(TWSE_LIST_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _normalize(row: dict) -> dict | None:
    code = (row.get("公司代號") or "").strip()
    name_zh = (row.get("公司簡稱") or row.get("公司名稱") or "").strip()
    sector = (row.get("產業別") or "其他").strip()
    if not code or not code.isdigit():
        return None
    return {
        "symbol": f"{code}.TW",
        "name_zh": name_zh,
        "name_en": "",
        "sector": sector,
    }


def refresh_universe(verbose: bool = True) -> int:
    """Refresh tickers_tw.json from TWSE OpenAPI. Returns count written."""
    rows = _fetch_twse_list()
    if verbose:
        print(f"[refresh] TWSE returned {len(rows)} rows")
    tickers: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        norm = _normalize(row)
        if norm is None or norm["symbol"] in seen:
            continue
        seen.add(norm["symbol"])
        tickers.append(norm)
    tickers.sort(key=lambda t: t["symbol"])
    payload = {
        "as_of": date.today().isoformat(),
        "exchange": "TWSE",
        "count": len(tickers),
        "tickers": tickers,
    }
    TICKERS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if verbose:
        print(f"[refresh] wrote {len(tickers)} tickers to {TICKERS_PATH}")
    return len(tickers)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TWSE universe loader/refresher")
    parser.add_argument("--refresh", action="store_true",
                        help="Fetch full TWSE listed company list and overwrite tickers_tw.json")
    parser.add_argument("--show", action="store_true",
                        help="Print the current universe count and first 10 symbols")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.refresh:
        count = refresh_universe()
        print(f"Refreshed {count} TWSE tickers.")
    if args.show or not args.refresh:
        symbols = load_symbols()
        print(f"Universe size: {len(symbols)}")
        for s in symbols[:10]:
            print(f"  {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Write `finance/taiwan-screener/tests/test_universe_tw.py`:

```python
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
```

- [ ] Write `finance/taiwan-screener/tests/finance_tw_path.py` (sys.path bootstrap helper used across the whole test suite):

```python
"""Inserts the taiwan-screener package root onto sys.path for pytest."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ensure_path() -> None:  # explicit callable for `from ... import ensure_path`
    return None
```

- [ ] Run tests:

```bash
cd "finance/taiwan-screener" && pytest tests/test_universe_tw.py -v
```

Expected output: `3 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/universe_tw.py finance/taiwan-screener/screener/tickers_tw.json finance/taiwan-screener/tests/test_universe_tw.py finance/taiwan-screener/tests/finance_tw_path.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 2: TWSE universe loader + 20 seed tickers + refresh CLI"
```

---

## Task 3: Technical indicators

**Files:**
- Create: `finance/taiwan-screener/screener/indicators_tw.py`
- Create: `finance/taiwan-screener/tests/test_indicators_tw.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/indicators_tw.py`:

```python
"""Taiwan technical indicators — long-only, parameter-configurable.

Every threshold here is overridable via the `params` dict so the Monte Carlo
optimizer can re-tune the screener without code changes.

DEFAULTS mirror backtest/optimal_params.json `best` block.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

DEFAULT_PARAMS: dict[str, Any] = {
    "rsi_low": 30,
    "rsi_high": 75,
    "bb_period": 20,
    "chandelier_period": 22,
    "chandelier_mult": 3.0,
    "ma_fast": 20,
    "ma_slow": 120,
    "adx_threshold": 20,
    "require_macd": True,
    "require_ttm": False,
    "require_adx": True,
    "require_ma_stack": True,
}


@dataclass
class Signal:
    name: str
    fired: bool
    value: float | None = None
    note: str = ""


def _merge(params: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(DEFAULT_PARAMS)
    if params:
        merged.update(params)
    return merged


def rsi_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    rsi = RSIIndicator(close=df["Close"], window=14).rsi()
    last = float(rsi.iloc[-1])
    fired = params["rsi_low"] < last < params["rsi_high"]
    return Signal("rsi", fired, last, f"RSI(14)={last:.1f}")


def bb_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    bb = BollingerBands(close=df["Close"], window=params["bb_period"], window_dev=2)
    mid = bb.bollinger_mavg()
    last_close = float(df["Close"].iloc[-1])
    last_mid = float(mid.iloc[-1])
    fired = last_close > last_mid
    return Signal("bb", fired, last_mid, f"Close>{last_mid:.2f}")


def macd_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    macd = MACD(close=df["Close"], window_slow=26, window_fast=12, window_sign=9)
    line = macd.macd()
    sig = macd.macd_signal()
    hist = macd.macd_diff()
    above = float(line.iloc[-1]) > float(sig.iloc[-1])
    rising = float(hist.iloc[-1]) > float(hist.iloc[-2])
    fired = bool(above and rising)
    return Signal("macd", fired, float(hist.iloc[-1]),
                  f"hist={float(hist.iloc[-1]):.3f}")


def chandelier_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    period = int(params["chandelier_period"])
    mult = float(params["chandelier_mult"])
    atr = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"],
                           window=period).average_true_range()
    hh = df["High"].rolling(period).max()
    ce_long = hh - mult * atr
    last_close = float(df["Close"].iloc[-1])
    last_ce = float(ce_long.iloc[-1])
    fired = last_close > last_ce
    return Signal("chandelier", fired, last_ce, f"CE={last_ce:.2f}")


def ttm_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    """TTM Squeeze: BB inside Keltner = squeeze ON. Fired when squeeze releases
    OR momentum oscillator is rising."""
    close = df["Close"]; high = df["High"]; low = df["Low"]
    bb = BollingerBands(close=close, window=20, window_dev=2)
    bb_up = bb.bollinger_hband(); bb_dn = bb.bollinger_lband()
    atr = AverageTrueRange(high=high, low=low, close=close, window=20
                           ).average_true_range()
    ema = close.ewm(span=20, adjust=False).mean()
    kc_up = ema + 1.5 * atr
    kc_dn = ema - 1.5 * atr
    squeeze_on = (bb_up < kc_up) & (bb_dn > kc_dn)
    fired_release = bool(squeeze_on.iloc[-2] and not squeeze_on.iloc[-1])
    midpoint = (high.rolling(20).max() + low.rolling(20).min()) / 2
    avg = (midpoint + close.rolling(20).mean()) / 2
    momo = (close - avg).rolling(20).apply(
        lambda x: np.polyfit(np.arange(len(x)), x, 1)[0], raw=False
    )
    momo_rising = bool(momo.iloc[-1] > momo.iloc[-2])
    fired = bool(fired_release or momo_rising)
    return Signal("ttm", fired, float(momo.iloc[-1]),
                  f"release={fired_release} rising={momo_rising}")


def ma_stack_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    fast = SMAIndicator(close=df["Close"], window=int(params["ma_fast"])
                        ).sma_indicator()
    mid = SMAIndicator(close=df["Close"], window=50).sma_indicator()
    slow = SMAIndicator(close=df["Close"], window=int(params["ma_slow"])
                        ).sma_indicator()
    c = float(df["Close"].iloc[-1])
    f = float(fast.iloc[-1]); m = float(mid.iloc[-1]); s = float(slow.iloc[-1])
    fired = (c > f) and (f > m) and (m > s)
    return Signal("ma_stack", fired, f,
                  f"C={c:.2f}>F={f:.2f}>M={m:.2f}>S={s:.2f}")


def adx_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    adx = ADXIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=14)
    last_adx = float(adx.adx().iloc[-1])
    last_pos = float(adx.adx_pos().iloc[-1])
    last_neg = float(adx.adx_neg().iloc[-1])
    fired = (last_adx >= float(params["adx_threshold"])) and (last_pos > last_neg)
    return Signal("adx", fired, last_adx,
                  f"ADX={last_adx:.1f} +DI={last_pos:.1f} -DI={last_neg:.1f}")


def volume_signal(df: pd.DataFrame, params: dict[str, Any]) -> Signal:
    """Up-week avg volume > down-week avg volume over last 10 bars."""
    sub = df.tail(10)
    up = sub[sub["Close"] >= sub["Open"]]["Volume"].mean()
    dn = sub[sub["Close"] < sub["Open"]]["Volume"].mean()
    up = 0.0 if pd.isna(up) else float(up)
    dn = 0.0 if pd.isna(dn) else float(dn)
    fired = up > dn
    return Signal("volume", fired, up, f"upV={up:.0f} dnV={dn:.0f}")


SIGNAL_FUNCS = [
    rsi_signal, bb_signal, macd_signal, chandelier_signal,
    ttm_signal, ma_stack_signal, adx_signal, volume_signal,
]


def score_signals_tw(df: pd.DataFrame, params: dict[str, Any] | None = None
                     ) -> dict[str, Any]:
    """Run all 8 signals on a weekly DataFrame. Returns score + per-signal results."""
    p = _merge(params)
    results: list[Signal] = []
    for fn in SIGNAL_FUNCS:
        try:
            results.append(fn(df, p))
        except Exception as exc:
            results.append(Signal(fn.__name__.replace("_signal", ""), False, None,
                                  f"ERR:{exc}"))

    # Required gates (long-only): respect params toggles
    name_to = {r.name: r for r in results}

    def gate(name: str, required_key: str) -> bool:
        if not p.get(required_key, False):
            return True
        return name_to[name].fired

    gates_ok = (
        gate("macd", "require_macd")
        and gate("ttm", "require_ttm")
        and gate("adx", "require_adx")
        and gate("ma_stack", "require_ma_stack")
    )

    score = sum(1 for r in results if r.fired)
    return {
        "score": int(score),
        "signals": {r.name: {"fired": r.fired, "value": r.value, "note": r.note}
                    for r in results},
        "gates_ok": bool(gates_ok),
        "params": p,
    }
```

- [ ] Write `finance/taiwan-screener/tests/test_indicators_tw.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.indicators_tw import score_signals_tw, DEFAULT_PARAMS


def _make_bull_df(n: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = np.linspace(20, 60, n)  # strong uptrend
    noise = rng.normal(0, 0.3, n)
    close = base + noise
    high = close + 0.5
    low = close - 0.5
    open_ = close - rng.normal(0, 0.1, n)
    vol = rng.integers(800_000, 2_000_000, n).astype(float)
    idx = pd.date_range("2024-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_score_returns_int_and_signals():
    df = _make_bull_df()
    out = score_signals_tw(df)
    assert isinstance(out["score"], int)
    assert 0 <= out["score"] <= 8
    assert set(out["signals"].keys()) == {
        "rsi", "bb", "macd", "chandelier", "ttm", "ma_stack", "adx", "volume"
    }


def test_bull_trend_scores_high():
    df = _make_bull_df()
    out = score_signals_tw(df)
    assert out["score"] >= 5, out


def test_params_override_rsi_band():
    df = _make_bull_df()
    out_default = score_signals_tw(df)
    out_narrow = score_signals_tw(df, {"rsi_low": 95, "rsi_high": 99})
    assert out_narrow["signals"]["rsi"]["fired"] is False
    assert out_default["signals"]["rsi"]["fired"] in (True, False)


def test_default_params_keys_present():
    for k in ["rsi_low", "rsi_high", "bb_period", "chandelier_period",
              "chandelier_mult", "ma_fast", "ma_slow", "adx_threshold"]:
        assert k in DEFAULT_PARAMS
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_indicators_tw.py -v
```

Expected output: `4 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/indicators_tw.py finance/taiwan-screener/tests/test_indicators_tw.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 3: Taiwan 8-indicator scorer (configurable params, long-only)"
```

---

## Task 4: Chart generator

**Files:**
- Create: `finance/taiwan-screener/screener/charts.py`
- Create: `finance/taiwan-screener/tests/test_charts.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/charts.py`:

```python
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
        body_low = min(o, c); body_h = abs(c - o) if c != o else 0.01
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
            ax_p.plot(show.index, sma, color=col, linewidth=1.2,
                      label=f"MA{w}")

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
```

- [ ] Write `finance/taiwan-screener/tests/test_charts.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.charts import build_chart


def _df():
    n = 80
    rng = np.random.default_rng(1)
    close = np.linspace(20, 30, n) + rng.normal(0, 0.2, n)
    high = close + 0.4; low = close - 0.4
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
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_charts.py -v
```

Expected output: `1 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/charts.py finance/taiwan-screener/tests/test_charts.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 4: Taiwan chart generator (red=bull, NT\$ labels, 3-panel)"
```

---

## Task 5: Pattern detection

**Files:**
- Create: `finance/taiwan-screener/screener/patterns.py`
- Create: `finance/taiwan-screener/tests/test_patterns_tw.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/patterns.py`:

```python
"""Three weekly chart patterns: Reverse H&S, Cup & Handle, Bull Flag.

Each detector returns a dict:
    {"pattern": "<name>", "confidence": 0.0-1.0, "neckline": float|None,
     "notes": str}
Detector returns the highest-confidence pattern found, or None.

Adapted from finance/stock-screener/screener/patterns.py — long-only only.
Pattern names in Traditional Chinese: 反向頭肩底 / 杯柄 / 旗形.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


def _troughs(close: np.ndarray, distance: int = 4) -> np.ndarray:
    idx, _ = find_peaks(-close, distance=distance)
    return idx


def _peaks(close: np.ndarray, distance: int = 4) -> np.ndarray:
    idx, _ = find_peaks(close, distance=distance)
    return idx


def detect_reverse_hns(df: pd.DataFrame) -> dict[str, Any] | None:
    closes = df["Close"].to_numpy()
    if len(closes) < 40:
        return None
    troughs = _troughs(closes[-40:], distance=3)
    if len(troughs) < 3:
        return None
    t = troughs[-3:]
    left, head, right = closes[-40:][t[0]], closes[-40:][t[1]], closes[-40:][t[2]]
    if head < left and head < right and abs(left - right) / left < 0.10:
        neckline = max(closes[-40:][t[0]:t[2]])
        depth = (left + right) / 2 - head
        conf = max(0.0, min(1.0, 1 - abs(left - right) / left * 4))
        return {"pattern": "反向頭肩底 (Reverse H&S)",
                "confidence": float(round(conf, 2)),
                "neckline": float(neckline),
                "notes": f"頭部={head:.2f} 左肩={left:.2f} 右肩={right:.2f} "
                         f"深度={depth:.2f}"}
    return None


def detect_cup_and_handle(df: pd.DataFrame) -> dict[str, Any] | None:
    closes = df["Close"].to_numpy()
    if len(closes) < 50:
        return None
    window = closes[-50:]
    left_peak_idx = int(np.argmax(window[:20]))
    right_window = window[20:]
    right_peak_idx = 20 + int(np.argmax(right_window))
    if right_peak_idx <= left_peak_idx + 10:
        return None
    cup_low = float(np.min(window[left_peak_idx:right_peak_idx]))
    left_peak = float(window[left_peak_idx]); right_peak = float(window[right_peak_idx])
    if abs(left_peak - right_peak) / left_peak > 0.08:
        return None
    handle = window[right_peak_idx:]
    if len(handle) < 4:
        return None
    handle_pullback = (right_peak - float(np.min(handle))) / right_peak
    if not (0.02 < handle_pullback < 0.18):
        return None
    depth = (left_peak - cup_low) / left_peak
    conf = max(0.0, min(1.0, 0.5 + (0.5 - abs(0.30 - depth))))
    return {"pattern": "杯柄 (Cup & Handle)",
            "confidence": float(round(conf, 2)),
            "neckline": float(max(left_peak, right_peak)),
            "notes": f"杯深={depth*100:.1f}% 柄回檔={handle_pullback*100:.1f}%"}


def detect_bull_flag(df: pd.DataFrame) -> dict[str, Any] | None:
    closes = df["Close"].to_numpy()
    if len(closes) < 20:
        return None
    pole = closes[-20:-8]
    flag = closes[-8:]
    pole_gain = (pole[-1] - pole[0]) / pole[0]
    if pole_gain < 0.10:
        return None
    flag_range = (float(np.max(flag)) - float(np.min(flag))) / float(np.mean(flag))
    if flag_range > 0.08:
        return None
    last = float(closes[-1])
    flag_top = float(np.max(flag))
    breakout_ready = last >= flag_top * 0.97
    conf = float(round(min(1.0, pole_gain * 3 + (0.05 - flag_range)
                           + (0.1 if breakout_ready else 0)), 2))
    return {"pattern": "旗形 (Bull Flag)",
            "confidence": max(0.0, conf),
            "neckline": flag_top,
            "notes": f"旗杆漲幅={pole_gain*100:.1f}% 旗區間={flag_range*100:.1f}%"}


def detect_pattern(df: pd.DataFrame) -> dict[str, Any] | None:
    candidates = []
    for fn in (detect_reverse_hns, detect_cup_and_handle, detect_bull_flag):
        try:
            r = fn(df)
            if r is not None:
                candidates.append(r)
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return candidates[0]
```

- [ ] Write `finance/taiwan-screener/tests/test_patterns_tw.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.patterns import detect_pattern, detect_bull_flag


def _bull_flag_df():
    n = 30
    pole = np.linspace(20, 28, 22)
    flag = np.array([28, 27.6, 27.8, 27.5, 27.7, 27.9, 28.0, 28.1])
    close = np.concatenate([pole, flag])[:n]
    high = close + 0.3; low = close - 0.3
    open_ = close - 0.05
    vol = np.full(n, 1_000_000.0)
    idx = pd.date_range("2025-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_bull_flag_detected():
    df = _bull_flag_df()
    r = detect_bull_flag(df)
    assert r is not None
    assert "旗形" in r["pattern"]
    assert 0 <= r["confidence"] <= 1


def test_detect_pattern_returns_one():
    df = _bull_flag_df()
    r = detect_pattern(df)
    assert r is not None
    assert "confidence" in r and "pattern" in r
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_patterns_tw.py -v
```

Expected output: `2 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/patterns.py finance/taiwan-screener/tests/test_patterns_tw.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 5: Pattern detection (反向頭肩底/杯柄/旗形)"
```

---

## Task 6: Support / Resistance

**Files:**
- Create: `finance/taiwan-screener/screener/support_resistance.py`
- Create: `finance/taiwan-screener/tests/test_sr.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/support_resistance.py`:

```python
"""Pivot-based support / resistance level detection.

Returns up to N support levels (below last close) and N resistance
levels (above last close), sorted by proximity. Used for entry/stop/target
suggestions and chart overlays.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


@dataclass
class SRLevel:
    price: float
    strength: int   # number of times the level was touched
    last_touch_bar: int


def _cluster(levels: list[float], tol: float = 0.015) -> list[tuple[float, int]]:
    if not levels:
        return []
    levels = sorted(levels)
    clusters: list[list[float]] = [[levels[0]]]
    for x in levels[1:]:
        if abs(x - clusters[-1][-1]) / clusters[-1][-1] < tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [(float(np.mean(c)), len(c)) for c in clusters]


def find_levels(df: pd.DataFrame, lookback: int = 80, n: int = 3
                ) -> dict[str, list[SRLevel]]:
    sub = df.tail(lookback).copy().reset_index(drop=True)
    highs = sub["High"].to_numpy()
    lows = sub["Low"].to_numpy()

    peak_idx, _ = find_peaks(highs, distance=3)
    trough_idx, _ = find_peaks(-lows, distance=3)

    peak_levels = [float(highs[i]) for i in peak_idx]
    trough_levels = [float(lows[i]) for i in trough_idx]

    resistance_clusters = _cluster(peak_levels)
    support_clusters = _cluster(trough_levels)

    last_close = float(sub["Close"].iloc[-1])

    resistances = sorted(
        [SRLevel(p, s, int(peak_idx[-1]) if len(peak_idx) else 0)
         for p, s in resistance_clusters if p > last_close],
        key=lambda x: x.price,
    )[:n]
    supports = sorted(
        [SRLevel(p, s, int(trough_idx[-1]) if len(trough_idx) else 0)
         for p, s in support_clusters if p < last_close],
        key=lambda x: x.price, reverse=True,
    )[:n]
    return {"support": supports, "resistance": resistances}


def suggest_trade_levels(df: pd.DataFrame, target_mult: float = 2.5,
                         min_rr: float = 2.0
                         ) -> dict[str, float | None]:
    """Pick entry = last close, stop = nearest support, target = entry + R*target_mult.

    target_mult applies to (entry - stop) distance.
    Returns {"entry","stop","target","rr"} or values=None when no valid setup.
    """
    levels = find_levels(df)
    last_close = float(df["Close"].iloc[-1])
    if not levels["support"]:
        return {"entry": None, "stop": None, "target": None, "rr": None}
    stop = levels["support"][0].price
    risk = last_close - stop
    if risk <= 0:
        return {"entry": None, "stop": None, "target": None, "rr": None}
    target = last_close + target_mult * risk
    rr = (target - last_close) / risk
    if rr < min_rr:
        return {"entry": last_close, "stop": stop, "target": target, "rr": float(rr)}
    return {"entry": last_close, "stop": stop, "target": target, "rr": float(rr)}
```

- [ ] Write `finance/taiwan-screener/tests/test_sr.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.support_resistance import find_levels, suggest_trade_levels


def _df():
    n = 100
    rng = np.random.default_rng(7)
    close = 25 + 5 * np.sin(np.linspace(0, 6, n)) + rng.normal(0, 0.2, n)
    high = close + 0.5; low = close - 0.5; open_ = close
    vol = np.full(n, 1_000_000.0)
    idx = pd.date_range("2024-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_find_levels_returns_lists():
    out = find_levels(_df())
    assert "support" in out and "resistance" in out


def test_trade_levels_have_positive_rr_when_set():
    out = suggest_trade_levels(_df())
    if out["entry"] is not None:
        assert out["rr"] > 0
        assert out["target"] > out["entry"] > out["stop"]
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_sr.py -v
```

Expected output: `2 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/support_resistance.py finance/taiwan-screener/tests/test_sr.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 6: support/resistance + trade-level suggestion"
```

---

## Task 7: Institution correlation

**Files:**
- Create: `finance/taiwan-screener/screener/institution.py`
- Create: `finance/taiwan-screener/tests/test_institution.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/institution.py`:

```python
"""US-ETF correlation, institutional holders, and analyst consensus for TW tickers.

Scoring lookup:
- SOXX correlation > 0.85 AND has institutions  -> 9.0
- SOXX correlation 0.70 - 0.85                  -> 7.0
- SOXX correlation < 0.50                       -> 4.0
- No correlation data available                 -> 5.0
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

US_BENCH = ["QQQ", "SOXX", "SPY", "AMAT"]


@dataclass
class InstitutionReport:
    correlations: dict[str, float | None]
    holders: list[dict]
    analyst: dict
    score: float
    label_zh: str


def _label(corr: float | None) -> str:
    if corr is None:
        return "資料不足"
    if corr > 0.80:
        return "高度正相關"
    if corr > 0.60:
        return "中度正相關"
    return "低度正相關"


def _weekly_returns(ticker: str, period: str = "2y") -> pd.Series | None:
    try:
        df = yf.download(ticker, period=period, interval="1wk",
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        return df["Close"].pct_change().dropna()
    except Exception:
        return None


def correlations_for(symbol: str) -> dict[str, float | None]:
    tw_ret = _weekly_returns(symbol)
    if tw_ret is None or len(tw_ret) < 30:
        return {b: None for b in US_BENCH}
    out: dict[str, float | None] = {}
    for b in US_BENCH:
        us_ret = _weekly_returns(b)
        if us_ret is None or len(us_ret) < 30:
            out[b] = None
            continue
        joined = pd.concat([tw_ret, us_ret], axis=1, join="inner").dropna()
        if len(joined) < 30:
            out[b] = None
            continue
        out[b] = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
    return out


def holders_for(symbol: str) -> list[dict]:
    try:
        tk = yf.Ticker(symbol)
        df = tk.institutional_holders
        if df is None or df.empty:
            return []
        df = df.head(5)
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "holder": str(r.get("Holder", "")),
                "shares": int(r.get("Shares", 0) or 0),
                "pct": float(r.get("% Out", r.get("pctHeld", 0)) or 0),
            })
        return rows
    except Exception:
        return []


def analyst_for(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info or {}
        return {
            "recommendation": info.get("recommendationKey", "n/a"),
            "target_mean": info.get("targetMeanPrice"),
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "num_analysts": info.get("numberOfAnalystOpinions"),
        }
    except Exception:
        return {}


def score_institution(corrs: dict[str, float | None], holders: list[dict]
                      ) -> tuple[float, str]:
    soxx = corrs.get("SOXX")
    has_holders = bool(holders)
    if soxx is None:
        return 5.0, _label(None)
    if soxx > 0.85 and has_holders:
        return 9.0, _label(soxx)
    if 0.70 <= soxx <= 0.85:
        return 7.0, _label(soxx)
    if soxx < 0.50:
        return 4.0, _label(soxx)
    return 6.0, _label(soxx)


def report_for(symbol: str) -> InstitutionReport:
    corrs = correlations_for(symbol)
    holders = holders_for(symbol)
    analyst = analyst_for(symbol)
    score, label = score_institution(corrs, holders)
    return InstitutionReport(
        correlations=corrs, holders=holders, analyst=analyst,
        score=score, label_zh=label,
    )
```

- [ ] Write `finance/taiwan-screener/tests/test_institution.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
from screener.institution import score_institution, _label


def test_score_high_corr_with_holders():
    score, label = score_institution({"SOXX": 0.92, "QQQ": 0.88,
                                      "SPY": 0.70, "AMAT": 0.91},
                                     [{"holder": "BlackRock"}])
    assert score == 9.0
    assert label == "高度正相關"


def test_score_mid_corr():
    score, _ = score_institution({"SOXX": 0.75, "QQQ": 0.6,
                                  "SPY": 0.5, "AMAT": 0.7}, [])
    assert score == 7.0


def test_score_low_corr():
    score, _ = score_institution({"SOXX": 0.30, "QQQ": 0.2,
                                  "SPY": 0.1, "AMAT": 0.2}, [])
    assert score == 4.0


def test_no_data_score():
    score, label = score_institution({"SOXX": None}, [])
    assert score == 5.0
    assert label == "資料不足"
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_institution.py -v
```

Expected output: `4 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/institution.py finance/taiwan-screener/tests/test_institution.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 7: institution correlation + holders + analyst consensus"
```

---

## Task 8: Screener core

**Files:**
- Create: `finance/taiwan-screener/screener/screener_core.py`
- Create: `finance/taiwan-screener/tests/test_screener_core.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/screener_core.py`:

```python
"""Screener core: liquidity gate + scoring + pick selection + cooldown.

Loaded params shape mirrors backtest/optimal_params.json `best`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yfinance as yf

from screener.indicators_tw import score_signals_tw, DEFAULT_PARAMS
from screener.patterns import detect_pattern
from screener.support_resistance import suggest_trade_levels

HERE = Path(__file__).resolve().parent
RECENT_PICKS_PATH = HERE / "recent_picks_tw.json"


def apply_liquidity_filter(df: pd.DataFrame, last_close: float,
                           params: dict[str, Any]) -> bool:
    if last_close < params.get("min_price", 10):
        return False
    if last_close > params.get("max_price", 100):
        return False
    avg_vol_k = float(df["Volume"].tail(10).mean()) / 1000.0
    if avg_vol_k < params.get("min_vol_k", 500):
        return False
    return True


@dataclass
class Pick:
    symbol: str
    name_zh: str
    sector: str
    last_close: float
    score: int
    indicators_fired: list[str]
    pattern: str | None
    pattern_confidence: float | None
    entry: float
    stop: float
    target: float
    rr: float
    hold_weeks: int
    params_version: str


def _load_recent() -> dict:
    try:
        return json.loads(RECENT_PICKS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"picks": []}


def _save_recent(d: dict) -> None:
    RECENT_PICKS_PATH.write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_on_cooldown(symbol: str, weeks: int = 2) -> bool:
    data = _load_recent()
    cutoff = datetime.utcnow() - timedelta(weeks=weeks)
    for p in data.get("picks", []):
        if p["symbol"] == symbol:
            dt = datetime.fromisoformat(p["date"])
            if dt > cutoff:
                return True
    return False


def record_picks(picks: Iterable[Pick]) -> None:
    data = _load_recent()
    today = datetime.utcnow().date().isoformat()
    for p in picks:
        data["picks"].append({"symbol": p.symbol, "date": today,
                              "score": p.score})
    # prune anything older than 8 weeks
    cutoff = datetime.utcnow() - timedelta(weeks=8)
    data["picks"] = [
        x for x in data["picks"]
        if datetime.fromisoformat(x["date"]) > cutoff
    ]
    _save_recent(data)


def _fetch(symbol: str) -> pd.DataFrame | None:
    try:
        df = yf.download(symbol, period="3y", interval="1wk",
                         auto_adjust=True, progress=False)
        if df is None or df.empty or len(df) < 60:
            return None
        return df.dropna()
    except Exception:
        return None


def evaluate_ticker(symbol: str, name_zh: str, sector: str,
                    params: dict[str, Any]) -> Pick | None:
    df = _fetch(symbol)
    if df is None:
        return None
    last_close = float(df["Close"].iloc[-1])
    if not apply_liquidity_filter(df, last_close, params):
        return None
    scored = score_signals_tw(df, params)
    if not scored["gates_ok"]:
        return None
    if scored["score"] < params.get("min_score", 6):
        return None
    levels = suggest_trade_levels(df,
                                  target_mult=params.get("target_mult", 2.5),
                                  min_rr=params.get("min_rr", 2.0))
    if levels["entry"] is None or levels["rr"] is None:
        return None
    if levels["rr"] < params.get("min_rr", 2.0):
        return None
    pat = detect_pattern(df) or {}
    fired = [k for k, v in scored["signals"].items() if v["fired"]]
    return Pick(
        symbol=symbol, name_zh=name_zh, sector=sector,
        last_close=last_close, score=scored["score"],
        indicators_fired=fired,
        pattern=pat.get("pattern"),
        pattern_confidence=pat.get("confidence"),
        entry=float(levels["entry"]),
        stop=float(levels["stop"]),
        target=float(levels["target"]),
        rr=float(levels["rr"]),
        hold_weeks=int(params.get("hold_weeks", 5)),
        params_version=params.get("params_version", "default"),
    )


def select_top(picks: list[Pick], n: int = 3,
               cooldown_weeks: int = 2) -> list[Pick]:
    candidates = [p for p in picks if not _is_on_cooldown(p.symbol, cooldown_weeks)]
    candidates.sort(key=lambda p: (p.score, p.rr,
                                    p.pattern_confidence or 0), reverse=True)
    return candidates[:n]
```

- [ ] Write `finance/taiwan-screener/tests/test_screener_core.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from screener.screener_core import apply_liquidity_filter, select_top, Pick


def test_liquidity_passes():
    n = 30
    df = pd.DataFrame({"Volume": np.full(n, 1_000_000.0)},
                      index=pd.date_range("2025-01-01", periods=n, freq="W-FRI"))
    assert apply_liquidity_filter(df, 25.0,
        {"min_price": 10, "max_price": 100, "min_vol_k": 500}) is True


def test_liquidity_blocks_low_volume():
    n = 30
    df = pd.DataFrame({"Volume": np.full(n, 50_000.0)},
                      index=pd.date_range("2025-01-01", periods=n, freq="W-FRI"))
    assert apply_liquidity_filter(df, 25.0,
        {"min_price": 10, "max_price": 100, "min_vol_k": 500}) is False


def test_liquidity_blocks_out_of_band_price():
    n = 30
    df = pd.DataFrame({"Volume": np.full(n, 1_000_000.0)},
                      index=pd.date_range("2025-01-01", periods=n, freq="W-FRI"))
    assert apply_liquidity_filter(df, 250.0,
        {"min_price": 10, "max_price": 100, "min_vol_k": 500}) is False


def _pick(symbol, score, rr):
    return Pick(symbol=symbol, name_zh="X", sector="半導體", last_close=20.0,
                score=score, indicators_fired=["rsi"], pattern=None,
                pattern_confidence=None, entry=20.0, stop=18.0, target=24.0,
                rr=rr, hold_weeks=5, params_version="t")


def test_select_top_orders_by_score():
    picks = [_pick("A.TW", 5, 3.0), _pick("B.TW", 8, 2.0), _pick("C.TW", 7, 4.0)]
    top = select_top(picks, n=2, cooldown_weeks=0)
    assert top[0].symbol == "B.TW"
    assert top[1].symbol == "C.TW"
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_screener_core.py -v
```

Expected output: `4 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/screener_core.py finance/taiwan-screener/tests/test_screener_core.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 8: screener core (liquidity, scoring, cooldown, top-N)"
```

---

## Task 9: Email template

**Files:**
- Create: `finance/taiwan-screener/screener/email_template_tw.html`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/email_template_tw.html`. The full template uses table layout, inline styles, and CID image refs:

```html
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>台股週報</title>
</head>
<body style="margin:0;padding:0;background:#0f1419;color:#e6edf3;font-family:'Noto Sans TC','PingFang TC',Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0f1419;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="background:#161b22;border-radius:12px;border:1px solid #21262d;">
        <tr>
          <td style="padding:24px;">
            <h1 style="margin:0 0 4px 0;font-size:22px;color:#e6edf3;">台股週報 — 交易機會</h1>
            <div style="font-size:13px;color:#8b949e;">{{ date_zh }} ｜ 本週掃描 {{ universe_count }} 檔，篩選出 {{ pick_count }} 個高分設置</div>
          </td>
        </tr>

        {% for pick in picks %}
        <tr>
          <td style="padding:0 24px 16px 24px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0d1117;border:1px solid #30363d;border-radius:10px;">
              <tr>
                <td style="padding:18px 18px 8px 18px;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="font-size:18px;font-weight:bold;color:#e6edf3;">
                        {{ pick.symbol }} ｜ {{ pick.name_zh }}
                        <span style="font-size:12px;color:#8b949e;font-weight:normal;">（{{ pick.sector }}）</span>
                      </td>
                      <td align="right" style="font-size:14px;color:#e53935;font-weight:bold;">
                        分數 {{ pick.score }}/8
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              <tr>
                <td align="center" style="padding:8px 18px;">
                  <img src="cid:{{ pick.chart_cid }}" alt="{{ pick.symbol }} 週線圖" width="560" style="display:block;width:100%;max-width:560px;border-radius:8px;">
                </td>
              </tr>
              <tr>
                <td style="padding:8px 18px;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td width="33%" style="padding:6px 0;font-size:13px;">
                        <div style="color:#8b949e;">進場</div>
                        <div style="color:#1e90ff;font-weight:bold;font-size:15px;">NT${{ "%.2f"|format(pick.entry) }}</div>
                      </td>
                      <td width="33%" style="padding:6px 0;font-size:13px;">
                        <div style="color:#8b949e;">停損</div>
                        <div style="color:#ffd740;font-weight:bold;font-size:15px;">NT${{ "%.2f"|format(pick.stop) }}</div>
                      </td>
                      <td width="33%" style="padding:6px 0;font-size:13px;">
                        <div style="color:#8b949e;">目標</div>
                        <div style="color:#e53935;font-weight:bold;font-size:15px;">NT${{ "%.2f"|format(pick.target) }}</div>
                      </td>
                    </tr>
                    <tr>
                      <td colspan="3" style="padding:8px 0 0 0;font-size:12px;color:#8b949e;">
                        報酬風險比 R:R = <span style="color:#e6edf3;font-weight:bold;">{{ "%.2f"|format(pick.rr) }}</span>
                        ｜ 持有 {{ pick.hold_weeks }} 週
                        {% if pick.pattern %}｜ 型態：<span style="color:#e6edf3;">{{ pick.pattern }}</span>（信心 {{ "%.0f"|format(pick.pattern_confidence * 100) }}%）{% endif %}
                      </td>
                    </tr>
                    <tr>
                      <td colspan="3" style="padding:6px 0 0 0;font-size:12px;color:#8b949e;">
                        觸發指標：<span style="color:#e6edf3;">{{ pick.indicators_fired | join("、") }}</span>
                      </td>
                    </tr>
                    <tr>
                      <td colspan="3" style="padding:6px 0 0 0;font-size:12px;color:#8b949e;">
                        機構相關性：<span style="color:#e6edf3;">{{ pick.institution_label }}</span>
                        （SOXX {{ "%.2f"|format(pick.soxx_corr) }}）｜ 機構評分 {{ "%.1f"|format(pick.institution_score) }}/10
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        {% endfor %}

        <tr>
          <td style="padding:18px 24px 24px 24px;font-size:11px;color:#6e7681;border-top:1px solid #21262d;">
            參數版本 {{ params_version }} ｜ 由 Monte Carlo 優化器產生
            ｜ 本郵件僅供研究參考，不構成投資建議
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
```

- [ ] Quick size and parse check:

```python
# save as /tmp/verify_email_tpl.py and run with: python /tmp/verify_email_tpl.py
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

root = Path("finance/taiwan-screener/screener")
size = len((root / "email_template_tw.html").read_bytes())
print(f"Template raw size: {size} bytes")
assert size < 8000, "template alone is already large; investigate"

env = Environment(loader=FileSystemLoader(str(root)),
                  autoescape=select_autoescape(["html"]))
tpl = env.get_template("email_template_tw.html")
html = tpl.render(picks=[], universe_count=1045, pick_count=0,
                  date_zh="2026年5月25日", params_version="t")
assert "台股週報" in html
print("OK")
```

Expected output ends with: `OK`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/email_template_tw.html
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 9: Traditional Chinese email template (Gmail-safe, table+inline)"
```

---

## Task 10: Mailer

**Files:**
- Create: `finance/taiwan-screener/screener/mailer.py`
- Create: `finance/taiwan-screener/tests/test_mailer.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/mailer.py`:

```python
"""Gmail SMTP sender with inline CID image attachments.

Reads credentials from env:
  GMAIL_USER         - sender address
  GMAIL_APP_PASSWORD - 16-char Google app password
  EMAIL_TO           - comma-separated recipient list
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 465


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(HERE)),
        autoescape=select_autoescape(["html"]),
    )


def render_weekly_email(picks: list[dict], universe_count: int,
                        date_zh: str, params_version: str) -> tuple[str, list[tuple[str, bytes]]]:
    """Render the email HTML and return (html, [(cid, png_bytes), ...]).

    Each pick dict must include `chart_png` (bytes). This function assigns a
    fresh CID, mutates pick["chart_cid"] in place, and returns the attachments.
    """
    env = _jinja_env()
    tpl = env.get_template("email_template_tw.html")
    attachments: list[tuple[str, bytes]] = []
    for pick in picks:
        cid = make_msgid(domain="tw-screener.local")[1:-1]  # strip <>
        pick["chart_cid"] = cid
        attachments.append((cid, pick.pop("chart_png")))
    html = tpl.render(picks=picks, universe_count=universe_count,
                      date_zh=date_zh, pick_count=len(picks),
                      params_version=params_version)
    return html, attachments


def send_email(subject: str, html: str,
               attachments: Sequence[tuple[str, bytes]],
               to_addrs: Sequence[str] | None = None,
               dry_run: bool = False) -> int:
    user = os.environ.get("GMAIL_USER", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipients = list(to_addrs) if to_addrs else \
        [a.strip() for a in os.environ.get("EMAIL_TO", "").split(",") if a.strip()]

    if not recipients:
        raise RuntimeError("EMAIL_TO is empty")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user or "no-reply@local"
    msg["To"] = ", ".join(recipients)
    msg.set_content("此郵件需要支援 HTML 的郵件客戶端才能正確顯示。")
    msg.add_alternative(html, subtype="html")

    html_part = msg.get_payload()[1]
    for cid, png in attachments:
        html_part.add_related(png, maintype="image", subtype="png", cid=f"<{cid}>")

    size = len(msg.as_bytes())
    if size > 102_000:
        raise RuntimeError(f"Email payload {size} bytes exceeds 102KB Gmail cap")

    if dry_run:
        return size

    with smtplib.SMTP_SSL(GMAIL_HOST, GMAIL_PORT) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    return size
```

- [ ] Write `finance/taiwan-screener/tests/test_mailer.py`:

```python
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
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_mailer.py -v
```

Expected output: `2 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/mailer.py finance/taiwan-screener/tests/test_mailer.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 10: Gmail mailer with CID inline images and 102KB guard"
```

---

## Task 11: Weekly orchestrator

**Files:**
- Create: `finance/taiwan-screener/main.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/main.py`:

```python
"""Weekly Taiwan screener orchestrator.

Workflow:
  1. Load optimal_params.json (last MC-tuned parameter set).
  2. Iterate the TWSE universe, evaluate each ticker.
  3. Select top 3 by score, R:R, pattern confidence (with 2-week cooldown).
  4. Build chart PNG + institution overlay for each.
  5. Render email + send via Gmail SMTP.
  6. Append picks to backtest/picks_log.json (status=open).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from screener.universe_tw import load_universe
from screener.screener_core import evaluate_ticker, select_top, record_picks
from screener.charts import build_chart
from screener.institution import report_for
from screener.mailer import render_weekly_email, send_email
import yfinance as yf

OPTIMAL_PARAMS = HERE / "backtest" / "optimal_params.json"
PICKS_LOG = HERE / "backtest" / "picks_log.json"


def _zh_date(dt: datetime) -> str:
    return f"{dt.year}年{dt.month}月{dt.day}日"


def load_params() -> tuple[dict, str]:
    data = json.loads(OPTIMAL_PARAMS.read_text(encoding="utf-8"))
    params = dict(data["best"])
    params["params_version"] = data.get("generated", "default")[:10]
    return params, params["params_version"]


def append_to_picks_log(picks: list, params_version: str) -> None:
    log = json.loads(PICKS_LOG.read_text(encoding="utf-8"))
    today = datetime.utcnow().date().isoformat()
    for p in picks:
        log["picks"].append({
            "date": today,
            "ticker": p.symbol,
            "entry": p.entry,
            "stop": p.stop,
            "target": p.target,
            "score": p.score,
            "indicators_fired": p.indicators_fired,
            "pattern": p.pattern,
            "pattern_confidence": p.pattern_confidence,
            "hold_weeks": p.hold_weeks,
            "status": "open",
            "exit_price": None,
            "exit_date": None,
            "outcome": None,
            "pnl_pct": None,
            "pnl_nt": None,
            "lot_cost": round(p.entry * 1000, 2),
            "params_version": params_version,
        })
    PICKS_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2),
                         encoding="utf-8")


def main() -> int:
    params, params_version = load_params()
    universe = load_universe()
    print(f"[main] universe={len(universe)}  params_version={params_version}")

    candidates = []
    for entry in tqdm(universe, desc="掃描"):
        pk = evaluate_ticker(entry["symbol"], entry["name_zh"],
                             entry["sector"], params)
        if pk is not None:
            candidates.append(pk)

    print(f"[main] candidates={len(candidates)}")
    top = select_top(candidates, n=3, cooldown_weeks=2)
    print(f"[main] selected={len(top)}")
    if not top:
        print("[main] no qualifying picks this week")
        return 0

    picks_for_email: list[dict] = []
    for p in top:
        try:
            df = yf.download(p.symbol, period="2y", interval="1wk",
                             auto_adjust=True, progress=False).dropna()
            png = build_chart(df, p.symbol, p.name_zh,
                              p.entry, p.stop, p.target)
        except Exception:
            png = b""
        inst = report_for(p.symbol)
        picks_for_email.append({
            "symbol": p.symbol, "name_zh": p.name_zh, "sector": p.sector,
            "score": p.score, "indicators_fired": p.indicators_fired,
            "pattern": p.pattern or "", "pattern_confidence": p.pattern_confidence or 0,
            "entry": p.entry, "stop": p.stop, "target": p.target,
            "rr": p.rr, "hold_weeks": p.hold_weeks,
            "institution_label": inst.label_zh,
            "soxx_corr": inst.correlations.get("SOXX") or 0,
            "institution_score": inst.score,
            "chart_png": png,
        })

    today = datetime.utcnow()
    html, atts = render_weekly_email(
        picks_for_email, universe_count=len(universe),
        date_zh=_zh_date(today), params_version=params_version)
    subject = f"台股週報 — 交易機會 — {_zh_date(today)}"
    size = send_email(subject, html, atts)
    print(f"[main] email sent: {size} bytes")

    record_picks(top)
    append_to_picks_log(top, params_version)
    print(f"[main] logged {len(top)} picks to picks_log.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Sanity-import (no network call):

```bash
cd "finance/taiwan-screener" && python -c "import main; print(hasattr(main, 'main'))"
```

Expected output: `True`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/main.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 11: weekly screener orchestrator (loads optimal_params.json)"
```

---

## Task 12: Analyze HTML template

**Files:**
- Create: `finance/taiwan-screener/screener/analyze_template_tw.html`

**Steps:**

- [ ] Write `finance/taiwan-screener/screener/analyze_template_tw.html`:

```html
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>{{ symbol }} {{ name_zh }} — 個股分析報告</title>
<style>
  @page { size: A4; margin: 18mm; }
  body { font-family: 'Noto Sans TC', 'PingFang TC', Arial, sans-serif;
         background:#0f1419; color:#e6edf3; margin:0; padding:0; }
  .wrap { max-width: 820px; margin: 0 auto; padding: 18px; }
  .card { background:#161b22; border:1px solid #30363d; border-radius:10px;
          padding:18px; margin-bottom:14px; }
  .h1 { font-size:22px; font-weight:700; margin:0 0 6px 0; }
  .muted { color:#8b949e; font-size:12px; }
  .grid { width:100%; }
  .grid td { padding:6px 8px; vertical-align:top; font-size:13px; }
  .pillar { font-weight:700; color:#e6edf3; font-size:14px; }
  .badge-buy   { background:#e53935; color:#fff; padding:2px 8px;
                 border-radius:999px; font-weight:700; }
  .badge-hold  { background:#ffd740; color:#000; padding:2px 8px;
                 border-radius:999px; font-weight:700; }
  .badge-avoid { background:#43a047; color:#fff; padding:2px 8px;
                 border-radius:999px; font-weight:700; }
  .price { color:#1e90ff; font-weight:700; }
  .target { color:#e53935; font-weight:700; }
  .stop { color:#ffd740; font-weight:700; }
</style>
</head>
<body>
<div class="wrap">

  <div class="card">
    <div class="h1">{{ symbol }} ｜ {{ name_zh }}</div>
    <div class="muted">產業：{{ sector }} ｜ 報告日期：{{ date_zh }} ｜ 參數版本 {{ params_version }}</div>
    <table class="grid" cellpadding="0" cellspacing="0">
      <tr>
        <td><span class="muted">最新收盤</span><br><span style="font-size:18px;font-weight:700;">NT${{ "%.2f"|format(last_close) }}</span></td>
        <td><span class="muted">總分</span><br><span style="font-size:18px;font-weight:700;">{{ "%.1f"|format(total_score) }}/10</span></td>
        <td><span class="muted">評等</span><br>
          {% if rating == "強力買進" %}<span class="badge-buy">{{ rating }}</span>
          {% elif rating == "買進" %}<span class="badge-buy">{{ rating }}</span>
          {% elif rating == "觀望" %}<span class="badge-hold">{{ rating }}</span>
          {% elif rating == "謹慎" %}<span class="badge-hold">{{ rating }}</span>
          {% else %}<span class="badge-avoid">{{ rating }}</span>{% endif %}
        </td>
      </tr>
    </table>
  </div>

  <div class="card">
    <div class="pillar">技術分析 — 權重 55% — 分數 {{ "%.1f"|format(tech_score) }}/10</div>
    <img src="{{ chart_path }}" alt="週線圖" style="display:block;width:100%;max-width:780px;border-radius:8px;margin:10px 0;">
    <table class="grid" cellpadding="0" cellspacing="0">
      <tr>
        <td><span class="muted">進場</span><br><span class="price">NT${{ "%.2f"|format(entry) }}</span></td>
        <td><span class="muted">停損</span><br><span class="stop">NT${{ "%.2f"|format(stop) }}</span></td>
        <td><span class="muted">目標</span><br><span class="target">NT${{ "%.2f"|format(target) }}</span></td>
        <td><span class="muted">R:R</span><br>{{ "%.2f"|format(rr) }}</td>
      </tr>
    </table>
    <div class="muted" style="margin-top:8px;">
      8 指標分數：{{ indicator_score }}/8 ｜ 觸發：{{ indicators_fired | join("、") }}
      {% if pattern %}<br>型態：{{ pattern }}（信心 {{ "%.0f"|format(pattern_confidence * 100) }}%）{% endif %}
    </div>
  </div>

  <div class="card">
    <div class="pillar">基本面分析 — 權重 30% — 分數 {{ "%.1f"|format(fund_score) }}/10</div>
    <table class="grid" cellpadding="0" cellspacing="0">
      <tr>
        <td><span class="muted">本益比 (Fwd)</span><br>{{ fwd_pe }}</td>
        <td><span class="muted">本益比 (TTM)</span><br>{{ ttm_pe }}</td>
        <td><span class="muted">EV / EBITDA</span><br>{{ ev_ebitda }}</td>
      </tr>
      <tr>
        <td><span class="muted">EPS 成長 (YoY)</span><br>{{ eps_growth }}</td>
        <td><span class="muted">營收成長 (YoY)</span><br>{{ rev_growth }}</td>
        <td><span class="muted">毛利率</span><br>{{ gross_margin }}</td>
      </tr>
      <tr>
        <td><span class="muted">營業利益率</span><br>{{ op_margin }}</td>
        <td><span class="muted">自由現金流</span><br>{{ fcf }}</td>
        <td><span class="muted">負債權益比</span><br>{{ de_ratio }}</td>
      </tr>
      <tr>
        <td colspan="3"><span class="muted">下次財報日</span><br>{{ next_earnings }}</td>
      </tr>
    </table>
  </div>

  <div class="card">
    <div class="pillar">機構相關性 — 權重 15% — 分數 {{ "%.1f"|format(inst_score) }}/10</div>
    <table class="grid" cellpadding="0" cellspacing="0">
      <tr><td><span class="muted">QQQ 2年週相關</span><br>{{ "%.2f"|format(corr_qqq) }}</td>
          <td><span class="muted">SOXX</span><br>{{ "%.2f"|format(corr_soxx) }}</td>
          <td><span class="muted">SPY</span><br>{{ "%.2f"|format(corr_spy) }}</td>
          <td><span class="muted">AMAT</span><br>{{ "%.2f"|format(corr_amat) }}</td></tr>
      <tr><td colspan="4"><span class="muted">相關性分類</span><br>{{ inst_label }}</td></tr>
    </table>
    <div class="muted" style="margin-top:8px;">主要機構持股：
      {% if holders %}{% for h in holders %}{{ h.holder }}（{{ "%.2f"|format(h.pct) }}%）{% if not loop.last %}、{% endif %}{% endfor %}
      {% else %}無資料{% endif %}
    </div>
    <div class="muted" style="margin-top:4px;">分析師共識：{{ analyst_recommendation }} ｜ 目標均價：{{ analyst_target_mean }} ｜ 分析師數：{{ analyst_count }}</div>
  </div>

  <div class="muted" style="text-align:center;font-size:11px;margin-top:16px;">
    本報告僅供研究參考，不構成投資建議
  </div>

</div>
</body>
</html>
```

- [ ] Render-smoke verify the template parses with Jinja:

```python
# save as /tmp/verify_analyze_tpl.py and run with: python /tmp/verify_analyze_tpl.py
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

root = Path("finance/taiwan-screener/screener")
env = Environment(loader=FileSystemLoader(str(root)),
                  autoescape=select_autoescape(["html"]))
tpl = env.get_template("analyze_template_tw.html")
html = tpl.render(
    symbol="2330.TW", name_zh="台積電", sector="半導體",
    date_zh="2026年5月25日", params_version="2026-05-01",
    last_close=600.0, total_score=8.4, rating="買進",
    tech_score=8.5, fund_score=8.2, inst_score=9.0,
    indicator_score=7, indicators_fired=["rsi","bb","macd"],
    entry=600.0, stop=540.0, target=750.0, rr=2.5,
    pattern="旗形 (Bull Flag)", pattern_confidence=0.7,
    chart_path="file:///tmp/x.png",
    fwd_pe="18.50", ttm_pe="22.10", ev_ebitda="12.30",
    eps_growth="15.0%", rev_growth="8.0%", gross_margin="55.0%",
    op_margin="40.0%", fcf="1.2T", de_ratio="20.00",
    next_earnings="2026-07-18",
    corr_qqq=0.88, corr_soxx=0.91, corr_spy=0.70, corr_amat=0.85,
    inst_label="高度正相關", holders=[{"holder":"BlackRock","pct":7.5}],
    analyst_recommendation="buy", analyst_target_mean="650.00",
    analyst_count=32,
)
assert "強力買進" not in html  # rating is 買進 in this fixture
assert "台積電" in html and "機構相關性" in html
print("template OK", len(html), "chars")
```

Expected output: `template OK <N> chars`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/screener/analyze_template_tw.html
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 12: /analyze_tw HTML template (3-pillar, Traditional Chinese)"
```

---

## Task 13: Analyze tool

**Files:**
- Create: `finance/taiwan-screener/analyze_tw.py`
- Create: `finance/taiwan-screener/tests/test_analyze_tw.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/analyze_tw.py`:

```python
"""`/analyze_tw <TICKER>` — single-stock institutional-grade report.

Pillars: 技術 55% / 基本面 30% / 機構相關性 15%

Outputs HTML and (if weasyprint available) PDF into ./out/.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yfinance as yf
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from screener.indicators_tw import score_signals_tw
from screener.patterns import detect_pattern
from screener.support_resistance import suggest_trade_levels
from screener.charts import build_chart
from screener.institution import report_for
from screener.universe_tw import load_universe

OUT_DIR = HERE / "out"
OPTIMAL = HERE / "backtest" / "optimal_params.json"


def _params() -> tuple[dict, str]:
    data = json.loads(OPTIMAL.read_text(encoding="utf-8"))
    p = dict(data["best"])
    return p, data.get("generated", "default")[:10]


def _name_for(symbol: str) -> tuple[str, str]:
    for t in load_universe():
        if t["symbol"] == symbol:
            return t["name_zh"], t["sector"]
    return symbol.replace(".TW", ""), "未分類"


def _rate(total: float) -> str:
    if total >= 9.0: return "強力買進"
    if total >= 7.5: return "買進"
    if total >= 6.0: return "觀望"
    if total >= 4.0: return "謹慎"
    return "避開"


def _fmt(v: Any, suffix: str = "", pct: bool = False) -> str:
    if v is None or v == "":
        return "n/a"
    try:
        f = float(v)
    except Exception:
        return str(v)
    if pct:
        return f"{f * 100:.1f}%"
    return f"{f:.2f}{suffix}"


def _fundamentals(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}

    score = 5.0
    # forward P/E sweet spot 8-25 -> +1.5
    fwd = info.get("forwardPE")
    if fwd and 8 < fwd < 25: score += 1.5
    eps_g = info.get("earningsQuarterlyGrowth")
    if eps_g and eps_g > 0.10: score += 1.0
    rev_g = info.get("revenueGrowth")
    if rev_g and rev_g > 0.05: score += 0.5
    gm = info.get("grossMargins")
    if gm and gm > 0.30: score += 0.5
    fcf = info.get("freeCashflow")
    if fcf and fcf > 0: score += 0.5
    de = info.get("debtToEquity")
    if de is not None and de < 100: score += 0.5
    score = max(0.0, min(10.0, score))

    next_earn = info.get("earningsTimestamp") or info.get("earningsDate")
    if isinstance(next_earn, (int, float)):
        try:
            next_earn = datetime.utcfromtimestamp(next_earn).date().isoformat()
        except Exception:
            next_earn = "n/a"
    return {
        "fwd_pe": _fmt(fwd),
        "ttm_pe": _fmt(info.get("trailingPE")),
        "ev_ebitda": _fmt(info.get("enterpriseToEbitda")),
        "eps_growth": _fmt(eps_g, pct=True),
        "rev_growth": _fmt(rev_g, pct=True),
        "gross_margin": _fmt(gm, pct=True),
        "op_margin": _fmt(info.get("operatingMargins"), pct=True),
        "fcf": _fmt(fcf),
        "de_ratio": _fmt(de),
        "next_earnings": next_earn or "n/a",
        "score": score,
    }


def analyze(symbol: str) -> dict:
    OUT_DIR.mkdir(exist_ok=True)
    params, params_version = _params()
    name_zh, sector = _name_for(symbol)

    df = yf.download(symbol, period="3y", interval="1wk",
                     auto_adjust=True, progress=False).dropna()
    if df.empty or len(df) < 60:
        raise RuntimeError(f"insufficient data for {symbol}")

    last_close = float(df["Close"].iloc[-1])
    scored = score_signals_tw(df, params)
    fired = [k for k, v in scored["signals"].items() if v["fired"]]
    levels = suggest_trade_levels(df, target_mult=params.get("target_mult", 2.5),
                                  min_rr=params.get("min_rr", 2.0))
    pat = detect_pattern(df) or {}

    # Technical score 0-10
    tech_score = (scored["score"] / 8.0) * 10.0
    if levels.get("rr") and levels["rr"] >= 2.5:
        tech_score = min(10.0, tech_score + 0.5)
    if pat.get("confidence"):
        tech_score = min(10.0, tech_score + 0.5 * pat["confidence"])

    fund = _fundamentals(symbol)
    inst = report_for(symbol)

    total = 0.55 * tech_score + 0.30 * fund["score"] + 0.15 * inst.score
    rating = _rate(total)

    png = build_chart(df, symbol, name_zh,
                      entry=levels.get("entry") or last_close,
                      stop=levels.get("stop") or last_close * 0.9,
                      target=levels.get("target") or last_close * 1.2)
    chart_file = OUT_DIR / f"{symbol.replace('.', '_')}_chart.png"
    chart_file.write_bytes(png)

    env = Environment(loader=FileSystemLoader(str(HERE / "screener")),
                      autoescape=select_autoescape(["html"]))
    tpl = env.get_template("analyze_template_tw.html")
    now = datetime.utcnow()
    ctx = {
        "symbol": symbol, "name_zh": name_zh, "sector": sector,
        "date_zh": f"{now.year}年{now.month}月{now.day}日",
        "params_version": params_version,
        "last_close": last_close,
        "total_score": total, "rating": rating,
        "tech_score": tech_score, "fund_score": fund["score"],
        "inst_score": inst.score,
        "indicator_score": scored["score"],
        "indicators_fired": fired,
        "entry": levels.get("entry") or last_close,
        "stop": levels.get("stop") or last_close * 0.9,
        "target": levels.get("target") or last_close * 1.2,
        "rr": levels.get("rr") or 0.0,
        "pattern": pat.get("pattern"),
        "pattern_confidence": pat.get("confidence") or 0.0,
        "chart_path": chart_file.as_uri(),
        "fwd_pe": fund["fwd_pe"], "ttm_pe": fund["ttm_pe"],
        "ev_ebitda": fund["ev_ebitda"],
        "eps_growth": fund["eps_growth"], "rev_growth": fund["rev_growth"],
        "gross_margin": fund["gross_margin"], "op_margin": fund["op_margin"],
        "fcf": fund["fcf"], "de_ratio": fund["de_ratio"],
        "next_earnings": fund["next_earnings"],
        "corr_qqq": inst.correlations.get("QQQ") or 0.0,
        "corr_soxx": inst.correlations.get("SOXX") or 0.0,
        "corr_spy": inst.correlations.get("SPY") or 0.0,
        "corr_amat": inst.correlations.get("AMAT") or 0.0,
        "inst_label": inst.label_zh,
        "holders": inst.holders,
        "analyst_recommendation": inst.analyst.get("recommendation", "n/a"),
        "analyst_target_mean": _fmt(inst.analyst.get("target_mean")),
        "analyst_count": inst.analyst.get("num_analysts") or "n/a",
    }
    html = tpl.render(**ctx)
    out_html = OUT_DIR / f"{symbol.replace('.', '_')}_analyze.html"
    out_html.write_text(html, encoding="utf-8")

    pdf_path: Path | None = None
    try:
        from weasyprint import HTML
        pdf_path = OUT_DIR / f"{symbol.replace('.', '_')}_analyze.pdf"
        HTML(string=html, base_url=str(HERE)).write_pdf(str(pdf_path))
    except Exception as e:
        print(f"[analyze_tw] PDF skipped: {e}")

    print(f"[analyze_tw] {symbol}: total={total:.2f} ({rating})")
    print(f"[analyze_tw] HTML -> {out_html}")
    if pdf_path:
        print(f"[analyze_tw] PDF  -> {pdf_path}")
    return ctx


def main(argv=None):
    parser = argparse.ArgumentParser(description="/analyze_tw <TICKER>")
    parser.add_argument("symbol", help="e.g. 2330.TW")
    args = parser.parse_args(argv)
    analyze(args.symbol)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Write `finance/taiwan-screener/tests/test_analyze_tw.py`:

```python
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
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_analyze_tw.py -v
```

Expected output: `2 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/analyze_tw.py finance/taiwan-screener/tests/test_analyze_tw.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 13: analyze_tw.py (3-pillar HTML+PDF report)"
```

---

## Task 14: Backtest engine

**Files:**
- Create: `finance/taiwan-screener/backtest/engine.py`
- Create: `finance/taiwan-screener/tests/test_engine.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/backtest/engine.py`:

```python
"""Walk-forward weekly backtest with no look-ahead.

For each weekly bar T from `start` to len(df)-hold_weeks:
  1. Slice df[:T+1] (information available at close of bar T).
  2. Score signals + liquidity gate.
  3. If qualifies, simulate the trade across bars [T+1 .. T+hold_weeks].
  4. Outcome:
       WIN     -> first bar after entry where High >= target
       LOSS    -> first bar after entry where Low  <= stop
       NEUTRAL -> neither hit within hold_weeks
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from screener.indicators_tw import score_signals_tw
from screener.support_resistance import suggest_trade_levels


@dataclass
class TradeResult:
    ticker: str
    entry_date: str
    entry: float
    stop: float
    target: float
    exit_date: str | None
    exit_price: float | None
    outcome: str       # "win" | "loss" | "neutral"
    pnl_pct: float
    hold_weeks_actual: int
    score: int


def _qualifies(df_so_far: pd.DataFrame, params: dict[str, Any]
               ) -> tuple[bool, dict, dict]:
    last_close = float(df_so_far["Close"].iloc[-1])
    if last_close < params.get("min_price", 10) or last_close > params.get("max_price", 100):
        return False, {}, {}
    avg_vol_k = float(df_so_far["Volume"].tail(10).mean()) / 1000.0
    if avg_vol_k < params.get("min_vol_k", 500):
        return False, {}, {}
    scored = score_signals_tw(df_so_far, params)
    if not scored["gates_ok"] or scored["score"] < params.get("min_score", 6):
        return False, scored, {}
    levels = suggest_trade_levels(df_so_far,
                                  target_mult=params.get("target_mult", 2.5),
                                  min_rr=params.get("min_rr", 2.0))
    if levels["entry"] is None or (levels["rr"] or 0) < params.get("min_rr", 2.0):
        return False, scored, levels
    return True, scored, levels


def simulate(ticker: str, df: pd.DataFrame, params: dict[str, Any],
             start: int = 60) -> list[TradeResult]:
    hold = int(params.get("hold_weeks", 5))
    results: list[TradeResult] = []
    last_exit_idx = -1
    for t in range(start, len(df) - hold):
        if t <= last_exit_idx:
            continue
        slice_ = df.iloc[: t + 1]
        ok, scored, levels = _qualifies(slice_, params)
        if not ok:
            continue
        entry = float(levels["entry"]); stop = float(levels["stop"])
        target = float(levels["target"])
        window = df.iloc[t + 1: t + 1 + hold]
        outcome = "neutral"; exit_price = None; exit_date = None
        hold_actual = hold
        for k, (ts, row) in enumerate(window.iterrows(), start=1):
            hit_stop = float(row["Low"]) <= stop
            hit_tgt = float(row["High"]) >= target
            if hit_stop and hit_tgt:
                # both hit same bar - conservative: assume stop first
                outcome = "loss"; exit_price = stop
                exit_date = str(ts.date()); hold_actual = k; break
            if hit_stop:
                outcome = "loss"; exit_price = stop
                exit_date = str(ts.date()); hold_actual = k; break
            if hit_tgt:
                outcome = "win"; exit_price = target
                exit_date = str(ts.date()); hold_actual = k; break
        if outcome == "neutral":
            exit_price = float(window["Close"].iloc[-1])
            exit_date = str(window.index[-1].date())
        pnl_pct = (exit_price - entry) / entry * 100.0
        results.append(TradeResult(
            ticker=ticker, entry_date=str(df.index[t].date()),
            entry=entry, stop=stop, target=target,
            exit_date=exit_date, exit_price=exit_price,
            outcome=outcome, pnl_pct=float(pnl_pct),
            hold_weeks_actual=hold_actual, score=int(scored["score"]),
        ))
        last_exit_idx = t + hold_actual
    return results


def summarize(trades: list[TradeResult]) -> dict[str, Any]:
    if not trades:
        return {"total_trades": 0}
    wins = sum(1 for t in trades if t.outcome == "win")
    losses = sum(1 for t in trades if t.outcome == "loss")
    neut = sum(1 for t in trades if t.outcome == "neutral")
    rets = [t.pnl_pct for t in trades]
    avg_ret = sum(rets) / len(rets)
    import statistics as st
    sd = st.pstdev(rets) if len(rets) > 1 else 0.0
    sharpe = (avg_ret / sd) if sd > 0 else 0.0  # weekly Sharpe proxy
    cum = []
    eq = 1.0
    for r in rets:
        eq *= (1 + r / 100)
        cum.append(eq)
    peak = cum[0]; max_dd = 0.0
    for x in cum:
        peak = max(peak, x)
        max_dd = max(max_dd, (peak - x) / peak * 100)
    return {
        "total_trades": len(trades),
        "wins": wins, "losses": losses, "neutral": neut,
        "win_rate": wins / len(trades),
        "avg_return_pct": avg_ret,
        "median_return_pct": st.median(rets),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
        "best": max(rets), "worst": min(rets),
    }
```

- [ ] Write `finance/taiwan-screener/tests/test_engine.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd
from dataclasses import asdict

from backtest.engine import simulate, summarize, TradeResult


def _df(n=200, drift=0.005, seed=3):
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.02, n)
    close = 20 * np.cumprod(1 + rets)
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    vol = rng.integers(700_000, 2_000_000, n).astype(float)
    idx = pd.date_range("2021-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_simulate_returns_trade_results():
    params = {"min_score": 4, "rsi_low": 25, "rsi_high": 85, "bb_period": 20,
              "chandelier_period": 22, "chandelier_mult": 3.0,
              "ma_fast": 20, "ma_slow": 120, "adx_threshold": 15,
              "target_mult": 2.0, "hold_weeks": 5,
              "min_price": 10, "max_price": 100, "min_vol_k": 500,
              "min_rr": 1.5,
              "require_macd": False, "require_ttm": False,
              "require_adx": False, "require_ma_stack": False}
    trades = simulate("TEST.TW", _df(), params)
    for t in trades:
        assert isinstance(t, TradeResult)
        assert t.outcome in ("win", "loss", "neutral")


def test_summarize_empty():
    out = summarize([])
    assert out["total_trades"] == 0


def test_summarize_basic():
    t = [TradeResult("X.TW", "2024-01-01", 20, 18, 25, "2024-02-01", 25,
                     "win", 25.0, 4, 6),
         TradeResult("X.TW", "2024-03-01", 20, 18, 25, "2024-04-01", 18,
                     "loss", -10.0, 4, 6)]
    s = summarize(t)
    assert s["total_trades"] == 2
    assert s["wins"] == 1
    assert s["win_rate"] == 0.5
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_engine.py -v
```

Expected output: `3 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/backtest/engine.py finance/taiwan-screener/tests/test_engine.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 14: walk-forward backtest engine + summary stats"
```

---

## Task 15: Live pick tracker

**Files:**
- Create: `finance/taiwan-screener/backtest/tracker.py`
- Create: `finance/taiwan-screener/tests/test_tracker.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/backtest/tracker.py`:

```python
"""Live picks log reader/writer with per-trade PnL.

Schema (one entry):
{
  "date": "YYYY-MM-DD", "ticker": "2887.TW",
  "entry": 22.50, "stop": 19.80, "target": 29.25,
  "score": 6, "indicators_fired": [...],
  "pattern": "Bull Flag", "pattern_confidence": 0.7,
  "hold_weeks": 5,
  "status": "open" | "closed",
  "exit_price": null|float, "exit_date": null|str,
  "outcome": null|"win"|"loss"|"neutral",
  "pnl_pct": null|float, "pnl_nt": null|float,
  "lot_cost": 22500.0,
  "params_version": "2026-05-01"
}
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PICKS_LOG = HERE / "picks_log.json"


def load_log() -> dict:
    if not PICKS_LOG.exists():
        return {"version": 1, "picks": []}
    return json.loads(PICKS_LOG.read_text(encoding="utf-8"))


def save_log(data: dict) -> None:
    PICKS_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")


def add_pick(pick: dict[str, Any]) -> None:
    log = load_log()
    log["picks"].append(pick)
    save_log(log)


def open_picks() -> list[dict]:
    return [p for p in load_log()["picks"] if p.get("status") == "open"]


def closed_picks() -> list[dict]:
    return [p for p in load_log()["picks"] if p.get("status") == "closed"]


def close_pick(ticker: str, entry_date: str, exit_price: float,
               exit_date: str, outcome: str) -> bool:
    log = load_log()
    for p in log["picks"]:
        if (p["ticker"] == ticker and p["date"] == entry_date
                and p.get("status") == "open"):
            p["status"] = "closed"
            p["exit_price"] = float(exit_price)
            p["exit_date"] = exit_date
            p["outcome"] = outcome
            entry = float(p["entry"])
            pnl_pct = (exit_price - entry) / entry * 100.0
            p["pnl_pct"] = float(pnl_pct)
            p["pnl_nt"] = float(p.get("lot_cost", entry * 1000)) * pnl_pct / 100.0
            save_log(log)
            return True
    return False


def expired_picks(today: datetime | None = None) -> list[dict]:
    """Open picks whose hold_weeks have elapsed."""
    today = today or datetime.utcnow()
    out = []
    for p in open_picks():
        d = datetime.fromisoformat(p["date"])
        if today >= d + timedelta(weeks=int(p.get("hold_weeks", 5))):
            out.append(p)
    return out


def stats() -> dict:
    closed = closed_picks()
    if not closed:
        return {"closed": 0, "open": len(open_picks())}
    wins = [p for p in closed if p.get("outcome") == "win"]
    losses = [p for p in closed if p.get("outcome") == "loss"]
    rets = [p["pnl_pct"] for p in closed if p.get("pnl_pct") is not None]
    avg = sum(rets) / len(rets) if rets else 0.0
    return {
        "open": len(open_picks()),
        "closed": len(closed),
        "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / len(closed),
        "avg_return_pct": avg,
    }
```

- [ ] Write `finance/taiwan-screener/tests/test_tracker.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import json
from pathlib import Path

import backtest.tracker as T


def _redirect(tmp_path, monkeypatch):
    p = tmp_path / "picks_log.json"
    p.write_text('{"version":1,"picks":[]}', encoding="utf-8")
    monkeypatch.setattr(T, "PICKS_LOG", p)
    return p


def test_add_and_close(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    T.add_pick({
        "date": "2026-05-25", "ticker": "2330.TW",
        "entry": 600.0, "stop": 540.0, "target": 750.0,
        "score": 7, "indicators_fired": ["rsi"], "pattern": None,
        "pattern_confidence": None, "hold_weeks": 5, "status": "open",
        "exit_price": None, "exit_date": None, "outcome": None,
        "pnl_pct": None, "pnl_nt": None,
        "lot_cost": 600000.0, "params_version": "t"})
    assert len(T.open_picks()) == 1
    ok = T.close_pick("2330.TW", "2026-05-25", 750.0, "2026-06-29", "win")
    assert ok is True
    closed = T.closed_picks()
    assert closed[0]["outcome"] == "win"
    assert abs(closed[0]["pnl_pct"] - 25.0) < 1e-6


def test_stats_empty(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    s = T.stats()
    assert s["closed"] == 0
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_tracker.py -v
```

Expected output: `2 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/backtest/tracker.py finance/taiwan-screener/tests/test_tracker.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 15: live pick tracker (per-trade pnl_pct, pnl_nt)"
```

---

## Task 16: Backtest evaluator

**Files:**
- Create: `finance/taiwan-screener/backtest/evaluator.py`
- Create: `finance/taiwan-screener/tests/test_evaluator.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/backtest/evaluator.py`:

```python
"""Monthly outcome checker for open picks.

For every open pick:
  * Pull daily bars from entry_date to today.
  * If High >= target on any bar     -> close as win @ target
  * Else if Low <= stop on any bar   -> close as loss @ stop
  * Else if hold_weeks elapsed       -> close as neutral @ last close
  * Else                              -> leave open
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from backtest.tracker import open_picks, close_pick


def evaluate_open_picks(today: datetime | None = None) -> dict[str, int]:
    today = today or datetime.utcnow()
    wins = losses = neutrals = unchanged = 0
    for p in open_picks():
        entry_date = datetime.fromisoformat(p["date"])
        hold_w = int(p.get("hold_weeks", 5))
        expire = entry_date + timedelta(weeks=hold_w)
        try:
            df = yf.download(p["ticker"],
                             start=entry_date.date(),
                             end=min(today, expire + timedelta(days=2)).date(),
                             interval="1d", auto_adjust=True, progress=False)
        except Exception:
            unchanged += 1
            continue
        if df is None or df.empty:
            unchanged += 1
            continue
        outcome = None; exit_price = None; exit_date = None
        for ts, row in df.iterrows():
            if float(row["High"]) >= float(p["target"]):
                outcome = "win"; exit_price = float(p["target"])
                exit_date = str(ts.date()); break
            if float(row["Low"]) <= float(p["stop"]):
                outcome = "loss"; exit_price = float(p["stop"])
                exit_date = str(ts.date()); break
        if outcome is None and today >= expire:
            outcome = "neutral"
            exit_price = float(df["Close"].iloc[-1])
            exit_date = str(df.index[-1].date())
        if outcome is None:
            unchanged += 1
            continue
        close_pick(p["ticker"], p["date"], exit_price, exit_date, outcome)
        if outcome == "win": wins += 1
        elif outcome == "loss": losses += 1
        else: neutrals += 1
    return {"wins": wins, "losses": losses, "neutrals": neutrals,
            "still_open": unchanged}


def main() -> int:
    out = evaluate_open_picks()
    print(f"[evaluator] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] Write `finance/taiwan-screener/tests/test_evaluator.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import json
import pandas as pd
from datetime import datetime

import backtest.evaluator as E
import backtest.tracker as T


def test_evaluator_uses_open_picks(tmp_path, monkeypatch):
    log_path = tmp_path / "picks_log.json"
    log_path.write_text(json.dumps({"version": 1, "picks": [{
        "date": "2026-04-01", "ticker": "2330.TW",
        "entry": 600.0, "stop": 540.0, "target": 750.0,
        "score": 7, "indicators_fired": [], "pattern": None,
        "pattern_confidence": None, "hold_weeks": 5, "status": "open",
        "exit_price": None, "exit_date": None, "outcome": None,
        "pnl_pct": None, "pnl_nt": None,
        "lot_cost": 600000.0, "params_version": "t"
    }]}), encoding="utf-8")
    monkeypatch.setattr(T, "PICKS_LOG", log_path)
    monkeypatch.setattr(E, "open_picks", T.open_picks)
    monkeypatch.setattr(E, "close_pick", T.close_pick)

    # Stub yfinance.download to return a frame where the target hits
    import yfinance
    def fake_download(*a, **k):
        idx = pd.date_range("2026-04-02", periods=5, freq="D")
        return pd.DataFrame({
            "Open": [600, 610, 620, 700, 760],
            "High": [605, 615, 630, 720, 780],
            "Low": [598, 605, 615, 690, 750],
            "Close": [604, 612, 625, 715, 770],
            "Volume": [1e6] * 5}, index=idx)
    monkeypatch.setattr(yfinance, "download", fake_download)

    result = E.evaluate_open_picks(today=datetime(2026, 5, 10))
    assert result["wins"] == 1
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_evaluator.py -v
```

Expected output: `1 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/backtest/evaluator.py finance/taiwan-screener/tests/test_evaluator.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 16: monthly outcome evaluator (win/loss/neutral)"
```

---

## Task 17: Monte Carlo optimizer

**Files:**
- Create: `finance/taiwan-screener/backtest/optimizer.py`
- Create: `finance/taiwan-screener/tests/test_optimizer.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/backtest/optimizer.py`:

```python
"""Monte Carlo parameter optimizer for the Taiwan screener.

Procedure:
  1. Sample n_samples random parameter dicts from PARAM_SPACE.
  2. For each dict, run simulate() across every ticker in data_cache.
  3. Aggregate trades and summarize to {win_rate, avg_return_pct, sharpe, max_drawdown}.
  4. Score with composite_score().
  5. Filter quality: win_rate >= 0.70 AND total_trades >= 20 AND avg_return_pct >= 15.
  6. Return top-20 by composite score and write best -> optimal_params.json.

Targets:
  - Win rate >= 80%
  - Avg return per trade 20-30%
  - Hold period 5-6 weeks
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from backtest.engine import simulate, summarize

HERE = Path(__file__).resolve().parent
OPTIMAL_PARAMS_PATH = HERE / "optimal_params.json"

# ----- PARAMETER SPACE -------------------------------------------------------
PARAM_SPACE: dict[str, list] = {
    "min_score":         [4, 5, 6, 7, 8],
    "rsi_low":           [20, 25, 30, 35],
    "rsi_high":          [70, 75, 80, 85],
    "chandelier_mult":   [2.0, 2.5, 3.0, 3.5],
    "chandelier_period": [14, 18, 22, 26],
    "target_mult":       [1.5, 2.0, 2.5, 3.0, 3.5],
    "hold_weeks":        [3, 4, 5, 6],
    "min_price":         [5, 10, 15, 20],
    "max_price":         [80, 100, 150, 200],
    "min_vol_k":         [300, 500, 750, 1000],
    "bb_period":         [20, 25, 30],
    "ma_fast":           [20, 30],
    "ma_slow":           [90, 120],
    "adx_threshold":     [15, 20, 25],
    "min_rr":            [1.5, 2.0, 2.5, 3.0],
    "require_macd":      [True, False],
    "require_ttm":       [True, False],
    "require_adx":       [True, False],
    "require_ma_stack":  [True, False],
}


# ----- COMPOSITE SCORE -------------------------------------------------------
def composite_score(metrics: dict) -> float:
    if metrics.get("total_trades", 0) < 20:
        return 0.0
    win_rate = metrics.get("win_rate", 0)
    avg_ret  = metrics.get("avg_return_pct", 0)
    sharpe   = metrics.get("sharpe", 0)
    drawdown = abs(metrics.get("max_drawdown", 100))
    return (
        0.40 * win_rate
      + 0.25 * min(avg_ret / 30, 1.0)
      + 0.20 * min(sharpe / 3.0, 1.0)
      + 0.15 * (1 - drawdown / 30)
    )


def sample_params(rng: random.Random) -> dict[str, Any]:
    p = {k: rng.choice(v) for k, v in PARAM_SPACE.items()}
    if p["rsi_high"] <= p["rsi_low"] + 20:
        p["rsi_high"] = min(85, p["rsi_low"] + 25)
    if p["max_price"] <= p["min_price"] + 30:
        p["max_price"] = p["min_price"] + 50
    return p


def _backtest_all(data_cache: dict[str, pd.DataFrame],
                  params: dict[str, Any]) -> dict[str, Any]:
    all_trades = []
    for tk, df in data_cache.items():
        try:
            all_trades.extend(simulate(tk, df, params))
        except Exception:
            continue
    return summarize(all_trades)


def run_optimizer(
    data_cache: dict[str, pd.DataFrame],
    n_samples: int = 2000,
    seed: int = 42,
) -> list[dict]:
    """Sample n_samples random param sets, backtest each on data_cache,
    return top-20 quality results sorted by composite_score.

    Quality filter: win_rate >= 0.70 AND total_trades >= 20 AND avg_return_pct >= 15
    """
    rng = random.Random(seed)
    results: list[dict] = []
    for _ in tqdm(range(n_samples), desc="MC samples"):
        params = sample_params(rng)
        metrics = _backtest_all(data_cache, params)
        if (metrics.get("total_trades", 0) < 20
                or metrics.get("win_rate", 0) < 0.70
                or metrics.get("avg_return_pct", 0) < 15):
            continue
        cs = composite_score(metrics)
        results.append({"params": params, "metrics": metrics, "composite": cs})
    results.sort(key=lambda r: r["composite"], reverse=True)
    return results[:20]


def write_optimal(top: list[dict]) -> Path:
    if not top:
        # Keep existing best — do not overwrite with empty
        existing = json.loads(OPTIMAL_PARAMS_PATH.read_text(encoding="utf-8"))
        return OPTIMAL_PARAMS_PATH
    payload = {
        "generated": datetime.utcnow().isoformat(timespec="seconds"),
        "target": {"win_rate": 0.80, "avg_return_pct": 25, "hold_weeks": "5-6"},
        "best": top[0]["params"],
        "top20": top,
    }
    OPTIMAL_PARAMS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return OPTIMAL_PARAMS_PATH


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cache", type=str, required=True,
                        help="path to a pre-built parquet directory of weekly bars")
    args = parser.parse_args(argv)
    cache_dir = Path(args.cache)
    data_cache = {}
    for f in cache_dir.glob("*.parquet"):
        data_cache[f.stem] = pd.read_parquet(f)
    print(f"[optimizer] loaded {len(data_cache)} tickers from {cache_dir}")
    top = run_optimizer(data_cache, n_samples=args.samples, seed=args.seed)
    path = write_optimal(top)
    print(f"[optimizer] wrote {path}")
    if top:
        b = top[0]
        print(f"[optimizer] best composite={b['composite']:.3f} "
              f"win_rate={b['metrics']['win_rate']:.2%} "
              f"avg_ret={b['metrics']['avg_return_pct']:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] Write `finance/taiwan-screener/tests/test_optimizer.py`:

```python
from finance_tw_path import ensure_path  # noqa: F401
import numpy as np
import pandas as pd

from backtest.optimizer import (PARAM_SPACE, composite_score, sample_params,
                                run_optimizer)
import random


def test_param_space_keys():
    expected = {"min_score", "rsi_low", "rsi_high", "chandelier_mult",
                "chandelier_period", "target_mult", "hold_weeks",
                "min_price", "max_price", "min_vol_k", "bb_period",
                "ma_fast", "ma_slow", "adx_threshold", "min_rr",
                "require_macd", "require_ttm", "require_adx",
                "require_ma_stack"}
    assert set(PARAM_SPACE.keys()) == expected


def test_composite_score_zero_when_few_trades():
    assert composite_score({"total_trades": 5, "win_rate": 0.9,
                            "avg_return_pct": 25, "sharpe": 2.0,
                            "max_drawdown": 5}) == 0.0


def test_composite_score_high_value():
    cs = composite_score({"total_trades": 50, "win_rate": 0.85,
                          "avg_return_pct": 28, "sharpe": 2.5,
                          "max_drawdown": 8})
    assert 0.7 < cs <= 1.0


def test_sample_params_keys_match_space():
    p = sample_params(random.Random(1))
    assert set(p.keys()) == set(PARAM_SPACE.keys())


def _df(n=180, seed=1):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.003, 0.02, n)
    close = 20 * np.cumprod(1 + rets)
    high = close * 1.01; low = close * 0.99
    open_ = close * (1 + rng.normal(0, 0.001, n))
    vol = rng.integers(700_000, 2_000_000, n).astype(float)
    idx = pd.date_range("2021-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def test_run_optimizer_smoke():
    cache = {f"T{i}.TW": _df(seed=i) for i in range(3)}
    top = run_optimizer(cache, n_samples=20, seed=1)
    assert isinstance(top, list)
    for r in top:
        assert r["metrics"]["win_rate"] >= 0.70
        assert r["metrics"]["total_trades"] >= 20
        assert r["metrics"]["avg_return_pct"] >= 15
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_optimizer.py -v
```

Expected output: `5 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/backtest/optimizer.py finance/taiwan-screener/tests/test_optimizer.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 17: Monte Carlo optimizer (2000 samples, composite, top20)"
```

---

## Task 18: Portfolio simulator

**Files:**
- Create: `finance/taiwan-screener/backtest/portfolio.py`
- Create: `finance/taiwan-screener/tests/test_portfolio.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/backtest/portfolio.py`:

```python
"""Portfolio simulator — $100K starting capital, $10K per pick, max 3 concurrent.

Inputs: list of TradeResult-like dicts (entry_date, exit_date, pnl_pct).
Output: equity curve (date -> nav), summary stats.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import pandas as pd


def simulate_portfolio(trades: Iterable[dict[str, Any]],
                       starting_cash: float = 100_000.0,
                       per_pick: float = 10_000.0,
                       max_concurrent: int = 3) -> dict[str, Any]:
    sorted_trades = sorted(trades, key=lambda t: t["entry_date"])
    open_book: list[dict] = []  # active positions
    cash = starting_cash
    nav_history: list[tuple[str, float]] = []
    closed_trades = []

    def _value_open(today: str) -> float:
        # MVP: assume positions revalue linearly to exit price by exit_date.
        # For NAV between entry and exit we use entry value (no MTM here).
        return sum(p["cost"] for p in open_book)

    for t in sorted_trades:
        # First, close anything that has exited on/before this trade's entry
        new_open = []
        for p in open_book:
            if p["exit_date"] <= t["entry_date"]:
                cash += p["cost"] * (1 + p["pnl_pct"] / 100.0)
                closed_trades.append(p)
            else:
                new_open.append(p)
        open_book = new_open

        if len(open_book) >= max_concurrent:
            continue   # cannot take this trade
        if cash < per_pick:
            continue
        cash -= per_pick
        open_book.append({"entry_date": t["entry_date"],
                          "exit_date": t["exit_date"] or t["entry_date"],
                          "ticker": t["ticker"],
                          "cost": per_pick,
                          "pnl_pct": float(t["pnl_pct"])})
        nav_history.append((t["entry_date"], cash + _value_open(t["entry_date"])))

    # Finally drain everything still open
    final_exit_dates = sorted(p["exit_date"] for p in open_book)
    for d in final_exit_dates:
        still = []
        for p in open_book:
            if p["exit_date"] == d:
                cash += p["cost"] * (1 + p["pnl_pct"] / 100.0)
                closed_trades.append(p)
            else:
                still.append(p)
        open_book = still
        nav_history.append((d, cash))

    final_nav = cash
    starting = starting_cash
    total_return = (final_nav - starting) / starting * 100
    return {
        "final_nav": float(final_nav),
        "total_return_pct": float(total_return),
        "trades_taken": len(closed_trades),
        "trades_skipped": len(sorted_trades) - len(closed_trades),
        "equity_curve": nav_history,
    }
```

- [ ] Write `finance/taiwan-screener/tests/test_portfolio.py`:

```python
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


def test_concurrency_cap():
    trades = [_t(f"T{i}.TW", "2024-01-05", "2024-12-01", 10.0)
              for i in range(5)]
    out = simulate_portfolio(trades, max_concurrent=3)
    assert out["trades_taken"] == 3
    assert out["trades_skipped"] == 2
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_portfolio.py -v
```

Expected output: `2 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/backtest/portfolio.py finance/taiwan-screener/tests/test_portfolio.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 18: portfolio simulator (\$100K, \$10K/pick, max 3 concurrent)"
```

---

## Task 19: Monthly backtest report

**Files:**
- Create: `finance/taiwan-screener/backtest/report.py`
- Create: `finance/taiwan-screener/tests/test_report.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/backtest/report.py`:

```python
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
```

- [ ] Write `finance/taiwan-screener/tests/test_report.py`:

```python
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
```

- [ ] Run:

```bash
cd "finance/taiwan-screener" && pytest tests/test_report.py -v
```

Expected output: `1 passed`

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/backtest/report.py finance/taiwan-screener/tests/test_report.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 19: monthly backtest HTML report (6 charts + MC summary)"
```

---

## Task 20: GitHub Actions

**Files:**
- Create: `finance/taiwan-screener/.github/workflows/weekly_screener_tw.yml`
- Create: `finance/taiwan-screener/.github/workflows/monthly_backtest_tw.yml`
- Create: `finance/taiwan-screener/run_monthly.py`

**Steps:**

- [ ] Write `finance/taiwan-screener/run_monthly.py`:

```python
"""Monthly orchestrator: evaluate open picks, rebuild data cache,
run Monte Carlo optimizer, write report."""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import yfinance as yf
from tqdm import tqdm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from screener.universe_tw import load_universe
from backtest.evaluator import evaluate_open_picks
from backtest.optimizer import run_optimizer, write_optimal
from backtest.report import main as build_report_main


def build_data_cache() -> dict[str, pd.DataFrame]:
    cache: dict[str, pd.DataFrame] = {}
    for entry in tqdm(load_universe(), desc="cache"):
        try:
            df = yf.download(entry["symbol"], period="5y", interval="1wk",
                             auto_adjust=True, progress=False)
            if df is None or df.empty or len(df) < 80:
                continue
            cache[entry["symbol"]] = df.dropna()
        except Exception:
            continue
    return cache


def main() -> int:
    print(f"[monthly] start {datetime.utcnow().isoformat()}")
    closed_stats = evaluate_open_picks()
    print(f"[monthly] evaluator: {closed_stats}")
    cache = build_data_cache()
    print(f"[monthly] cache built: {len(cache)} tickers")
    top = run_optimizer(cache, n_samples=2000, seed=42)
    write_optimal(top)
    print(f"[monthly] MC produced {len(top)} quality sets")
    build_report_main()
    print("[monthly] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Write `finance/taiwan-screener/.github/workflows/weekly_screener_tw.yml`:

```yaml
name: Taiwan Weekly Screener

on:
  schedule:
    - cron: "0 14 * * 0"   # Sunday 7am Pacific Time (UTC-7)
  workflow_dispatch:

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: finance/taiwan-screener
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install system fonts and weasyprint deps
        run: |
          sudo apt-get update
          sudo apt-get install -y fonts-noto-cjk libpango-1.0-0 libpangoft2-1.0-0

      - name: Install Python deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run weekly screener
        env:
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
        run: python main.py

      - name: Commit updated picks_log.json
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git add backtest/picks_log.json screener/recent_picks_tw.json || true
          git commit -m "weekly: update picks_log + recent_picks (auto)" || echo "no changes"
          git push || echo "push skipped"
```

- [ ] Write `finance/taiwan-screener/.github/workflows/monthly_backtest_tw.yml`:

```yaml
name: Taiwan Monthly Backtest + MC Optimizer

on:
  schedule:
    - cron: "0 14 1 * *"   # 1st of month, 7am Pacific
  workflow_dispatch:

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 360
    defaults:
      run:
        working-directory: finance/taiwan-screener
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install system fonts and weasyprint deps
        run: |
          sudo apt-get update
          sudo apt-get install -y fonts-noto-cjk libpango-1.0-0 libpangoft2-1.0-0

      - name: Install Python deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run monthly backtest + MC optimizer
        run: python run_monthly.py

      - name: Commit updated optimal_params + picks_log + report
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git add backtest/optimal_params.json backtest/picks_log.json out/ || true
          git commit -m "monthly: MC re-optimization + monthly report (auto)" || echo "no changes"
          git push || echo "push skipped"

      - name: Upload monthly report artifact
        uses: actions/upload-artifact@v4
        with:
          name: taiwan-backtest-report
          path: finance/taiwan-screener/out/backtest_monthly_*.html
```

- [ ] Validate workflow YAML locally:

```bash
cd "finance/taiwan-screener"
python -c "
import yaml
for p in ['.github/workflows/weekly_screener_tw.yml',
         '.github/workflows/monthly_backtest_tw.yml']:
    yaml.safe_load(open(p))
print('YAML OK')
"
```

Expected output: `YAML OK`

- [ ] Run the full test suite end-to-end:

```bash
cd "finance/taiwan-screener" && pytest -v
```

Expected: every test listed in tasks 2-19 passes (approx 30 tests).

- [ ] Commit:

```bash
git -C "/Users/robertliu/Documents/Claude Code Projects" add finance/taiwan-screener/.github/workflows finance/taiwan-screener/run_monthly.py
git -C "/Users/robertliu/Documents/Claude Code Projects" commit -m "task 20: GitHub Actions (weekly screener + monthly MC backtest)"
```

---

## Done criteria

- [ ] All 20 tasks committed
- [ ] `pytest -v` passes in `finance/taiwan-screener/`
- [ ] Manual dispatch of `weekly_screener_tw.yml` produces an email Rob can see in his inbox
- [ ] Manual dispatch of `monthly_backtest_tw.yml` produces a fresh `optimal_params.json` and `out/backtest_monthly_YYYYMM.html`
- [ ] First MC run shows at least one parameter set with `win_rate >= 0.80` and `avg_return_pct >= 20`. If none, expand `PARAM_SPACE` or relax quality filter and document in CLAUDE.md.
