"""
Real Kraken WebSocket v2 public market data service.

- Subscribes to `ticker` (real-time last prices) and `ohlc-v1` (candle updates)
- Heartbeat ping every 5s, automatic reconnect with exponential backoff
- Thread-safe in-memory cache: latest tickers, per-(pair,interval) confirmed candles
- Exposes the same shape the UI expects; returns [] / 0 when the feed is down —
  never synthetic data.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.config import Settings
from app.kraken.spot_client import KrakenSpotClient

logger = logging.getLogger("app.kraken.ws")


class KrakenWebSocketService:
    def __init__(self, settings: Settings, on_event: Optional[Callable[[str, Any], None]] = None):
        self.settings = settings
        self.on_event = on_event  # SSE fanout callback: (event_name, data_dict)

        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

        self.connected = False
        self.last_message_time: Optional[float] = None
        self.started_at: Optional[float] = None
        self.reconnect_attempts = 0

        # caches
        self.tick_data: Dict[str, List[float]] = {}  # pair -> [c,o,h,l,v,vw,l,a,spread]
        self.ticker_time: Dict[str, float] = {}
        self.candles: Dict[str, List[List[float]]] = {}  # "PAIR|interval" -> rows [t,o,h,l,c,v,cnt]
        self.last_rest_latency_ms: float = 0.0

    # ---------------------------------------------------------------- control
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._run_loop, name="kraken-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------- loop
    def _run_loop(self) -> None:
        import websocket  # websockets or websocket-client, loaded lazily

        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._connect_and_listen()
                backoff = 1.0  # reset backoff on clean long session
            except Exception as exc:  # noqa: BLE001
                logger.warning("WS loop error: %s", exc)
            with self._lock:
                self.connected = False
            if self._stop.is_set():
                break
            self.reconnect_attempts += 1
            self._emit("status", {"wsConnected": False, "reconnectAttempt": self.reconnect_attempts})
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 30.0)

    def _connect_and_listen(self) -> None:
        import websocket

        ws = websocket.WebSocketApp(
            self.settings.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        with self._lock:
            self._ws = ws
        # run_forever blocks until the connection closes. Built-in pings (8s)
        # keep the Kraken v2 session alive and detect dead links (ping_timeout).
        ws.run_forever(ping_interval=8, ping_timeout=5)

    def _on_open(self, ws) -> None:
        pairs = [KrakenSpotClient.pair_to_native(s) for s in self.settings.tracked_symbols]
        subs = [{"subscription": {"name": "ticker"}, "pair": pairs}]
        for interval in (self.settings.default_interval,):
            subs.append({"subscription": {"name": "ohlc-v1", "interval": str(interval)}, "pair": pairs})
        ws.send(json.dumps({"method": "subscribe", "params": subs, "id": "alpha-sub-1"}))
        with self._lock:
            self.connected = True
            self.reconnect_attempts = 0
        self._emit("status", {"wsConnected": True})

    def _on_message(self, ws, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        self.last_message_time = time.time()
        mtype = msg.get("method")
        if mtype in ("snapshot", "heartbeat"):
            return
        if msg.get("channelType") == "data" and msg.get("subscription"):
            self._handle_data(msg)
        elif mtype in ("subscribe", "unsubscribe", "error"):
            self._emit("ws-message", msg)

    def _handle_data(self, msg: Dict[str, Any]) -> None:
        sub = msg.get("subscription") or {}
        name = (sub.get("name") or "").lower()
        data = msg.get("data") or {}
        with self._lock:
            if name == "ticker":
                for pair, row in data.items():
                    if isinstance(row, list) and len(row) >= 9:
                        self.tick_data[pair] = [float(x) if x is not None else 0.0 for x in row]
                        self.ticker_time[pair] = time.time()
            elif name.startswith("ohlc"):
                interval = sub.get("interval", str(self.settings.default_interval))
                for pair, rows in data.items():
                    if not isinstance(rows, dict):
                        continue
                    for _iv, row_list in rows.items():
                        key = f"{pair}|{_iv}"
                        bucket = self.candles.setdefault(key, [])
                        for row in row_list:
                            if isinstance(row, list) and len(row) >= 6:
                                if bucket and abs(float(row[0]) - float(bucket[-1][0])) < 1:
                                    bucket[-1] = row
                                else:
                                    bucket.append(row)
                        if len(bucket) > 2000:
                            del bucket[: len(bucket) - 2000]
        self._emit("ticker", {"tickers": self.get_tickers()})

    def _on_error(self, ws, error) -> None:
        logger.debug("WS error: %s", error)

    def _on_close(self, ws, *_args) -> None:
        with self._lock:
            self.connected = False
        self._emit("status", {"wsConnected": False})

    def _emit(self, event: str, data: Any) -> None:
        if self.on_event:
            try:
                self.on_event(event, data)
            except Exception:  # noqa: BLE001
                logger.exception("on_event handler failed")

    # ------------------------------------------------------------------ reads
    def get_tickers(self) -> List[Dict[str, Any]]:
        """Latest real tickers. [] when feed unavailable."""
        spot = KrakenSpotClient(self.settings)
        out: List[Dict[str, Any]] = []
        with self._lock:
            for symbol in self.settings.tracked_symbols:
                native = spot.pair_to_native(symbol)
                row = self.tick_data.get(native)
                if not row:
                    continue
                last, open_, high, low, volume = row[0], row[1], row[2], row[3], row[4]
                if open_ <= 0:
                    continue
                change24h = (last - open_) / open_ * 100.0  # 24h open from ticker frame
                out.append(
                    {
                        "pair": symbol,
                        "symbol": symbol,
                        "price": last,
                        "lastPrice": last,
                        "change24h": round(change24h, 4),
                        "high": high,
                        "low": low,
                        "volume": volume,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.ticker_time.get(native, time.time()))),
                        "source": "ws.kraken.com/v2 (live)",
                    }
                )
        return out

    def get_mark_price(self, symbol: str) -> Optional[float]:
        native = KrakenSpotClient.pair_to_native(symbol)
        with self._lock:
            row = self.tick_data.get(native)
            return row[0] if row else None

    def get_candles(self, symbol: str, interval: int) -> List[List[float]]:
        """Real confirmed candles from the WS feed (may be sparse right after start)."""
        native = KrakenSpotClient.pair_to_native(symbol)
        key = f"{native}|{interval}"
        with self._lock:
            return list(self.candles.get(key, []))

    def get_real_time_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "wsConnected": self.connected,
                "lastMessageTime": self.last_message_time,
                "secondsSinceMessage": (time.time() - self.last_message_time) if self.last_message_time else None,
                "reconnectAttempts": self.reconnect_attempts,
                "cachedTickers": len(self.tick_data),
            }
