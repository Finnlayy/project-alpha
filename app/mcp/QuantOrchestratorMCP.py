"""
=========================================================
Datei:      app/mcp/QuantOrchestratorMCP.py
Zweck:      MCP (Model Context Protocol) Tools für autonome Agenten (Neo_Fable / KimiSwarm)
Knoten:     Jaune (Carrera-Engine) / MCP Gateway
System:     "The Judge & The Swarm" - Zero-Dummy Guarantee
=========================================================
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional
from app.execution.QuantOrchestrator import QuantOrchestrator

logger = logging.getLogger("app.mcp.quant_orchestrator")


class QuantOrchestratorMCP:
    """
    Exponiert MCP-Tools für autonome Agenten wie Neo_Fable oder KimiSwarm,
    um Bot-Sessions aus der Historie bei Regimewechseln autonom zu klonen.
    """

    def __init__(self, orchestrator: Optional[QuantOrchestrator] = None):
        self.orchestrator = orchestrator or QuantOrchestrator()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Gibt JSON-Schema Tool-Definitionen für LLM Function Calling zurück."""
        return [
            {
                "name": "spawn_from_history",
                "description": (
                    "Klont eine verifizierte historische Bot-Session aus der Datenbank als "
                    "neuen Live-Worker im Swarm. Parameter (wie Hebel oder DCA-Range) können "
                    "über 'modifier' an die aktuelle Marktvolatilität angepasst werden."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "historical_bot_id": {
                            "type": "string",
                            "description": "Die ID des historischen Vorbild-Bots (z.B. 'BOT-HIST-7742')."
                        },
                        "modifier": {
                            "type": "object",
                            "description": (
                                "Optionale Parameteranpassungen durch den AI-Agenten "
                                "(z.B. {'leverage': 3, 'name': 'NeoFable HighVola Adaption'})."
                            )
                        }
                    },
                    "required": ["historical_bot_id"]
                }
            },
            {
                "name": "query_historical_bots",
                "description": (
                    "Durchsucht die historische Bot-Datenbank nach profitablen Sessions "
                    "für ein bestimmtes Währungspaar und/oder Markt-Regime (z.B. 'persistent_trending', 'mean_reverting')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pair": {
                            "type": "string",
                            "description": "Optionales Handelspaar (z.B. 'BTC/USD.P' oder 'ETH/USD')."
                        },
                        "regime": {
                            "type": "string",
                            "description": "Optionales Markt-Regime (z.B. 'persistent_trending', 'mean_reverting', 'high_volatility')."
                        }
                    }
                }
            },
            {
                "name": "stop_worker_session",
                "description": "Stoppt einen aktiven Worker-Bot und archiviert dessen finale P&L in der Datenbank.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "bot_id": {
                            "type": "string",
                            "description": "Die ID des aktiven Bots."
                        },
                        "reason": {
                            "type": "string",
                            "description": "Grund für den Abbruch (z.B. 'REGIME_SHIFT_DETECTED', 'MAX_DRAWDOWN_HIT')."
                        }
                    },
                    "required": ["bot_id"]
                }
            }
        ]

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Führt einen MCP-Tool-Call deterministisch aus."""
        if tool_name == "spawn_from_history":
            hist_id = arguments.get("historical_bot_id")
            if not hist_id:
                raise ValueError("Argument 'historical_bot_id' ist erforderlich.")
            modifier = arguments.get("modifier")
            new_bot = self.orchestrator.spawn_from_history(hist_id, modifier=modifier)
            return {
                "success": True,
                "action": "SPAWNED_FROM_HISTORY",
                "bot_id": new_bot["id"],
                "name": new_bot["name"],
                "pair": new_bot["pair"],
                "leverage": new_bot["leverage"],
                "initial_investment": new_bot["metrics"]["investment"],
                "status": new_bot["status"]
            }

        elif tool_name == "query_historical_bots":
            pair = arguments.get("pair")
            regime = arguments.get("regime")
            results = self.orchestrator.list_historical_bots(pair=pair, regime=regime)
            return {
                "success": True,
                "count": len(results),
                "sessions": results
            }

        elif tool_name == "stop_worker_session":
            bot_id = arguments.get("bot_id")
            reason = arguments.get("reason", "MANUAL_STOP")
            if not bot_id:
                raise ValueError("Argument 'bot_id' ist erforderlich.")
            res = self.orchestrator.stop_worker(bot_id, reason=reason)
            return {
                "success": True,
                "action": "STOPPED_AND_ARCHIVED",
                **res
            }

        else:
            raise ValueError(f"Unbekanntes MCP-Tool: '{tool_name}'")
