"""
Thread-safe event bus: ring buffer + SSE fanout.
The 'watchdog buffered events' the UI shows are these real engine events.
"""
from __future__ import annotations

import itertools
import json
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional


class LogBus:
    def __init__(self, capacity: int = 512):
        self._lock = threading.RLock()
        self._seq = itertools.count(1)
        self._ring: deque = deque(maxlen=capacity)
        self._subs: List[Callable[[str, Any], None]] = []
        self.capacity = capacity
        self.dropped = 0

    def emit(self, level: str, module: str, message: str, strategy_id: str = "") -> Dict[str, Any]:
        event = {
            "id": f"EVT-{next(self._seq):06d}",
            "timestamp": int(time.time() * 1000),
            "level": level,
            "module": module,
            "message": message,
            "strategyId": strategy_id,
            "severity": {"info": "INFO", "warn": "WARN", "error": "ERROR", "trade": "OK"}.get(level, "INFO"),
        }
        with self._lock:
            self._ring.append(event)
            subs = list(self._subs)
        for cb in subs:
            try:
                cb("event", event)
            except Exception:
                self.dropped += 1
        return event

    def buffer(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._ring)

    def flush(self) -> int:
        with self._lock:
            n = len(self._ring)
            self._ring.clear()
            return n

    def fill_percent(self) -> int:
        with self._lock:
            return round(100.0 * len(self._ring) / self.capacity)

    def subscribe(self, cb: Callable[[str, Any], None]) -> None:
        with self._lock:
            self._subs.append(cb)

    def unsubscribe(self, cb: Callable[[str, Any], None]) -> None:
        with self._lock:
            if cb in self._subs:
                self._subs.remove(cb)
