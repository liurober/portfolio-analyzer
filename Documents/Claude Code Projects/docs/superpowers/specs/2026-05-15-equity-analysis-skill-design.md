# Equity Analysis Skill — Design Spec
**Date:** 2026-05-15
**Status:** Approved

---

## Overview

A Claude Code skill (`/analyze <TICKER>`) that produces a commercial-grade, single-stock equity analysis report on demand. The output is an HTML report that opens in the browser and is automatically saved to Obsidian.

The report covers three pillars: TradingView-style technical analysis, Goldman/Morgan-style fundamental analysis, and Barchart GEX options positioning. Each pillar is independently scored and combined into a weighted BUY/HOLD/SELL rating with conviction level.

**Invocation:** `/analyze TSLA` — everything after `/analyze` is treated as the ticker symbol.

---

## Architecture

**Pattern: Python fetches data → Claude scores and writes narrative → HTML report rendered**

```
User: /analyze TSLA
        │
        ▼
[Skill: analyze.md]
        │
        ├── Runs: python stock-screener/analyze.py TSLA
        │         │
        │         ├── yfinance → OHLCV history (2yr weekly + 6mo daily)
        │         ├── FactSet/S&P Global MCP → real-time price + fundamentals
        │         ├── indicators.py → RSI, BB, MACD, Chandelier Exit, TTM Squeeze
        │         ├── patterns.py → Reverse H&S, Cup & Handle, Bull Flag, Wyckoff
        │         ├── charts.py → annotated weekly candlestick chart (base64 PNG)
        │         └── barchart_gex.py → net GEX, flip level, put/call wall
        │
        ├── Outputs: analysis.json (structured data)
        │
        ├── Claude reads analysis.json
        │         ├── equity-research:thesis skill → investment thesis
        │         ├── financial-analysis plugins → fundamental scoring
        │         ├── Scores all 3 pillars (0–10 each)
        │         ├── Computes weighted final score
        │         └── Writes analyst narrative for each section
        │
        ├── Renders: report.html → opens in browser
        └── Saves: Obsidian note → iCloud vault / Trading / <TICKER>-<date>.md
```

---

## Components

### 1. Python Data Collector (`stock-screener/analyze.py`)

Entry point. Takes ticker as CLI arg. Orchestrates all data fetching and outputs `analysis.json`.

**Outputs `analysis.json` with:**
```json
{
  "ticker": "TSLA",
  "as_of": "2026-05-15T09:32:00",
  "price": {
    "current": 175.40,
    "open": 173.20,
    "day_high": 176.80,
    "day_low": 172.10,
    "week_52_high": 271.00,
    "week_52_low": 138.80,
    "volume": 98234100,
    "avg_volume": 112000000,
    "float_shares": 3180000000
  },
  "technicals": {
    "score_long": 4,
    "score_short": 1,
    "direction": "long",
    "rsi": 58.2,
    "sig_rsi": true,
    "sig_bb": true,
    "sig_macd": true,
    "sig_chandelier": true,
    "sig_ttm": false,
    "squeeze_fired": false,
    "squeeze_on": false,
    "bb_upper": 182.0,
    "bb_lower": 158.0,
    "ce_long": 161.0,
    "atr": 8.4,
    "entry": 175.40,
    "stop": 161.00,
    "target": 211.40,
    "rr_ratio": 2.5,
    "pattern": "Cup & Handle",
    "pattern_confidence": 0.72,
    "pattern_confirmed": true
  },
  "chart_b64": "<base64 PNG>",
  "gex": {
    "net_gex": -2400000000,
    "dealer_bias": "short_gamma",
    "flip_level": 170.00,
    "distance_to_flip_pct": -3.1,
    "put_wall": 160.00,
    "call_wall": 180.00,
    "raw_scraped_at": "2026-05-15T09:30:00"
  },
  "fundamentals": {
    "market_cap": 557000000000,
    "enterprise_value": 589000000000,
    "pe_ttm": 48.2,
    "pe_forward": 38.5,
    "ps_ttm": 6.1,
    "ev_ebitda": 28.4,
    "peg_ratio": 1.8,
    "eps_ttm": 3.64,
    "eps_growth_yoy": 0.38,
    "revenue_growth_yoy": 0.21,
    "gross_margin": 0.178,
    "operating_margin": 0.087,
    "net_margin": 0.094,
    "free_cash_flow": 3600000000,
    "debt_to_equity": 0.08,
    "next_earnings_date": "2026-07-22",
    "analyst_consensus": "Hold",
    "analyst_price_target": 195.00,
    "insider_ownership_pct": 0.131
  }
}
```

