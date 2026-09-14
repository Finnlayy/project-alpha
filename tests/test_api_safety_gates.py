"""
INVARIANT 2.3 / MODULE F — fail-closed API safety gates.

End-to-end tests over the real FastAPI router. The app is assembled WITHOUT
``AppState.start_background()``, so no websocket thread, no network and no
background loop is started: these tests are hermetic and deterministic.

They lock down:

  * ``POST /api/kraken/toggle-mode`` validates its body strictly. A malformed
    request must be rejected with 422 *before* any mutation — it may never be
    answered with ``{"success": true}`` while silently forcing paper mode.
  * Going live requires a verified passkey session (401) and configured
    Kraken credentials (412).
  * Every mutative/order endpoint is session-gated (401).
  * Revoked and forged session tokens are rejected.
  * The credentials payload served over HTTP carries no fabricated key preview.
"""
from __future__ import annotations

import base64
from typing import Iterator, Tuple

import pytest
from fastapi.testclient import TestClient

from app.api.state import AppState
from app.main import app as real_app

CREDENTIAL_VARS = (
    "KRAKEN_SPOT_API_KEY",
    "KRAKEN_SPOT_PRIVATE_KEY",
    "KRAKEN_API_KEY",
    "KRAKEN_PRIVATE_KEY",
    "KRAKEN_FUTURES_API_KEY",
    "KRAKEN_FUTURES_PRIVATE_KEY",
    "KRAKEN_PRO_API_KEY",
    "KRAKEN_PRO_PRIVATE_KEY",
)

# A well-formed base64 secret (the published Kraken documentation fixture).
DOC_SECRET = (
    "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg=="
)


def _build_client(monkeypatch: pytest.MonkeyPatch, tmp_path, with_credentials: bool) -> Tuple[TestClient, AppState]:
    for var in CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    if with_credentials:
        monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "TestOperatorKey1234567890")
        monkeypatch.setenv("KRAKEN_SPOT_PRIVATE_KEY", DOC_SECRET)

    # isolate DuckDB + the HMAC session key inside tmp_path
    monkeypatch.setenv("ALPHA_DB_PATH", str(tmp_path / "lake.duckdb"))
    monkeypatch.setenv("ALPHA_DATA_DIR", str(tmp_path))
    import app.api.state as state_module

    monkeypatch.setattr(state_module, "get_session_secret", lambda settings: "test-session-secret-0123456789abcdef")

    # Use the REAL application object (so /api/health from main.py is covered)
    # but never enter the TestClient context manager: that would run the
    # lifespan and start the websocket/engine background threads.
    state = AppState()  # no start_background(): no WS thread, no engine loops
    state.settings.session_key_file = str(tmp_path / "session.key")
    real_app.state.alpha = state
    return TestClient(real_app), state


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[Tuple[TestClient, AppState]]:
    c, state = _build_client(monkeypatch, tmp_path, with_credentials=False)
    yield c, state
    state.lake.close()


@pytest.fixture
def client_with_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[Tuple[TestClient, AppState]]:
    c, state = _build_client(monkeypatch, tmp_path, with_credentials=True)
    yield c, state
    state.lake.close()


# ------------------------------------------------------- toggle-mode contract
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"live": True},
        {"paperTradng": False},          # typo must NOT silently mean "paper"
        {"paperTrading": "false"},       # string, not bool
        {"paperTrading": None},
        {"paperTrading": 0},
        {"paperTrading": 1},
        [1, 2, 3],
        "paperTrading=false",
    ],
)
def test_toggle_mode_rejects_malformed_body_fail_closed(client, body) -> None:
    c, state = client
    before = state.settings.execution_mode

    if isinstance(body, str):
        resp = c.post("/api/kraken/toggle-mode", content=body, headers={"Content-Type": "text/plain"})
    else:
        resp = c.post("/api/kraken/toggle-mode", json=body)

    assert resp.status_code == 422, f"expected fail-closed 422 for {body!r}, got {resp.status_code}: {resp.text}"
    assert "success" not in resp.json().get("detail", ""), resp.text
    assert state.settings.execution_mode == before, "mode must not change on a rejected request"


def test_toggle_mode_explicit_paper_is_allowed_without_session(client) -> None:
    """Downgrading to paper only ever reduces risk, so no passkey is needed."""
    c, state = client
    resp = c.post("/api/kraken/toggle-mode", json={"paperTrading": True})

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["success"] is True
    assert payload["paperTrading"] is True
    assert payload["mode"] == "paper"
    assert state.settings.execution_mode == "paper"


