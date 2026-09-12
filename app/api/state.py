"""
Application state: singletons + bootstrap for the FastAPI app.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from app.auth.session import SessionService
from app.config import Settings, get_session_secret, load_settings
from app.crypto.webauthn import WebAuthnEngine
from app.execution.trading_engine import TradingEngine
from app.kraken.ws_service import KrakenWebSocketService
from app.logbus import LogBus
from app.storage.lake import DataLake

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


class AppState:
    def __init__(self):
        self.settings: Settings = load_settings()
        self.lake: DataLake = DataLake(self.settings.db_path)
        self.bus: LogBus = LogBus(capacity=512)

        def _ws_event(event: str, data: Any) -> None:
            import json as _json

            self.bus.emit("info", "KrakenWS", f"{event}: {str(data)[:280]}")

        self.ws: KrakenWebSocketService = KrakenWebSocketService(self.settings, on_event=_ws_event)
        self.engine: TradingEngine = TradingEngine(self.settings, self.lake, self.bus)
        self.engine.set_ws_service(self.ws)
        self.webauthn: WebAuthnEngine = WebAuthnEngine(
            rp_id=self.settings.rp_id,
            rp_name="Projekt:Alpha",
            allowed_origins=self.settings.allowed_origins,
            challenge_ttl=self.settings.challenge_ttl_seconds,
        )
        self.sessions: SessionService = SessionService(get_session_secret(self.settings).encode("utf-8"), self.settings.session_ttl_seconds)
        self._ws_started = False

    def start_background(self) -> None:
        if not self._ws_started:
            self.ws.start()
            self._ws_started = True
        self.engine.load()
        self.bus.emit("info", "Bootstrap", "backend ready")

    def candle_cache(self, symbol: str, interval_min: int, limit: int = 500) -> tuple[list, str]:
        """(candles, source) — lake cache first, live REST refresh on top."""
        from app.kraken.spot_client import KrakenError, KrakenSpotClient

        spot = KrakenSpotClient(self.settings)
        try:
            payload = spot.ohlc(KrakenSpotClient.pair_to_native(symbol), interval_min)
            if payload:
                native = list(payload.keys())[0]
                rows = [
                    {"time": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5]) if len(r) > 5 else 0.0}
                    for r in payload[native]
                ]
                if rows:
                    self.lake.upsert_candles(symbol, interval_min, rows[-limit:])
                    return rows[-limit:], "api.kraken.com (live)"
        except KrakenError:
            pass
        cached = self.lake.fetch_candles(symbol, interval_min, limit=limit)
        return cached, "lake cache (stale — Kraken REST unreachable)"

    def market_tickers(self):
        return self.ws.get_tickers()