### 2. GEX Scraper (`stock-screener/screener/barchart_gex.py`)

Scrapes Barchart's public options page for the ticker. Extracts:
- Net GEX (positive = dealers long gamma = dampening effect; negative = short gamma = amplifying effect)
- GEX flip level (price where dealer positioning switches)
- Put wall / Call wall (largest open interest strikes)
- Dealer bias label (long_gamma / short_gamma)

Uses `requests` + `BeautifulSoup`. Gracefully returns `null` fields if scrape fails (Barchart layout changes) rather than crashing the whole run.

### 3. Chart Generator (extends `stock-screener/screener/charts.py`)

Extends the existing chart generator to add:
- Daily timeframe option (6mo daily for near-term view)
- Pattern annotation overlays (highlight detected pattern on chart)
- Indicator subplot: RSI, MACD histogram, BB bands shown on price chart
- TTM Squeeze dots (red/green on zero line)
- Entry / stop / target horizontal lines

Output: base64-encoded PNG embedded directly in HTML (no external file dependency).

### 4. Skill File (`financial-services/plugins/vertical-plugins/equity-research/skills/analyze/SKILL.md`)

The Claude skill definition. On invocation:
1. Validates ticker format
2. Runs `python stock-screener/analyze.py <TICKER>`
3. Reads `analysis.json`
4. Invokes `equity-research:thesis` for investment thesis context
5. Scores all three pillars using the rubric below
6. Writes analyst narrative for each section
7. Renders HTML report
8. Opens report in browser (`open report.html`)
9. Saves Obsidian note

### 5. HTML Report Template (`stock-screener/screener/analysis_template.html`)

Single-file HTML (inline CSS, base64 chart). Sections:

```
┌─────────────────────────────────────────────┐
│  TSLA — Tesla Inc.          May 15, 2026     │
│  $175.40  ▲2.4%  |  BUY — HIGH CONVICTION  │
│  Final Score: 8.3/10                        │
├──────────────┬──────────────┬───────────────┤
│ TECHNICAL    │ FUNDAMENTAL  │ GEX / OPTIONS │
│   8.0/10     │   8.5/10     │   8.1/10      │
│   45% weight │   40% weight │   15% weight  │
├──────────────┴──────────────┴───────────────┤
│ [Annotated Chart — weekly candlestick]      │
├─────────────────────────────────────────────┤
│ TECHNICAL ANALYSIS                          │
│  Indicators: RSI ✓  BB ✓  MACD ✓  CE ✓  TTM ✗│
│  Pattern: Cup & Handle (72% confidence)    │
│  Entry: $175.40 | Stop: $161.00 | Target: $211.40│
│  R:R — 2.5:1                               │
│  [Analyst narrative — 2-3 paragraphs]      │
├─────────────────────────────────────────────┤
│ FUNDAMENTAL ANALYSIS                        │
│  Earnings: EPS $3.64 +38% YoY ✓           │
│  Valuation: P/E 48x fwd 38x vs sector avg  │
│  Balance Sheet: FCF $3.6B, D/E 0.08 ✓     │
│  Next Earnings: Jul 22, 2026               │
│  [Analyst narrative — 2-3 paragraphs]      │
├─────────────────────────────────────────────┤
│ GEX / OPTIONS POSITIONING                   │
│  Net GEX: -$2.4B (Short Gamma — amplifying)│
│  Flip Level: $170 | Distance: -3.1%        │
│  Put Wall: $160 | Call Wall: $180          │
│  [1-paragraph dealer positioning summary]  │
├─────────────────────────────────────────────┤
│ FINAL VERDICT                               │
│  BUY — HIGH CONVICTION (8.3/10)           │
│  12-Month Price Target: $211               │
│  Upside: +20.3%                            │
│  [1-paragraph investment thesis]           │
│  Data as of: 2026-05-15 09:32 ET          │
└─────────────────────────────────────────────┘
```

