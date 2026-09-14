/**
 * End-to-end MCP protocol probe (verification harness, not shipped code).
 *
 * Performs a real Streamable-HTTP MCP handshake against the running server and
 * reads every registered resource, printing the URI, the backend route it was
 * wired to, and whether the payload is real data or an explicit degraded state.
 */
const BASE = process.env.MCP_URL ?? "http://127.0.0.1:4100/mcp";
let sessionId;
let id = 0;

async function rpc(method, params, isNotification = false) {
  const body = isNotification
    ? { jsonrpc: "2.0", method, params }
    : { jsonrpc: "2.0", id: ++id, method, params };

  const res = await fetch(BASE, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      ...(sessionId ? { "mcp-session-id": sessionId } : {}),
    },
    body: JSON.stringify(body),
  });

  const sid = res.headers.get("mcp-session-id");
  if (sid) sessionId = sid;

  const text = await res.text();
  if (isNotification) return { status: res.status };

  // Responses may be SSE-framed: "event: message\ndata: {...}\n\n"
  let json = null;
  if (text.trim().startsWith("{")) {
    json = JSON.parse(text);
  } else {
    for (const line of text.split("\n")) {
      if (line.startsWith("data:")) {
        const chunk = line.slice(5).trim();
        if (chunk) { json = JSON.parse(chunk); break; }
      }
    }
  }
  return { status: res.status, json };
}

const init = await rpc("initialize", {
  protocolVersion: "2025-06-18",
  capabilities: {},
  clientInfo: { name: "alpha-wiring-probe", version: "1.0.0" },
});
console.log("initialize       ->", init.status, init.json?.result?.serverInfo ?? init.json?.error);

await rpc("notifications/initialized", {}, true);

const [tools, prompts, resources, templates] = await Promise.all([
  rpc("tools/list", {}),
  rpc("prompts/list", {}),
  rpc("resources/list", {}),
  rpc("resources/templates/list", {}),
]);

const toolCount = tools.json?.result?.tools?.length ?? 0;
const promptCount = prompts.json?.result?.prompts?.length ?? 0;
const resList = resources.json?.result?.resources ?? [];
const tmplList = templates.json?.result?.resourceTemplates ?? [];

console.log(`\ntools=${toolCount}  prompts=${promptCount}  resources=${resList.length}  templates=${tmplList.length}`);

console.log("\n--- resources/list ---");
for (const r of resList) console.log(`  ${r.uri}`);
console.log("--- resources/templates/list ---");
for (const t of tmplList) console.log(`  ${t.uriTemplate}`);

// Every concrete URI to read: the static ones + template instances.
const uris = [
  ...resList.map((r) => r.uri),
  "lake://candles/BTC%2FUSD",
  "lake://candles/ETH%2FUSD",
];

console.log("\n--- resources/read ---");
let failures = 0;
for (const uri of uris) {
  const out = await rpc("resources/read", { uri });
  const content = out.json?.result?.contents?.[0];
  if (!content) {
    console.log(`  ${uri.padEnd(34)} ERROR ${JSON.stringify(out.json?.error ?? out.status)}`);
    failures++;
    continue;
  }
  let parsed;
  try { parsed = JSON.parse(content.text); } catch { parsed = null; }
  const isDegraded = parsed && parsed.status === "offline";
  const tag = isDegraded ? `OFFLINE ${parsed.reason}` : "REAL";
  const addr = isDegraded ? parsed.backend : "";
  const keys = parsed && !isDegraded ? Object.keys(parsed).slice(0, 6).join(",") : (isDegraded ? parsed.detail?.slice(0, 60) : "");
  console.log(`  ${uri.padEnd(34)} ${tag.padEnd(22)} ${addr.padEnd(46)} ${keys}`);
  if (out.json?.error) failures++;
}

console.log(`\nprotocol-level failures: ${failures}`);
process.exit(failures === 0 ? 0 : 1);
