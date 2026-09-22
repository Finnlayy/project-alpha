"""
Conformance tests for the Kraken API signing schemes.

We cannot hit the exchange from CI, so we validate against the SPEC:
  Spot API-2 : api_sign = base64( HMAC-SHA512( base64decode(secret),
                                             api_path + SHA256(nonce + post_data) ) )
               https://docs.kraken.com/api/docs/guides/spot-rest-auth/
  Futures    : authent = base64( HMAC-SHA512( base64decode(secret),
                                             SHA256(post_data + nonce + endpoint_path) ) )
               https://docs.futures.kraken.com/#http-api-http-api-introduction-authentication

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
def _reference_spot_sign(api_path: str, post_data: str, secret_b64: str, nonce: str) -> str:
    sha256 = hashlib.sha256((nonce + post_data).encode("utf-8")).digest()
    mac = hmac.new(base64.b64decode(secret_b64), api_path.encode("utf-8") + sha256, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode("utf-8")


def test_spot_signature_matches_official_documented_vector():
    # Golden vector straight from the Kraken docs (AddOrder example).
    secret = "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg=="
    post_data = "nonce=1616492376594&ordertype=limit&pair=XBTUSD&price=37500&type=buy&volume=1.25"
    got = KrakenSpotClient.sign_request("/0/private/AddOrder", post_data, secret, "1616492376594")
    assert got == "4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8MPtnRfp32bAb0nmbRn6H8ndwLUQ=="


def test_spot_signature_matches_spec_reference():
    cases = [
        ("/0/private/Balance", "nonce=1726000000000&asset=XBT",
         base64.b64encode(b"S3cr3tKey-32-bytes-pad-to-64!!").decode(), "1726000000000"),
        ("/0/private/AddOrder", "nonce=1&pair=XBTUSD&type=buy&ordertype=limit&volume=0.1&price=65000&oflags=post",
         base64.b64encode(b"x" * 32).decode(), "1"),
        ("/0/private/CancelAll", "nonce=999", base64.b64encode(b"k" * 64).decode(), "999"),
    ]
    for path, data, secret, nonce in cases:
        got = KrakenSpotClient.sign_request(path, data, secret, nonce)
        want = _reference_spot_sign(path, data, secret, nonce)
        assert got == want, (path, got, want)
        # structure: 64-byte HMAC-SHA512 digest, base64-encoded
        raw = base64.b64decode(got)
        assert len(raw) == 64


def test_spot_pair_mapping():
    # Simplified Kraken names: required by WS v2, accepted by v0 public API
    assert KrakenSpotClient.pair_to_native("BTC/USD") == "XBTUSD"
    assert KrakenSpotClient.pair_to_native("ETH/USD") == "ETHUSD"
    assert KrakenSpotClient.pair_to_native("ETH/EUR") == "ETHZEUR"
    assert KrakenSpotClient.pair_to_native("DOGE/USD") == "XDGUSD"
    # Round-trips
    for symbol in ("BTC/USD", "ETH/USD", "ETH/EUR", "XRP/USD", "SOL/USD", "BTC/EUR"):
        assert KrakenSpotClient.native_to_pair(KrakenSpotClient.pair_to_native(symbol)) == symbol


# ---------------------------------------------------------------- Futures
def _reference_futures_sign(post_data: str, nonce: str, endpoint_path: str, secret_b64: str) -> str:
    sha256 = hashlib.sha256(f"{post_data}{nonce}{endpoint_path}".encode("utf-8")).digest()
    mac = hmac.new(base64.b64decode(secret_b64), sha256, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode("utf-8")


def _b64_secret(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


def test_futures_signature_matches_spec_reference():
    cases = [
        ("contract=PF_XBTUSD", "1726000000000", "/api/v3/positions", _b64_secret(b"sec")),
        ("orderType=mkt&symbol=PF_XBTUSD&side=buy&size=1", "1726000000001",
         "/api/v3/sendorder", _b64_secret(b"s" * 32)),
        ("", "42", "/api/v3/tickers", _b64_secret(b"another-secret")),
    ]
    for post_data, nonce, path, secret in cases:
        got = KrakenFuturesClient.sign_v3(post_data, nonce, path, secret)
        want = _reference_futures_sign(post_data, nonce, path, secret)
        assert got == want
        assert len(got) == 88  # base64 of a 64-byte HMAC-SHA512 digest


def test_futures_sign_path_excludes_derivatives_prefix():
    # The on-the-wire path carries /derivatives, the signature must not.
    assert KrakenFuturesClient.API_PATH == "/derivatives/api/v3"
    assert KrakenFuturesClient.SIGN_PREFIX == "/api/v3"


def test_futures_symbol_mapping():
    assert KrakenFuturesClient.symbol_to_contract("BTC/USD") == "PF_XBTUSD"
    assert KrakenFuturesClient.symbol_to_contract("ETH/USD") == "PF_ETHUSD"
    assert KrakenFuturesClient.symbol_to_contract("DOGE/USD") == "PF_XDGUSD"
    # round-trips
    for symbol in ("BTC/USD", "ETH/USD", "DOGE/USD", "SOL/USD"):
        assert KrakenFuturesClient.contract_to_symbol(
            KrakenFuturesClient.symbol_to_contract(symbol)) == symbol


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
