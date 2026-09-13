/**
 * Projekt:Alpha MCP Server factory.
 *
 * Builds and returns a fully-configured McpServer with all Projekt:Alpha
 * tools, resources, and prompts registered. Supports both stdio (Claude
 * Desktop, inspector) and HTTP (Streamable HTTP) transports.
 */
import { McpServer } from "@modelcontextprotocol/server";
import { AlphaClient } from "./alphaClient.js";
import { registerDashboardTools } from "./tools/dashboard.js";
import { registerMarketTools } from "./tools/market.js";
import { registerTradingTools } from "./tools/trading.js";
import { registerQuantTools } from "./tools/quant.js";
import { registerBacktestTools } from "./tools/backtest.js";
import { registerWorkerTools } from "./tools/workers.js";
import { registerResources } from "./resources.js";
import { registerPrompts } from "./prompts.js";

export function createAlphaServer(): McpServer {
  const client = new AlphaClient();
  const server = new McpServer({
    name: "projekt-alpha",
    version: "2.0.0",
  });

  // Register all tool categories (35 tools)
  registerDashboardTools(server, client);
  registerMarketTools(server, client);
  registerTradingTools(server, client);
  registerQuantTools(server, client);
  registerBacktestTools(server, client);
  registerWorkerTools(server, client);

  // Register resources (live data endpoints)
  registerResources(server, client);

  // Register prompts (pre-built analysis workflows)
  registerPrompts(server);

  return server;
}
