// Centralized API client for the REAL Projekt:Alpha backend.
// Zero-Dummy rule: on network/HTTP failure these helpers return null /
// {ok:false} with a reason — never fabricated data. Components render explicit
// offline/empty states when they receive null.
import { KrakenDualCredentialsStatus } from "../types";

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
