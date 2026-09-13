# Projekt:Alpha — Kraken Pro Execution System (v2.0)

A live-trading orchestration stack for **Kraken Spot** and **Kraken Futures (Pro)**:
real strategy execution, real quant analytics, a real genetic optimizer and a
real DuckDB data lake — with a single iron rule:

> **Zero-Dummy Guarantee.** No endpoint, panel or engine returns fabricated
> data. When a source (Kraken feed, credentials, candles) is unavailable the
> system reports an explicit `offline / not_configured / insufficient data`
> state (HTTP 424/503 or an empty payload) instead of inventing numbers.

---

## What is real here

| Subsystem | Implementation | Verification |
|---|---|---|
| Kraken Spot REST | `app/kraken/spot_client.py` — official `API-Sign` = base64(HMAC-SHA512(base64_decode(secret), path + SHA256(nonce + post_data))) | bit-exact vs. Kraken's published worked example (`tests/test_kraken_clients.py`) |
| Kraken Futures v3 | `app/kraken/futures_client.py` — official `Authent` (auth flow of 2024-02-20) = base64(HMAC-SHA512(base64_decode(secret), SHA256(postData + nonce + endpointPath))), `endpointPath` without `/derivatives` | bit-exact vs. an independent transcription of the 5 documented steps |
| Live market feed | `app/kraken/ws_service.py` — `wss://ws.kraken.com/v2`, ticker + ohlc-v1, heartbeat pings, exponential reconnect | SSE `/api/kraken/stream` |
| Trading engine | `app/execution/trading_engine.py` — per-instance loops: strategy → M8 gate → churn guard + fee hurdle → leverage sizing → fill → autopsy → vault | integration tests (`tests/test_trading_engine.py`) |
| M8 state machine | `app/execution/M8StateEngine.py` — ACTIVE/THROTTLED/QUARANTINED, budget multiplier, post-trade update | unit tests |
| Backtester | `app/backtest/engine.py` — next-bar-open fills, maker/taker fees, slippage, funding (perps), MFE/MAE, intra-bar stops | no-lookahead prefix-consistency test |
| Metrics | `app/backtest/metrics.py` — Sharpe, Sortino, Calmar, max-DD, profit factor, **Deflated Sharpe Ratio** (Bailey & López de Pedraza) | golden tests |
| Genetic optimizer | `app/optimizer/genetic.py` — elitism, tournament, blend crossover, Gaussian mutation, Pareto front, walk-forward IS/OOS, deterministic seeds | determinism + OOS tests |
| Quant math | `app/quant/*` — DFA Hurst (Kantelhardt), ADX/ATR/RSI (Wilder), regime Ampel, cross-correlation lead-lag, funding-based sentiment | property/golden tests |
| Data lake | `app/storage/lake.py` — DuckDB (candles, trades, instances, vault ledger, M8 state, events) + atomic Parquet export | round-trip tests |
| WebAuthn | `app/crypto/webauthn.py` — real FIDO2: COSE keys, challenge/origin checks, `none`/`packed` attestation, ES256/RS256 assertion verification, signCount anti-clone | spec-compliant simulated-browser round-trip |
| Sessions | `app/auth/session.py` — HMAC-SHA256 signed tokens, revocation, TTL | round-trip/expiry tests |
| API | `app/api/routes.py` + `app/main.py` — FastAPI, all ~50 UI endpoints, SSE telemetry, passkey-gated mutations | live smoke tests |
| UI | React dashboard — all data comes from the real backend; explicit offline/error states, no mock fallbacks | `npx tsc --noEmit` |
| MCP Server | `mcp-server/` — TypeScript MCP server (v2 SDK, 2026-07-28 spec), 59 tools + 5 resources + 4 prompts over stdio/HTTP | `npm run type-check:mcp` |

**What is NOT here (honestly):** there is no LLM/"AI model" — every panel
labeled "AI" runs deterministic statistical diagnostics (sensitivity re-runs,
IS/OOS overfit checks, genome aggregation). Live trading requires your own
Kraken API keys; without keys the engine runs in **paper mode** with real
market data (or idles with an explicit "waiting for market data" state).

---

## Quick start (local)

Prerequisites: Python 3.10+, Node 20+.

```bash
# 1. Backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # optional: add real Kraken API keys

# 2. Run both (backend :8000, frontend :3000 with /api proxy)
./bin/run.sh

# 3. Control the engine
python3 bin/m8-ctl status
python3 bin/m8-ctl sync       # pull real Kraken candles into the lake
python3 bin/m8-ctl logs 30
```

Open **http://localhost:3000**. Register a passkey in the UI (or via the
`/api/v1/auth/passkey/*` endpoints); the session token then gates live-mode
switch, `cancel-all`, state overrides and history reset.

## Quick start (Docker)

```bash
cp .env.example .env          # add real keys if you have them
docker compose up --build
# frontend: http://localhost:3000   backend: http://localhost:8000   MCP: http://localhost:4100/mcp
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q      # deterministic suite, no network needed
npm run type-check                        # React UI gate (root tsconfig, src/ only)
npm run type-check:mcp                    # MCP server gate (mcp-server/tsconfig.json)
npm run type-check:all                    # both
npx vite build                            # production build of the dashboard
```

The root `tsconfig.json` deliberately covers **only** the React UI (`src/`,
`vite.config.ts`); `mcp-server/` is a separate package with its own tsconfig and
dependencies, so it is type-checked by `type-check:mcp`.

Test notes:
- Kraken is not reachable from all CI/sandbox environments; the signing
  schemes are verified against the documented spec (independent reference
  implementations), and every network layer has explicit offline paths.
