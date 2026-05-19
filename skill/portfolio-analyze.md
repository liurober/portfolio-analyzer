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

# Mode 2 — Build from scratch
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

---

## Instructions

### Step 0: Determine Mode

If args contain `--build`, run Mode 2. Otherwise run Mode 1.

**Mode 2 — always ask these 4 questions before running** (even if some flags were provided):
1. Total investment amount?
2. Risk profile? (aggressive / balanced / conservative / income)
3. Time horizon in years?
4. Investment goal? (growth / income / capital preservation / retirement / FIRE)

If the user already provided all 4 via flags, skip the questions and proceed directly.

---

### Step 1 (Mode 1): Run Python Orchestrator

```bash
cd /Users/robertliu && python portfolio-analyzer/run_analyze.py {file_path}
```

If the script exits with 0 positions parsed (output says `0 positions`), the PDF parser failed to extract tables. **Do not stop — fall back to Claude vision:** use the file content visible in session to manually build the holdings list and write it directly into the context JSON (see PDF Fallback below).

Read the context:
```bash
cat /Users/robertliu/portfolio-analyzer/.analysis_context.json
```

### Step 1 (Mode 2): Run Python Orchestrator

```bash
cd /Users/robertliu && python portfolio-analyzer/run_build.py --amount {amount} --profile {profile} --horizon {horizon} --goal {goal}
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

**You are acting as a Bridgewater-caliber senior portfolio manager. Every output must be institutional-grade: specific numbers, named tickers, dollar amounts, and multi-sentence explanatory paragraphs. Vague or brief outputs are unacceptable.**

Read the full context JSON before writing anything. The analysis dict must contain the following layers.

---

#### Layer 1 — Implicit Bet

- Examine ALL positions ranked by `weight × beta` (risk-weighted contribution)
- Identify the single macro thesis that connects the top risk contributors
- `implicit_bet` must be **3–4 full sentences minimum**, written as a professional investment memo paragraph:
  - Sentence 1: name the bet explicitly and which positions drive it
  - Sentence 2: quantify the exposure (e.g., "the top 3 positions represent X% of capital and contribute Y% of total portfolio risk")
  - Sentence 3: explain the macro dependency (what economic conditions must hold for this to work)
  - Sentence 4: state the tail risk — what a -20% drawdown in the top holding costs in dollars (`top_weight × 0.20 × total_value`)
- Example quality bar: "This portfolio is an unhedged high-conviction bet on continued AI infrastructure spending and semiconductor cycle expansion. NVDA (18.2%), SMCI (9.4%), and AMD (7.1%) together represent 34.7% of capital and an estimated 61% of total portfolio risk. The implicit thesis requires sustained enterprise AI capex growth, continued margin expansion in fab-light semiconductor models, and no material deterioration in the Fed's accommodative stance on technology credit. A 20% drawdown in NVDA alone would cost approximately $18,400 on a $142,300 portfolio — before any correlated selloff in the remaining AI names."

---

#### Layer 2 — Red Flags

Include only flags that actually apply. **Order by descending dollar impact.** Each flag must be a full explanatory sentence that names the specific ticker or sector, states the exact percentage, and estimates the dollar consequence. Do not write one-liners.

Required format per flag:
```python
{"rank": int, "flag": str, "impact_est": "High" | "Medium" | "Low"}
```

Trigger conditions and required sentence depth:
- **Position concentration** (single position > 10%): "Position concentration risk: {ticker} represents {pct}% of the portfolio (${value:,.0f}), making a 30% drawdown in this single name a ${impact:,.0f} hit — {pct * 1.5:.0f}% of the total portfolio value evaporates from one stock."
- **Sector concentration** (sector > 40%): "Sector concentration: the {sector} sleeve accounts for {pct}% of capital and an estimated {risk_pct}% of total portfolio risk; a sector-wide correction of 25% would cost approximately ${impact:,.0f}."
- **Cosmetic diversification** (avg correlation > 0.5): "Cosmetic diversification: the average pairwise correlation across holdings is {corr:.2f}, meaning positions move together during stress and the portfolio behaves like a {effective_n:.1f}-stock portfolio, not a {n}-stock one."
- **Stagflation blindspot** (no bonds/gold/commodity): "Stagflation blindspot: the portfolio holds zero fixed income, real assets, or commodity exposure; in a 1970s-style stagflation scenario, all equity positions would face simultaneous earnings compression and multiple contraction."
- **Yield trap** (any position yield > 8%): "{ticker} yields {pct}%, which is above the threshold typically associated with dividend sustainability risk; this level often signals payout ratios in excess of 90% or structural business deterioration."
- **Leverage risk** (beta > 1.5): "Portfolio beta of {beta:.2f} implies the portfolio will amplify a 10% market selloff into approximately a {10 * beta:.0f}% drawdown — ${impact:,.0f} of losses in a standard correction."
- **Risk parity gap** (equity risk > 90%): "Risk parity gap: equities drive {pct:.0f}% of total portfolio risk; the portfolio has no meaningful risk offset from bonds, real assets, or volatility hedges and will not benefit from flight-to-quality during risk-off regimes."

---

#### Layer 3 — Macro Regime Sensitivity

For each Dalio quadrant, provide a 2–3 sentence assessment of how the current portfolio performs, citing specific positions:
- Rising Growth + Low Inflation
- Rising Growth + Rising Inflation
- Stagflation
- Deflation / Recession

Include an estimated return range (e.g., "+12% to +24%") based on the portfolio's sector exposures and beta.

Store as a top-level key `macro_sensitivity` dict:
```python
"macro_sensitivity": {
  "Rising Growth + Low Inflation": str,     # 2-3 sentences + range
  "Rising Growth + Rising Inflation": str,
  "Stagflation": str,
  "Deflation / Recession": str,
}
```

---

#### Layer 4 — Grades

**Grades must be a dict with `grade` (letter) and `note` (2–3 sentence explanation).** Do NOT use plain strings.

```python
"grades": {
  "diversification":       {"grade": "C+", "note": "The portfolio holds 12 positions but 8 are in the Technology sector..."},
  "risk_adjusted_return":  {"grade": "B",  "note": "..."},
  "macro_resilience":      {"grade": "D",  "note": "..."},
  "income_quality":        {"grade": "C",  "note": "..."},
  "market_alignment":      {"grade": "B+", "note": "..."},
}
```

Grade scale: A / A- / B+ / B / B- / C+ / C / C- / D / F

The `note` for each grade must be 2–3 sentences that:
1. State the specific metric or observation driving the grade
2. Name at least one ticker or position that contributed to it
3. Explain what would need to change to earn a higher grade

---

#### Layer 5 — 4 Restructuring Plans

**Every plan must be institutionally complete. This is not a snapshot — every position in the portfolio must appear in exactly one of: `sell`, `buy`, or `hold`. No position may be omitted.**

Plan names: `aggressive`, `balanced`, `conservative`, `income`

**`rationale`** must be a 3–4 sentence paragraph that:
- Explains the philosophical stance of the plan
- States the primary macro regime it is optimized for
- Names the key positions being added or exited and why
- Quantifies the target risk profile (target beta, yield, asset allocation %)

**`sell` list** — for each position being reduced or exited:
```python
{
  "ticker":   str,
  "action":   "Exit" | "Reduce",
  "proceeds": float,    # dollars freed
  "reason":   str,      # 1 full sentence explaining the specific reason for this action
}
```

**`buy` list** — for each new or increased position:
```python
{
  "ticker":          str,
  "pct":             float,   # 0–1 decimal (e.g. 0.05 = 5%)
  "dollars":         float,
  "reason":          str,     # 1 full sentence — must name specific macro rationale or income rationale
  "tag":             str,     # "ETF" or "Stock"
  "est_annual_income": float, # REQUIRED for ALL plans — dollars (dollars × ticker's realistic yield)
}
```

**`est_annual_income` must be accurate** — use the ticker's actual dividend/coupon yield, not a generic plan rate:
- Bond ETFs (AGG, BND, TLT, LQD, HYG): 3.5–6.5% of dollars invested
- REIT ETFs (VNQ, SCHH) or REIT stocks: 3.5–5.0% of dollars invested
- Dividend equity ETFs (SCHD, VYM, HDV): 3.0–4.5% of dollars invested
- Growth ETFs (SPY, QQQ, VTI): 1.0–1.5% of dollars invested
- Individual growth stocks (AAPL, MSFT, NVDA): 0.0–1.5% of dollars invested
- Cash equivalents (SHV, BIL, SGOV): 4.5–5.2% of dollars invested
- Gold/commodity (GLD, IAU, GSG): 0% (no income)

Example: SCHD with $10,000 invested → est_annual_income = 350 (3.5% yield), not $70 (0.7% plan rate)

**`hold` list** — for every position not sold or bought:
```python
{"ticker": str, "reason": str}   # 1 sentence — do not write "no change needed", explain WHY it stays
```

**`macro_grid`** — exact keys, no variation:
```python
"macro_grid": {
  "Rising Growth + Low Inflation":    str,   # e.g. "+14% to +22%"
  "Rising Growth + Rising Inflation": str,
  "Stagflation":                      str,
  "Deflation / Recession":            str,
}
```

**`fit_grade`** — letter grade for how well this plan fits the current macro regime (e.g. "A-")

---

#### Output format

Output the full `analysis` dict as a JSON code block, then write it into the context:

```python
import json
ctx = json.load(open("/Users/robertliu/portfolio-analyzer/.analysis_context.json"))
ctx["analysis"] = analysis   # paste parsed dict here
json.dump(ctx, open("/Users/robertliu/portfolio-analyzer/.analysis_context.json","w"), indent=2)
```

The top-level structure of `analysis` must be:
```python
{
  "implicit_bet":        str,          # 3-4 sentence paragraph
  "drawdown_impact":     float,        # dollars
  "red_flags":           list[dict],
  "green_flags":         list[str],
  "macro_sensitivity":   dict,
  "grades":              dict[str, dict],
  "plans": {
    "aggressive":  { ... },
    "balanced":    { ... },
    "conservative":{ ... },
    "income":      { ... },
  }
}
```

---

### Step 2: Claude Analysis (Mode 2 only)

Produce the `analysis` dict with:
- `construction_rationale`: 3–4 sentence paragraph explaining why each sleeve was sized the way it was and how it fits the current macro regime
- `red_flags`: same structure as Mode 1
- `grades`: same dict-of-dicts structure as Mode 1
- `plans`: same structure as Mode 1 but `sell` and `hold` are empty lists; only `buy` populated (include `est_annual_income` in income plan buys)

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
- **Grades render as raw dicts in HTML**: the `report.html` template uses `{% set grade_letter = grade.grade if grade is mapping else grade %}` — if you see raw dicts, the template is stale; copy from `~/portfolio-analyzer/templates/report.html`