def test_toggle_mode_to_live_requires_passkey_session(client) -> None:
    c, state = client
    resp = c.post("/api/kraken/toggle-mode", json={"paperTrading": False})

    assert resp.status_code == 401, resp.text
    assert "passkey" in resp.json()["detail"].lower()
    assert state.settings.execution_mode == "paper", "must not go live without a session"


def test_toggle_mode_to_live_requires_credentials(client) -> None:
    """Session valid, but no Kraken keys -> 412, mode unchanged."""
    c, state = client
    token = state.sessions.mint("operator@alpha.internal")

    resp = c.post(
        "/api/kraken/toggle-mode",
        json={"paperTrading": False},
        headers={"X-Alpha-Session": token},
    )

    assert resp.status_code == 412, resp.text
    assert "credentials" in resp.json()["detail"].lower()
    assert state.settings.execution_mode == "paper"


def test_toggle_mode_to_live_succeeds_with_session_and_credentials(client_with_credentials) -> None:
    c, state = client_with_credentials
    assert state.settings.spot.configured is True
    token = state.sessions.mint("operator@alpha.internal")

    resp = c.post(
        "/api/kraken/toggle-mode",
        json={"paperTrading": False},
        headers={"X-Alpha-Session": token},
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["mode"] == "live"
    assert payload["paperTrading"] is False
    assert state.settings.execution_mode == "live"

    # and back down to paper again (no session needed)
    resp2 = c.post("/api/kraken/toggle-mode", json={"paperTrading": True})
    assert resp2.status_code == 200 and resp2.json()["mode"] == "paper"


def test_toggle_mode_rejects_revoked_and_forged_tokens(client_with_credentials) -> None:
    c, state = client_with_credentials
    token = state.sessions.mint("operator@alpha.internal")
    assert state.sessions.revoke(token) is True

    revoked = c.post("/api/kraken/toggle-mode", json={"paperTrading": False}, headers={"X-Alpha-Session": token})
    assert revoked.status_code == 401, revoked.text

    forged = c.post(
        "/api/kraken/toggle-mode",
        json={"paperTrading": False},
        headers={"X-Alpha-Session": "forged.token.value"},
    )
    assert forged.status_code == 401, forged.text
    assert state.settings.execution_mode == "paper"


# ---------------------------------------------------- mutative endpoint gates
@pytest.mark.parametrize(
    "path",
    [
        "/api/emergency/cancel-all",
        "/api/kraken/spot/orders",
        "/api/kraken/spot/orders/cancel-all",
        "/api/kraken/futures/orders",
        "/api/kraken/futures/orders/cancel-all",
        "/api/manifest/reset",
    ],
)
def test_mutative_endpoints_require_a_session(client, path) -> None:
    c, _state = client
    resp = c.post(path, json={})
    assert resp.status_code == 401, f"{path} must be passkey-gated, got {resp.status_code}: {resp.text}"


def test_session_accepted_via_query_param_too(client) -> None:
    c, state = client
    token = state.sessions.mint("operator@alpha.internal")
    # cancel-all with a valid session: allowed past the gate (no creds -> no live cancel)
    resp = c.post(f"/api/emergency/cancel-all?token={token}", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


# ------------------------------------------------------------- honest payload
def test_credentials_status_over_http_is_not_fabricated(client) -> None:
    c, _state = client
    resp = c.get("/api/kraken/credentials-status")
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["hasCredentials"] is False
    for venue in ("spot", "futures"):
        assert payload[venue]["configured"] is False
        assert payload[venue]["keyPreview"] == ""
        assert payload[venue]["source"] == "not_configured"


def test_health_reports_real_offline_state(client) -> None:
    """No WS connection and no instances -> say so, do not fake a green board."""
    c, _state = client
    payload = c.get("/api/health").json()
    assert payload["ws"] is False
    assert payload["instances"] == 0
    assert payload["mode"] == "paper"


def test_spot_balance_endpoint_reports_dependency_failure_not_fake_numbers(client) -> None:
    """Invariant 1.2: unavailable upstream -> explicit 4xx/5xx, never invented balances."""
    c, _state = client
    resp = c.get("/api/kraken/spot/trade-balance")
    assert resp.status_code in (412, 424, 503), f"expected an explicit degraded status, got {resp.status_code}: {resp.text}"
    text = resp.text.lower()
    assert "simulat" not in text and "mock" not in text, resp.text


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
