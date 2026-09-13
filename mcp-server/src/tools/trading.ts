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
        const data = await client.get("/api/strategies");
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
        "Create a new strategy instance. Requires passkey-gated session for live trading mode.",
      inputSchema: {
        strategy: z.string().describe("Strategy template name (e.g. 'momentum_crossover', 'mean_reversion')"),
        pair: z.string().describe("Trading pair (e.g. 'BTC/USD', 'ETH/USD.P')"),
        params: z.record(z.string(), z.any()).optional().describe("Strategy parameters — see strategy template for available params"),
      },
    },
    async ({ strategy, pair, params }) => {
      try {
        const data = await client.post("/api/strategies", { strategy, pair, params });
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
      description: "Update parameters of an existing strategy instance.",
      inputSchema: {
        sid: z.string().describe("Strategy instance ID"),
        params: z.record(z.string(), z.any()).describe("Updated parameters"),
      },
    },
    async ({ sid, params }) => {
      try {
        const data = await client.put(`/api/strategies/${sid}`, { params });
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
        const data = await client.get("/api/dashboard/init");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );
}
