/**
 * MCP Resources — live, read-only views onto the Projekt:Alpha backend.
 *
 * WIRING CONTRACT
 * ---------------
 * Every resource below proxies exactly one real FastAPI route on the
 * Projekt:Alpha backend. The route is named in each registration and repeated
 * in the degraded envelope, so the mapping URI -> address is auditable from
 * either side. The backend base URL comes from ALPHA_BACKEND_URL
 * (default http://127.0.0.1:8000) and is the same address the 59 tools use.
 *
 *   kraken://positions          -> GET /api/kraken/positions/pro
 *   kraken://status             -> GET /api/kraken/status
 *   m8://state                  -> GET /api/quant/execution/m8-judge
 *   lake://candles/{symbol}     -> GET /api/lake/query?symbol=<symbol>&limit=<n>
 *   alpha://system/status       -> GET /api/dashboard/init
 *   alpha://system/health       -> GET /api/health
 *   alpha://strategies/active   -> GET /api/strategies
 *   alpha://workers/active      -> GET /api/quant/workers
 *
 * ZERO-DUMMY GUARANTEE
 * --------------------
 * Nothing here synthesises values. When the backend is unreachable, or the
 * route answers 4xx/5xx because a dependency is genuinely missing (no Kraken
 * credentials, an empty lake, no running instances), the resource returns an
 * explicit degraded envelope — status/reason/detail plus the exact backend
 * address that was queried — instead of placeholder numbers. A 404 from
 * `/api/quant/execution/m8-judge` really does mean "no instance is running",
 * and that is what the client is told.
 */
import { McpServer, ResourceTemplate } from "@modelcontextprotocol/server";
import { AlphaClient } from "./alphaClient.js";

/** Backend address the resources are wired to (same default as AlphaClient). */
const BACKEND_BASE = (process.env.ALPHA_BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

/** Default candle window for `lake://candles/{symbol}`. */
const DEFAULT_CANDLE_LIMIT = 200;
const MAX_CANDLE_LIMIT = 5000;

type Contents = { uri: string; mimeType: string; text: string };

function envelope(uri: string, payload: unknown): { contents: Contents[] } {
  return {
    contents: [
      {
        uri,
        mimeType: "application/json",
        text: JSON.stringify(payload, null, 2),
      },
    ],
  };
}

/**
 * Turn an AlphaClient failure into an explicit, type-safe degraded state.
 *
 * AlphaClient throws `GET <path> → <status>: <body>` for any non-2xx response,
 * so a backend that answered (404 empty lake, 412 missing credentials) is
 * distinguishable from one that was unreachable — and the real reason is
 * surfaced verbatim rather than being flattened into a generic error.
 */
function degraded(uri: string, route: string, err: unknown): { contents: Contents[] } {
  const message = err instanceof Error ? err.message : String(err);
  const matched = message.match(/^(?:GET|POST|PUT|DELETE)\s+(\S+)\s+→\s+(\d{3}):\s*([\s\S]*)$/);

  let reason = "BACKEND_UNREACHABLE";
  let detail = message;
  let httpStatus: number | null = null;

  if (matched) {
    httpStatus = Number(matched[2]);
    reason = `HTTP_${matched[2]}`;
    const body = matched[3] ?? "";
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      detail = typeof parsed.detail === "string" ? parsed.detail : body || matched[3];
    } catch {
      detail = body || matched[3];
    }
  }

  return envelope(uri, {
    status: "offline",
    reason,
    httpStatus,
    detail,
    resource: uri,
    backend: `${BACKEND_BASE}${route}`,
    note: "Zero-Dummy Guarantee: no synthetic data is substituted for an unavailable source.",
  });
}

