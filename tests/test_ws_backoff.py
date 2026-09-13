"""
MODULE A — Websocket v2 reconnect backoff.

Regression test for a real reconnect storm. ``websocket.run_forever()`` reports
a failed DNS/TLS/handshake through ``on_error`` and then RETURNS NORMALLY
instead of raising. The previous loop treated "returned without an exception"
as a clean session and reset ``backoff = 1.0`` on every iteration, so an
unreachable feed was retried exactly once per second, forever — never reaching
the documented exponential ladder or its 30 s cap.

The loop now measures how long the session actually lasted:

    session_seconds = now - opened_at      (0.0 when the socket never opened)
    stable          = session_seconds >= STABLE_SESSION_SECONDS

and only a stable session resets the ladder.

These tests drive ``_run_loop`` synchronously with a stubbed transport and a
recording ``Event.wait``, so the exact wait sequence is asserted without any
network access and without spawning threads.
"""
from __future__ import annotations

import time
from typing import List, Optional

import pytest

from app.config import Settings
from app.kraken.ws_service import KrakenWebSocketService


@pytest.fixture
def svc() -> KrakenWebSocketService:
    return KrakenWebSocketService(Settings())


def _drive(
    svc: KrakenWebSocketService,
    monkeypatch: pytest.MonkeyPatch,
    opened_offsets: List[Optional[float]],
) -> List[float]:
    """Run the loop over a scripted sequence of sessions; return the waits used.

    ``opened_offsets[i]`` is either ``None`` (the socket never opened) or the
    number of seconds the i-th session lasted. The loop is stopped after the
    final scripted session.
    """
    waits: List[float] = []
    index = {"i": 0}

    def fake_connect() -> Optional[float]:
        i = index["i"]
        index["i"] += 1
        if i >= len(opened_offsets):
            # script exhausted: stop the loop. The check happens at the TOP of a
            # session, so every scripted session still completes its own wait —
            # len(waits) == len(opened_offsets).
            svc._stop.set()
            return None
        offset = opened_offsets[i]
        if offset is None:
            return None              # handshake failed: never opened
        return time.time() - offset  # opened `offset` seconds ago

    monkeypatch.setattr(svc, "_connect_and_listen", fake_connect)
    monkeypatch.setattr(svc._stop, "wait", lambda seconds: waits.append(seconds) or False)

    svc._run_loop()
    return waits


# ------------------------------------------------------------ pure policy
def test_backoff_policy_does_not_reset_on_a_failed_handshake(svc: KrakenWebSocketService) -> None:
    """A session that never opened (0.0 s) must NOT reset the ladder."""
    assert svc.backoff_for_session(8.0, 0.0) == 8.0
    assert svc.backoff_for_session(30.0, 0.0) == 30.0


def test_backoff_policy_does_not_reset_on_a_flapping_session(svc: KrakenWebSocketService) -> None:
    """Just under the stability threshold still counts as unhealthy."""
    just_under = svc.STABLE_SESSION_SECONDS - 0.001
    assert svc.backoff_for_session(16.0, just_under) == 16.0
    assert svc.backoff_for_session(16.0, 5.0) == 16.0


def test_backoff_policy_resets_only_on_a_stable_session(svc: KrakenWebSocketService) -> None:
    assert svc.backoff_for_session(30.0, svc.STABLE_SESSION_SECONDS) == svc.RECONNECT_BACKOFF_INITIAL
    assert svc.backoff_for_session(30.0, 3600.0) == svc.RECONNECT_BACKOFF_INITIAL


def test_escalation_is_geometric_and_capped(svc: KrakenWebSocketService) -> None:
    ladder: List[float] = []
    backoff = svc.RECONNECT_BACKOFF_INITIAL
    for _ in range(9):
        ladder.append(backoff)
        backoff = svc.escalate_backoff(backoff)

    assert ladder == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0, 30.0]
    assert max(ladder) == svc.RECONNECT_BACKOFF_MAX


# ------------------------------------------------------------- loop behaviour
def test_loop_escalates_when_the_handshake_never_opens(
    svc: KrakenWebSocketService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact production bug: five failed handshakes must escalate, not repeat 1 s."""
    waits = _drive(svc, monkeypatch, [None, None, None, None, None])

    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0], waits
    assert len(set(waits)) == len(waits), "wait times must not be pinned to a constant"
    assert svc.reconnect_attempts == 5
    assert svc.last_session_seconds == 0.0
    assert svc.connected is False


def test_loop_reaches_the_cap_on_a_prolonged_outage(
    svc: KrakenWebSocketService, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits = _drive(svc, monkeypatch, [None] * 9)

    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0, 30.0], waits
    assert svc.reconnect_backoff_seconds == svc.RECONNECT_BACKOFF_MAX


def test_stable_session_resets_the_ladder(
    svc: KrakenWebSocketService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fail, fail, long stable session, fail -> the ladder restarts after stability."""
    stable = svc.STABLE_SESSION_SECONDS + 60.0
    waits = _drive(svc, monkeypatch, [None, None, stable, None, None])

    assert waits == [1.0, 2.0, svc.RECONNECT_BACKOFF_INITIAL, 2.0, 4.0], waits
    # the stable session is not counted as a failed reconnect
    assert svc.reconnect_attempts == 4
    assert svc.last_session_seconds == 0.0  # the final (failed) session


def test_loop_records_a_meaningful_error_when_the_socket_never_opened(
    svc: KrakenWebSocketService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero-Dummy: the offline reason is explicit, not an invented 'connected' state."""
    _drive(svc, monkeypatch, [None])

    assert svc.connected is False
    assert svc.last_error is not None
    assert "never opened" in svc.last_error or svc.last_error


def test_status_payload_exposes_the_real_reconnect_state(
    svc: KrakenWebSocketService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _drive(svc, monkeypatch, [None, None, None])

    status = svc.get_real_time_status()
    assert status["wsConnected"] is False
    assert status["reconnectAttempts"] == 3
    assert status["reconnectBackoffSeconds"] == 4.0
    assert status["lastSessionSeconds"] == 0.0
    assert status["cachedTickers"] == 0
    assert status["cachedBars"] == 0


def test_no_data_is_fabricated_while_the_feed_is_down(svc: KrakenWebSocketService) -> None:
    """An offline feed returns empty containers, never synthetic tickers/candles."""
    assert svc.get_tickers() == []
    assert svc.get_last_bars() == {}
    assert svc.get_candles("BTC/USD", 5) == []
    assert svc.connected is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
