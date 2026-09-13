# Projekt:Alpha MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes all of Projekt:Alpha's Kraken trading, quantitative analytics, backtesting, genetic optimization, and strategy orchestration capabilities to LLM clients — Claude Desktop, MCP Inspector, or any MCP-compatible host.

Built on the official [`@modelcontextprotocol/server`](https://github.com/modelcontextprotocol/typescript-sdk) v2 SDK (2026-07-28 spec).

## Architecture

```
LLM Client (Claude Desktop / Inspector / custom)
    │
    │  MCP protocol (stdio or Streamable HTTP)
    ▼
┌──────────────────────────────────────┐
│  Projekt:Alpha MCP Server            │
│  (mcp-server/src/)                   │
│                                      │
│  Tools:                              │
│  ├─ Dashboard & system status (6)    │
│  ├─ Market data & Kraken (5)         │
│  ├─ Strategy management (8)          │
│  ├─ Quant analytics (6)              │
│  ├─ Backtesting & optimizer (4)      │
│  └─ Worker bot swarm (6)             │
│                                      │
│  35 tools total                      │
└──────────┬───────────────────────────┘
           │  HTTP (REST)
           ▼
┌──────────────────────────────────────┐
│  FastAPI Backend (:8000)             │
│  Real Kraken execution engine        │
└──────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Node.js 20+
- The FastAPI backend running on port 8000

### Option 1: stdio (for Claude Desktop, MCP Inspector)

```bash
cd mcp-server
npm install
npx tsx src/index.ts
```

### Option 2: HTTP (Streamable HTTP transport)

```bash
cd mcp-server
npm install
npx tsx src/http-server.ts
# MCP endpoint: http://localhost:4100/mcp
```

### Option 3: MCP Inspector (interactive testing)

```bash
cd mcp-server
npm run inspect
# Opens the MCP Inspector UI in your browser
```

### Option 4: Docker Compose

The MCP server is included in `docker-compose.yml` and starts automatically:

```bash
docker compose up --build
# MCP endpoint: http://localhost:4100/mcp
```

## Claude Desktop Configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "projekt-alpha": {
      "command": "npx",
      "args": ["tsx", "/absolute/path/to/project-alpha/mcp-server/src/index.ts"],
      "env": {
        "ALPHA_BACKEND_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

## Available Tools (35)

### Dashboard & System (6)

| Tool | Description |
|------|-------------|
| `alpha_dashboard_status` | System status — execution mode, credentials, strategies, lake health |
| `alpha_health` | Quick health check — backend alive, WS connection, instance count |
| `alpha_kraken_status` | Kraken connection status — spot/futures auth, websocket state |
| `alpha_kraken_credentials` | Detailed Kraken API credentials configuration |
| `alpha_logs` | Latest system log entries from the execution engine |
| `alpha_queue_matrices` | Strategy queue matrices — all instances with state, P&L, M8 health |

### Market Data (5)

| Tool | Description |
|------|-------------|
| `alpha_market_data` | Current market data for a symbol — candles, OHLCV, indicators |
| `alpha_kraken_ledgers` | Kraken account ledger entries (requires credentials) |
| `alpha_futures_positions` | Current Kraken Futures positions (perps, margin, P&L) |
| `alpha_kraken_symbols` | Available trading symbols on Kraken |
| `alpha_backtest_ohlc` | OHLC candle data for backtesting |

### Strategy Management (8)

| Tool | Description |
|------|-------------|
| `alpha_strategies_list` | List all strategy instances (active, stopped, archived) |
| `alpha_strategy_templates` | Available strategy templates with gene spaces |
| `alpha_strategy_create` | Create a new strategy instance |
| `alpha_strategy_update` | Update strategy parameters |
| `alpha_strategy_delete` | Delete a strategy permanently |
| `alpha_strategy_archive` | Archive a strategy (soft-delete) |
| `alpha_strategy_restore` | Restore an archived strategy |
| `alpha_pnl_history` | P&L trade history for a strategy |
| `alpha_data_lake` | Data lake status — row counts, storage, sync time |

### Quantitative Analytics (6)

| Tool | Description |
|------|-------------|
| `alpha_quant_hurst` | Hurst exponent (DFA) — trending vs mean-reverting |
| `alpha_quant_regime` | Market regime classification (traffic-light Ampel) |
| `alpha_quant_lead_lag` | Cross-impact / lead-lag analysis across symbols |
| `alpha_quant_sentiment` | Funding-rate-based sentiment score |
| `alpha_quant_m8_judge` | M8 State Engine judgement (ACTIVE/THROTTLED/QUARANTINED) |
| `alpha_quant_watchdog` | Buffered watchdog events — anomalies and risk triggers |

### Backtesting & Optimization (4)

| Tool | Description |
|------|-------------|
| `alpha_backtest_run` | Run a backtest — equity curve, Sharpe, Sortino, Calmar, DSR |
| `alpha_backtest_analyze` | AI-assisted analysis — sensitivity, overfit detection (IS/OOS) |
| `alpha_genetic_run` | Genetic optimizer — Pareto-optimal genomes with walk-forward |
| `alpha_genetic_deploy` | Deploy optimized genome as live strategy |

### Worker Bot Swarm (6)

| Tool | Description |
|------|-------------|
| `alpha_workers_list` | List active worker bots |
| `alpha_workers_history` | List historical (stopped) workers |
| `alpha_workers_spawn` | Clone a historical bot as a new live worker |
| `alpha_workers_spawn_logic` | View a worker's spawn logic / entry criteria |
| `alpha_workers_toggle` | Toggle a worker between active/paused |
| `alpha_workers_delete` | Stop and delete a worker |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPHA_BACKEND_URL` | `http://127.0.0.1:8000` | URL of the FastAPI backend |
| `MCP_PORT` | `4100` | HTTP server port (HTTP mode only) |
| `MCP_HOST` | `0.0.0.0` | HTTP server bind address |

## Zero-Dummy Guarantee

Consistent with the rest of Projekt:Alpha, this MCP server returns **real data only**. When the backend is unreachable or credentials are missing, tools return explicit error messages — never fabricated data.

## Development

```bash
cd mcp-server
npm install
npm run typecheck    # TypeScript type checking
npm run dev          # Watch mode (auto-reload on changes)
npm run inspect      # MCP Inspector for interactive testing
```
