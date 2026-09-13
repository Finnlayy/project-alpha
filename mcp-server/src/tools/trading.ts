/**
 * Strategy & trading management MCP tools.
 */
import { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";
import { AlphaClient } from "../alphaClient.js";

export function registerTradingTools(server: McpServer, client: AlphaClient) {
  // ---------- list strategies ----------
  server.registerTool(
    "alpha_strategies_list",
    {
      description:
        "List all strategy instances — active, stopped, and archived. Includes P&L, M8 state, regime classification, and entry prices.",
    },
    async () => {
      try {
        const data = await client.get("/api/strategies");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- available strategy templates ----------
  server.registerTool(
    "alpha_strategy_templates",
    {
      description:
        "List available strategy templates — their code, parameters, gene spaces, and descriptions. Use this before creating a new strategy.",
    },
    async () => {
      try {
        const data = await client.get("/api/strategies/templates");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- create strategy ----------
  server.registerTool(
    "alpha_strategy_create",
    {
      description:
        "Create a new strategy instance (always starts in paper mode). Call alpha_strategy_templates first for valid template names and params.",
      inputSchema: {
        strategy: z.string().describe("Strategy template name — see alpha_strategy_templates (e.g. 'EMA_TREND_RSI')"),
        pair: z.string().default("BTC/USD").describe("Trading pair (e.g. 'BTC/USD')"),
        params: z.record(z.string(), z.any()).optional().describe("Strategy parameters — see strategy template for available params"),
        name: z.string().optional().describe("Instance display name"),
        interval: z.number().optional().describe("Bar interval in minutes (default: server default)"),
      },
    },
    async ({ strategy, pair, params, name, interval }) => {
      try {
        const data = await client.post("/api/strategies", {
          strategyType: strategy,
          assetPair: pair,
          parameters: params,
          name,
          interval,
        });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- update strategy ----------
  server.registerTool(
    "alpha_strategy_update",
    {
      description:
        "Update name/parameters of an existing strategy instance. Queue switches (paper<->live) only apply while the instance is stopped.",
      inputSchema: {
        sid: z.string().describe("Strategy instance ID"),
        params: z.record(z.string(), z.any()).optional().describe("Updated parameters"),
        name: z.string().optional().describe("Updated display name"),
        executionMode: z.enum(["paper", "live"]).optional().describe("Execution queue (only while stopped)"),
      },
    },
    async ({ sid, params, name, executionMode }) => {
      try {
        const data = await client.put(`/api/strategies/${sid}`, { parameters: params, name, executionMode });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- delete strategy ----------
  server.registerTool(
    "alpha_strategy_delete",
    {
      description: "Delete a strategy instance permanently.",
      inputSchema: {
        sid: z.string().describe("Strategy instance ID to delete"),
      },
    },
    async ({ sid }) => {
      try {
        const data = await client.delete(`/api/strategies/${sid}`);
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- archive strategy ----------
  server.registerTool(
    "alpha_strategy_archive",
    {
      description: "Archive a strategy instance (soft-delete — can be restored).",
      inputSchema: {
        sid: z.string().describe("Strategy instance ID to archive"),
      },
    },
    async ({ sid }) => {
      try {
        const data = await client.post(`/api/strategies/${sid}/archive`);
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- restore strategy ----------
  server.registerTool(
    "alpha_strategy_restore",
    {
      description: "Restore a previously archived strategy instance.",
      inputSchema: {
        sid: z.string().describe("Strategy instance ID to restore"),
      },
    },
    async ({ sid }) => {
      try {
        const data = await client.post(`/api/strategies/${sid}/restore`);
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- P&L history ----------
  server.registerTool(
    "alpha_pnl_history",
    {
      description: "Get P&L trade history for a strategy instance.",
      inputSchema: {
        strategyId: z.string().describe("Strategy instance ID"),
      },
    },
    async ({ strategyId }) => {
      try {
        const data = await client.get(`/api/pnl/history/${strategyId}`);
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- data lake summary ----------
  server.registerTool(
    "alpha_data_lake",
    {
      description:
        "Get the data lake status — table row counts, storage size, last sync time, and Parquet export info.",
    },
    async () => {
      try {
        const data = await client.get("/api/lake/summary");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );
}
