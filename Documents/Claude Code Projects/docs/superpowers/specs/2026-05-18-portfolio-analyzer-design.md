# Portfolio Analyzer — Design Spec
**Date:** 2026-05-18  
**Status:** Approved  
**Author:** Rob Liu + Claude

---

## 1. Overview

A Claude slash command (`/portfolio-analyze`) that accepts a portfolio file (PDF, Excel, or screenshot), runs a Bridgewater-grade quantitative and qualitative analysis, fetches current market conditions, and produces three outputs: an in-session terminal summary, a full HTML report, and an Obsidian note.

### Invocation

```bash
/portfolio-analyze ~/Downloads/fidelity-holdings.pdf
/portfolio-analyze ~/portfolio.xlsx
```

---

## 2. Architecture

**Approach: Skill + Python Backend**

The Claude skill orchestrates a Python layer for deterministic quantitative work. Claude handles all intelligent interpretation, narrative critique, and restructuring recommendations.

```
PDF / Excel / Screenshot
        ↓
  parser.py          — extracts structured holdings dict
        ↓
  macro_context.py   — fetches live market/economic signals
        ↓
  metrics.py         — computes all quantitative metrics
        ↓
  Claude Analysis    — critique, implicit bet, macro regime, 4 plans
        ↓
  report.py          — renders HTML report (Jinja2)
        ↓
  Obsidian save      — YAML frontmatter note
  Terminal summary   — in-session digest
```

### File & Folder Structure

```
Claude Code Projects/
  stock-screener/
    analysis.json          ← Option C: screener picks (if < 7 days old)
    screener/universe.py   ← Option A: full screener universe
  portfolio-reports/         ← HTML report output directory (auto-created)
  portfolio-analyzer/      ← NEW
    parser.py
    macro_context.py
    metrics.py
    report.py
    requirements.txt
    templates/
      report.html          ← Jinja2 HTML template
  superpowers/skills/
    portfolio-analyze.md   ← The slash command skill file
  docs/superpowers/specs/
    2026-05-18-portfolio-analyzer-design.md  ← this file
```

---

## 3. Input Handling

### Supported Formats
| Format | Library | Notes |
|---|---|---|
| PDF | `pdfplumber` | Primary format. Multi-page support. |
| Excel / CSV | `openpyxl`, `pandas` | Common brokerage exports. |
| Screenshot / image | Claude vision (via skill) | Falls back to Claude reading the image directly. |

### Graceful Degradation
The tool works with whatever data is present — it never fails, it just computes fewer metrics.

| Available data | Metrics unlocked |
|---|---|
| Ticker + weight only | Beta, vol, concentration, correlation, yield, style |
| + Current value | + VaR, Sharpe, Sortino, Calmar, drawdown |
| + Cost basis | + Unrealized P&L, actual return, alpha, income estimate |

### Unknown Tickers
- `yf.download(ticker)` attempted for every position — no universe filter
- On failure: position listed in output, excluded from quantitative metrics, flagged explicitly
- International ADRs, ETFs, REITs, crypto ETFs all handled natively

---

## 4. Market Context Layer (per run)

Fetched fresh every run via yfinance and web search. Used to classify current macro regime and rank restructuring plans by current relevance.

### Signals Fetched

| Signal | Source | Purpose |
|---|---|---|
| VIX | `^VIX` yfinance | Fear / complacency gauge |
| 3M-10Y yield spread | `^TNX`, `^IRX` | Recession signal (3M-10Y is most predictive) |
| SPY vs 200-day SMA | yfinance | Bull / bear market classification |
| TIPS breakeven (inflation expectations) | `RINF` or TIP/TNX spread | Inflation regime |
| Sector rotation | XLK, XLE, XLU, XLF SPDRs vs SPY | Where capital is rotating |
| Fed Funds Rate | web search (FRED) | Rate environment |
| Dollar strength | `DX-Y.NYB` | Global risk appetite |

### Macro Regime Classification

Maps signals to one of four quadrants (Dalio All Weather framework):

| Quadrant | Conditions | Favored assets |
|---|---|---|
| Rising Growth + Low Inflation | SPY > 200D, VIX < 18, 3M-10Y spread positive | Equities, credit |
| Rising Growth + Rising Inflation | SPY > 200D, TIPS breakeven rising | Commodities, TIPS, equities |
| Stagflation | SPY < 200D, inflation elevated, 3M-10Y spread inverted | Gold, commodities, short bonds |
| Deflation / Recession | SPY < 200D, VIX > 25, 3M-10Y deeply inverted | Long bonds, gold, cash |

### Market Context Output Block (all three outputs)

```
Current Regime: [Quadrant Name]
VIX: X.X  |  3M-10Y spread: +X.XXbps  |  SPY vs 200D: +X.X%  |  Inflation exp: X.X%
Regime Assessment: [1-2 sentence narrative]
Most Relevant Plan Today: [Plan name + reason]
```

