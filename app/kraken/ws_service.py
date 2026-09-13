"""
Real Kraken WebSocket v2 public market data service.

Docs: https://docs.kraken.com/api/docs/websocket-v2/

- Subscribes to `ticker` (L1 last/bid/ask, 24h change) and `ohlc` (candle
  updates) using the v2 envelope:
      {"method": "subscribe", "params": {"channel": "ticker", "symbol": ["BTC/USD"], "snapshot": true}}
  NOTE: v2 symbols are canonical ("BTC/USD"), NOT native ("XBTUSD").
- Incoming frames:
      {"channel": "ticker", "type": "snapshot|update", "data": [{symbol, bid, ask, last, volume, vwap, low, high, change, change_pct}]}
      {"channel": "ohlc", "type": "snapshot|update", "data": [{symbol, interval, open, high, low, close, volume, vwap, count, interval_begin}]}
      {"channel": "heartbeat"}
      {"method": "subscribe", "success": true, "result": {...}}   (ack)
- Heartbeat ping every 8s (websocket-client run_forever), automatic reconnect
  with exponential backoff.
- Thread-safe in-memory cache: latest tickers, per-(symbol,interval) candles,
  latest bar per (symbol,interval) for SSE fanout.
- Returns [] / None when the feed is down — never synthetic data.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from app.config import Settings

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
        self.last_subscribe_ack: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None

        # caches (keyed by CANONICAL symbol, e.g. "BTC/USD")
        self.tick_data: Dict[str, Dict[str, float]] = {}
        self.ticker_time: Dict[str, float] = {}
        self.candles: Dict[str, List[List[float]]] = {}  # "SYMBOL|interval" -> rows [t,o,h,l,c,v,count]
        self.last_bars: Dict[str, Dict[str, Any]] = {}   # "SYMBOL|interval" -> latest bar dict
        self._bar_seq = 0

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
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._connect_and_listen()
                backoff = 1.0  # reset backoff on clean long session
            except Exception as exc:  # noqa: BLE001
                logger.warning("WS loop error: %s", exc)
                self.last_error = f"{type(exc).__name__}: {exc}"[:200]
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
        # v2 wants canonical symbols ("BTC/USD")
        symbols = list(self.settings.tracked_symbols)
        interval = int(self.settings.default_interval)
        ws.send(json.dumps({
            "method": "subscribe",
            "params": {"channel": "ticker", "symbol": symbols, "snapshot": True},
        }))
        ws.send(json.dumps({
            "method": "subscribe",
            "params": {"channel": "ohlc", "symbol": symbols, "interval": interval, "snapshot": True},
        }))
        with self._lock:
            self.connected = True
            self.reconnect_attempts = 0
        self._emit("status", {"wsConnected": True})

    def _on_message(self, ws, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        if not isinstance(msg, dict):
            return
        self.last_message_time = time.time()

        # acknowledgements / errors for (un)subscribe
        if "method" in msg:
            method = msg.get("method")
            if method in ("subscribe", "unsubscribe", "ping", "pong"):
                if msg.get("success") is False:
                    self.last_error = str(msg.get("error") or msg)[:200]
                    self._emit("ws-message", msg)
                else:
                    with self._lock:
                        self.last_subscribe_ack = msg
                    self._emit("ws-message", msg)
                return
            self._emit("ws-message", msg)
            return

        channel = (msg.get("channel") or "").lower()
        if channel == "heartbeat":
            return
        if channel == "status":
            self._emit("status", msg)
            return
        if channel == "ticker":
            self._handle_ticker(msg.get("data") or [])
        elif channel == "ohlc":
            self._handle_ohlc(msg.get("data") or [])
        else:
            self._emit("ws-message", msg)

    def _handle_ticker(self, rows: List[Dict[str, Any]]) -> None:
        with self._lock:
            for row in rows:
                try:
                    symbol = row.get("symbol")
                    if not symbol:
                        continue
                    last = float(row.get("last") or 0)
                    if last <= 0:
                        continue
                    self.tick_data[symbol] = {
                        "last": last,
                        "bid": float(row.get("bid") or 0),
                        "ask": float(row.get("ask") or 0),
                        "high": float(row.get("high") or 0),
                        "low": float(row.get("low") or 0),
                        "volume": float(row.get("volume") or 0),
                        "vwap": float(row.get("vwap") or 0),
                        "change": float(row.get("change") or 0),
                        "change_pct": float(row.get("change_pct") or 0),
                    }
                    self.ticker_time[symbol] = time.time()
                except (TypeError, ValueError):
                    continue
        self._emit("ticker", {"tickers": self.get_tickers()})

    def _handle_ohlc(self, rows: List[Dict[str, Any]]) -> None:
        bars: List[Dict[str, Any]] = []
        with self._lock:
            for row in rows:
                try:
                    symbol = row.get("symbol")
                    interval = int(row.get("interval") or self.settings.default_interval)
                    if not symbol:
                        continue
                    # v2 uses interval_begin (ISO); older frames used timestamp (sec)
                    begin = row.get("interval_begin") or row.get("timestamp")
                    if isinstance(begin, str):
                        try:
                            t = time.mktime(time.strptime(begin[:19], "%Y-%m-%dT%H:%M:%S"))
                        except ValueError:
                            t = time.time()
                    else:
                        t = float(begin or time.time())
                    o = float(row.get("open") or 0)
                    h = float(row.get("high") or 0)
                    low = float(row.get("low") or 0)
                    c = float(row.get("close") or 0)
                    v = float(row.get("volume") or 0)
                    if c <= 0:
                        continue
                    key = f"{symbol}|{interval}"
                    bucket = self.candles.setdefault(key, [])
                    frame = [t, o, h, low, c, v, float(row.get("count") or 0)]
                    if bucket and abs(frame[0] - bucket[-1][0]) < 1:
                        bucket[-1] = frame
                    else:
                        bucket.append(frame)
                    if len(bucket) > 2000:
                        del bucket[: len(bucket) - 2000]
                    bar = {
                        "symbol": symbol,
                        "pair": symbol,
                        "interval": interval,
                        "time": int(t),
                        "timestamp": int(t * 1000),
                        "open": o,
                        "high": h,
                        "low": low,
                        "close": c,
                        "volume": v,
                        "source": "ws.kraken.com/v2 (live)",
                    }
                    self.last_bars[key] = bar
                    self._bar_seq += 1
                    bars.append(bar)
                except (TypeError, ValueError):
                    continue
        for bar in bars:
            self._emit("ohlc_bar", {"type": "ohlc_bar", "bar": bar})

    def _on_error(self, ws, error) -> None:
        logger.debug("WS error: %s", error)
        self.last_error = str(error)[:200]

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
        out: List[Dict[str, Any]] = []
        with self._lock:
            for symbol in self.settings.tracked_symbols:
                row = self.tick_data.get(symbol)
                if not row:
                    continue
                out.append(
                    {
                        "pair": symbol,
                        "symbol": symbol,
                        "price": row["last"],
                        "lastPrice": row["last"],
                        "bid": row["bid"],
                        "ask": row["ask"],
                        "change24h": round(row["change_pct"], 4),
                        "changeAbs": round(row["change"], 6),
                        "high": row["high"],
                        "low": row["low"],
                        "volume": row["volume"],
                        "vwap": row["vwap"] or None,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.ticker_time.get(symbol, time.time()))),
                        "source": "ws.kraken.com/v2 (live)",
                    }
                )
        return out

    def get_mark_price(self, symbol: str) -> Optional[float]:
        with self._lock:
            row = self.tick_data.get(symbol)
            return row["last"] if row else None

    def get_candles(self, symbol: str, interval: int) -> List[List[float]]:
        """Real confirmed candles from the WS feed (may be sparse right after start)."""
        key = f"{symbol}|{interval}"
        with self._lock:
            return list(self.candles.get(key, []))

    def get_last_bars(self) -> Dict[str, Dict[str, Any]]:
        """Latest ohlc bar per 'SYMBOL|interval' (for SSE fanout)."""
        with self._lock:
            return dict(self.last_bars)

    def get_real_time_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "wsConnected": self.connected,
                "lastMessageTime": self.last_message_time,
                "secondsSinceMessage": (time.time() - self.last_message_time) if self.last_message_time else None,
                "reconnectAttempts": self.reconnect_attempts,
                "cachedTickers": len(self.tick_data),
                "cachedBars": len(self.last_bars),
                "lastError": self.last_error,
            }
