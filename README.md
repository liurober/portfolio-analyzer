# Portfolio Analyzer

A Python backend for Bridgewater-grade portfolio analysis and portfolio construction from scratch. Designed to run as a Claude Code skill (`/portfolio-analyze`) but fully usable as a standalone CLI tool.

---

## What It Does

**Mode 1 — Analyze an existing portfolio**
Parse a PDF, Excel, or JSON holdings file and get:
- Sharpe / Sortino / Calmar / Beta / VaR / HHI / risk parity metrics
- 7-signal Dalio macro regime classification (live yfinance data)
- Bridgewater-style analysis: Implicit Bet, Red Flags, Macro Regime Sensitivity, Letter Grades
- 4 restructuring plans (Aggressive / Balanced / Conservative / Income) with buy/sell/hold tables and $ amounts
- Dark-theme 5-tab HTML report (auto-opens in browser)
- YAML-frontmattered Obsidian note saved automatically

**Mode 2 — Build a portfolio from scratch**
Given an amount, risk profile, time horizon, and goal:
- Constructs 4 portfolios with macro regime tilts (Dalio quadrant-aware)
- Shows every position grouped by sleeve (Equity / Fixed Income / Real Assets / REITs / Cash)
- Est. Annual Income in $ for each plan (annual / monthly / weekly)
- Full HTML report + Obsidian note

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Dependencies: `yfinance`, `pandas`, `numpy`, `scipy`, `pdfplumber`, `openpyxl`, `jinja2`, `requests`

### 2. Run Mode 1 — Analyze an existing portfolio

```bash
python run_analyze.py ~/Downloads/fidelity-holdings.pdf
python run_analyze.py ~/portfolio.xlsx
python run_analyze.py ~/portfolio.json
```

Supported formats: **PDF**, **Excel (.xlsx / .xls)**, **JSON** (see schema below)

### 3. Run Mode 2 — Build from scratch

```bash
# Interactive (will prompt for all params)
python run_build.py

# Non-interactive
python run_build.py --amount 50000 --profile aggressive --horizon 15 --goal growth

# With optional age and avoid list
python run_build.py --amount 100000 --profile balanced --horizon 10 --goal retirement --age 42 --avoid "TSLA,crypto"
```

**Profile options:** `aggressive` · `balanced` · `conservative` · `income`  
**Goal options:** `growth` · `income` · `capital preservation` · `retirement` · `FIRE`

---

## Portfolio JSON Schema (Mode 1)

If passing a `.json` file, use this structure:

```json
{
  "positions": [
    {
      "ticker": "NVDA",
      "weight": 0.12,
      "value": 17076.0,
      "cost_basis": 8000.0,
      "shares": 120.0
    },
    {
      "ticker": "AAPL",
      "weight": 0.08,
      "value": 11384.0,
      "cost_basis": 9500.0,
      "shares": 60.0
    }
  ],
  "total_value": 142300.0,
  "data_completeness": "full"
}
```

`weight` is required (0–1 float or percentage string like `"12%"`). All other fields are optional.

---

## Module Reference

| Module | Description |
|---|---|
| `parser.py` | PDF / Excel / JSON → standardized holdings dict |
| `macro_context.py` | 7 live yfinance signals → Dalio regime classification |
| `metrics.py` | Sharpe / Sortino / Calmar / Beta / VaR / HHI / risk parity |
| `screener_picks.py` | Candidate picks: local analysis.json + live yfinance scoring + ETF fallbacks |
| `report.py` | Jinja2 HTML report renderer (auto-opens in browser) |
| `obsidian.py` | YAML-frontmattered Obsidian vault note writer |
| `builder.py` | Mode 2: constructs 4 portfolios with regime tilts |
| `run_analyze.py` | Mode 1 orchestrator — parses → macro → metrics → picks → context JSON |
| `run_build.py` | Mode 2 orchestrator — params → macro → build → context JSON |

---

## Macro Regime Classifier

Runs 7 live signals every time to classify the current Dalio quadrant:

| Signal | Ticker | What It Measures |
|---|---|---|
| VIX | ^VIX | Fear / volatility regime |
| 3M-10Y Treasury spread | ^IRX / ^TNX | Yield curve (recession signal) |
| SPY vs 200D MA | SPY | Trend direction |
| Inflation proxy | TIP vs TLT | Real rates / inflation pressure |
| Gold | GLD | Tail risk / inflation hedge demand |
| USD | DX-Y.NYB | Dollar strength |
| Credit spread | HYG vs LQD | Risk-on vs risk-off |

Output: one of 4 Dalio regimes + plain-English narrative + recommended plan.

---

## The 4 Portfolio Archetypes

| Archetype | Equity | Bonds | Real Assets | REIT | Cash | Beta est | Yield est |
|---|---|---|---|---|---|---|---|
| Aggressive | 93% | 2% | 2% | 0% | 3% | ~1.35 | ~0.7% |
| Balanced | 55% | 30% | 12% | 3% | 3% | ~0.80 | ~2.0% |
| Conservative | 28% | 48% | 8% | 3% | 10% | ~0.45 | ~3.0% |
| Income | 47% | 20% | 8% | 20% | 5% | ~0.65 | ~4.5% |

Each plan receives a **macro fit score (1–5)** for the current regime so you can see which is best positioned right now.

---

## Output Files

| Output | Default Path |
|---|---|
| HTML report | `~/portfolio-reports/YYYY-MM-DD-analysis.html` |
| Analysis context JSON | `portfolio-analyzer/.analysis_context.json` |
| Build context JSON | `portfolio-analyzer/.build_context.json` |
| Obsidian note | `Trading/Portfolio Analysis/YYYY-MM-DD-portfolio-review.md` |

The HTML report opens automatically in a new browser window.

---

## Obsidian Integration

If you use Obsidian, set `VAULT_BASE` in `obsidian.py` to your vault path:

```python
VAULT_BASE = "/path/to/your/vault"
```

Notes are saved to `Trading/Portfolio Analysis/` with full YAML frontmatter (Sharpe, Beta, Max Drawdown, regime, recommended plan) — queryable with Dataview.

---

## Claude Code Skill

This tool ships with a `/portfolio-analyze` Claude Code skill. To install:

```bash
mkdir -p ~/.claude/skills/portfolio-analyze
cp skill/portfolio-analyze.md ~/.claude/skills/portfolio-analyze/SKILL.md
```

Then in Claude Code:

```
/portfolio-analyze ~/Downloads/fidelity.pdf
/portfolio-analyze --build --amount 50000 --profile aggressive --horizon 15 --goal growth
```

Claude acts as a Bridgewater-caliber PM to produce the Implicit Bet, Red Flags (ordered by $ impact), Macro Regime Sensitivity across all 4 Dalio quadrants, and Letter Grades — then renders the full HTML report and saves the Obsidian note automatically.

---

## Tests

```bash
python -m pytest tests/ -v
```

83 tests, all passing.

---

## Requirements

- Python 3.11+
- yfinance >= 0.2.40
- pandas >= 2.0.0
- numpy >= 1.24.0
- scipy >= 1.11.0
- pdfplumber >= 0.9.0
- openpyxl >= 3.1.0
- jinja2 >= 3.1.2
- requests >= 2.31.0
