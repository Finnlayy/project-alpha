# Trace cros-ltcusd-955960103 (paper CROSS_BOOK): pair_to_native binds LTC/USD
# only to the one AssetPairs row Peter confirmed (key XLTCZUSD, altname LTCUSD,
# wsname LTC/USD, base XLTC, quote ZUSD, status online). XLTUSD is rejected.
# Zero or multiple exact hits leave the pair unbound so that worker stays paused.
# This file does not place orders and does not init or reset paper state.
"""
Real Kraken Spot REST client (public + private).

Private endpoints use the official Kraken Spot authentication scheme
(https://docs.kraken.com/api/docs/guides/spot-rest-auth/):

    1. nonce     = str(int(time.time() * 1000))   (ms precision, strictly increasing)
    2. post_data = urlencoded body, ALWAYS starting with nonce=<nonce>&...
    3. sha256    = SHA256(nonce + post_data)
    4. api_sign  = base64( HMAC-SHA512( base64_decode(secret), api_path + sha256 ) )
    5. headers   = API-Key, API-Sign

The secret shown in Kraken's account management is base64-encoded and MUST be
base64-decoded before use as the HMAC key. Any deviation (e.g. signing with the
raw secret string, or omitting the nonce from the body) yields EAPI:Invalid key.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from app.config import KrakenCredentials, Settings


class KrakenError(RuntimeError):
    def __init__(self, error: str, http_status: int = 0, errors: Optional[list] = None):
        super().__init__(error)
        self.http_status = http_status
        self.errors = errors or []


class PairUnbound(KrakenError):
    """Lookup was not one exact pair. No substitute pair is returned.

    Paper CROSS_BOOK worker cros-ltcusd-955960103 stays paused.
    """


class KrakenSpotClient:
    """Synchronous Kraken Spot REST client. Thread-safe (stateless transport)."""

    _nonce_lock = threading.Lock()
    _last_nonce = 0

    def __init__(self, settings: Settings, timeout: Optional[float] = None):
        self.settings = settings
        self.base = settings.spot_rest.rstrip("/")
        self.timeout = timeout or settings.request_timeout

    # ------------------------------------------------------------------ auth
    @classmethod
    def _next_nonce(cls) -> str:
        """Monotonic millisecond nonce (Kraken rejects reused/decreasing nonces)."""
        with cls._nonce_lock:
            ms = int(time.time() * 1000)
            if ms <= cls._last_nonce:
                ms = cls._last_nonce + 1
            cls._last_nonce = ms
            return str(ms)

    @staticmethod
    def sign_request(api_path: str, post_data: str, secret_b64: str, nonce: str) -> str:
        """Official Spot API-Sign.

        api_sign = base64(HMAC-SHA512(base64decode(secret), api_path + SHA256(nonce + post_data)))

        Verified against the official documented vector:
          secret=kQH5HW/...+F1huXg== nonce=1616492376594
          payload=nonce=1616492376594&ordertype=limit&pair=XBTUSD&price=37500&type=buy&volume=1.25
          path=/0/private/AddOrder
          → 4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8MPtnRfp32bAb0nmbRn6H8ndwLUQ==
        """
        try:
            secret = base64.b64decode(secret_b64)
        except Exception as exc:
            raise KrakenError(f"Spot API secret is not valid base64: {exc}")
        sha256 = hashlib.sha256((nonce + post_data).encode("utf-8")).digest()
        mac = hmac.new(secret, api_path.encode("utf-8") + sha256, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _request(
        self,
        method: str,
        api_path: str,
        params: Optional[Dict[str, Any]] = None,
        private: bool = False,
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        url = self.base + api_path
        data: Optional[str] = None

        if private:
            creds: KrakenCredentials = self.settings.spot
            if not creds.configured:
                raise KrakenError("Kraken Spot credentials not configured (set KRAKEN_SPOT_API_KEY / KRAKEN_SPOT_PRIVATE_KEY).")
            nonce = self._next_nonce()
            # nonce FIRST so the body starts with nonce=<nonce> per the spec
            body: Dict[str, Any] = {"nonce": nonce}
            for k, v in (params or {}).items():
                if v is not None:
                    body[k] = v
            data = urlencode(body)
            headers = {
                "API-Key": creds.api_key,
                "API-Sign": self.sign_request(api_path, data, creds.api_secret, nonce),
                "Content-Type": "application/x-www-form-urlencoded",
            }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                if method == "GET":
                    resp = client.get(url, params=params or None, headers=headers)
                else:
                    resp = client.post(url, content=data, headers=headers)
        except httpx.HTTPError as e:
            raise KrakenError(f"Kraken network failure for {api_path}: {type(e).__name__}: {str(e)[:160]}")

        try:
            payload = resp.json()
        except Exception:
            raise KrakenError(f"Non-JSON response from Kraken (HTTP {resp.status_code}): {resp.text[:200]}", resp.status_code)

        if resp.status_code != 200:
            err_list = payload.get("error", []) if isinstance(payload, dict) else []
            raise KrakenError(f"HTTP {resp.status_code} from {api_path}", resp.status_code, err_list if isinstance(err_list, list) else [err_list])

        if isinstance(payload, dict) and payload.get("error"):
            errors = payload["error"] if isinstance(payload["error"], list) else [payload["error"]]
            raise KrakenError("; ".join(str(e) for e in errors), resp.status_code, errors)

        return payload

    # ---------------------------------------------------------------- public
    def server_time(self) -> Dict[str, Any]:
        return self._request("GET", "/0/public/Time")

    def system_status(self) -> Dict[str, Any]:
        return self._request("GET", "/0/public/SystemStatus")

    def ticker(self, pairs: List[str]) -> Dict[str, Any]:
        """pairs: Kraken-native names (XBTUSD, ...). Returns raw Ticker payload."""
        return self._request("GET", "/0/public/Ticker", {"pair": ",".join(pairs)})

    def ohlc(self, pair: str, interval: int, since: Optional[int] = None) -> Dict[str, Any]:
        """Real OHLC candles. interval in minutes (1,5,15,30,60,...)."""
        params: Dict[str, Any] = {"pair": pair, "interval": interval}
        if since:
            params["since"] = since
        return self._request("GET", "/0/public/OHLC", params)

    def asset_pairs(self) -> Dict[str, Any]:
        return self._request("GET", "/0/public/AssetPairs")

    def assets(self) -> Dict[str, Any]:
        return self._request("GET", "/0/public/Assets")

    def depth(self, pair: str, count: int = 20) -> Dict[str, Any]:
        return self._request("GET", "/0/public/Depth", {"pair": pair, "count": count})

    def recent_trades(self, pair: str, since: Optional[int] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"pair": pair}
        if since:
            params["since"] = since
        return self._request("GET", "/0/public/Trades", params)

    # -------------------------------------------------------------- private
    def balance(self, asset: Optional[str] = None) -> Dict[str, Any]:
        params = {"asset": asset} if asset else {}
        return self._request("POST", "/0/private/Balance", params, private=True)

    def trade_balance(self, asset: str = "ZUSD") -> Dict[str, Any]:
        """Margin overview: equity, free/total margin, P&L. Real margin health."""
        return self._request("POST", "/0/private/TradeBalance", {"asset": asset}, private=True)

    def ledgers(
        self,
        asset: Optional[str] = None,
        ledger_type: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        ofs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Real ledger entries (deposits, withdrawals, trades, fees, ...)."""
        params: Dict[str, Any] = {}
        if asset:
            params["asset"] = asset
        if ledger_type:
            params["type"] = ledger_type
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if ofs:
            params["ofs"] = ofs
        return self._request("POST", "/0/private/Ledgers", params, private=True)

    def open_orders(self, trades: bool = False) -> Dict[str, Any]:
        return self._request("POST", "/0/private/OpenOrders", {"trades": trades}, private=True)

    def closed_orders(self, trades: bool = False, start: Optional[int] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"trades": trades}
        if start:
            params["start"] = start
        return self._request("POST", "/0/private/ClosedOrders", params, private=True)

    def cancel_all(self) -> Dict[str, Any]:
        return self._request("POST", "/0/private/CancelAll", private=True)

    def cancel_order(self, txid: str) -> Dict[str, Any]:
        return self._request("POST", "/0/private/CancelOrder", {"txid": txid}, private=True)

    def add_order(
        self,
        pair: str,
        side: str,
        ordertype: str,
        volume: float,
        price: Optional[float] = None,
        price2: Optional[float] = None,
        oflags: str = "post",
        validate: bool = False,
        leverage: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Real order placement. side: buy|sell · ordertype: market|limit|stop-loss|...

        oflags 'post' = maker-only. validate=True runs full server-side
        validation without placing the order (dry-run).
        """
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        params: Dict[str, Any] = {
            "pair": pair,
            "type": side,
            "ordertype": ordertype,
            "volume": f"{volume:.8f}".rstrip("0").rstrip("."),
            "oflags": oflags,
        }
        if price is not None:
            params["price"] = f"{price:.10f}".rstrip("0").rstrip(".")
        if price2 is not None:
            params["price2"] = f"{price2:.10f}".rstrip("0").rstrip(".")
        if leverage:
            params["leverage"] = leverage
        if validate:
            params["validate"] = True
        return self._request("POST", "/0/private/AddOrder", params, private=True)

    def query_orders(self, txid: str, trades: bool = False) -> Dict[str, Any]:
        return self._request("POST", "/0/private/QueryOrders", {"txid": txid, "trades": trades}, private=True)

    def trades_history(self, type: str = "all", trades: bool = False, start: Optional[int] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"type": type, "trades": trades}
        if start:
            params["start"] = start
        return self._request("POST", "/0/private/TradesHistory", params, private=True)

    # ------------------------------------------------------------------ util
    # LTC is not in this map. The old LTC -> XLT entry made LTC/USD into XLTUSD.
    _BASE = {"BTC": "XBT", "DOGE": "XDG", "XETH": "ETH"}
    _QUOTE = {"USD": "USD", "EUR": "ZEUR", "GBP": "ZGBP", "JPY": "ZJPY"}

    # One row from GET /0/public/AssetPairs?pair=LTCUSD. No other spot pair is recorded.
    _LTC_SPOT_ROW = {
        "key": "XLTCZUSD",
        "altname": "LTCUSD",
        "wsname": "LTC/USD",
        "base": "XLTC",
        "quote": "ZUSD",
        "status": "online",
    }
    _LTC_SPOT_FIELDS = ("key", "altname", "wsname", "base", "quote", "status")
    _REJECTED_SPOT_KEYS = frozenset({"XLTUSD"})

    @staticmethod
    def _exact_ltc_spot_hits(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rows that equal the single confirmed LTC/USD AssetPairs row."""
        confirmed = KrakenSpotClient._LTC_SPOT_ROW
        hits: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = str(row.get("key", "")).upper()
            if key in KrakenSpotClient._REJECTED_SPOT_KEYS:
                continue
            if all(str(row.get(field, "")) == confirmed[field] for field in KrakenSpotClient._LTC_SPOT_FIELDS):
                hits.append(row)
        return hits

    @staticmethod
    def _bind_ltc_spot(symbol: str, rows: Optional[List[Dict[str, Any]]] = None) -> str:
        """Return XLTCZUSD only when exactly one confirmed row matches.

        Any other count leaves cros-ltcusd-955960103 unbound. XLTUSD is never returned.
        """
        token = (symbol or "").strip().upper()
        if token in {"XLTUSD", "XLT/USD"}:
            raise PairUnbound(
                "rejected XLTUSD; paper worker cros-ltcusd-955960103 stays paused"
            )
        base, _, quote = (symbol or "").partition("/")
        base_u = base.strip().upper()
        quote_u = quote.strip().upper()
        exact_request = token in {"LTC/USD", "LTCUSD", "XLTCZUSD"} or (base_u == "LTC" and quote_u == "USD")
        if not exact_request:
            raise PairUnbound(
                "LTC spot lookup had no exact LTC/USD row; paper worker cros-ltcusd-955960103 stays paused"
            )
        catalog = rows if rows is not None else [dict(KrakenSpotClient._LTC_SPOT_ROW)]
        hits = KrakenSpotClient._exact_ltc_spot_hits(catalog)
        if len(hits) != 1:
            raise PairUnbound(
                f"LTC/USD spot lookup hit {len(hits)} rows; paper worker cros-ltcusd-955960103 stays paused"
            )
        key = str(hits[0].get("key", ""))
        if key != "XLTCZUSD":
            raise PairUnbound(
                "LTC/USD spot row was not XLTCZUSD; paper worker cros-ltcusd-955960103 stays paused"
            )
        return key

    @staticmethod
    def pair_to_native(symbol: str) -> str:
        """'BTC/USD' -> 'XBTUSD', 'ETH/EUR' -> 'ETHZEUR', 'LTC/USD' -> 'XLTCZUSD'.

        Simplified pair names accepted by the v0 public/private REST API.
        (WebSocket v2 wants the canonical 'BTC/USD' form instead.)

        LTC/USD is bound only when the confirmed AssetPairs lookup is unique
        and exact. That row's key is XLTCZUSD. XLTUSD is rejected.
        """
        token = (symbol or "").strip().upper()
        base, _, quote = (symbol or "").partition("/")
        base_u = base.strip().upper()
        quote_u = quote.strip().upper()
        if base_u in {"LTC", "XLT"} or token in {"LTC/USD", "LTCUSD", "XLTCZUSD", "XLTUSD", "XLT/USD"}:
            return KrakenSpotClient._bind_ltc_spot(symbol)
        b = KrakenSpotClient._BASE.get(base_u, base_u)
        q = KrakenSpotClient._QUOTE.get(quote_u, quote_u)
        native = b + q
        if native.upper() == "XLTUSD":
            raise PairUnbound(
                "rejected XLTUSD; paper worker cros-ltcusd-955960103 stays paused"
            )
        return native

    _NATIVE_QUOTES = {"USD": "USD", "ZEUR": "EUR", "ZGBP": "GBP", "ZJPY": "JPY"}
    _NATIVE_TO_USER = {
        "XBT": "BTC", "XXBT": "BTC", "XDG": "DOGE",
        "XETH": "ETH", "XXRP": "XRP", "XLTC": "LTC", "XXLM": "XLM",
        "ZUSD": "USD", "ZEUR": "EUR", "ZGBP": "GBP", "ZJPY": "JPY",
    }

    @staticmethod
    def native_to_pair(native: str) -> str:
        """'XBTUSD'/'XXBTZUSD' -> 'BTC/USD' (inverse of pair_to_native).

        Kraken REST answers with FULL altname keys ('XXBTZUSD') even when asked
        with simplified names ('XBTUSD') — both forms are handled here.
        """
        n = (native or "").upper()
        # full 8-char altname: 4-char base + 4-char quote (XXBTZUSD, XETHZEUR, ...)
        if len(n) == 8 and (n.startswith("X") or n.startswith("Z")):
            base = KrakenSpotClient._NATIVE_TO_USER.get(n[:4], n[:4])
            quote = KrakenSpotClient._NATIVE_TO_USER.get(n[4:], n[4:])
            return f"{base}/{quote}"
        for native_q, quote in KrakenSpotClient._NATIVE_QUOTES.items():
            if n.endswith(native_q) and len(n) > len(native_q):
                base = n[: -len(native_q)]
                base = KrakenSpotClient._NATIVE_TO_USER.get(base, base)
                return f"{base}/{quote}"
        return native
