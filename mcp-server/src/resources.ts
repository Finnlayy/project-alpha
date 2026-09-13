/**
 * MCP Resources — read-only data that LLM clients can browse.
 *
 * Resources expose live system state as URIs that clients can read.
 * They are distinct from tools (which perform actions).
 */
import { McpServer } from "@modelcontextprotocol/server";
import { AlphaClient } from "./alphaClient.js";

export function registerResources(server: McpServer, client: AlphaClient) {
  // ---------- system status ----------
  server.registerResource(
    "system-status",
    "alpha://system/status",
    {
      title: "System Status",
      description: "Current Projekt:Alpha system status — execution mode, credentials, active strategies.",
      mimeType: "application/json",
    },
    async () => {
      try {
        const data = await client.get("/api/dashboard/init");
        return {
          contents: [
            {
              uri: "alpha://system/status",
              mimeType: "application/json",
              text: JSON.stringify(data, null, 2),
            },
          ],
        };
      } catch (e: any) {
        return {
          contents: [
            {
              uri: "alpha://system/status",
              mimeType: "application/json",
              text: JSON.stringify({ error: e.message, backend: "unreachable" }),
            },
          ],
        };
      }
    }
  );

  // ---------- active strategies ----------
  server.registerResource(
    "active-strategies",
    "alpha://strategies/active",
    {
      title: "Active Strategies",
      description: "All currently active strategy instances with their state, P&L, and M8 health.",
      mimeType: "application/json",
    },
    async () => {
      try {
        const data = await client.get("/api/strategies");
        return {
          contents: [
            {
              uri: "alpha://strategies/active",
              mimeType: "application/json",
              text: JSON.stringify(data, null, 2),
            },
          ],
        };
      } catch (e: any) {
        return {
          contents: [
            {
              uri: "alpha://strategies/active",
              mimeType: "application/json",
              text: JSON.stringify({ error: e.message }),
            },
          ],
        };
      }
    }
  );

  // ---------- active workers ----------
  server.registerResource(
    "active-workers",
    "alpha://workers/active",
    {
      title: "Active Worker Bots",
      description: "All currently active worker bots in the swarm.",
      mimeType: "application/json",
    },
    async () => {
      try {
        const data = await client.get("/api/quant/workers");
        return {
          contents: [
            {
              uri: "alpha://workers/active",
              mimeType: "application/json",
              text: JSON.stringify(data, null, 2),
            },
          ],
        };
      } catch (e: any) {
        return {
          contents: [
            {
              uri: "alpha://workers/active",
              mimeType: "application/json",
              text: JSON.stringify({ error: e.message }),
            },
          ],
        };
      }
    }
  );

  // ---------- kraken status ----------
  server.registerResource(
    "kraken-status",
    "alpha://kraken/status",
    {
      title: "Kraken Connection Status",
      description: "Kraken API connection status — spot/futures auth, websocket state, server time.",
      mimeType: "application/json",
    },
    async () => {
      try {
        const data = await client.get("/api/kraken/status");
        return {
          contents: [
            {
              uri: "alpha://kraken/status",
              mimeType: "application/json",
              text: JSON.stringify(data, null, 2),
            },
          ],
        };
      } catch (e: any) {
        return {
          contents: [
            {
              uri: "alpha://kraken/status",
              mimeType: "application/json",
              text: JSON.stringify({ error: e.message }),
            },
          ],
        };
      }
    }
  );

  // ---------- system health ----------
  server.registerResource(
    "system-health",
    "alpha://system/health",
    {
      title: "System Health",
      description: "Quick health check — backend status, execution mode, WS connection, instance count.",
      mimeType: "application/json",
    },
    async () => {
      try {
        const data = await client.get("/api/health");
        return {
          contents: [
            {
              uri: "alpha://system/health",
              mimeType: "application/json",
              text: JSON.stringify(data, null, 2),
            },
          ],
        };
      } catch (e: any) {
        return {
          contents: [
            {
              uri: "alpha://system/health",
              mimeType: "application/json",
              text: JSON.stringify({ error: e.message, healthy: false }),
            },
          ],
        };
      }
    }
  );
}
