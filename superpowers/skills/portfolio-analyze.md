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

## Instructions

### Step 0: Determine Mode

If args contain `--build`, run Mode 2. Otherwise run Mode 1.

If no args and no `--build` flag: ask the user: "Provide a portfolio file path to analyze, or type `--build` to create a portfolio from scratch."

### Step 1 (Mode 1): Run Python Orchestrator

Run:
```bash
cd "/Users/robertliu/Documents/Claude Code Projects" && python portfolio-analyzer/run_analyze.py {file_path}
```

Read the context:
```bash
cat "/Users/robertliu/Documents/Claude Code Projects/portfolio-analyzer/.analysis_context.json"
```

### Step 1 (Mode 2): Run Python Orchestrator

If `--amount`, `--profile`, `--horizon`, `--goal` are all provided, run:
```bash
cd "/Users/robertliu/Documents/Claude Code Projects" && python portfolio-analyzer/run_build.py --amount {amount} --profile {profile} --horizon {horizon} --goal {goal} {--age X if provided} {--avoid "..." if provided}
```

Otherwise run interactively:
```bash
cd "/Users/robertliu/Documents/Claude Code Projects" && python portfolio-analyzer/run_build.py
```

Read the context:
```bash
cat "/Users/robertliu/Documents/Claude Code Projects/portfolio-analyzer/.build_context.json"
```

### Step 2: Claude Analysis (Mode 1 only)

Read the context JSON. Now act as a Bridgewater-caliber portfolio manager and produce the `analysis` dict:

**Layer 1 — Implicit Bet:**
- Examine the top 3 positions by weight × beta (risk-weighted contribution)
- Identify the single macro thesis connecting them
- Write a 1-2 sentence `implicit_bet` that names the bet explicitly (e.g., "This portfolio requires continued AI capex expansion and no US recession")
- Calculate the drawdown impact of a -20% drop in the top holding: `top_weight × 0.20 × total_value`

**Layer 2 — Red Flags (check each, include only those that apply):**
- Single position > 10% capital weight → "Position concentration: {ticker} = {pct}% of capital"
- Sector > 40% capital → "Sector concentration: {sector} = {pct}% capital, {risk_pct}% risk contribution"
- Avg correlation > 0.5 → "Cosmetic diversification: avg pairwise correlation = {corr:.2f} — positions move together"
- No bond/gold/commodity allocation → "Stagflation blindspot: zero real assets or fixed income"
- Yield > 8% in any position → "Yield trap risk: {ticker} yields {pct}% — payout sustainability risk"
- Beta > 1.5 → "Leverage risk: portfolio beta {beta} — amplified drawdown in bear markets"
- Equity risk contribution > 90% → "Risk parity gap: equity drives {equity_risk_pct:.0%} of portfolio risk"

Order red flags by estimated $ impact (highest first). Each gets: rank, flag (string), impact_est ("High"/"Medium"/"Low").

**Layer 3 — Macro Regime Sensitivity:**
For each of the 4 Dalio quadrants, estimate portfolio % impact range based on sector exposure and beta:
- Rising Growth + Low Inflation: base case if tech-heavy + high beta
- Rising Growth + Rising Inflation: estimate impact of energy/commodity weight
- Stagflation: harsh for tech-heavy, no-commodity portfolios; estimate -30% to -50% typical
- Deflation / Recession: worst case for high-beta equity portfolios; estimate -35% to -55%

**Layer 4 — Grades:**
Assign letter grades (A/B+/B/B-/C+/C/D/F) for:
- Diversification: based on HHI, avg correlation, sector concentration
- Risk-adjusted return: based on Sharpe vs SPY benchmark (SPY Sharpe ≈ 0.9)
- Macro resilience: based on regime sensitivity range — tighter = better
- Income quality: based on yield sustainability (not just level)
- Market alignment: based on current macro regime fit

**For each of the 4 restructuring plans:**
Generate `sell`, `buy`, `hold` tables and `rationale`:

For sell: positions to reduce/exit. Include tickers that are overconcentrated, add no diversification, or conflict with the plan's risk target.

For buy: use picks from context["picks"][plan_type]. Assign target % weights summing to 100% after sells. Calculate `dollars = total_value × pct`.

For hold: positions to keep unchanged. Brief reason.

Macro grid: estimate portfolio performance for each quadrant AFTER restructuring.

Fit grade: how well does this restructured portfolio fit the current macro regime?

Output the full `analysis` dict as a JSON code block — this is the canonical output that gets passed to the report and Obsidian modules.

### Step 2: Claude Analysis (Mode 2 only)

For build mode, produce a simpler `analysis` dict with:
- `construction_rationale`: explanation of why each position was chosen and how it fits the macro regime
- `red_flags`: any risks in the constructed portfolio (concentration, missing asset classes)
- `plans`: same structure as Mode 1 but with `buy` only (no sell/hold), `rationale` per plan

### Step 3: Generate HTML Report

Run:
```python
import sys
sys.path.insert(0, "/Users/robertliu/Documents/Claude Code Projects")
from portfolio_analyzer.report import generate_report
from datetime import date
import json

context = json.load(open("/Users/robertliu/Documents/Claude Code Projects/portfolio-analyzer/.analysis_context.json"))
# (or .build_context.json for Mode 2)

output_path = f"/Users/robertliu/Documents/Claude Code Projects/portfolio-reports/{date.today().isoformat()}-analysis.html"

generate_report(
    holdings=context["holdings"],
    macro=context["macro"],
    metrics=context["metrics"],
    picks=context["picks"],
    analysis=analysis,  # from Step 2
    output_path=output_path,
    mode=context["mode"]
)
```

### Step 4: Save Obsidian Note

```python
from portfolio_analyzer.obsidian import save_note
from datetime import date

save_note(
    holdings=context["holdings"],
    macro=context["macro"],
    metrics=context["metrics"],
    analysis=analysis,
    date_str=date.today().isoformat(),
    mode=context["mode"]
)
```

### Step 5: Terminal Summary

Print the terminal summary using `render_terminal_summary()` from `run_analyze.py` (Mode 1) or `_render_build_summary()` from `run_build.py` (Mode 2).

Then print:
```
→ HTML report: ~/portfolio-reports/{date}-analysis.html
→ Obsidian note: Trading/Portfolio Analysis/{date}-portfolio-review.md
```

## Error Handling

- If Python script fails: print the error, ask user to check the file format, offer to try Claude vision directly on the file
- If yfinance data is unavailable: the script handles this gracefully — metrics will note skipped tickers
- If Obsidian vault not found: print warning, skip Obsidian save, HTML report still generated
