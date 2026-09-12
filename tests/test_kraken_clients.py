"""
Conformance tests for the Kraken API signing schemes.

We cannot hit the exchange from CI, so we validate against the SPEC:
  Spot API-2 : base64( post_data + nonce + HMAC-SHA512(api_path + post_data, secret) )
  Futures v3 : HMAC-SHA256( timestamp + method + path_with_query + body, secret ).hexdigest()

The reference implementations below are written independently from the
production code and must produce identical signatures.
"""
import base64
import hashlib
import hmac

from app.config import Settings
from app.kraken.futures_client import KrakenFuturesClient
from app.kraken.spot_client import KrakenSpotClient


# ---------------------------------------------------------------- Spot API-2
def _reference_spot_sign(api_path: str, post_data: str, secret: str, nonce: str) -> str:
    sig = hmac.new(secret.encode(), (api_path + post_data).encode(), hashlib.sha512).digest()
    return base64.b64encode((post_data + nonce + sig.hex()).encode()).decode()


def test_spot_signature_matches_spec_reference():
    cases = [
        ("/0/private/Balance", "asset=XBT", "S3cr3tKey", "1726000000000"),
        ("/0/private/AddOrder", "pair=XBTUSD&type=buy&ordertype=limit&volume=0.1&price=65000&oflags=post", "x", "1"),
        ("/0/private/CancelAll", "", "k" * 64, "999"),
    ]
    for path, data, secret, nonce in cases:
        got = KrakenSpotClient.sign_request(path, data, secret, nonce)
        want = _reference_spot_sign(path, data, secret, nonce)
        assert got == want, (path, got, want)
        # structure: decodable base64, starts with post_data + nonce
        raw = base64.b64decode(got)
        assert raw.startswith((data + nonce).encode())
        assert len(raw) == len(data + nonce) + 128  # sha512 hex


def test_spot_pair_mapping():
    # Simplified Kraken names: required by WS v2, accepted by v0 public API
    assert KrakenSpotClient.pair_to_native("BTC/USD") == "XBTUSD"
    assert KrakenSpotClient.pair_to_native("ETH/USD") == "ETHUSD"
    assert KrakenSpotClient.pair_to_native("ETH/EUR") == "ETHZEUR"
    assert KrakenSpotClient.pair_to_native("DOGE/USD") == "XDGUSD"
    # Round-trips
    for symbol in ("BTC/USD", "ETH/USD", "ETH/EUR", "XRP/USD", "SOL/USD", "BTC/EUR"):
        assert KrakenSpotClient.native_to_pair(KrakenSpotClient.pair_to_native(symbol)) == symbol


# ---------------------------------------------------------------- Futures v3
def _reference_futures_sign(ts: str, method: str, path: str, body: str, secret: str) -> str:
    return hmac.new(secret.encode(), f"{ts}{method.upper()}{path}{body}".encode(), hashlib.sha256).hexdigest()


def test_futures_signature_matches_spec_reference():
    cases = [
        ("1726000000000", "GET", "/derivatives/api/v3/positions", "", "sec"),
        ("1726000000000", "POST", "/derivatives/api/v3/order", '{"contract":"XBTUSD-P","side":"buy","size":1}', "s" * 32),
        ("42", "GET", "/derivatives/api/v3/candles?contract=XBTUSD-P&max=300", "", "another-secret"),
    ]
    for ts, method, path, body, secret in cases:
        got = KrakenFuturesClient.sign_v3(ts, method, path, body, secret)
        want = _reference_futures_sign(ts, method, path, body, secret)
        assert got == want
        assert len(got) == 64


def test_futures_symbol_mapping():
    assert KrakenFuturesClient.symbol_to_contract("BTC/USD") == "XBTUSD-P"
    assert KrakenFuturesClient.symbol_to_contract("ETH/USD") == "ETHUSD-P"
    assert KrakenFuturesClient.symbol_to_contract("BTC/USD", perpetual=False) == "XBTUSD-M"


def test_client_requires_credentials_for_private():
    from app.kraken.spot_client import KrakenError

    settings = Settings()
    assert not settings.spot.configured
    client = KrakenSpotClient(settings)
    try:
        client.balance()
        raise AssertionError("expected KrakenError for missing credentials")
    except KrakenError as e:
        assert "not configured" in str(e)
