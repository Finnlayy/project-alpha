"""
Conformance tests for the Kraken API signing schemes.

Kraken is not reachable from CI/sandbox egress, so instead of hitting the
exchange we validate against the PUBLISHED OFFICIAL SPEC plus the official
worked example ("test vector") that Kraken ships in its own documentation:

  Spot REST — API-Sign
      https://docs.kraken.com/exchange/guides/rest/authentication
      api_sign = base64( HMAC-SHA512( key = base64_decode(api_secret),
                                      msg = uri_path + SHA256(nonce + post_data) ) )

  Futures / Derivatives REST v3 — Authent  (auth flow updated 2024-02-20)
      https://docs.kraken.com/api/docs/guides/futures-rest/
      1. msg     = postData + nonce + endpointPath
                   (endpointPath EXCLUDES the '/derivatives' prefix, e.g. '/api/v3/sendorder')
      2. digest  = SHA256(msg)
      3. key     = base64_decode(api_secret)
      4. mac     = HMAC-SHA512(key, digest)
      5. Authent = base64_encode(mac)

The reference implementations below are written independently of the
production code, directly from the documented steps, and must agree bit for
bit with ``KrakenSpotClient.sign_request`` / ``KrakenFuturesClient.sign_v3``.

--------------------------------------------------------------------------
SUPERSEDED (WRONG) VECTORS — kept documented so they are never reintroduced
--------------------------------------------------------------------------
An earlier revision of this file asserted:

  * Spot    : base64( post_data + nonce + HMAC-SHA512(path + post_data,
                       secret.encode()).hexdigest() )
  * Futures : HMAC-SHA256( timestamp + method + path + body,
                           secret.encode() ).hexdigest()   (64 hex chars)
  * Futures : symbol_to_contract("BTC/USD") == "XBTUSD-P"

None of those is a Kraken scheme. The Spot construction was never published
by Kraken (and signs with the raw secret string instead of the base64-decoded
key, so the digest is wrong twice over); the Futures construction is the
pre-2024-02-20 Crypto Facilities legacy flow, which the production API no
longer accepts; and ``XBTUSD-P`` is not a Kraken contract symbol (linear
perpetuals are ``PF_XBTUSD``). Signing with any of them yields
``EAPI:Invalid key`` / ``authenticationError`` against the real exchange, so
the vectors asserted here are the official ones.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac

import pytest

from app.config import Settings
from app.kraken.futures_client import KrakenFuturesClient
from app.kraken.spot_client import KrakenError, KrakenSpotClient

# The private key from Kraken's own documentation example. It is a published
# doc fixture, not a live credential.
DOC_SECRET = (
    "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg=="
)


# ---------------------------------------------------------------- Spot API-2
def _reference_spot_sign(api_path: str, post_data: str, secret_b64: str, nonce: str) -> str:
    """Independent transcription of the documented Spot signing rule."""
    encoded = (nonce + post_data).encode("utf-8")
    message = api_path.encode("utf-8") + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret_b64), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode("utf-8")


def test_spot_signature_matches_official_documented_vector() -> None:
    """Bit-exact match against the worked example published by Kraken.

    Kraken states that if your code produces a different API-Sign for this
    input, your application of the methodology is wrong — so this is a hard
    gate, not a self-consistency check.
    """
    api_path = "/0/private/AddOrder"
    post_data = "nonce=1616492376594&ordertype=limit&pair=XBTUSD&price=37500&type=buy&volume=1.25"
    nonce = "1616492376594"
    expected = (
        "4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8MPtnRfp32bAb0nmbRn6H8ndwLUQ=="
    )

    got = KrakenSpotClient.sign_request(api_path, post_data, DOC_SECRET, nonce)

    assert got == expected, f"Spot API-Sign deviates from the official vector: {got}"


def test_spot_signature_matches_spec_reference() -> None:
    """Production signer == independent reference across varied inputs."""
    cases = [
        ("/0/private/Balance", "nonce=1726000000000", "1726000000000"),
        (
            "/0/private/AddOrder",
            "nonce=1&pair=XBTUSD&type=buy&ordertype=limit&volume=0.1&price=65000&oflags=post",
            "1",
        ),
        ("/0/private/CancelAll", "nonce=999", "999"),
        ("/0/private/TradeBalance", "nonce=1540973848000&asset=xbt", "1540973848000"),
        # query strings belong to the signed URI path verbatim
        ("/0/private/GetCustodyTask?id=TGWOJ4JQPOTZT2", "nonce=1616492376594", "1616492376594"),
    ]
    for api_path, post_data, nonce in cases:
        got = KrakenSpotClient.sign_request(api_path, post_data, DOC_SECRET, nonce)
        want = _reference_spot_sign(api_path, post_data, DOC_SECRET, nonce)
        assert got == want, (api_path, got, want)
        # SHA-512 digest -> 64 raw bytes -> 88 base64 chars
        assert len(got) == 88, (api_path, len(got))
        assert len(base64.b64decode(got)) == 64, api_path


def test_spot_signature_is_sensitive_to_every_signed_input() -> None:
    """No input may be ignored: path, payload, nonce and secret all matter."""
    path = "/0/private/AddOrder"
    data = "nonce=1616492376594&pair=XBTUSD&type=buy"
    nonce = "1616492376594"
    base = KrakenSpotClient.sign_request(path, data, DOC_SECRET, nonce)

    assert base != KrakenSpotClient.sign_request("/0/private/Balance", data, DOC_SECRET, nonce)
    assert base != KrakenSpotClient.sign_request(path, data + "&volume=1", DOC_SECRET, nonce)
    assert base != KrakenSpotClient.sign_request(path, data, DOC_SECRET, "1616492376595")

    other_secret = base64.b64encode(b"another-32-byte-secret-key!!!!!").decode()
    assert base != KrakenSpotClient.sign_request(path, data, other_secret, nonce)


def test_spot_rejects_non_base64_secret_fail_closed() -> None:
    """Invariant 1/2: a malformed secret must raise, never silently sign."""
    for bad_secret in ("S3cr3tKey", "not base64!!", "", "   ", "\n"):
        with pytest.raises(KrakenError):
            KrakenSpotClient.sign_request("/0/private/Balance", "nonce=1", bad_secret, "1")


def test_spot_nonce_is_monotonically_increasing() -> None:
    """Kraken bans reused/decreasing nonces (EAPI:Invalid nonce)."""
    nonces = [int(KrakenSpotClient._next_nonce()) for _ in range(500)]
    assert nonces == sorted(set(nonces)), "nonce sequence must be strictly increasing"


def test_spot_pair_mapping() -> None:
    # Simplified Kraken names: required by WS v2, accepted by v0 public API
    assert KrakenSpotClient.pair_to_native("BTC/USD") == "XBTUSD"
    assert KrakenSpotClient.pair_to_native("ETH/USD") == "ETHUSD"
    assert KrakenSpotClient.pair_to_native("ETH/EUR") == "ETHZEUR"
    assert KrakenSpotClient.pair_to_native("DOGE/USD") == "XDGUSD"
    # Round-trips
    for symbol in ("BTC/USD", "ETH/USD", "ETH/EUR", "XRP/USD", "SOL/USD", "BTC/EUR"):
        assert KrakenSpotClient.native_to_pair(KrakenSpotClient.pair_to_native(symbol)) == symbol


# ---------------------------------------------------------------- Futures v3
def _reference_futures_sign(post_data: str, nonce: str, endpoint_path: str, secret_b64: str) -> str:
    """Independent transcription of the 5 documented Futures Authent steps."""
    message = post_data + nonce + endpoint_path                      # step 1
    digest = hashlib.sha256(message.encode("utf-8")).digest()        # step 2
    key = base64.b64decode(secret_b64)                               # step 3
    mac = hmac.new(key, digest, hashlib.sha512)                      # step 4
    return base64.b64encode(mac.digest()).decode("utf-8")            # step 5


def test_futures_signature_matches_spec_reference() -> None:
    cases = [
        ("", "1726000000000", "/api/v3/openPositions"),
        ("", "1726000000000", "/api/v3/accounts"),
        (
            "orderType=mkt&side=buy&size=1&symbol=PF_XBTUSD",
            "1726000000001",
            "/api/v3/sendorder",
        ),
        ("max=300&symbol=PF_XBTUSD", "42", "/api/v3/candles"),
        ("symbol=PF_XBTUSD", "1726000000002", "/api/v3/tickers"),
    ]
    for post_data, nonce, endpoint_path in cases:
        got = KrakenFuturesClient.sign_v3(post_data, nonce, endpoint_path, DOC_SECRET)
        want = _reference_futures_sign(post_data, nonce, endpoint_path, DOC_SECRET)
        assert got == want, (endpoint_path, got, want)


def test_futures_authent_is_base64_sha512_not_legacy_hex() -> None:
    """Guards against regressing to the pre-2024 HMAC-SHA256 hexdigest flow.

    The legacy scheme produced 64 lowercase hex characters; the current scheme
    produces an 88-character base64 string decoding to a 64-byte SHA-512 MAC.
    """
    authent = KrakenFuturesClient.sign_v3("", "1726000000000", "/api/v3/openPositions", DOC_SECRET)

    assert len(authent) == 88, len(authent)
    raw = base64.b64decode(authent, validate=True)
    assert len(raw) == 64
    with pytest.raises(binascii.Error):
        base64.b64decode(authent + "!", validate=True)
    # a hex digest would round-trip through int(..., 16); base64 SHA-512 does not
    assert not (len(authent) == 64 and all(c in "0123456789abcdef" for c in authent))


def test_futures_signature_excludes_derivatives_prefix() -> None:
    """The signed endpointPath must NOT contain '/derivatives'.

    On the wire the URL is /derivatives/api/v3/... but only /api/v3/... is
    signed. Signing the wrong path yields authenticationError.
    """
    assert KrakenFuturesClient.API_PATH == "/derivatives/api/v3"
    assert KrakenFuturesClient.SIGN_PREFIX == "/api/v3"
    assert not KrakenFuturesClient.SIGN_PREFIX.startswith("/derivatives")
    assert KrakenFuturesClient.API_PATH.endswith(KrakenFuturesClient.SIGN_PREFIX)

    signed = KrakenFuturesClient.sign_v3("", "1", "/api/v3/openPositions", DOC_SECRET)
    wrong = KrakenFuturesClient.sign_v3("", "1", "/derivatives/api/v3/openPositions", DOC_SECRET)
    assert signed != wrong


def test_futures_rejects_non_base64_secret_fail_closed() -> None:
    for bad_secret in ("sec", "not base64!!", "", "   ", "\n"):
        with pytest.raises(KrakenError):
            KrakenFuturesClient.sign_v3("", "1", "/api/v3/accounts", bad_secret)


def test_futures_nonce_is_monotonically_increasing() -> None:
    nonces = [int(KrakenFuturesClient._next_nonce()) for _ in range(500)]
    assert nonces == sorted(set(nonces)), "nonce sequence must be strictly increasing"


def test_futures_symbol_mapping() -> None:
    """Real Kraken Futures contract symbols (linear perpetuals are PF_*)."""
    assert KrakenFuturesClient.symbol_to_contract("BTC/USD") == "PF_XBTUSD"
    assert KrakenFuturesClient.symbol_to_contract("ETH/USD") == "PF_ETHUSD"
    assert KrakenFuturesClient.symbol_to_contract("SOL/USD") == "PF_SOLUSD"
    # case-insensitive on the way in, canonical uppercase on the way out
    assert KrakenFuturesClient.symbol_to_contract("btc/usd") == "PF_XBTUSD"


def test_futures_contract_to_symbol_round_trip() -> None:
    for contract in ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PI_XBTUSD", "FF_XBTUSD"):
        symbol = KrakenFuturesClient.contract_to_symbol(contract)
        assert "/" in symbol, contract
        assert KrakenFuturesClient.symbol_to_contract(symbol) == "PF_" + contract[3:]

    assert KrakenFuturesClient.contract_to_symbol("PF_XBTUSD") == "BTC/USD"
    # dated futures carry a YYMMDD suffix that must be stripped
    assert KrakenFuturesClient.contract_to_symbol("FI_XBTUSD_260327") == "BTC/USD"


# ------------------------------------------------------- credential gating
def test_client_requires_credentials_for_private() -> None:
    settings = Settings()
    assert not settings.spot.configured
    client = KrakenSpotClient(settings)
    with pytest.raises(KrakenError) as excinfo:
        client.balance()
    assert "not configured" in str(excinfo.value)


def test_futures_client_requires_credentials_for_private() -> None:
    settings = Settings()
    assert not settings.futures.configured
    client = KrakenFuturesClient(settings)
    with pytest.raises(KrakenError) as excinfo:
        client.open_positions()
    assert "not configured" in str(excinfo.value)


def test_public_endpoints_do_not_require_credentials() -> None:
    """Public calls must be attempted (and fail with a network error offline),
    never rejected as 'not configured' — otherwise the UI could not show real
    market data without API keys."""
    settings = Settings()
    spot, fut = KrakenSpotClient(settings), KrakenFuturesClient(settings)
    for call in (spot.server_time, fut.tickers):
        try:
            call()
        except KrakenError as exc:  # offline sandbox: transport failure
            assert "not configured" not in str(exc).lower(), str(exc)
