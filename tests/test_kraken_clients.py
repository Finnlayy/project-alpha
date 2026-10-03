# Trace cros-ltcusd-955960103 (paper CROSS_BOOK): these tests check that
# pair_to_native and symbol_to_contract bind LTC/USD only from an injected
# catalog or from the live public books. Zero hits and more than one exact
# hit raise PairUnbound without a live network. XLTUSD, PF_XLTUSD, and
# PI_LTCUSD are not selected. Tests do not place orders or init or reset paper state.
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
from app.kraken.spot_client import KrakenSpotClient, PairUnbound


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
    assert "LTC" not in KrakenSpotClient._BASE
    assert "XLT" not in KrakenSpotClient._BASE.values()
    # Round-trips. LTC/USD is covered with an injected catalog so this test
    # does not call the live AssetPairs book.
    for symbol in ("BTC/USD", "ETH/USD", "ETH/EUR", "XRP/USD", "SOL/USD", "BTC/EUR"):
        assert KrakenSpotClient.native_to_pair(KrakenSpotClient.pair_to_native(symbol)) == symbol


def _confirmed_ltc_spot_row():
    return dict(KrakenSpotClient._LTC_SPOT_ROW)


def _expect_unbound(fn):
    try:
        fn()
    except PairUnbound:
        return
    raise AssertionError("expected PairUnbound")


def test_ltc_usd_spot_binds_only_exact_xltczusd():
    row = _confirmed_ltc_spot_row()
    original = KrakenSpotClient._fetch_ltc_spot_rows

    def _no_live_fetch():
        raise AssertionError("pair_to_native fetched the live book while a catalog was injected")

    KrakenSpotClient._fetch_ltc_spot_rows = staticmethod(_no_live_fetch)
    try:
        assert KrakenSpotClient.pair_to_native("LTC/USD", rows=[row]) == "XLTCZUSD"
        assert KrakenSpotClient.pair_to_native("LTCUSD", rows=[row]) == "XLTCZUSD"
        assert KrakenSpotClient.pair_to_native("XLTCZUSD", rows=[row]) == "XLTCZUSD"
        assert KrakenSpotClient.native_to_pair(KrakenSpotClient.pair_to_native("LTC/USD", rows=[row])) == "LTC/USD"
        # A rejected XLTUSD key next to the one exact row is not a second hit.
        assert KrakenSpotClient.pair_to_native("LTC/USD", rows=[row, {"key": "XLTUSD"}]) == "XLTCZUSD"
    finally:
        KrakenSpotClient._fetch_ltc_spot_rows = original


def test_ltc_usd_spot_unbound_when_not_unique():
    row = _confirmed_ltc_spot_row()
    cases = (
        [],
        [row, dict(row)],
        [{"key": "XLTUSD"}],
        [dict(row, status="")],
    )
    original = KrakenSpotClient._fetch_ltc_spot_rows

    def _no_live_fetch():
        raise AssertionError("pair_to_native fetched the live book while a catalog was injected")

    KrakenSpotClient._fetch_ltc_spot_rows = staticmethod(_no_live_fetch)
    try:
        for rows in cases:
            _expect_unbound(lambda rows=rows: KrakenSpotClient.pair_to_native("LTC/USD", rows=rows))
        for symbol in ("XLTUSD", "XLT/USD", "LTC/EUR"):
            _expect_unbound(lambda symbol=symbol: KrakenSpotClient.pair_to_native(symbol))
    finally:
        KrakenSpotClient._fetch_ltc_spot_rows = original


def test_pair_to_native_reads_live_asset_pairs_when_no_catalog():
    seen = {}
    original = KrakenSpotClient._get_public_json

    def fake(url, params=None):
        seen["url"] = url
        seen["params"] = params
        return {"error": [], "result": {}}

    KrakenSpotClient._get_public_json = staticmethod(fake)
    try:
        _expect_unbound(lambda: KrakenSpotClient.pair_to_native("LTC/USD"))
    finally:
        KrakenSpotClient._get_public_json = original
    assert seen["url"] == "https://api.kraken.com/0/public/AssetPairs"
    assert seen["params"] == {"pair": "LTCUSD"}


def test_pair_to_native_live_payload_zero_and_many_hits_do_not_bind():
    row = _confirmed_ltc_spot_row()
    original = KrakenSpotClient._fetch_ltc_spot_rows
    try:
        KrakenSpotClient._fetch_ltc_spot_rows = staticmethod(lambda: [])
        _expect_unbound(lambda: KrakenSpotClient.pair_to_native("LTC/USD"))
        KrakenSpotClient._fetch_ltc_spot_rows = staticmethod(lambda: [row, dict(row)])
        _expect_unbound(lambda: KrakenSpotClient.pair_to_native("LTC/USD"))
        KrakenSpotClient._fetch_ltc_spot_rows = staticmethod(lambda: [row])
        assert KrakenSpotClient.pair_to_native("LTC/USD") == "XLTCZUSD"
    finally:
        KrakenSpotClient._fetch_ltc_spot_rows = original


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
    # round-trips. LTC/USD uses an injected catalog so this test does not
    # call the live instruments book.
    for symbol in ("BTC/USD", "ETH/USD", "DOGE/USD", "SOL/USD"):
        assert KrakenFuturesClient.contract_to_symbol(
            KrakenFuturesClient.symbol_to_contract(symbol)) == symbol
    assert KrakenFuturesClient.contract_to_symbol(
        KrakenFuturesClient.symbol_to_contract("LTC/USD", instruments=["PF_LTCUSD"])
    ) == "LTC/USD"


