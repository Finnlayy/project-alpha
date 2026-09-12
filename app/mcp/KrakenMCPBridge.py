"""
=========================================================
Kraken MCP Bridge (v2.0) — dual-key routing (Spot vs Futures)
for MCP exchange tools, wired to the REAL Kraken REST clients.

No simulation: a tool without credentials returns an explicit
NOT_CONFIGURED error; a network failure returns the real transport
error. Routing:
  1. Spot API   (api.kraken.com)        : ledgers, orders, tickers
  2. Futures API (futures.kraken.com)   : perps, margin, leverage
=========================================================
"""
import logging
from typing import Any, Dict, Optional

from app.config import load_settings
from app.kraken.futures_client import KrakenFuturesClient
from app.kraken.spot_client import KrakenError, KrakenSpotClient

logger = logging.getLogger("app.mcp.kraken_bridge")


class KrakenMCPBridge:
    FUTURES_TOOLS = {
        "get_futures_positions", "get_perpetuals_ticker", "place_futures_order",
        "cancel_futures_order", "get_futures_margin_health", "set_futures_leverage",
        "get_liquidation_price", "get_funding_rates",
    }

    SPOT_TOOLS = {
        "get_spot_ledger", "get_spot_ticker", "place_spot_order",
        "cancel_spot_order", "get_spot_open_orders", "get_server_time",
    }

    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.spot = KrakenSpotClient(self.settings)
        self.futures = KrakenFuturesClient(self.settings)

    # ---------------------------------------------------------------- routing
    def resolve_tool_credentials(self, tool_name: str) -> Dict[str, Any]:
        is_futures = tool_name in self.FUTURES_TOOLS or "futures" in tool_name.lower() or "perp" in tool_name.lower()
        if is_futures:
            creds = self.settings.futures
            return {
                "targetDomain": "futures.kraken.com",
                "apiType": "FUTURES",
                "executionMode": "real_futures" if creds.configured else "not_configured",
                "hasKey": creds.configured,
                "keyPreview": creds.key_preview,
                "baseEndpoint": "https://futures.kraken.com/derivatives/api/v3",
            }
        creds = self.settings.spot
        return {
            "targetDomain": "api.kraken.com",
            "apiType": "SPOT",
            "executionMode": "real_spot" if creds.configured else "not_configured",
            "hasKey": creds.configured,
            "keyPreview": creds.key_preview,
            "baseEndpoint": "https://api.kraken.com/0/private",
        }

    # ---------------------------------------------------------------- execute
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        routing = self.resolve_tool_credentials(tool_name)
        logger.info("MCP tool %s via %s (%s)", tool_name, routing["targetDomain"], routing["executionMode"])
        base = {"routing": routing, "tool": tool_name}
        cfg_ok = routing["executionMode"].startswith("real")
        needs_auth = tool_name in self.FUTURES_TOOLS | self.SPOT_TOOLS

        try:
            data = self._dispatch(tool_name, arguments)
        except KrakenError as e:
            return {**base, "status": "error", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {**base, "status": "error", "error": f"{type(e).__name__}: {e}"}

        if data is None and needs_auth and not cfg_ok:
            return {
                **base,
                "status": "not_configured",
                "error": (
                    f"Kraken {routing['apiType']} credentials missing — set "
                    f"KRAKEN_{routing['apiType']}_API_KEY / KRAKEN_{routing['apiType']}_PRIVATE_KEY. "
                    "No simulated result is returned."
                ),
            }
        return {**base, "status": "success", "data": data}

    def _dispatch(self, tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
        # ---- public tools (no credentials needed) ----
        if tool_name == "get_server_time":
            return self.spot.server_time()
        if tool_name == "get_spot_ticker":
            pair = args.get("pair", "BTC/USD")
            return self.spot.ticker([KrakenSpotClient.pair_to_native(pair)])
        if tool_name == "get_perpetuals_ticker":
            pair = args.get("pair", "BTC/USD")
            return self.futures.ticker(KrakenFuturesClient.symbol_to_contract(pair))
        if tool_name == "get_funding_rates":
            pair = args.get("pair", "BTC/USD")
            return self.futures.funding_rates(KrakenFuturesClient.symbol_to_contract(pair))
        # ---- private tools (credentials required) ----
        if tool_name == "get_spot_ledger":
            if not self.settings.spot.configured:
                return None
            return self.spot.balance(args.get("asset"))
        if tool_name == "get_spot_open_orders":
            if not self.settings.spot.configured:
                return None
            return self.spot.open_orders()
        if tool_name == "place_spot_order":
            if not self.settings.spot.configured:
                return None
            pair = args["pair"]
            side = args["side"]
            return self.spot.add_order(
                KrakenSpotClient.pair_to_native(pair), side, args.get("ordertype", "limit"),
                float(args["volume"]), price=args.get("price"), oflags=args.get("oflags", "post"),
            )
        if tool_name == "cancel_spot_order":
            if not self.settings.spot.configured:
                return None
            return self.spot.cancel_order(args["txid"])
        if tool_name == "get_futures_positions":
            if not self.settings.futures.configured:
                return None
            return self.futures.positions()
        if tool_name == "place_futures_order":
            if not self.settings.futures.configured:
                return None
            pair = args["pair"]
            return self.futures.place_order(
                KrakenFuturesClient.symbol_to_contract(pair), args["side"], int(args["size"]),
                order_type=args.get("order_type", "limit"), price=args.get("price"),
            )
        if tool_name == "cancel_futures_order":
            if not self.settings.futures.configured:
                return None
            return self.futures.cancel_order(args["pair"], args["order_id"])
        if tool_name == "set_futures_leverage":
            if not self.settings.futures.configured:
                return None
            return self.futures.set_leverage(args["pair"], int(args["leverage"]))
        raise ValueError(f"unknown MCP tool '{tool_name}'")
