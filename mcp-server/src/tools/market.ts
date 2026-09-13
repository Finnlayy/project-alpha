/**
 * Market data MCP tools — live tickers, OHLC candles, ledgers, symbols.
 *
 * Wiring notes (backend contract):
 * - GET /api/market-data?symbols=A,B returns the L1 ticker LIST (no candles).
 * - GET /api/backtest/ohlc?pair=&interval=&count= returns OHLC candles.
 * - GET /api/kraken/symbols?venue=spot|futures|all returns the catalog.
 * - GET /api/kraken/ledgers?asset=&limit= returns enriched spot+pro ledgers.
 * - GET /api/kraken/positions/pro returns the normalized futures margin overview.
 */
import { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";
import { AlphaClient } from "../alphaClient.js";

export function registerMarketTools(server: McpServer, client: AlphaClient) {
  // ---------- market data ----------
  server.registerTool(
    "alpha_market_data",
    {
      description:
        "Get live L1 market tickers (price, 24h change, high/low, volume) for tracked pairs. " +
        "Set includeCandles=true to also fetch OHLC candles for one pair.",
      inputSchema: {
        symbols: z.string().optional().describe("Comma-separated filter, e.g. 'BTC/USD,ETH/USD'. Omit for all tracked pairs."),
        includeCandles: z.boolean().default(false).describe("Also fetch OHLC candles (requires 'pair' — tickers carry no candles)."),
        pair: z.string().default("BTC/USD").describe("Pair for candles when includeCandles=true"),
        interval: z.number().default(5).describe("Candle interval in minutes: 1, 5, 15, 30, 60, 240, 1440"),
        count: z.number().default(100).describe("Number of candles to return"),
      },
    },
    async ({ symbols, includeCandles, pair, interval, count }) => {
      try {
        const tickers = await client.get("/api/market-data", symbols ? { symbols } : undefined);
        if (!includeCandles) {
          return { content: [{ type: "text", text: JSON.stringify(tickers, null, 2) }] };
        }
        const candles = await client.get("/api/backtest/ohlc", { pair, interval, count });
        return {
          content: [{ type: "text", text: JSON.stringify({ tickers, candles }, null, 2) }],
        };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- kraken ledgers ----------
  server.registerTool(
    "alpha_kraken_ledgers",
    {
      description:
        "Get Kraken account ledgers — enriched spot balances (valuations, 24h change, in-order locks) " +
        "and futures margin overview with marked-to-market positions. Requires configured Kraken API credentials; " +
        "returns explicit configured:false + error otherwise (never fabricated data).",
      inputSchema: {
        asset: z.string().optional().describe("Filter spot assets by code (e.g. BTC, ETH). Omit for all."),
        limit: z.number().optional().describe("Cap the number of assets/positions returned."),
      },
    },
    async ({ asset, limit }) => {
      try {
        const data = await client.get("/api/kraken/ledgers", { asset, limit });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- futures positions ----------
  server.registerTool(
    "alpha_futures_positions",
    {
      description:
        "Get the normalized Kraken Futures margin overview — collateral, free/used margin, margin level, " +
        "effective leverage, and open perpetual positions with mark prices and unrealized P&L.",
      inputSchema: {
        limit: z.number().optional().describe("Cap the number of positions returned."),
      },
    },
    async ({ limit }) => {
      try {
        const data = await client.get("/api/kraken/positions/pro", { limit });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- kraken symbols ----------
  server.registerTool(
    "alpha_kraken_symbols",
    {
      description:
        "List the Kraken + Kraken Pro symbol catalog — spot pairs with precision/leverage metadata and " +
        "futures instruments with contract specs. Public endpoint, no credentials needed.",
      inputSchema: {
        venue: z.enum(["spot", "futures", "all"]).default("all").describe("Which venue catalog to return"),
      },
    },
    async ({ venue }) => {
      try {
        const data = await client.get("/api/kraken/symbols", { venue });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- backtest OHLC ----------
  server.registerTool(
    "alpha_backtest_ohlc",
    {
      description:
        "Get OHLC candle data suitable for backtesting — from the data lake or live Kraken API.",
      inputSchema: {
        pair: z.string().default("BTC/USD").describe("Trading pair"),
        interval: z.number().default(5).describe("Candle interval in minutes"),
        count: z.number().default(300).describe("Number of candles"),
      },
    },
    async ({ pair, interval, count }) => {
      try {
        const data = await client.get("/api/backtest/ohlc", { pair, interval, count });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );
}
