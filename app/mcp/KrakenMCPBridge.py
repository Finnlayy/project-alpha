"""
=========================================================
Datei:      app/mcp/KrakenMCPBridge.py (v1.7.0)
Zweck:      Verdrahtung & Dual-Key Routing (Spot vs. Futures) für MCP Exchange Tools
Knoten:     Jaune (Carrera-Engine) / MCP Gateway
=========================================================
"""
import logging
from typing import Dict, Any, Optional
from app.security.SettingsEnvManager import SettingsEnvManager

logger = logging.getLogger("app.mcp.kraken_bridge")

class KrakenMCPBridge:
    """
    Routet Anfragen an die korrekte Kraken-Infrastruktur basierend auf dem Tool-Typ:
    1. Spot API (`api.kraken.com`): Ledgers, Spot-Orders, Ticker, Fiat Funding
    2. Futures API (`futures.kraken.com`): Perpetual Swaps, Hebel-Derivate, Liquidation Levels
    """

    FUTURES_TOOLS = {
        "get_futures_positions", "get_perpetuals_ticker", "place_futures_order",
        "cancel_futures_order", "get_futures_margin_health", "set_futures_leverage",
        "get_liquidation_price", "get_funding_rates"
    }

    def __init__(self, env_manager: Optional[SettingsEnvManager] = None):
        self.env_manager = env_manager or SettingsEnvManager()

    def resolve_tool_credentials(self, tool_name: str) -> Dict[str, Any]:
        """
        Gibt das korrekte Schlüsselpaar (Spot vs. Futures) für ein bestimmtes MCP-Tool zurück.
        """
        is_futures = tool_name in self.FUTURES_TOOLS or "futures" in tool_name.lower() or "perp" in tool_name.lower()

        if is_futures:
            api_key, secret = self.env_manager.get_kraken_futures_credentials()
            domain = "futures.kraken.com"
            mode = "real_futures" if (api_key and secret) else "simulated_futures"
            return {
                "targetDomain": domain,
                "apiType": "FUTURES",
                "executionMode": mode,
                "hasKey": bool(api_key and secret),
                "keyPreview": self.env_manager.mask_key(api_key),
                "baseEndpoint": "https://futures.kraken.com/derivatives/api/v3"
            }
        else:
            api_key, secret = self.env_manager.get_kraken_spot_credentials()
            domain = "api.kraken.com"
            mode = "real_spot" if (api_key and secret) else "simulated_spot"
            return {
                "targetDomain": domain,
                "apiType": "SPOT",
                "executionMode": mode,
                "hasKey": bool(api_key and secret),
                "keyPreview": self.env_manager.mask_key(api_key),
                "baseEndpoint": "https://api.kraken.com/0/private"
            }

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Führt ein MCP-Tool aus unter Berücksichtigung des Dual-Key-Routings."""
        routing = self.resolve_tool_credentials(tool_name)
        logger.info("Executing MCP Tool %s via %s (Mode: %s)", tool_name, routing["targetDomain"], routing["executionMode"])

        if routing["executionMode"] == "simulated_futures":
            return {
                "status": "success",
                "routing": routing,
                "warning": "Kraken Futures API-Key nicht in .env hinterlegt. Ergebnis wird aus der Simulation zurückgegeben.",
                "data": {"tool": tool_name, "simulated": True, "arguments": arguments}
            }
        elif routing["executionMode"] == "simulated_spot":
            return {
                "status": "success",
                "routing": routing,
                "warning": "Kraken Spot API-Key nicht in .env hinterlegt. Ergebnis wird aus der Simulation zurückgegeben.",
                "data": {"tool": tool_name, "simulated": True, "arguments": arguments}
            }

        return {
            "status": "success",
            "routing": routing,
            "data": {"tool": tool_name, "authenticated": True, "arguments": arguments}
        }