def test_ltc_usd_futures_binds_only_exact_pf_ltcusd():
    one = ["PF_LTCUSD"]
    fuzzy = ["PI_LTCUSD", "PF_XLTUSD", "PF_LTCUSD"]
    original = KrakenFuturesClient._fetch_ltc_futures_symbols

    def _no_live_fetch():
        raise AssertionError("symbol_to_contract fetched the live book while a catalog was injected")

    KrakenFuturesClient._fetch_ltc_futures_symbols = staticmethod(_no_live_fetch)
    try:
        assert KrakenFuturesClient.symbol_to_contract("LTC/USD", instruments=one) == "PF_LTCUSD"
        assert KrakenFuturesClient.symbol_to_contract("LTCUSD", instruments=one) == "PF_LTCUSD"
        assert KrakenFuturesClient.symbol_to_contract("PF_LTCUSD", instruments=one) == "PF_LTCUSD"
        # Fuzzy LTC results include PI_LTCUSD. Only the exact PF_ symbol counts.
        assert KrakenFuturesClient.symbol_to_contract("LTC/USD", instruments=fuzzy) == "PF_LTCUSD"
    finally:
        KrakenFuturesClient._fetch_ltc_futures_symbols = original


def test_ltc_usd_futures_unbound_when_not_unique():
    cases = (
        [],
        ["PI_LTCUSD"],
        ["PF_XLTUSD"],
        ["PI_LTCUSD", "PF_XLTUSD"],
        ["PF_LTCUSD", "PF_LTCUSD"],
    )
    original = KrakenFuturesClient._fetch_ltc_futures_symbols

    def _no_live_fetch():
        raise AssertionError("symbol_to_contract fetched the live book while a catalog was injected")

    KrakenFuturesClient._fetch_ltc_futures_symbols = staticmethod(_no_live_fetch)
    try:
        for instruments in cases:
            _expect_unbound(
                lambda instruments=instruments: KrakenFuturesClient.symbol_to_contract(
                    "LTC/USD", instruments=instruments
                )
            )
        for symbol in ("PF_XLTUSD", "PI_LTCUSD", "XLT/USD", "LTC/EUR"):
            _expect_unbound(lambda symbol=symbol: KrakenFuturesClient.symbol_to_contract(symbol))
    finally:
        KrakenFuturesClient._fetch_ltc_futures_symbols = original


def test_symbol_to_contract_reads_live_instruments_when_no_catalog():
    seen = {}
    original = KrakenFuturesClient._get_public_json

    def fake(url, params=None):
        seen["url"] = url
        seen["params"] = params
        return {
            "result": "success",
            "instruments": [
                {"symbol": "PI_LTCUSD"},
                {"symbol": "PF_XLTUSD"},
                {"symbol": "PF_LTCUSD"},
                {"symbol": "PF_LTCUSD"},
            ],
        }

    KrakenFuturesClient._get_public_json = staticmethod(fake)
    try:
        _expect_unbound(lambda: KrakenFuturesClient.symbol_to_contract("LTC/USD"))
    finally:
        KrakenFuturesClient._get_public_json = original
    assert seen["url"] == "https://futures.kraken.com/derivatives/api/v3/instruments"
    assert seen["params"] is None


def test_symbol_to_contract_live_payload_zero_and_one_exact_hit():
    original = KrakenFuturesClient._fetch_ltc_futures_symbols
    try:
        KrakenFuturesClient._fetch_ltc_futures_symbols = staticmethod(lambda: [])
        _expect_unbound(lambda: KrakenFuturesClient.symbol_to_contract("LTC/USD"))
        KrakenFuturesClient._fetch_ltc_futures_symbols = staticmethod(lambda: ["PI_LTCUSD", "PF_XLTUSD"])
        _expect_unbound(lambda: KrakenFuturesClient.symbol_to_contract("LTC/USD"))
        KrakenFuturesClient._fetch_ltc_futures_symbols = staticmethod(
            lambda: ["PI_LTCUSD", "PF_XLTUSD", "PF_LTCUSD"]
        )
        assert KrakenFuturesClient.symbol_to_contract("LTC/USD") == "PF_LTCUSD"
    finally:
        KrakenFuturesClient._fetch_ltc_futures_symbols = original


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
