/**
 * Worker bot swarm MCP tools — spawn, stop, query, clone from history.
 */
import { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";
import { AlphaClient } from "../alphaClient.js";

export function registerWorkerTools(server: McpServer, client: AlphaClient) {
  // ---------- list workers ----------
  server.registerTool(
    "alpha_workers_list",
    {
      description:
        "List all active worker bots in the swarm — their state, pair, strategy, P&L, M8 health, and uptime.",
    },
    async () => {
      try {
        const data = await client.get("/api/quant/workers");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- worker history ----------
  server.registerTool(
    "alpha_workers_history",
    {
      description:
        "List historical (stopped/archived) worker bots — useful for finding profitable sessions to clone.",
    },
    async () => {
      try {
        const data = await client.get("/api/quant/workers/history");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- spawn from history ----------
  server.registerTool(
    "alpha_workers_spawn",
    {
      description:
        "Clone a verified historical bot session as a new live worker. " +
        "Parameters can be adapted via 'modifier' to adjust to current market conditions.",
      inputSchema: {
        historicalBotId: z.string().describe("ID of the historical bot to clone (e.g. 'BOT-HIST-7742')"),
        modifier: z
          .record(z.string(), z.any())
          .optional()
          .describe("Optional parameter overrides (e.g. { leverage: 3, name: 'Adapted v2' })"),
      },
    },
    async ({ historicalBotId, modifier }) => {
      try {
        const data = await client.post("/api/quant/workers/spawn-from-history", {
          historical_bot_id: historicalBotId,
          modifier,
        });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- spawn logic (read-only) ----------
  server.registerTool(
    "alpha_workers_spawn_logic",
    {
      description:
        "View the strategy logic / entry criteria that a worker bot was spawned with.",
      inputSchema: {
        botId: z.string().describe("Worker bot ID"),
      },
    },
    async ({ botId }) => {
      try {
        const data = await client.get(`/api/quant/workers/${botId}/spawn-logic`);
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- toggle worker ----------
  server.registerTool(
    "alpha_workers_toggle",
    {
      description: "Toggle a worker bot between active and paused states.",
      inputSchema: {
        botId: z.string().describe("Worker bot ID"),
      },
    },
    async ({ botId }) => {
      try {
        const data = await client.post(`/api/quant/workers/${botId}/toggle`);
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- delete worker ----------
  server.registerTool(
    "alpha_workers_delete",
    {
      description: "Stop and permanently delete a worker bot.",
      inputSchema: {
        botId: z.string().describe("Worker bot ID to delete"),
      },
    },
    async ({ botId }) => {
      try {
        const data = await client.delete(`/api/quant/workers/${botId}`);
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );
}
