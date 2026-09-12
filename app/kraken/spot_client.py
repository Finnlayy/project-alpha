"""
Real Kraken Spot REST client (public + private).

Private endpoints use the official Kraken API-2 signature scheme:
    1. nonce        = str(int(time.time() * 1000))          (ms precision, monotonic)
    2. post_data    = urlencoded form body
    3. hex_sig      = HMAC-SHA512( api_path + post_data, secret ).hexdigest()
    4. api_sign     = base64( post_data + nonce + hex_sig )
    5. headers      = API-Key, API-Sign
Reference: https://docs.kraken.com/api/docs/guides/api-auth
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
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


class KrakenSpotClient:
    """Synchronous Kraken Spot REST client. Thread-safe (stateless transport)."""

    def __init__(self, settings: Settings, timeout: Optional[float] = None):
        self.settings = settings
        self.base = settings.spot_rest.rstrip("/")
        self.timeout = timeout or settings.request_timeout
        self._nonce_lock_counter = 0

    # ------------------------------------------------------------------ auth
    @staticmethod
    def _next_nonce() -> str:
        return str(int(time.time() * 1000))

    @staticmethod
    def sign_request(api_path: str, post_data: str, secret: str, nonce: str) -> str:
        """API-2 signature: base64( post_data + nonce + hmac_sha512(api_path+post_data) )."""
        message = (api_path + post_data).encode("utf-8")
        hex_sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha512).hexdigest()
        payload = (post_data + nonce + hex_sig).encode("utf-8")
        return base64.b64encode(payload).decode("utf-8")

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
            data = urlencode(params or {})
            nonce = self._next_nonce()
            headers = {
                "API-Key": creds.api_key,
                "API-Sign": self.sign_request(api_path, data, creds.api_secret, nonce),
                "Content-Type": "application/x-www-form-urlencoded",
            }
            url = self.base + api_path

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
            raise KrakenError(f"HTTP {resp.status_code} from {api_path}", resp.status_code, payload.get("errors", []))

        if isinstance(payload, dict) and payload.get("error"):
            errors = payload["error"] if isinstance(payload["error"], list) else [payload["error"]]
            raise KrakenError("; ".join(str(e) for e in errors), resp.status_code, errors)

        return payload

    # ---------------------------------------------------------------- public
    def server_time(self) -> Dict[str, Any]:
        return self._request("GET", "/0/public/Time")

    def ticker(self, pairs: List[str]) -> Dict[str, Any]:
        """pairs: Kraken-native names (XBTUSD, ...). Returns raw Ticker payload."""
        return self._request("GET", "/0/public/Ticker", {"pair": ",".join(pairs)})

    def ohlc(self, pair: str, interval: int) -> Dict[str, Any]:
        """Real OHLC candles. interval in minutes (1,5,15,30,60,...)."""
        return self._request("GET", "/0/public/OHLC", {"pair": pair, "interval": interval})

    def asset_pairs(self) -> Dict[str, Any]:
        return self._request("GET", "/0/public/AssetPairs")

    def depth(self, pair: str, count: int = 20) -> Dict[str, Any]:
        return self._request("GET", "/0/public/Depth", {"pair": pair, "count": count})

    # -------------------------------------------------------------- private
    def balance(self, asset: Optional[str] = None) -> Dict[str, Any]:
        params = {"asset": asset} if asset else {}
        return self._request("POST", "/0/private/Balance", params, private=True)

    def open_orders(self) -> Dict[str, Any]:
        return self._request("POST", "/0/private/OpenOrders", private=True)

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
        oflags: str = "post",
        validate: bool = False,
    ) -> Dict[str, Any]:
        """Real order placement. side: buy|sell · ordertype: market|limit|stop-loss|... oflags: post (maker-only)."""
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
        if validate:
            params["validate"] = "true"
        return self._request("POST", "/0/private/AddOrder", params, private=True)

    def query_orders(self, txid: str) -> Dict[str, Any]:
        return self._request("POST", "/0/private/QueryOrders", {"txid": txid}, private=True)

    def trades_history(self, type: str = "all", start: Optional[int] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"type": type}
        if start:
            params["start"] = start
        return self._request("POST", "/0/private/TradesHistory", params, private=True)

    # ------------------------------------------------------------------ util
    _BASE = {"BTC": "XBT", "DOGE": "XDG", "LTC": "XLT", "XETH": "ETH"}
    _QUOTE = {"USD": "USD", "EUR": "ZEUR", "GBP": "ZGBP", "JPY": "ZJPY"}

    @staticmethod
    def pair_to_native(symbol: str) -> str:
        """'BTC/USD' -> 'XBTUSD', 'ETH/EUR' -> 'ETHZEUR'.

        Uses Kraken's simplified pair names (accepted by the v0 public API and
        required by the WebSocket v2 feed).
        """
        base, _, quote = symbol.partition("/")
        b = KrakenSpotClient._BASE.get(base.upper(), base.upper())
        q = KrakenSpotClient._QUOTE.get(quote.upper(), quote.upper())
        return b + q

    _NATIVE_QUOTES = {"USD": "USD", "ZEUR": "EUR", "ZGBP": "GBP", "ZJPY": "JPY"}
    _NATIVE_TO_USER = {"XBT": "BTC", "XDG": "DOGE", "XLT": "LTC"}

    @staticmethod
    def native_to_pair(native: str) -> str:
        """'XBTUSD' -> 'BTC/USD', 'ETHZEUR' -> 'ETH/EUR' (inverse of pair_to_native)."""
        for native_q, quote in KrakenSpotClient._NATIVE_QUOTES.items():
            if native.endswith(native_q) and len(native) > len(native_q):
                base = native[: -len(native_q)]
                base = KrakenSpotClient._NATIVE_TO_USER.get(base, base)
                return f"{base}/{quote}"
        return native