---

## Scoring Rubric

### Technical Score (45% weight)

| Condition | Points |
|---|---|
| Indicator score 5/5 | 10 |
| Indicator score 4/5 | 8 |
| Indicator score 3/5 | 6 |
| Indicator score 2/5 | 3 |
| Indicator score 0–1/5 | 0 |
| Pattern detected + confirmed | +1 (capped at 10) |
| Pattern confidence > 0.7 | +0.5 |
| R:R ≥ 3:1 | +0.5 |
| TTM Squeeze fired | +0.5 |

### Fundamental Score (40% weight)

Claude scores 0–10 based on:
- EPS growth YoY: >30% → strong, 10–30% → moderate, <10% → weak
- Revenue growth YoY: >20% → strong, 5–20% → moderate, <5% → weak
- Forward P/E vs. sector: below median → undervalued, above 2× median → stretched
- Gross margin trend: expanding → bullish, compressing → bearish
- FCF positive and growing → strong
- D/E < 0.5 → clean balance sheet
- Insider ownership > 10% → management aligned

### GEX Score (15% weight)

| Condition | Score |
|---|---|
| Long gamma + price above flip level | 9–10 |
| Long gamma + price near flip level | 7–8 |
| Short gamma + price far above flip | 5–6 |
| Short gamma + price near flip level | 3–4 |
| Short gamma + price below flip level | 0–2 |

### Final Rating

| Weighted Score | Rating |
|---|---|
| 8.0–10.0 | BUY — High Conviction |
| 6.5–7.9 | BUY — Moderate Conviction |
| 4.5–6.4 | HOLD |
| 3.0–4.4 | SELL — Moderate Conviction |
| 0–2.9 | SELL — High Conviction |

---

## Data Freshness

| Data | Source | Freshness |
|---|---|---|
| Spot price (report header) | FactSet / S&P Global MCP | Real-time institutional feed |
| OHLCV history (indicator math) | yfinance | Last closed candle (weekly partial included) |
| Intraday chart (today's action) | yfinance `interval="1m"` | ~15-min delayed — labeled in report |
| Weekly chart (pattern view) | yfinance | Current partial week candle included |
| GEX | Barchart scrape | Pulled at time of invocation |
| Fundamentals | FactSet / S&P Global MCP | As of last reported quarter |

**Chart labeling rule:** All chart candles display a "Prices delayed ~15 min" label. The live spot price from the MCP is shown prominently in the report header and is always current. For weekly swing trading, 15-min chart delay does not affect setup validity.

Every report explicitly states:
- **As-of timestamp** on every data field
- **Source label** (yfinance / FactSet / Barchart) per section
- **"Prices delayed ~15 min" notice** on all chart images

---

## Obsidian Save

Saved to:
`/Users/robertliu/Library/Mobile Documents/iCloud~md~obsidian/Documents/Rob's Valut/Trading/<TICKER>/<TICKER>-<YYYY-MM-DD>.md`

Note contains: final rating, all scores, entry/stop/target, key fundamental metrics, investment thesis paragraph, link to local HTML report.

---

## Error Handling

- **GEX scrape fails:** Report renders without GEX section; GEX weight redistributed to Technical (55%) and Fundamental (45%). Note shown in report.
- **FactSet/S&P MCP unavailable:** Falls back to yfinance fundamentals. Note shown in report.
- **Pattern not detected:** Technical score uses indicator score only; no pattern bonus.
- **Invalid ticker:** Skill returns error immediately before running any data fetch.

---

## Files Created / Modified

| File | Action |
|---|---|
| `financial-services/plugins/vertical-plugins/equity-research/skills/analyze/SKILL.md` | CREATE — skill definition |
| `stock-screener/analyze.py` | CREATE — main orchestrator |
| `stock-screener/screener/barchart_gex.py` | CREATE — GEX scraper |
| `stock-screener/screener/analysis_template.html` | CREATE — HTML report template |
| `stock-screener/screener/charts.py` | MODIFY — add daily timeframe + pattern annotations |
| `stock-screener/requirements.txt` | MODIFY — add beautifulsoup4 if not present |
