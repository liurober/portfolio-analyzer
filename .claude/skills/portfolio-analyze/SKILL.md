---
name: portfolio-analyze
description: Analyze an existing portfolio or build a new one from scratch with Bridgewater-grade metrics, macro regime analysis, and 4 restructuring plans.
---

# /portfolio-analyze

Analyzes an existing portfolio (PDF, Excel, screenshot) OR builds a new portfolio from scratch. Produces: in-session terminal summary, HTML report, and Obsidian note.

## Usage

```bash
# Mode 1 — Analyze existing portfolio
/portfolio-analyze ~/Downloads/fidelity-holdings.pdf
/portfolio-analyze ~/portfolio.xlsx

# Mode 2 — Build from scratch (interactive prompts follow)
/portfolio-analyze --build
/portfolio-analyze --build --amount 50000 --profile aggressive --horizon 15 --goal growth
```

## Base Paths

```
BASE_DIR  = /Users/robertliu
ANALYZER  = /Users/robertliu/portfolio-analyzer
REPORTS   = /Users/robertliu/portfolio-reports
CONTEXT   = /Users/robertliu/portfolio-analyzer/.analysis_context.json
BUILD_CTX = /Users/robertliu/portfolio-analyzer/.build_context.json
```

The `portfolio_analyzer` Python package is a symlink at `/Users/robertliu/portfolio_analyzer → portfolio-analyzer`.
All scripts must be run with `cd /Users/robertliu` so the symlink resolves correctly.

## Instructions

### Step 0: Determine Mode

If args contain `--build`, run Mode 2. Otherwise run Mode 1.

If no args and no `--build` flag: ask the user: "Provide a portfolio file path to analyze, or type `--build` to create a portfolio from scratch."

---

### Step 1 (Mode 1): Run Python Orchestrator

```bash
cd /Users/robertliu && python portfolio-analyzer/run_analyze.py {file_path}
```

If the script exits with 0 positions parsed (output says `0 positions`), the PDF parser failed to extract tables. **Do not stop — fall back to Claude vision:** the file was already read by the system at session start, so use its content to manually build the holdings list and write it directly into the context JSON (see PDF Fallback below).

Read the context:
```bash
cat /Users/robertliu/portfolio-analyzer/.analysis_context.json
```

### Step 1 (Mode 2): Run Python Orchestrator

If `--amount`, `--profile`, `--horizon`, `--goal` are all provided, run:
```bash
cd /Users/robertliu && python portfolio-analyzer/run_build.py --amount {amount} --profile {profile} --horizon {horizon} --goal {goal}
```

Otherwise run interactively:
```bash
cd /Users/robertliu && python portfolio-analyzer/run_build.py
```

Read the context:
```bash
cat /Users/robertliu/portfolio-analyzer/.build_context.json
```

---

### PDF Fallback (when parser returns 0 positions)

Extract all rows visible in the PDF. For each position build a dict with these keys:

```python
{
  "ticker":     str,           # e.g. "NVDA"
  "name":       str,           # full name
  "quantity":   float,
  "price":      float,         # last price
  "value":      float,         # current market value
  "weight":     float,         # value / total_account_value (0–1 decimal)
  "sector":     str,           # e.g. "Technology"
  "cost_basis": float,         # total cost basis
  "avg_cost":   float,         # average cost per share
  "beta":       float,         # estimate from sector knowledge
}
```

Compute `total_value` = sum of all position values + cash + pending.

Write positions into the context JSON:
```python
import json
ctx = json.load(open("/Users/robertliu/portfolio-analyzer/.analysis_context.json"))
ctx["holdings"] = {
    "positions": [...],
    "total_value": total_value,
    "cash_value": cash_amount,
    "data_completeness": "complete",
}
json.dump(ctx, open("/Users/robertliu/portfolio-analyzer/.analysis_context.json","w"), indent=2)
```

Then recompute metrics over the injected holdings:
```python
import sys; sys.path.insert(0, "/Users/robertliu")
from portfolio_analyzer.metrics import compute_metrics
ctx["metrics"] = compute_metrics(ctx["holdings"], risk_free_rate=ctx["macro"]["fed_rate"]/100)
json.dump(ctx, open("/Users/robertliu/portfolio-analyzer/.analysis_context.json","w"), indent=2)
```

---

### Step 2: Claude Analysis (Mode 1 only)

Read the context JSON. Act as a Bridgewater-caliber portfolio manager and produce the `analysis` dict.

**Layer 1 — Implicit Bet:**
- Examine the top 3 positions by weight × beta (risk-weighted contribution)
- Identify the single macro thesis connecting them
- Write a 1-2 sentence `implicit_bet` naming the bet explicitly
- Calculate drawdown impact of -20% drop in top holding: `top_weight × 0.20 × total_value`

**Layer 2 — Red Flags** (include only those that apply, order by $ impact):

Each flag must have: `rank` (int), `flag` (string), `impact_est` ("High"/"Medium"/"Low").

