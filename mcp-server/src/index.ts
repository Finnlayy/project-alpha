#!/usr/bin/env node
/**
 * Projekt:Alpha MCP Server — stdio transport entry point.
 *
 * Usage:
 *   npx tsx src/index.ts
 *
 * Or with the MCP Inspector:
 *   npx @modelcontextprotocol/inspector npx tsx src/index.ts
 *
 * Claude Desktop config (claude_desktop_config.json):
 *   {
 *     "mcpServers": {
 *       "projekt-alpha": {
 *         "command": "npx",
 *         "args": ["tsx", "/path/to/project-alpha/mcp-server/src/index.ts"],
 *         "env": {
 *           "ALPHA_BACKEND_URL": "http://127.0.0.1:8000"
 *         }
 *       }
 *     }
 *   }
 */
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { createAlphaServer } from "./server.js";

// serveStdio accepts a factory function that builds a fresh server per connection
serveStdio(() => createAlphaServer());
console.error("[projekt-alpha-mcp] server running on stdio — backend at", process.env.ALPHA_BACKEND_URL ?? "http://127.0.0.1:8000");
