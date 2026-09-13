/**
 * Market data MCP tools — Kraken spot/futures, live WS feed, ledgers.
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
        "Get current market data for a symbol pair — includes candles from the data lake or live Kraken API, OHLCV data, and technical indicators.",
      inputSchema: {
        symbol: z.string().default("BTC/USD").describe("Trading pair, e.g. BTC/USD, ETH/USD, SOL/USD"),
        interval: z.number().default(5).describe("Candle interval in minutes: 1, 5, 15, 60, 240, 1440"),
        count: z.number().default(100).describe("Number of candles to return"),
      },
    },
    async ({ symbol, interval, count }) => {
      try {
        const data = await client.get("/api/market-data", { symbol, interval, count });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
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
        "Get Kraken account ledger entries — deposits, withdrawals, trades, fees, and balance changes. Requires configured Kraken API credentials.",
      inputSchema: {
        asset: z.string().optional().describe("Filter by asset class (e.g. XBT, ETH, USD). Omit for all."),
        limit: z.number().default(50).describe("Maximum number of entries to return"),
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
        "Get current Kraken Futures positions — perpetual contracts with margin, unrealized P&L, leverage, and liquidation price.",
    },
    async () => {
      try {
        const data = await client.get("/api/kraken/positions/pro");
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
        "List available trading symbols on Kraken — both spot and futures pairs with their metadata.",
    },
    async () => {
      try {
        const data = await client.get("/api/kraken/symbols");
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
