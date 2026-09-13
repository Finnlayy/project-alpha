/**
 * Kraken Spot + Kraken Futures (Pro) MCP tools — 1:1 wiring over the backend's
 * /api/kraken/spot/* and /api/kraken/futures/* routes, which proxy the REAL
 * Kraken REST APIs (api.kraken.com and futures.kraken.com/derivatives/api/v3).
 *
 * Read tools state their credential needs; order-placement tools are
 * passkey-gated server-side (X-Alpha-Session) and return explicit errors when
 * credentials or the session are missing. Nothing here simulates fills.
 */
import { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";
import { AlphaClient } from "../alphaClient.js";

function ok(data: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
}

function err(e: any) {
  return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true as const };
}

export function registerKrakenTools(server: McpServer, client: AlphaClient) {
  // ============================== Spot — public ==============================
  server.registerTool(
    "alpha_spot_ticker",
    {
      description: "Spot L1 ticker for one pair via live Kraken REST (bid/ask/last/24h stats). Public, no credentials.",
      inputSchema: { pair: z.string().default("BTC/USD").describe("Pair, e.g. BTC/USD") },
    },
    async ({ pair }) => {
      try {
        return ok(await client.get("/api/kraken/spot/ticker", { pair }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_spot_orderbook",
    {
      description: "Spot L2 order book (Depth) for one pair. Public, no credentials.",
      inputSchema: {
        pair: z.string().default("BTC/USD").describe("Pair, e.g. BTC/USD"),
        count: z.number().default(20).describe("Depth levels per side (1-500)"),
      },
    },
    async ({ pair, count }) => {
      try {
        return ok(await client.get("/api/kraken/spot/orderbook", { pair, count }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  // ============================== Spot — private =============================
  server.registerTool(
    "alpha_spot_open_orders",
    {
      description: "List open Spot orders. Requires Spot credentials.",
    },
    async () => {
      try {
        return ok(await client.get("/api/kraken/spot/open-orders"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_spot_closed_orders",
    {
      description: "List recently closed/cancelled Spot orders. Requires Spot credentials.",
    },
    async () => {
      try {
        return ok(await client.get("/api/kraken/spot/closed-orders"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_spot_trades_history",
    {
      description: "Spot trade history (fills). Requires Spot credentials.",
      inputSchema: {
        type: z.string().default("all").describe("History type: all, market, limit"),
      },
    },
    async ({ type }) => {
      try {
        return ok(await client.get("/api/kraken/spot/trades-history", { type }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_spot_trade_balance",
    {
      description: "Spot margin overview — equity, free/total margin, P&L (TradeBalance). Requires Spot credentials.",
    },
    async () => {
      try {
        return ok(await client.get("/api/kraken/spot/trade-balance"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_spot_ledger_entries",
    {
      description: "Real Spot ledger entries — deposits, withdrawals, trades, fees (Ledgers endpoint). Requires Spot credentials.",
      inputSchema: {
        asset: z.string().optional().describe("Filter by asset (e.g. XBT, ETH)"),
        type: z.string().optional().describe("Ledger type filter (e.g. trade, deposit, withdrawal)"),
      },
    },
    async ({ asset, type }) => {
      try {
        return ok(await client.get("/api/kraken/spot/ledger-entries", { asset, type }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_spot_place_order",
    {
      description:
        "Place a REAL Spot order (passkey-gated server-side). Use validate=true to dry-run server-side validation without placing.",
      inputSchema: {
        pair: z.string().describe("Pair, e.g. BTC/USD"),
        side: z.enum(["buy", "sell"]).describe("Order side"),
        volume: z.number().describe("Base-asset volume"),
        ordertype: z.string().default("limit").describe("market, limit, stop-loss, take-profit, ..."),
        price: z.number().optional().describe("Limit price (required for limit orders)"),
        oflags: z.string().default("post").describe("Order flags — 'post' = maker-only"),
        validate: z.boolean().default(false).describe("Dry-run validation only"),
        leverage: z.number().optional().describe("Spot margin leverage (e.g. 2-5)"),
      },
    },
    async ({ pair, side, volume, ordertype, price, oflags, validate, leverage }) => {
      try {
        return ok(
          await client.post("/api/kraken/spot/orders", {
            pair, side, volume, ordertype, price, oflags, validate, leverage,
          })
        );
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_spot_cancel_order",
    {
      description: "Cancel one Spot open order by txid (passkey-gated).",
      inputSchema: { txid: z.string().describe("Order transaction ID") },
    },
    async ({ txid }) => {
      try {
        return ok(await client.post(`/api/kraken/spot/orders/${txid}/cancel`));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_spot_cancel_all",
    {
      description: "Cancel ALL Spot open orders (passkey-gated).",
    },
    async () => {
      try {
        return ok(await client.post("/api/kraken/spot/orders/cancel-all"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  // ============================ Futures — public =============================
  server.registerTool(
    "alpha_futures_tickers",
    {
      description: "Futures market tickers — mark price, bid/ask, funding rate, open interest. Public, no credentials.",
      inputSchema: {
        symbol: z.string().optional().describe("Filter by contract, e.g. PF_XBTUSD. Omit for all."),
      },
    },
    async ({ symbol }) => {
      try {
        return ok(await client.get("/api/kraken/futures/tickers", { symbol }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_instruments",
    {
      description: "Futures instrument catalog with contract specs (size, tick, margin). Public, no credentials.",
    },
    async () => {
      try {
        return ok(await client.get("/api/kraken/futures/instruments"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_orderbook",
    {
      description: "Futures L2 order book for one contract. Public, no credentials.",
      inputSchema: { symbol: z.string().default("PF_XBTUSD").describe("Contract, e.g. PF_XBTUSD") },
    },
    async ({ symbol }) => {
      try {
        return ok(await client.get("/api/kraken/futures/orderbook", { symbol }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_history",
    {
      description: "Public execution (trade) history for one futures contract.",
      inputSchema: { symbol: z.string().default("PF_XBTUSD").describe("Contract, e.g. PF_XBTUSD") },
    },
    async ({ symbol }) => {
      try {
        return ok(await client.get("/api/kraken/futures/history", { symbol }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  // ============================ Futures — private ============================
  server.registerTool(
    "alpha_futures_accounts",
    {
      description: "Futures wallets — balances, available/initial margin, unrealized P&L. Requires Futures credentials.",
    },
    async () => {
      try {
        return ok(await client.get("/api/kraken/futures/accounts"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_open_orders",
    {
      description: "List open Futures orders. Requires Futures credentials.",
    },
    async () => {
      try {
        return ok(await client.get("/api/kraken/futures/open-orders"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_fills",
    {
      description: "Futures fills (account execution history). Requires Futures credentials.",
    },
    async () => {
      try {
        return ok(await client.get("/api/kraken/futures/fills"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_place_order",
    {
      description:
        "Place a REAL Futures order via sendorder (passkey-gated server-side). " +
        "Give either 'symbol' (PF_XBTUSD) or 'pair' (BTC/USD — auto-mapped).",
      inputSchema: {
        symbol: z.string().optional().describe("Contract, e.g. PF_XBTUSD"),
        pair: z.string().optional().describe("Spot-style pair auto-mapped to the perpetual, e.g. BTC/USD"),
        side: z.enum(["buy", "sell"]).describe("Order side"),
        size: z.number().describe("Number of contracts"),
        orderType: z.string().default("lmt").describe("lmt, post, mkt, stp, take_profit, ioc, trailing_stop, fok"),
        limitPrice: z.number().optional().describe("Limit price"),
        stopPrice: z.number().optional().describe("Stop trigger price (stp/take_profit)"),
        reduceOnly: z.boolean().default(false).describe("Only reduce an existing position"),
        cliOrdId: z.string().optional().describe("Client order ID (globally unique)"),
        triggerSignal: z.string().optional().describe("Stop trigger source: mark, index, last"),
      },
    },
    async ({ symbol, pair, side, size, orderType, limitPrice, stopPrice, reduceOnly, cliOrdId, triggerSignal }) => {
      try {
        return ok(
          await client.post("/api/kraken/futures/orders", {
            symbol, pair, side, size, orderType, limitPrice, stopPrice, reduceOnly, cliOrdId, triggerSignal,
          })
        );
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_cancel_order",
    {
      description: "Cancel one Futures order by orderId or cliOrdId (passkey-gated).",
      inputSchema: {
        orderId: z.string().optional().describe("Exchange order ID"),
        cliOrdId: z.string().optional().describe("Client order ID"),
        symbol: z.string().optional().describe("Contract scope, e.g. PF_XBTUSD"),
      },
    },
    async ({ orderId, cliOrdId, symbol }) => {
      try {
        return ok(await client.post("/api/kraken/futures/orders/cancel", { orderId, cliOrdId, symbol }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_cancel_all",
    {
      description: "Cancel all open Futures orders, optionally scoped to one contract (passkey-gated).",
      inputSchema: {
        symbol: z.string().optional().describe("Contract scope, e.g. PF_XBTUSD. Omit for all."),
      },
    },
    async ({ symbol }) => {
      try {
        return ok(await client.post("/api/kraken/futures/orders/cancel-all", { symbol }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_futures_close_position",
    {
      description:
        "Close a Futures position with a reduce-only market order (passkey-gated). " +
        "Omit size to close the full position.",
      inputSchema: {
        symbol: z.string().optional().describe("Contract, e.g. PF_XBTUSD"),
        pair: z.string().optional().describe("Spot-style pair auto-mapped to the perpetual, e.g. BTC/USD"),
        size: z.number().optional().describe("Contracts to close (omit = full position)"),
      },
    },
    async ({ symbol, pair, size }) => {
      try {
        return ok(await client.post("/api/kraken/futures/positions/close", { symbol, pair, size }));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  // ============================ Account utilities ============================
  server.registerTool(
    "alpha_kraken_sync_balance",
    {
      description:
        "Force-refresh Spot balances + Futures wallets from both Kraken venues. " +
        "Requires at least one venue's credentials; returns per-venue errors explicitly.",
    },
    async () => {
      try {
        return ok(await client.post("/api/kraken/sync-balance"));
      } catch (e: any) {
        return err(e);
      }
    }
  );

  server.registerTool(
    "alpha_kraken_toggle_mode",
    {
      description:
        "Switch the execution mode between paper and live. Switching TO live is passkey-gated " +
        "server-side and requires Kraken credentials; switching to paper always works.",
      inputSchema: {
        paperTrading: z.boolean().describe("true = paper mode, false = live mode"),
      },
    },
    async ({ paperTrading }) => {
      try {
        return ok(await client.post("/api/kraken/toggle-mode", { paperTrading }));
      } catch (e: any) {
        return err(e);
      }
    }
  );
}
