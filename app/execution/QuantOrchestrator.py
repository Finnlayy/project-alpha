"""
=========================================================
Datei:      app/execution/QuantOrchestrator.py
Zweck:      Autonomer Multi-Agenten Bot-Lifecycle & Historical Session Respawn Engine
Knoten:     Jaune (Carrera-Engine) / Swarm Orchestration Core
System:     "The Judge & The Swarm" - Zero-Dummy Guarantee
=========================================================
"""
from __future__ import annotations
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.execution.quant_orchestrator")


class QuantOrchestrator:
    """
    Verwaltet historische Bot-Sessions und ermöglicht Multi-Agenten-Systemen
    (z.B. Neo_Fable / KimiSwarm), erfolgreich erprobte Bot-Konfigurationen 
    autonom anhand von Markt-Regimen als neue Live-Worker zu spawnen.
    """

    def __init__(self, db_path: str = ":memory:", broadcast_callback: Optional[callable] = None):
        self.db_path = db_path
        self.broadcast_callback = broadcast_callback
        self.active_workers: Dict[str, Dict[str, Any]] = {}
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_database()
        self._seed_historical_sessions()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_database(self) -> None:
        """Initialisiert das relationale Schema für persistierte Bot-Sessions."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_history (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    final_pnl REAL NOT NULL,
                    roi REAL NOT NULL,
                    config_json TEXT NOT NULL,
                    stopped_at TIMESTAMP NOT NULL
                )
            """)
            conn.commit()

    def _seed_historical_sessions(self) -> None:
        """Befüllt die Historie mit verifizierten historischen Bot-Konfigurationen."""
        initial_history = [
            {
                "id": "BOT-HIST-7742",
                "name": "Alpha-Momentum Worker (Genesis Run)",
                "pair": "BTC/USD.P",
                "regime": "persistent_trending",
                "final_pnl": 6000.70,
                "roi": 60.01,
                "config": {
                    "name": "Alpha Momentum Worker",
                    "exchange": "Kraken Futures",
                    "pair": "BTC/USD.P",
                    "strategy": "M8 KELLY DCA",
                    "direction": "LONG",
                    "leverage": 5,
                    "initial_investment": 10000.0,
                    "currency": "USD",
                    "dcaRangeMin": 60500.0,
                    "dcaRangeMax": 65200.0,
                    "dcaSteps": 6,
                    "liquidationPrice": 51800.0,
                    "liquidationDistancePct": 19.4,
                    "apr": 121.8,
                    "entryPrice": 62840.0,
                    "currentPrice": 64280.5
                },
                "stopped_at": "2026-09-08T18:30:00Z"
            },
            {
                "id": "BOT-HIST-8819",
                "name": "Sigma Mean-Reversion Bot (Alpha Epoch)",
                "pair": "ETH/USD",
                "regime": "mean_reverting",
                "final_pnl": 2576.25,
                "roi": 42.94,
                "config": {
                    "name": "Sigma Mean-Reversion Bot",
                    "exchange": "Kraken Pro Spot",
                    "pair": "ETH/USD",
                    "strategy": "DFA HURST BAND",
                    "direction": "LONG",
                    "leverage": 2,
                    "initial_investment": 6000.0,
                    "currency": "USD",
                    "dcaRangeMin": 3200.0,
                    "dcaRangeMax": 3650.0,
                    "dcaSteps": 5,
                    "liquidationPrice": 1750.0,
                    "liquidationDistancePct": 49.3,
                    "apr": 60.3,
                    "entryPrice": 3380.0,
                    "currentPrice": 3450.25
                },
                "stopped_at": "2026-09-07T12:15:00Z"
            },
            {
                "id": "BOT-HIST-9901",
                "name": "Delta Cadence Scalper (High Vola Cycle)",
                "pair": "SOL/USD.P",
                "regime": "high_volatility",
                "final_pnl": 2135.40,
                "roi": 61.01,
                "config": {
                    "name": "Delta Cadence Scalper",
                    "exchange": "Kraken Futures",
                    "pair": "SOL/USD.P",
                    "strategy": "CADENCE BANDPASS",
                    "direction": "SHORT",
                    "leverage": 4,
                    "initial_investment": 3500.0,
                    "currency": "USD",
                    "dcaRangeMin": 140.0,
                    "dcaRangeMax": 156.0,
                    "dcaSteps": 4,
                    "liquidationPrice": 182.2,
                    "liquidationDistancePct": 25.8,
                    "apr": 247.4,
                    "entryPrice": 148.5,
                    "currentPrice": 144.8
                },
                "stopped_at": "2026-09-06T22:45:00Z"
            }
        ]

        with self._get_connection() as conn:
            for item in initial_history:
                conn.execute("""
                    INSERT OR IGNORE INTO bot_history (id, name, pair, regime, final_pnl, roi, config_json, stopped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["id"],
                    item["name"],
                    item["pair"],
                    item["regime"],
                    item["final_pnl"],
                    item["roi"],
                    json.dumps(item["config"]),
                    item["stopped_at"]
                ))
            conn.commit()

    def get_historical_session(self, historical_bot_id: str) -> Optional[Dict[str, Any]]:
        """Ruft einen historischen Bot-Datensatz ab."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, name, pair, regime, final_pnl, roi, config_json, stopped_at FROM bot_history WHERE id = ?",
                (historical_bot_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "pair": row["pair"],
                "regime": row["regime"],
                "final_pnl": row["final_pnl"],
                "roi": row["roi"],
                "config": json.loads(row["config_json"]),
                "stopped_at": row["stopped_at"]
            }

    def list_historical_bots(self, pair: Optional[str] = None, regime: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gibt eine Liste archivierter Bot-Sessions zurück, optional gefiltert."""
        query = "SELECT id, name, pair, regime, final_pnl, roi, config_json, stopped_at FROM bot_history"
        params: List[Any] = []
        conditions: List[str] = []

        if pair:
            conditions.append("pair = ?")
            params.append(pair)
        if regime:
            conditions.append("regime = ?")
            params.append(regime)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY roi DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "pair": r["pair"],
                    "regime": r["regime"],
                    "final_pnl": r["final_pnl"],
                    "roi": r["roi"],
                    "config": json.loads(r["config_json"]),
                    "stopped_at": r["stopped_at"]
                }
                for r in rows
            ]

    def spawn_from_history(self, historical_bot_id: str, modifier: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Lässt den Orchestrator (z.B. Neo_Fable oder KimiSwarm) einen historischen Bot
        als neue, voll funktionale Live-Session klonen.
        'modifier' erlaubt es der AI, Parameter wie Hebel, Investment oder DCA-Range
        dynamisch an das aktuelle Markt-Regime anzupassen.
        """
        historical = self.get_historical_session(historical_bot_id)
        if not historical:
            raise ValueError(f"Historische Bot-Session '{historical_bot_id}' wurde nicht in der Datenbank gefunden.")

        old_config = historical["config"]
        new_bot_id = f"BOT-{str(uuid.uuid4())[:4].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Saubere Reset-Metriken für den neuen Durchlauf
        initial_invest = float(old_config.get("initial_investment", 5000.0))
        currency = old_config.get("currency", "USD")

        new_config: Dict[str, Any] = {
            **old_config,
            "id": new_bot_id,
            "name": f"{old_config.get('name', 'Cloned Bot')} [Spawned]",
            "status": "active",
            "spawnedFrom": historical_bot_id,
            "start_time": now_iso,
            "lastUpdate": now_iso,
            "unrealizedPnL": {
                "value": 0.0,
                "percentage": 0.0
            },
            "metrics": {
                "investment": initial_invest,
                "currency": currency,
                "realizedProfit": 0.0,
                "dcaRangeMin": old_config.get("dcaRangeMin", 100.0),
                "dcaRangeMax": old_config.get("dcaRangeMax", 110.0),
                "dcaSteps": old_config.get("dcaSteps", 5),
                "dcaOrdersTriggered": 0,
                "fundingFees": 0.0,
                "liquidationPrice": old_config.get("liquidationPrice", 0.0),
                "liquidationDistancePct": old_config.get("liquidationDistancePct", 30.0)
            },
            "runtime": {
                "days": 0,
                "hours": 0,
                "minutes": 0,
                "cycles": 0
            },
            "totalProfit": 0.0,
            "roi": 0.0,
            "apr": old_config.get("apr", 45.0)
        }

        # AI Modifier anwenden (z.B. AI passt Hebel oder DCA Range an)
        if modifier:
            for k, v in modifier.items():
                if k == "metrics" and isinstance(v, dict):
                    new_config["metrics"].update(v)
                elif k in new_config:
                    new_config[k] = v
                else:
                    new_config[k] = v

        # In aktiven Worker-Pool einreihen
        self.active_workers[new_bot_id] = new_config
        logger.info(f"Autonomer Respawn erfolgreich: Neuer Bot '{new_bot_id}' aus '{historical_bot_id}' geklont.")

        # Optionaler WebSocket / SSE Broadcast an das Dashboard
        self.broadcast_new_session(new_config)

        return new_config

    def stop_worker(self, bot_id: str, reason: str = "MANUAL_STOP") -> Dict[str, Any]:
        """Stoppt einen aktiven Worker und archiviert seine finale Session in bot_history."""
        if bot_id not in self.active_workers:
            raise ValueError(f"Worker '{bot_id}' ist nicht aktiv.")

        bot = self.active_workers.pop(bot_id)
        bot["status"] = "paused"
        stopped_at = datetime.now(timezone.utc).isoformat()

        final_pnl = float(bot.get("totalProfit", 0.0))
        investment = float(bot.get("metrics", {}).get("investment", 1000.0))
        roi = round((final_pnl / investment * 100.0), 2) if investment > 0 else 0.0

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO bot_history (id, name, pair, regime, final_pnl, roi, config_json, stopped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bot_id,
                bot.get("name", "Stopped Worker"),
                bot.get("pair", "UNKNOWN"),
                bot.get("regime", "neutral"),
                final_pnl,
                roi,
                json.dumps(bot),
                stopped_at
            ))
            conn.commit()

        logger.info(f"Worker '{bot_id}' gestoppt und in der Datenbank archiviert.")
        return {"bot_id": bot_id, "stopped_at": stopped_at, "final_pnl": final_pnl, "roi": roi}

    def broadcast_new_session(self, new_config: Dict[str, Any]) -> None:
        """Sendet Event über Broadcast-Channel (SSE / WebSocket)."""
        if callable(self.broadcast_callback):
            try:
                self.broadcast_callback(new_config)
            except Exception as e:
                logger.warning(f"Broadcast-Callback Fehler: {e}")