---

## 5. Metrics Engine (Python)

All metrics use 1-year daily price history from yfinance. Risk-free rate = 3M T-bill rate (fetched live from `^IRX`).

### Concentration Risk
- Top position weight (%)
- Top 5 combined weight (%)
- Largest sector weight (%)
- Herfindahl-Hirschman Index (HHI) — single concentration score 0–10,000
- Number of positions

**Thresholds:** Single position > 10% = flag. Sector > 30% = flag.

### Risk Metrics
- Portfolio beta (weighted average vs SPY)
- Annualized volatility (%)
- Max drawdown — 1Y rolling (%)
- Value at Risk — 95% confidence, 1-day ($)
- Average pairwise correlation across all positions

**Thresholds:** Avg correlation > 0.5 = poor diversification flag.

### Return Quality
- Sharpe ratio (> 1.0 = good, > 2.0 = exceptional)
- Sortino ratio (downside volatility only)
- Calmar ratio (annualized return / max drawdown, > 0.5 = acceptable)
- 1Y return % (if cost basis available)
- Alpha vs SPY (Jensen's alpha, 1Y)

### Income & Style
- Weighted dividend yield (%)
- Estimated annual income ($) at current portfolio value
- Market cap distribution (large / mid / small %)
- Geographic exposure (domestic / international %)
- Asset class breakdown (equity / bond / alt / cash %)

**Thresholds:** Yield > 8% = payout risk flag.

### Risk Parity (Bridgewater Layer)
- Risk contribution % per position (not just capital weight)
- Risk contribution % per sector
- Risk contribution % per asset class
- Implied leverage ratio (equity risk contribution ÷ total portfolio risk)

---

## 6. Claude Analysis Framework (Bridgewater-Grade)

Applied after Python metrics are computed. Claude receives a structured JSON of all metrics and produces:

### Layer 1 — Implicit Bet Test
Explicitly names the hidden macro thesis the portfolio is making. Examples:
- "This portfolio bets on continued AI capex with no recession."
- "70% of return attribution comes from NVDA and MSFT — not 14 positions."
- "A 20% NVDA drawdown would erase 6.8% of total portfolio value."

### Layer 2 — Risk Parity Critique
- Compares capital weight vs risk contribution per position and sector
- Flags any position with > 15% risk contribution
- Flags equity risk contribution > 85% of total portfolio risk
- Simulates correlation spike (2008-style crisis scenario)

### Layer 3 — Macro Regime Sensitivity
Scores portfolio across all four quadrants using current regime classification:
- Rising Growth + Low Inflation
- Rising Growth + Rising Inflation (stagflation precursor)
- Stagflation
- Deflation / Recession

Each quadrant gets an estimated portfolio impact (% gain/loss range).

### Layer 4 — Structured Critique

**Red Flags** (numbered, ordered by estimated $ impact):
- Cosmetic diversification (many correlated names)
- Stagflation blindspot (no gold / commodities / TIPS)
- Hidden leverage via high-beta concentration
- Yield-chasing above 8% (payout risk)
- Age/goal misalignment (120-minus-age equity rule)
- Long-duration bond trap (rate correlation since 2022)
- Single macro regime dependency

**Green Flags** (what's working):
- No single position > 5% (2% risk rule adherence)
- Avg pairwise correlation < 0.4
- Multiple asset classes represented
- Beta matched to inferred risk appetite
- Dividend coverage and yield sustainability
- Sector breadth (Bob Farrell Rule 7)

### Portfolio Grade
A letter grade (A–F) per dimension:
- Diversification
- Risk-adjusted return
- Macro resilience
- Income quality
- Alignment with current market conditions

---

## 7. Stock Pick Logic (Options A + C Hybrid)

For each restructuring plan, specific picks are sourced as follows:

```
Priority 1: stock-screener/analysis.json (if < 7 days old)
  → Top-scoring names per relevant sector, pre-validated by 6-indicator system

Priority 2: Live screener score on universe subset (if analysis.json stale/missing)
  → Run indicator scoring on the relevant sector slice of the screener universe
  → Select top 3–5 names per sector needed by the restructuring plan

Priority 3: Curated ETFs (always included as alternatives)
  → Sector ETFs, factor ETFs, income ETFs, real asset ETFs
  → Never requires the screener — always available
```

All picks show: ticker, tag (`screener` / `ETF` / `REIT`), reason, target % of portfolio, $ to invest.

---

## 8. Four Restructuring Plans

Each plan is generated for the current portfolio and outputs:
- Sell/Reduce table: ticker, action, proceeds ($), reason
- Buy table: ticker, reason, target % of portfolio, **$ to invest**, source tag
- Hold table: ticker, yield, current value
- Allocation bars: label, %, $ amount, delta vs current
- Target metrics: beta, Sharpe, max drawdown, equity %, yield
- Macro regime grid: performance expectation across all 4 quadrants
- Rationale narrative
- Fit grade vs current portfolio

### Aggressive Growth
- Beta target: 1.2–1.5 | Equity: 90–100% | Max single position: 8%
- Picks: screener top scorers, momentum leaders, sector ETFs (QQQ, SOXX)
- Designed for: rising growth + low/moderate inflation

### Balanced / All-Weather
- Beta target: 0.7–0.85 | Equity: 55% | True risk parity across 4 quadrants
- Picks: mid-beta screener picks, VTI, TLT, GLD, PDBC, TIPS
- Designed for: all four macro regimes (Dalio framework)

### Conservative
- Beta target: 0.35–0.55 | Equity: 20–40% | Hard drawdown ceiling < 15%
- Picks: low-beta screener picks, BND, SGOV, USMV, VYM, GLD
- Designed for: capital preservation, near-liquidity event

### Passive Income
- Target yield: 3.5–5.5% | Payout ratio < 75% | REIT allocation 15–25%
- Picks: high-yield screener picks, SCHD, JEPI, O, VNQ, MAIN
- Designed for: FIRE, income supplement, semi-retirement
- Shows: monthly $ income projection, per-source income breakdown

**Current conditions integration:** The plan best matched to the current macro regime is highlighted as "Recommended for Today's Market" in all three outputs.

---

## 9. Outputs

### ① In-Session Terminal Summary
- Implicit Bet statement (1–2 sentences)
- 4-metric scorecard: Sharpe, beta, max drawdown, yield
- Market Context block (current regime + most relevant plan)
- Top 3 red flags (with estimated $ impact)
- Top 2 green flags
- Links to HTML report and Obsidian note

### ② HTML Report
Five sections, self-contained file saved to `~/portfolio-reports/YYYY-MM-DD-analysis.html`:

1. **Portfolio Snapshot** — holdings table, sector donut, asset class bar, market cap distribution
2. **Metrics Dashboard** — all quantitative metrics, risk contribution heatmap, correlation matrix, rolling drawdown chart
3. **Bridgewater Analysis** — implicit bet, macro regime grid (4 quadrants), stress test results, risk parity vs actual comparison
4. **Critique** — red flags (prioritized by $ impact), green flags, ChartSchool rule checklist, grade per dimension
5. **Restructuring Plans** — tabbed interface (Aggressive / Balanced / Conservative / Income), each with sell table, buy table with $ to invest, allocation bars, macro grid

### ③ Obsidian Note
Saved to `Rob's Personal Vault/Trading/Portfolio Analysis/YYYY-MM-DD-portfolio-review.md`

```yaml
---
tags:
  - portfolio-analysis
  - equity
  - trading
  - review
date: YYYY-MM-DD
stream: Trading / Finance
total_value: $XXX,XXX
sharpe: X.XX
beta: X.XX
max_drawdown: -XX%
current_regime: [regime name]
report_html: ~/portfolio-reports/YYYY-MM-DD-analysis.html
---
```

Full narrative, metric tables, macro analysis, and all 4 restructuring plans in markdown.

---

## 10. Python Dependencies

```
yfinance          # price history + market data
pdfplumber        # PDF parsing
openpyxl          # Excel parsing
pandas            # data manipulation
numpy             # quantitative metrics
scipy             # correlation, regression
jinja2            # HTML report rendering
matplotlib        # charts (correlation matrix, drawdown, allocation)
requests          # web fetch for Fed rate (FRED)
python-dotenv     # env vars
```

---

## 11. ChartSchool Rules Applied

From Rob's Obsidian vault (`ChartSchool/` folder):

| Rule source | Applied check |
|---|---|
| Asset Allocation & Diversification | Asset class spread, systematic vs non-systematic risk |
| Arthur Hill on Goals, Style & Strategy | Portfolio style consistency with implied risk appetite |
| Bob Farrell Rule 7 | Market breadth — no narrow concentration in one style |
| Bob Farrell Rule 1 | Mean reversion warning on overextended positions |
| Donchian / 2% Rule | No single position > 2% of portfolio at risk |
| Murphy's 10 Laws | Trend alignment of individual holdings |
| Asset Allocation & Diversification | Moving average stop strategy for downside protection |

---

## 12. Error Handling

- Ticker yfinance can't resolve → skip, flag in output, analysis continues
- PDF parsing fails → prompt user to try Excel export, fall back to Claude vision
- analysis.json stale (> 7 days) → log warning, fall back to Option A live scoring
- Macro data fetch fails → use last known values, flag data as potentially stale
- Insufficient price history (< 30 days) → skip risk metrics for that ticker, note it

---

## 13. Out of Scope

- Does not post orders or interact with any brokerage API
- Does not store portfolio data between sessions
- Does not provide tax advice or cost basis optimization
- Does not handle options positions (flags them as "unsupported instrument")
- Does not support real-time streaming prices (snapshot at run time)