export function registerResources(server: McpServer, client: AlphaClient) {
  /** Fetch a backend route and wrap it, or degrade explicitly on failure. */
  async function read(
    uri: string,
    route: string,
    params?: Record<string, string | number | undefined>
  ): Promise<{ contents: Contents[] }> {
    try {
      return envelope(uri, await client.get(route, params));
    } catch (err) {
      return degraded(uri, route, err);
    }
  }

  // ---------- kraken://positions -------------------------------------------
  server.registerResource(
    "kraken-positions",
    "kraken://positions",
    {
      title: "Kraken Positions & Margin",
      description:
        "Live Kraken Pro (Futures) position and margin state — collateral, free/used margin, " +
        "margin level and unrealised PnL. Wired to GET /api/kraken/positions/pro. Without " +
        "futures credentials the backend answers configured:false with explicit zeros.",
      mimeType: "application/json",
    },
    async (uri) => read(uri.href, "/api/kraken/positions/pro")
  );

  // ---------- kraken://status ----------------------------------------------
  server.registerResource(
    "kraken-status",
    "kraken://status",
    {
      title: "Kraken Connection Status",
      description:
        "Kraken connectivity — REST latency/availability, WS v2 feed state, reconnect attempts " +
        "and spot/futures credential presence. Wired to GET /api/kraken/status.",
      mimeType: "application/json",
    },
    async (uri) => read(uri.href, "/api/kraken/status")
  );

  // ---------- m8://state ----------------------------------------------------
  server.registerResource(
    "m8-state",
    "m8://state",
    {
      title: "M8 Risk State",
      description:
        "M8 state-engine verdict for the active instance: state (ACTIVE/THROTTLED/QUARANTINED), " +
        "current vs. base budget, budget multiplier applied to Kelly sizing, churn risk score, " +
        "consecutive losses and open-position flag. Wired to GET /api/quant/execution/m8-judge. " +
        "Answers HTTP 404 while no instance is running — reported as an explicit offline reason, " +
        "never as invented state. Use the alpha_quant_m8_judge tool for a specific instance id.",
      mimeType: "application/json",
    },
    async (uri) => read(uri.href, "/api/quant/execution/m8-judge")
  );

  // ---------- lake://candles/{symbol} ---------------------------------------
  // The symbol is a URI path segment, so '/' must be percent-encoded:
  //   lake://candles/BTC%2FUSD   -> /api/lake/query?symbol=BTC/USD
  server.registerResource(
    "lake-candles",
    new ResourceTemplate("lake://candles/{symbol}", { list: undefined }),
    {
      title: "Data Lake Candles",
      description:
        "Real OHLC candles for one symbol out of the DuckDB lake, newest first. Wired to " +
        "GET /api/lake/query?symbol=<symbol>&limit=<n>. The symbol is a path segment, so " +
        "percent-encode the slash: lake://candles/BTC%2FUSD. An empty lake answers HTTP 404 " +
        "(run /api/lake/sync) — surfaced verbatim, never padded with synthetic candles.",
      mimeType: "application/json",
    },
    async (uri, variables) => {
      const raw = Array.isArray(variables.symbol) ? variables.symbol[0] : variables.symbol;
      const symbol = (() => {
        try {
          return decodeURIComponent(String(raw ?? ""));
        } catch {
          return String(raw ?? "");
        }
      })();

      if (!symbol) {
        return envelope(uri.href, {
          status: "offline",
          reason: "INVALID_ARGUMENT",
          detail: "lake://candles/{symbol} requires a symbol, e.g. lake://candles/BTC%2FUSD",
          resource: uri.href,
          backend: `${BACKEND_BASE}/api/lake/query`,
        });
      }

      const limitParam = uri.searchParams.get("limit");
      const parsedLimit = limitParam === null ? NaN : Number(limitParam);
      const limit = Number.isFinite(parsedLimit) && parsedLimit > 0
        ? Math.min(Math.floor(parsedLimit), MAX_CANDLE_LIMIT)
        : DEFAULT_CANDLE_LIMIT;

      return read(uri.href, "/api/lake/query", { symbol, limit });
    }
  );

  // ---------- alpha://system/status -----------------------------------------
  server.registerResource(
    "system-status",
    "alpha://system/status",
    {
      title: "System Status",
      description:
        "Full Projekt:Alpha dashboard payload — execution mode, uptime, credential state, lake " +
        "health, instance list and live market-feed status. Wired to GET /api/dashboard/init.",
      mimeType: "application/json",
    },
    async (uri) => read(uri.href, "/api/dashboard/init")
  );

  // ---------- alpha://system/health -----------------------------------------
  server.registerResource(
    "system-health",
    "alpha://system/health",
    {
      title: "System Health",
      description:
        "Minimal liveness probe — backend alive, execution mode, WS connected flag and running " +
        "instance count. Wired to GET /api/health.",
      mimeType: "application/json",
    },
    async (uri) => read(uri.href, "/api/health")
  );

  // ---------- alpha://strategies/active -------------------------------------
  server.registerResource(
    "active-strategies",
    "alpha://strategies/active",
    {
      title: "Active Strategies",
      description:
        "All strategy instances with their state, P&L and M8 health. Wired to GET /api/strategies. " +
        "Returns an empty array when nothing is queued — that is the real state, not a stub.",
      mimeType: "application/json",
    },
    async (uri) => read(uri.href, "/api/strategies")
  );

  // ---------- alpha://workers/active ----------------------------------------
  server.registerResource(
    "active-workers",
    "alpha://workers/active",
    {
      title: "Active Worker Bots",
      description:
        "The worker-bot swarm — real running strategy instances with live P&L. Wired to " +
        "GET /api/quant/workers.",
      mimeType: "application/json",
    },
    async (uri) => read(uri.href, "/api/quant/workers")
  );
}
