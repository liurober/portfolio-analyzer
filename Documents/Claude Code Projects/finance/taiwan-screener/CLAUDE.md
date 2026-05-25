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
- Win rate ≥ 80%
- Avg return per trade: 20–30%
- Hold period: 5–6 weeks
