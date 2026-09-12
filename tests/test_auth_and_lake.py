"""
Verification for real WebAuthn (spec-compliant simulated browser round-trip),
session tokens, and the DuckDB data lake.

The 'browser' is simulated exactly as the WebAuthn API specifies:
  - clientDataJSON with type/challenge/origin/crossOrigin
  - attestationObject = CBOR {fmt, attStmt, authData}
  - assertion signature over SHA256(authData || SHA256(clientDataJSON))
"""
import base64
import hashlib
import json
import os
import tempfile
import time

import cbor2
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from app.auth.session import SessionService
from app.crypto.webauthn import WebAuthnEngine, WebAuthnError, b64_encode
from app.storage.lake import DataLake

ORIGIN = "http://localhost:3000"
RP_ID = "projekt-alpha.local"


# ---------------------------------------------------------------- WebAuthn
class FakeAuthenticator:
    """Speaks the browser WebAuthn API's wire format."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        pub = self.key.public_key().public_numbers()
        self.cred_id = os.urandom(32)
        self.sign_count = 0
        self.cose_key = {
            1: 2, 2: -7, -1: 1, -2: pub.x.to_bytes(32, "big"), -3: pub.y.to_bytes(32, "big")
        }

    def _client_data(self, chal_b64: str, wtype: str) -> bytes:
        return json.dumps({"type": wtype, "challenge": chal_b64, "origin": ORIGIN, "crossOrigin": False}).encode()

    def _auth_header(self, flags: int, with_credential: bool) -> bytes:
        header = hashlib.sha256(RP_ID.encode()).digest() + bytes([flags]) + self.sign_count.to_bytes(4, "big")
        if with_credential:
            header += b"\x00" * 16 + len(self.cred_id).to_bytes(2, "big") + self.cred_id + cbor2.dumps(self.cose_key)
        return header

    def create(self, chal_b64: str) -> dict:
        header = self._auth_header(0x41, with_credential=True)
        self.sign_count = 0
        att_obj = cbor2.dumps({"fmt": "none", "attStmt": cbor2.CBORTag(0, {}) if False else {}, "authData": header})
        return {
            "id": b64_encode(self.cred_id),
            "rawId": b64_encode(self.cred_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64_encode(self._client_data(chal_b64, "webauthn.create")),
                "attestationObject": b64_encode(bytes(att_obj)),
            },
        }

    def get(self, chal_b64: str) -> dict:
        self.sign_count += 1
        header = self._auth_header(0x01, with_credential=False)
        message = header + hashlib.sha256(self._client_data(chal_b64, "webauthn.get")).digest()
        from cryptography.hazmat.primitives import hashes as _h

        der = self.key.sign(message, ec.ECDSA(_h.SHA256()))
        r, s = decode_dss_signature(der)
        sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")  # FIDO2: raw r||s, 64 bytes
        auth_data = header + sig
        return {
            "id": b64_encode(self.cred_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64_encode(self._client_data(chal_b64, "webauthn.get")),
                "authenticatorData": b64_encode(auth_data),
            },
        }


def make_engine() -> WebAuthnEngine:
    return WebAuthnEngine(RP_ID, "Projekt:Alpha", allowed_origins=[ORIGIN])


def test_webauthn_full_roundtrip():
    engine = make_engine()
    auth = FakeAuthenticator()

    reg_opts = engine.generate_registration_options("user1", "user1@alpha.local", "Quant Operator")
    chal = reg_opts["publicKey"]["challenge"]
    resp = auth.create(chal)
    cred = engine.verify_registration("user1", "user1@alpha.local", resp)
    assert cred.credential_id_b64 == resp["id"]
    assert "user1" in engine.user_credentials

    auth_opts = engine.generate_authentication_options("user1")
    chal2 = auth_opts["publicKey"]["challenge"]
    resp2 = auth.get(chal2)
    cred2 = engine.verify_authentication("user1", resp2["id"], resp2["response"])
    assert cred2.sign_count == 1
    assert cred2.last_used is not None


def test_webauthn_replayed_challenge_rejected():
    engine = make_engine()
    auth = FakeAuthenticator()
    chal = engine.generate_registration_options("u", "u", "u")["publicKey"]["challenge"]
    engine.verify_registration("u", "u", auth.create(chal))
    # replaying the registration challenge must fail
    with pytest.raises(WebAuthnError):
        engine.verify_registration("u", "u", auth.create(chal))


def test_webauthn_wrong_origin_rejected():
    engine = make_engine()
    auth = FakeAuthenticator()

    class EvilAuth(FakeAuthenticator):
        def _client_data(self, chal_b64, wtype):
            return json.dumps({"type": wtype, "challenge": chal_b64, "origin": "https://evil.example", "crossOrigin": False}).encode()

    evil = EvilAuth()
    chal = engine.generate_registration_options("u", "u", "u")["publicKey"]["challenge"]
    with pytest.raises(WebAuthnError, match="origin"):
        engine.verify_registration("u", "u", evil.create(chal))


def test_webauthn_tampered_signature_rejected():
    engine = make_engine()
    auth = FakeAuthenticator()
    chal = engine.generate_registration_options("u", "u", "u")["publicKey"]["challenge"]
    engine.verify_registration("u", "u", auth.create(chal))

    resp = auth.get(engine.generate_authentication_options("u")["publicKey"]["challenge"])
    data = bytearray(b64_decode_sig(resp["response"]["authenticatorData"]))
    data[-1] ^= 0xFF  # corrupt the signature
    resp["response"]["authenticatorData"] = b64_encode(bytes(data))
    with pytest.raises(WebAuthnError):
        engine.verify_authentication("u", resp["id"], resp["response"])


def test_webauthn_unknown_user_credential_rejected():
    engine = make_engine()
    auth = FakeAuthenticator()
    chal = engine.generate_registration_options("alice", "a", "a")["publicKey"]["challenge"]
    engine.verify_registration("alice", "a", auth.create(chal))
    chal2 = engine.generate_authentication_options("alice")["publicKey"]["challenge"]
    resp = auth.get(chal2)
    with pytest.raises(WebAuthnError):
        engine.verify_authentication("bob", resp["id"], resp["response"])


def b64_decode_sig(s: str) -> bytes:
    pad = (-len(s)) % 4
    return base64.b64decode(s + "=" * pad)


# ---------------------------------------------------------------- sessions
def test_session_token_roundtrip_and_expiry():
    svc = SessionService(b"secret" * 8, ttl_seconds=60)
    tok = svc.mint("alice", roles=["OPERATOR", "M8_GATE_CONTROLLER"])
    payload = svc.verify(tok)
    assert payload["sub"] == "alice"
    assert "OPERATOR" in payload["roles"]

    # expired
    short = SessionService(b"secret" * 8, ttl_seconds=-1)
    assert short.verify(short.mint("alice")) is None

    # tampered
    tampered = tok[:-2] + ("aa" if not tok.endswith("aa") else "bb")
    assert svc.verify(tampered) is None

    # revoked
    svc.revoke(tok)
    assert svc.verify(tok) is None


def test_session_wrong_secret_rejected():
    a = SessionService(b"secret-a" * 8)
    b = SessionService(b"secret-b" * 8)
    assert b.verify(a.mint("x")) is None


# --------------------------------------------------------------------- lake
@pytest.fixture
def lake():
    with tempfile.TemporaryDirectory() as tmp:
        d = DataLake(os.path.join(tmp, "lake.duckdb"))
        yield d
        d.close()


def test_lake_candle_roundtrip(lake):
    rows = [
        {"time": 1000 + i * 900, "open": 1.0 + i * 0.01, "high": 1.05 + i * 0.01, "low": 0.95 + i * 0.01, "close": 1.02 + i * 0.01, "volume": 10.0}
        for i in range(50)
    ]
    assert lake.upsert_candles("BTC/USD", 15, rows) == 50
    fetched = lake.fetch_candles("BTC/USD", 15, limit=1000)
    assert len(fetched) == 50
    assert fetched[0]["time"] == 1000
    assert fetched[-1]["close"] == rows[-1]["close"]
    # upsert idempotent
    lake.upsert_candles("BTC/USD", 15, rows[:5])
    assert len(lake.fetch_candles("BTC/USD", 15)) == 50
    # limit respected
    assert len(lake.fetch_candles("BTC/USD", 15, limit=7)) == 7


def test_lake_instances_and_trades(lake):
    lake.upsert_instance({
        "id": "inst-1", "strategy_type": "EMA_TREND_RSI", "name": "t", "symbol": "BTC/USD",
        "interval_min": 15, "mode": "paper", "status": "active", "params": {"a": 1}, "initial_balance": 100.0,
    })
    inst = lake.get_instance("inst-1")
    assert inst["params"] == {"a": 1}
    lake.set_instance_status("inst-1", "stopped", "TEST")
    assert lake.get_instance("inst-1")["status"] == "stopped"
    assert lake.get_instance("inst-1")["stop_reason"] == "TEST"

    lake.add_trade({
        "id": "tr-1", "instance_id": "inst-1", "strategy_id": "EMA_TREND_RSI", "mode": "paper", "pair": "BTC/USD",
        "side": "long", "entry_time": "e", "exit_time": "x", "ts_open": 100, "ts_close": 200,
        "entry_price": 100.0, "exit_price": 105.0, "amount": 1.0, "notional_usd": 100.0,
        "fee_usd": 0.05, "funding_usd": 0.0, "gross_pnl": 5.0, "net_pnl": 4.95,
        "mfe_pct": 6.0, "mae_pct": -1.0, "exit_reason": "TAKE_PROFIT", "r_multiple": 2.0, "zone": "GOOD",
    })
    trades = lake.trades_for(mode="paper")
    assert len(trades) == 1
    assert trades[0]["zone"] == "GOOD"


def test_lake_vault_and_state(lake):
    lake.sweep_vault("v-1", "inst-1", 12.5, 62.5)
    lake.sweep_vault("v-2", "inst-1", 3.5, 58.5, vtype="PROFIT_SWEEP")
    assert abs(lake.vault_total() - 16.0) < 1e-9

    lake.upsert_state("inst-1", "THROTTLED", 50.0, 25.0, 3, 0.5)
    st = lake.fetch_state("inst-1")
    assert st["status"] == "THROTTLED"
    assert st["budget_multiplier"] == 0.5


def test_lake_events_ordered(lake):
    for i in range(5):
        lake.log_event("info", "TEST", f"event {i}")
    ev = lake.recent_events(limit=10)
    assert len(ev) == 5
    assert ev[-1]["message"] == "event 4"
    assert ev[0]["message"] == "event 0"


def test_lake_parquet_roundtrip(lake):
    rows = [{"time": 1000 + i * 900, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 5.0} for i in range(10)]
    lake.upsert_candles("ETH/USD", 15, rows)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "eth_15.parquet")
        assert lake.export_candles_parquet("ETH/USD", 15, out) == 10
        assert os.path.exists(out)
        assert not os.path.exists(out + ".tmp")
        with tempfile.TemporaryDirectory() as tmp2:
            lake2 = DataLake(os.path.join(tmp2, "lake2.duckdb"))
            assert lake2.import_candles_parquet("ETH/USD", 15, out) == 10
            assert len(lake2.fetch_candles("ETH/USD", 15)) == 10
            lake2.close()


def test_lake_summary(lake):
    lake.upsert_candles("BTC/USD", 15, [{"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    s = lake.summary()
    assert s["totalCandles"] == 1
    assert s["status"] == "healthy"
    assert s["symbols"][0]["symbol"] == "BTC/USD"
