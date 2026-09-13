/**
 * Lightweight HTTP client for the Projekt:Alpha FastAPI backend.
 * All MCP tool handlers proxy through here.
 */

const DEFAULT_BASE = process.env.ALPHA_BACKEND_URL ?? "http://127.0.0.1:8000";

export class AlphaClient {
  private base: string;
  private sessionToken?: string;

  constructor(base?: string, sessionToken?: string) {
    this.base = (base ?? DEFAULT_BASE).replace(/\/$/, "");
    this.sessionToken = sessionToken;
  }

  setSession(token: string | undefined) {
    this.sessionToken = token;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    if (this.sessionToken) {
      h["X-Alpha-Session"] = this.sessionToken;
    }
    return h;
  }

  async get<T = unknown>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
    const url = new URL(path, this.base);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined) url.searchParams.set(k, String(v));
      }
    }
    const res = await fetch(url.toString(), { headers: this.headers() });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`GET ${path} → ${res.status}: ${body || res.statusText}`);
    }
    return res.json() as Promise<T>;
  }

  async post<T = unknown>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(new URL(path, this.base).toString(), {
      method: "POST",
      headers: this.headers(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`POST ${path} → ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<T>;
  }

  async put<T = unknown>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(new URL(path, this.base).toString(), {
      method: "PUT",
      headers: this.headers(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`PUT ${path} → ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<T>;
  }

  async delete<T = unknown>(path: string): Promise<T> {
    const res = await fetch(new URL(path, this.base).toString(), {
      method: "DELETE",
      headers: this.headers(),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`DELETE ${path} → ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<T>;
  }
}