- Backtest/optimizer tests use deterministic synthetic candles **as fixtures**
  (standard practice) — the engines themselves only ever consume whatever
  candles they are given, and in production that means real Kraken OHLC.

## MCP Server (LLM Integration)

The `mcp-server/` directory contains a [Model Context Protocol](https://modelcontextprotocol.io) server built on the official [`@modelcontextprotocol/server`](https://github.com/modelcontextprotocol/typescript-sdk) v2 SDK. It exposes all of Projekt:Alpha's capabilities — Kraken trading, quant analytics, backtesting, genetic optimization, and strategy orchestration — to LLM clients like Claude Desktop.

```bash
# stdio mode (for Claude Desktop / MCP Inspector)
cd mcp-server && npm install && npx tsx src/index.ts

# HTTP mode (Streamable HTTP on :4100)
cd mcp-server && npx tsx src/http-server.ts

# MCP Inspector (interactive testing)
cd mcp-server && npm run inspect
```

**59 tools**, **5 resources** (`alpha://system/status`, `alpha://system/health`, `alpha://strategies/active`, `alpha://workers/active`, `alpha://kraken/status`), and **4 prompts** (`analyze-market`, `backtest-strategy`, `optimize-deploy`, `system-diagnostics`) covering:
- Dashboard & system status (health, credentials, logs, queue matrices)
- Market data (OHLC, ledgers, futures positions, symbols)
- Strategy management (create, update, archive, restore, P&L)
- Quantitative analytics (Hurst DFA, regime, sentiment, M8 judge, watchdog)
- Backtesting & genetic optimization (run, analyze, optimize, deploy)
- Worker bot swarm (list, spawn from history, toggle, delete)

See [`mcp-server/README.md`](mcp-server/README.md) for full details and Claude Desktop configuration.

## Execution model

```
Kraken WS v2 / REST OHLC ──► candles (DuckDB lake + WS cache)
        │
        ▼
per-instance loop (real strategy code, app/strategies/registry.py)
        │
        ├─ M8 state gate (budget multiplier, quarantine)
        ├─ TradeChurnGuard (cooldown, daily cap, fee hurdle)
        ├─ LeverageEngine (sizing, max-leverage caps)
        ▼
PAPER: deterministic fill at live mark ± slippage, ledger in DuckDB
LIVE:  real Kraken order via the signed clients (passkey-gated mode switch)
        │
        ▼
close → AutopsyProcessor (zones, R-multiple, MFE/MAE capture)
      → M8 budget update → profit sweep → vault_ledger
      → events → SSE telemetry → UI
```

## Repository layout

```
app/
  main.py               FastAPI entrypoint (uvicorn app.main:app)
  config.py             env-driven settings (no hardcoded secrets)
  kraken/               real Spot + Futures v3 clients, WS v2 feed
  quant/                DFA Hurst, indicators, regime, lead-lag, sentiment
  backtest/             event-driven backtester + real metrics (DSR)
  optimizer/            genetic walk-forward optimizer + fitness guardrails
  strategies/           real strategy implementations + gene spaces
  execution/            M8 state, leverage, fees, churn guard, autopsy,
                        StorageUtils, QuantOrchestrator, TradingEngine
  storage/              DuckDB lake (candles, trades, vault, state, events)
  crypto/               real WebAuthn (COSE, attestation, assertions)
  auth/                 HMAC session tokens
  api/                  routes (~50 endpoints the UI consumes) + app state
  telegram/             real Bot API HTTP client (optional notifications)
  security/             real .env manager (SettingsEnvManager)
  mcp/                  Python MCP bridge wired to the real clients
mcp-server/
  src/index.ts          stdio transport entry point
  src/http-server.ts    Streamable HTTP transport entry point (:4100)
  src/server.ts         McpServer factory (59 tools + 5 resources + 4 prompts)
  src/alphaClient.ts    HTTP client proxying to the FastAPI backend
  src/tools/            tool registrations (dashboard, market, trading, quant, backtest, workers)
  src/resources.ts      MCP resources (system status, strategies, workers, kraken)
  src/prompts.ts        MCP prompts (market analysis, backtest, diagnostics, optimize)
bin/
  run.sh                local runner (venv + uvicorn + vite + mcp)
  m8-ctl                control CLI (status/halt/resume/cancel-all/sync/logs)
tests/                  pytest suite (deterministic)
src/                    React dashboard (all data from the real backend)
```

## Operating notes

- **Mode switch to live** requires a verified passkey session and configured
  Kraken credentials; the switch is refused otherwise (HTTP 401/412).
- **Funding & liquidation** figures for perps come from the live futures API
  when credentials exist; otherwise the UI shows `unconfigured` — never
  placeholder numbers.
- **Credentials** are read from `.env` (`cp .env.example .env`). Every
   variable is optional: with none set, the UI shows `not_configured` and the
   private endpoints answer 412/424 — no key preview or balance is ever
   invented.
- **Lake data** lives in `data/` (gitignored). `bin/m8-ctl sync` ingests real
  candles; `/api/lake/compact` checkpoints DuckDB; Parquet export is atomic.
- `setup_alpha.py` is the **frozen legacy v1.6.4 skeleton bootstrap**. Its
   barrier is the first executable statement in the script, so nothing is
   written before it decides: it refuses by default, refuses to target the
   repository (or any parent of it), and refuses any target that already
   contains v2.0 production code (`app/main.py`, `app/kraken/spot_client.py`,
   `app/storage/lake.py`, `.git`). The only permitted use is writing the
   historical scaffold to a fresh non-repository path with the explicit
   `--i-understand-this-is-the-frozen-v1.6.4-skeleton` flag. Enforced by
   `tests/test_legacy_barrier.py`.
