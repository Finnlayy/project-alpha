#!/usr/bin/env node
/**
 * Projekt:Alpha MCP Server — Streamable HTTP transport.
 *
 * Serves the MCP endpoint on port 4100 (configurable via MCP_PORT).
 * Clients connect to http://host:4100/mcp
 *
 * Usage:
 *   ALPHA_BACKEND_URL=http://127.0.0.1:8000 npx tsx src/http-server.ts
 */
import { createServer as createHttpServer, type IncomingMessage, type ServerResponse } from "node:http";
import { createMcpHandler, type McpHttpHandler } from "@modelcontextprotocol/server";
import { createAlphaServer } from "./server.js";

const PORT = parseInt(process.env.MCP_PORT ?? "4100", 10);
const HOST = process.env.MCP_HOST ?? "0.0.0.0";

const handler: McpHttpHandler = createMcpHandler(() => createAlphaServer());

/**
 * Bridge Node.js IncomingMessage/ServerResponse → Web-standard Request/Response
 * for the MCP handler's fetch function.
 */
async function nodeToWebHandler(req: IncomingMessage, res: ServerResponse): Promise<void> {
  // Build the web-standard URL
  const protocol = "http";
  const host = req.headers.host ?? `${HOST}:${PORT}`;
  const url = `${protocol}://${host}${req.url ?? "/"}`;

  // Collect request body
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(chunk as Buffer);
  }
  const body = chunks.length > 0 ? Buffer.concat(chunks) : undefined;

  // Build web-standard headers
  const headers = new Headers();
  for (const [key, value] of Object.entries(req.headers)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      for (const v of value) headers.append(key, v);
    } else {
      headers.set(key, value);
    }
  }

  // Construct the web-standard Request
  const method = req.method ?? "GET";
  const webReq = new Request(url, {
    method,
    headers,
    body: body && method !== "GET" && method !== "HEAD" ? body : undefined,
  });

  try {
    // Call the MCP handler's fetch
    const webRes = await handler.fetch(webReq);

    // Write response
    res.writeHead(webRes.status, Object.fromEntries(webRes.headers.entries()));

    if (webRes.body) {
      const reader = webRes.body.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        res.write(value);
      }
    }
    res.end();
  } catch (err: any) {
    console.error("[projekt-alpha-mcp] handler error:", err);
    if (!res.headersSent) {
      res.writeHead(500, { "Content-Type": "application/json" });
    }
    res.end(JSON.stringify({ error: "Internal server error" }));
  }
}

const httpServer = createHttpServer(nodeToWebHandler);

httpServer.listen(PORT, HOST, () => {
  console.error(`[projekt-alpha-mcp] HTTP MCP server listening on http://${HOST}:${PORT}/mcp`);
  console.error(`[projekt-alpha-mcp] Backend: ${process.env.ALPHA_BACKEND_URL ?? "http://127.0.0.1:8000"}`);
});

// Graceful shutdown
process.on("SIGINT", async () => {
  console.error("[projekt-alpha-mcp] shutting down...");
  await handler.close();
  httpServer.close();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  await handler.close();
  httpServer.close();
  process.exit(0);
});
