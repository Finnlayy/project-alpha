// Centralized API client for the REAL Projekt:Alpha backend.
// Zero-Dummy rule: on network/HTTP failure these helpers return null /
// {ok:false} with a reason — never fabricated data. Components render explicit
// offline/empty states when they receive null.
import { KrakenDualCredentialsStatus, QueueMatrixData, StrategyQueueMatrix } from "../types";
import { WorkerBotData } from "../types/trading";

function asNumber(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function normalizeQueueStrategy(raw: Partial<StrategyQueueMatrix> & Record<string, unknown>): StrategyQueueMatrix {
  const status = raw.status === "archived" || raw.status === "stopped" ? "inactive" : (raw.status || "inactive");
  return {
    strategyId: String(raw.strategyId || raw.id || ""),
    strategyName: String(raw.strategyName || raw.name || "Unnamed"),
    assetPair: String(raw.assetPair || "BTC/USD"),
    status: status === "error" ? "error" : status === "active" ? "active" : "inactive",
    interval: asNumber(raw.interval, 5),
    executionMode: raw.executionMode === "live" ? "live" : "paper",
    parameters: (raw.parameters as Record<string, unknown> | undefined) || {},
    realizedPnL: asNumber(raw.realizedPnL),
    unrealizedPnL: asNumber(raw.unrealizedPnL),
    totalPnL: asNumber(raw.totalPnL),
    totalTrades: asNumber(raw.totalTrades),
    winningTrades: asNumber(raw.winningTrades),
    losingTrades: asNumber(raw.losingTrades),
    winRate: asNumber(raw.winRate),
    volumeTradedUSD: asNumber(raw.volumeTradedUSD),
    profitFactor: asNumber(raw.profitFactor),
    maxDrawdown: asNumber(raw.maxDrawdown),
    avgTradeReturn: asNumber(raw.avgTradeReturn),
    bestTrade: asNumber(raw.bestTrade),
    worstTrade: asNumber(raw.worstTrade),
    trades: Array.isArray(raw.trades) ? raw.trades : [],
  };
}

export function normalizeQueueMatrix(raw: Partial<QueueMatrixData> | null | undefined, queue: "paper" | "live"): QueueMatrixData {
  const strategies = Array.isArray(raw?.strategies) ? raw.strategies.map((s) => normalizeQueueStrategy(s as StrategyQueueMatrix & Record<string, unknown>)) : [];
  return {
    queue,
    queueLabel: raw?.queueLabel || (queue === "live" ? "Live Execution Matrix (Protected)" : "Paper Execution Matrix"),
    automationLevel: asNumber(raw?.automationLevel, 4),
    totalRealizedPnL: asNumber(raw?.totalRealizedPnL),
    totalUnrealizedPnL: asNumber(raw?.totalUnrealizedPnL),
    totalPnL: asNumber(raw?.totalPnL),
    cumulativeReturnPercent: asNumber(raw?.cumulativeReturnPercent),
    totalClosedTrades: asNumber(raw?.totalClosedTrades),
    totalAllTrades: asNumber(raw?.totalAllTrades),
    winningTrades: asNumber(raw?.winningTrades),
    losingTrades: asNumber(raw?.losingTrades),
    winRate: asNumber(raw?.winRate),
    volumeTradedUSD: asNumber(raw?.volumeTradedUSD),
    profitFactor: asNumber(raw?.profitFactor),
    sharpeRatio: asNumber(raw?.sharpeRatio),
    sortinoRatio: asNumber(raw?.sortinoRatio),
    maxDrawdownPercent: asNumber(raw?.maxDrawdownPercent),
    averageTradeReturn: asNumber(raw?.averageTradeReturn),
    bestTradeUSD: asNumber(raw?.bestTradeUSD),
    worstTradeUSD: asNumber(raw?.worstTradeUSD),
    activeWorkers: asNumber(raw?.activeWorkers),
    strategies,
    allTimeTrades: Array.isArray(raw?.allTimeTrades) ? raw.allTimeTrades : [],
    pnlTrajectory: Array.isArray(raw?.pnlTrajectory) ? raw.pnlTrajectory : [],
    assetBreakdown: Array.isArray(raw?.assetBreakdown) ? raw.assetBreakdown : [],
  };
}

export function normalizeWorkerBot(raw: Record<string, any> | null | undefined): WorkerBotData {
  const metricsRaw = raw?.metrics && typeof raw.metrics === "object" ? raw.metrics : {};
  const runtimeRaw = raw?.runtime && typeof raw.runtime === "object" ? raw.runtime : {};
  const investment = asNumber(metricsRaw.investment ?? raw?.investment ?? raw?.initialBalance);
  const realized = asNumber(metricsRaw.realizedProfit ?? raw?.realizedProfit);
  const unrealizedVal = asNumber(raw?.unrealizedPnL?.value ?? raw?.unrealizedPnL);
  const totalProfit = asNumber(raw?.totalProfit, realized + unrealizedVal);
  const direction = String(raw?.direction || "LONG").toUpperCase() === "SHORT" ? "SHORT" : "LONG";
  return {
    id: String(raw?.id || ""),
    name: String(raw?.name || "Worker"),
    exchange: String(raw?.exchange || "Kraken"),
    status: raw?.status === "active" ? "active" : "paused",
    pair: String(raw?.pair || raw?.assetPair || "BTC/USD"),
    strategy: String(raw?.strategy || raw?.strategyType || ""),
    direction,
    leverage: asNumber(raw?.leverage, 1),
    unrealizedPnL: {
      value: unrealizedVal,
      percentage: asNumber(raw?.unrealizedPnL?.percentage),
    },
    entryPrice: asNumber(raw?.entryPrice),
    currentPrice: asNumber(raw?.currentPrice),
    metrics: {
      investment,
      currency: String(metricsRaw.currency || raw?.currency || "USD"),
      realizedProfit: realized,
      dcaRangeMin: asNumber(metricsRaw.dcaRangeMin),
      dcaRangeMax: asNumber(metricsRaw.dcaRangeMax),
      dcaSteps: asNumber(metricsRaw.dcaSteps),
      dcaOrdersTriggered: asNumber(metricsRaw.dcaOrdersTriggered),
      fundingFees: asNumber(metricsRaw.fundingFees ?? raw?.fundingFees),
      liquidationPrice: asNumber(metricsRaw.liquidationPrice),
      liquidationDistancePct: asNumber(metricsRaw.liquidationDistancePct),
    },
    runtime: {
      days: asNumber(runtimeRaw.days),
      hours: asNumber(runtimeRaw.hours),
      minutes: asNumber(runtimeRaw.minutes),
      cycles: asNumber(runtimeRaw.cycles ?? raw?.closedTrades),
    },
    totalProfit,
    roi: asNumber(raw?.roi),
    apr: asNumber(raw?.apr),
    lastUpdate: raw?.lastUpdate ?? Date.now(),
    spawnedFrom: raw?.spawnedFrom,
    spawnedAt: raw?.spawnedAt,
    regime: raw?.regime,
    historicalOrigin: raw?.historicalOrigin,
  };
}

export interface DashboardInitResponse {
  status: string;
  uptime: number;
  timestamp: string;
  isPaperTrading: boolean;
  hasCredentials: boolean;
  hasSpotCredentials?: boolean;
  hasFuturesCredentials?: boolean;
  bothConfigured?: boolean;
  credentialsStatus?: KrakenDualCredentialsStatus;
  default_timeframe: string;
  symbols: string[];
  activeStrategiesCount: number;
  totalStrategiesCount: number;
  lake_status: string;
  lake_rows?: number;
  market_feed?: string;
}

export interface KrakenStatusResponse {
  connected: boolean;
  ohlcStreamConnected?: boolean;
  wsConnected?: boolean;
  restLatencyMs?: number | null;
  restAvailable?: boolean;
  hasCredentials: boolean;
  hasSpotCredentials: boolean;
  hasFuturesCredentials: boolean;
  bothConfigured: boolean;
  paperTrading: boolean;
  mode: "paper" | "live";
  credentialsStatus: KrakenDualCredentialsStatus;
}

// ------------------------------------------------------------------ session
const TOKEN_KEY = "alpha_passkey_session";

export function getSessionToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setSessionToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) };
  const tok = getSessionToken();
  if (tok) h["X-Alpha-Session"] = tok;
  return h;
}