- Single position > 10% capital → "Position concentration: {ticker} = {pct}% of capital"
- Sector > 40% capital → "Sector concentration: {sector} = {pct}% capital, ~{risk_pct}% risk contribution"
- Avg correlation > 0.5 → "Cosmetic diversification: avg pairwise correlation = {corr:.2f}"
- No bond/gold/commodity → "Stagflation blindspot: zero real assets or fixed income"
- Any position yield > 8% → "Yield trap risk: {ticker} yields {pct}%"
- Beta > 1.5 → "Leverage risk: portfolio beta {beta}"
- Equity risk > 90% → "Risk parity gap: equity drives {pct:.0%} of portfolio risk"

**Layer 3 — Macro Regime Sensitivity:**

For each Dalio quadrant estimate portfolio % impact range:
- Rising Growth + Low Inflation
- Rising Growth + Rising Inflation
- Stagflation
- Deflation / Recession

**Layer 4 — Grades** (A/B+/B/B-/C+/C/D/F):
- `diversification`, `risk_adjusted_return`, `macro_resilience`, `income_quality`, `market_alignment`

**4 Restructuring Plans** — aggressive / balanced / conservative / income.

Each plan dict **must** use these exact field names (the report template and obsidian renderer depend on them):

```python
{
  "rationale": str,
  "fit_grade": str,          # e.g. "A-"
  "sell": [
    {
      "ticker":   str,
      "action":   str,       # "Exit" or "Reduce"
      "proceeds": float,     # dollars freed (NOT freed_dollars)
      "reason":   str,
    }
  ],
  "buy": [
    {
      "ticker":      str,
      "pct":         float,  # decimal 0–1 (e.g. 0.05 for 5%) — NOT target_pct
      "dollars":     float,
      "reason":      str,
      "tag":         str,    # "ETF" or "Stock"
    }
  ],
  "hold": [
    {"ticker": str, "reason": str}
  ],
  "macro_grid": {
    "Rising Growth + Low Inflation": str,    # e.g. "+14% to +22%"
    "Rising Growth + Rising Inflation": str,
    "Stagflation": str,
    "Deflation / Recession": str,
  }
}
```

Output the full `analysis` dict as a JSON code block, then write it into the context:

```python
import json
ctx = json.load(open("/Users/robertliu/portfolio-analyzer/.analysis_context.json"))
ctx["analysis"] = analysis   # paste parsed dict here
json.dump(ctx, open("/Users/robertliu/portfolio-analyzer/.analysis_context.json","w"), indent=2)
```

### Step 2: Claude Analysis (Mode 2 only)

Produce a simpler `analysis` dict with:
- `construction_rationale`: why each position was chosen and how it fits the macro regime
- `red_flags`: same structure as Mode 1
- `plans`: same structure as Mode 1 but `sell` and `hold` are empty lists; only `buy` populated

---

### Step 3: Generate HTML Report + Obsidian Note + Terminal Summary

Run all three together. If `ctx["analysis"]` raises `KeyError`, Step 2 was not completed — go back and run it first.

```python
import sys, json, os
sys.path.insert(0, "/Users/robertliu")
from portfolio_analyzer.report import generate_report
from portfolio_analyzer.obsidian import save_note
from portfolio_analyzer.run_analyze import render_terminal_summary
from datetime import date

CONTEXT_PATH = "/Users/robertliu/portfolio-analyzer/.analysis_context.json"
ctx = json.load(open(CONTEXT_PATH))

if "analysis" not in ctx:
    raise RuntimeError("analysis key missing — complete Step 2 first and write ctx['analysis'] to the context file")

os.makedirs("/Users/robertliu/portfolio-reports", exist_ok=True)
date_str = ctx.get("date", date.today().isoformat())
output_path = f"/Users/robertliu/portfolio-reports/{date_str}-analysis.html"

generate_report(
    holdings=ctx["holdings"],
    macro=ctx["macro"],
    metrics=ctx["metrics"],
    picks=ctx["picks"],
    analysis=ctx["analysis"],
    output_path=output_path,
    mode=ctx["mode"]
)

save_note(
    holdings=ctx["holdings"],
    macro=ctx["macro"],
    metrics=ctx["metrics"],
    analysis=ctx["analysis"],
    date_str=date_str,
    mode=ctx["mode"]
)

render_terminal_summary(ctx["holdings"], ctx["macro"], ctx["metrics"], ctx["analysis"])
print(f"\n→ HTML report: ~/portfolio-reports/{date_str}-analysis.html")
print(f"→ Obsidian note: Trading/Portfolio Analysis/{date_str}-portfolio-review.md")
```

---

## Error Handling

- **Parser returns 0 positions**: use Claude vision fallback (see PDF Fallback above) — never stop the analysis
- **`KeyError: 'analysis'`**: Step 2 not completed or context was reset — re-run Step 2, write the analysis dict into the context JSON, then retry Step 3
- **yfinance data unavailable**: `compute_metrics` handles gracefully; skipped tickers reported
- **`dividendYield` > 20%**: already clamped in `metrics.py` — yfinance sometimes returns garbage values
- **`ModuleNotFoundError: portfolio_analyzer`**: ensure you ran `cd /Users/robertliu` and the symlink exists; recreate with `cd /Users/robertliu && ln -sf portfolio-analyzer portfolio_analyzer`
- **Obsidian vault not found**: print warning, skip Obsidian save, HTML report still generated
