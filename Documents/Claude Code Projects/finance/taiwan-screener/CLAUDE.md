# Taiwan Screener — Project Notes

This project is fully isolated from `finance/stock-screener/`. Do NOT import across the two.

## Conventions (Taiwan)
- Ticker format: `NNNN.TW` (TWSE) — Phase 1 is TWSE only
- 1 lot = 1,000 shares
- Currency display: `NT${value:.2f}`
- Candle colors are SWAPPED from US: RED `#e53935` = bull/up/漲, GREEN `#43a047` = bear/down/跌
- All user-facing strings: Traditional Chinese (繁體中文)
- All long-only trades. No short side.

## Workflow
- `main.py` runs weekly (Sun 7am PT via GitHub Actions). Loads `backtest/optimal_params.json` for live parameters.
- `analyze_tw.py <TICKER>` produces a single-stock HTML+PDF report.
- `backtest/engine.py` + `backtest/optimizer.py` run monthly (1st @ 6am PT) — walk-forward + Monte Carlo → writes new `optimal_params.json`.

## Email rules (Gmail-safe — PERMANENT, do not regress)
- HTML `<table>` layout only — no grid/flex
- Inline styles only — no `<style>` block
- Charts as CID inline attachments — no `data:` URIs
- Total payload < 102KB

## Optimizer targets
- Win rate ≥ 80% (profitable_rate = PnL > 0 / total trades)
- Avg return on winning picks ≥ 10% (avg_win_return_pct)
- Overall avg return > 0% (avg_return_pct across all trades)
- Hold period: 5–6 weeks

## Win rate definition
`win_rate` in `summarize()` = **profitable_rate**: fraction of trades where `pnl_pct > 0`.
`strict_win_rate` = fraction where the strict target was hit within `hold_weeks`.
The optimizer optimizes for `win_rate` (profitable_rate) — this is the 80% target.

## Market regime filter
`require_index_regime: True` in params → `engine.simulate()` only enters a trade
if 0050.TW (Taiwan 50 ETF) close is above its 52-week (52-bar) weekly MA.
`main.py` honors this at the start of the weekly scan and skips the entire scan
when the market is in a downtrend.

## Key parameter notes
- `max_price` in PARAM_SPACE: must cover TSMC (~2255 NT$) and MediaTek (~3860 NT$).
  Current range: [500, 1000, 2000, 5000]. Do NOT reduce below 2000.
- `require_index_regime`: new in optimizer — highly recommended. Filters out
  bear-market false positives that drag profitable_rate below 60%.
