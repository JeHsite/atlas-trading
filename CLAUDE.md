# Atlas — notes for Claude

Personal multi-asset research & trading system for one retail investor's own account.
Markets: US, Israel (TASE), Europe, China/HK. Assets: equities, ETFs, bonds, crypto, FX.

## Non-negotiable principles
1. LLMs never calculate numbers. Prices, indicators, ratios, sizes and P&L are computed in
   deterministic Python and passed to the model as data.
2. LLMs never place orders. Model output is a `TradeProposal`; `atlas.risk.evaluate` approves
   or rejects it; only an approved `RiskDecision` may reach execution.
3. Paper trading by default. Live needs `ATLAS_LIVE_TRADING=true` plus
   `ATLAS_LIVE_TRADING_CONFIRM` set to the phrase in `atlas/config.py`. `ATLAS_KILL_SWITCH`
   halts everything.
4. All external text goes through `atlas.untrusted.wrap_untrusted` before reaching a model.
5. Every decision is logged (see `db/schema.sql`).
6. Every module has tests; a phase is done only when `uv run pytest` and `uv run ruff check .`
   pass.

## Models
- `claude-haiku-5-5`: bulk screening, news classification, document summaries.
- `claude-opus-5-5`: deep analysis and trade proposals (adaptive thinking; effort `high` for
  deep dives, `medium` for routine). Prompt caching for static prompts, Batch API overnight.

## Commands
- `uv run pytest` — tests
- `uv run ruff check . && uv run ruff format --check .` — lint
- `docker compose up -d` — TimescaleDB + Redis

## Roadmap
1. ✅ Skeleton, config, domain types, risk engine, market calendars, schema, data interfaces
2. Technical/quant engine + backtester + walk-forward validation
3. LLM analysis layer (screening, earnings, central-bank speeches, macro, daily report)
4. Signal fusion + portfolio construction
5. Paper execution (IBKR paper, crypto testnet), reconciliation
6. Dashboard, Telegram alerts, Hebrew reports, cost monitor
7. Hardening and monitoring