/**
 * Safe JSON fetch with AbortController timeout.
 * Returns null (never throws, never fabricates) when the backend is
 * unreachable or the response is not valid JSON.
 */
export async function safeFetchJson<T>(url: string, options?: RequestInit, timeoutMs: number = 4000): Promise<T | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      ...options,
      headers: authHeaders(options?.headers as Record<string, string> | undefined),
      signal: controller.signal
    });
    clearTimeout(timer);

    if (!res.ok) return null;

    const contentType = res.headers.get("content-type");
    if (contentType && !contentType.includes("application/json")) return null;

    const text = await res.text();
    if (!text || text.trim().startsWith("<")) return null;
    return JSON.parse(text) as T;
  } catch {
    clearTimeout(timer);
    return null;
  }
}

/**
 * Mutation with strict timeout. Failures are reported honestly:
 * { ok:false, error } — the UI shows the error instead of faking success.
 */
export async function safeMutation<T>(
  url: string,
  method: "POST" | "PUT" | "DELETE",
  body?: any,
  timeoutMs: number = 6000
): Promise<{ ok: boolean; data?: T; error?: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method,
      headers: authHeaders(body ? { "Content-Type": "application/json" } : undefined),
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal
    });
    clearTimeout(timer);

    let parsed: any = null;
    const contentType = res.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      try {
        parsed = await res.json();
      } catch {
        parsed = null;
      }
    }
    if (!res.ok) {
      return { ok: false, error: (parsed && (parsed.detail || parsed.error)) || `HTTP ${res.status}` };
    }
    return { ok: true, data: parsed as T };
  } catch (e: any) {
    clearTimeout(timer);
    return { ok: false, error: `backend unreachable (${e?.name || "network error"})` };
  }
}
