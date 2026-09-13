/**
 * Quantitative analytics MCP tools — Hurst, regime, sentiment, M8 judge.
 */
import { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";
import { AlphaClient } from "../alphaClient.js";

export function registerQuantTools(server: McpServer, client: AlphaClient) {
  // ---------- Hurst exponent (DFA) ----------
  server.registerTool(
    "alpha_quant_hurst",
    {
      description:
        "Compute the Hurst exponent via Detrended Fluctuation Analysis (DFA) for a given symbol. " +
        "H > 0.5 = persistent/trending, H < 0.5 = mean-reverting, H ≈ 0.5 = random walk.",
      inputSchema: {
        symbol: z.string().default("BTC/USD").describe("Trading pair to analyze"),
      },
    },
    async ({ symbol }) => {
      try {
        const data = await client.get("/api/quant/dfa/hurst", { symbol });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- regime classification ----------
  server.registerTool(
    "alpha_quant_regime",
    {
      description:
        "Classify the current market regime for a symbol — outputs a traffic-light (Ampel) signal " +
        "with regime type (persistent_trending, mean_reverting, high_volatility, etc.) and confidence.",
      inputSchema: {
        symbol: z.string().default("BTC/USD").describe("Trading pair to analyze"),
      },
    },
    async ({ symbol }) => {
      try {
        const data = await client.get("/api/quant/regime/ampel", { symbol });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- lead-lag cross impact ----------
  server.registerTool(
    "alpha_quant_lead_lag",
    {
      description:
        "Compute cross-impact / lead-lag analysis across tracked symbols. " +
        "Identifies which symbols lead price movements and which lag — useful for pair trading and hedging.",
    },
    async () => {
      try {
        const data = await client.get("/api/quant/lead-lag/cross-impact");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- sentiment score ----------
  server.registerTool(
    "alpha_quant_sentiment",
    {
      description:
        "Get the funding-rate-based sentiment score for a symbol. " +
        "Positive = longs paying shorts (bullish crowding), negative = shorts paying longs (bearish crowding).",
      inputSchema: {
        symbol: z.string().default("BTC/USD").describe("Trading pair to analyze"),
      },
    },
    async ({ symbol }) => {
      try {
        const data = await client.get("/api/quant/sentiment/score", { symbol });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- M8 judge ----------
  server.registerTool(
    "alpha_quant_m8_judge",
    {
      description:
        "Get the M8 State Engine judgement for a strategy instance (or the global state). " +
        "Returns ACTIVE/THROTTLED/QUARANTINED status, budget multiplier, risk assessment, and reasoning.",
      inputSchema: {
        instance: z.string().optional().describe("Specific strategy instance ID. Omit for global state."),
      },
    },
    async ({ instance }) => {
      try {
        const data = await client.get("/api/quant/execution/m8-judge", { instance });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- watchdog buffered events ----------
  server.registerTool(
    "alpha_quant_watchdog",
    {
      description:
        "Get buffered watchdog events — anomalies, risk triggers, and execution guard violations captured by the system.",
    },
    async () => {
      try {
        const data = await client.get("/api/quant/watchdog/buffered-events");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );
}
