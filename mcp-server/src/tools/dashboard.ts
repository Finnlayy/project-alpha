/**
 * Dashboard & system status MCP tools.
 */
import { McpServer } from "@modelcontextprotocol/server";
import { AlphaClient } from "../alphaClient.js";

export function registerDashboardTools(server: McpServer, client: AlphaClient) {
  // ---------- dashboard_init ----------
  server.registerTool(
    "alpha_dashboard_status",
    {
      description:
        "Get the Projekt:Alpha system status — execution mode, credentials state, active strategies, lake health, and live market feed status.",
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

  // ---------- health ----------
  server.registerTool(
    "alpha_health",
    {
      description: "Quick health check — backend alive, execution mode, WS connection, instance count.",
    },
    async () => {
      try {
        const data = await client.get("/api/health");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- kraken_status ----------
  server.registerTool(
    "alpha_kraken_status",
    {
      description:
        "Get Kraken connection status — spot/futures auth, websocket state, server time, and balance overview.",
    },
    async () => {
      try {
        const data = await client.get("/api/kraken/status");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- kraken_credentials_status ----------
  server.registerTool(
    "alpha_kraken_credentials",
    {
      description:
        "Get the detailed Kraken API credentials configuration status — which keys are set, their permissions, and domain info.",
    },
    async () => {
      try {
        const data = await client.get("/api/kraken/credentials-status");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- logs ----------
  server.registerTool(
    "alpha_logs",
    {
      description: "Get the latest system log entries from the execution engine.",
    },
    async () => {
      try {
        const data = await client.get("/api/logs");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- queue matrices ----------
  server.registerTool(
    "alpha_queue_matrices",
    {
      description:
        "Get the strategy queue matrices — all running strategy instances with their state, P&L, M8 health, and risk metrics.",
    },
    async () => {
      try {
        const data = await client.get("/api/queue-matrices");
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );
}
