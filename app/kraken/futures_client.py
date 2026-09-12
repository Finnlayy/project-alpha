"""
Real Kraken Futures (Pro) API v3 client (public + private).

Private endpoints use the documented v3 authentication scheme:
    headers:
        Key       = API key
        Timestamp = milliseconds since epoch
        Signature = HMAC-SHA256( timestamp + method + path + body, secret ).hexdigest()
    path = e.g. '/derivatives/api/v3/positions' (with query string for GET)
Reference: https://docs.kraken.com/ft/api-docs/ft/v3#authentication
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from app.config import KrakenCredentials, Settings
from app.kraken.spot_client import KrakenError


class KrakenFuturesClient:
    """Synchronous Kraken Futures (Pro) REST client."""

    API_PATH = "/derivatives/api/v3"

    def __init__(self, settings: Settings, timeout: Optional[float] = None):
        self.settings = settings
        self.base = settings.futures_rest.rstrip("/")
        self.timeout = timeout or settings.request_timeout

    # ------------------------------------------------------------------ auth
    @staticmethod
    def sign_v3(timestamp_ms: str, method: str, path_with_query: str, body: str, secret: str) -> str:
        message = f"{timestamp_ms}{method.upper()}{path_with_query}{body}".encode("utf-8")
        return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def _request(
        self,
        method: str,
        endpoint: str,  # e.g. '/positions' (relative to API_PATH)
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        private: bool = False,
    ) -> Any:
        import json as _json

        full_path = self.API_PATH + endpoint
        query = f"?{urlencode(params)}" if params else ""
        path_with_query = full_path + query
        url = self.base + path_with_query

        body_str = ""
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if json_body is not None:
            body_str = _json.dumps(json_body, separators=(",", ":"))

        if private:
            creds: KrakenCredentials = self.settings.futures
            if not creds.configured:
                raise KrakenError("Kraken Futures credentials not configured (set KRAKEN_FUTURES_API_KEY / KRAKEN_FUTURES_PRIVATE_KEY).")
            ts = str(int(time.time() * 1000))
            headers.update(
                {
                    "Key": creds.api_key,
                    "Timestamp": ts,
                    "Signature": self.sign_v3(ts, method, path_with_query, body_str, creds.api_secret),
                }
            )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, content=body_str or None, headers=headers)
        except httpx.HTTPError as e:
            raise KrakenError(f"Kraken Futures network failure for {endpoint}: {type(e).__name__}: {str(e)[:160]}")

        text = resp.text
        try:
            payload = _json.loads(text) if text else None
        except Exception:
            raise KrakenError(f"Non-JSON response from Kraken Futures (HTTP {resp.status_code}): {text[:200]}", resp.status_code)

        if resp.status_code != 200:
            errors = payload.get("errors") if isinstance(payload, dict) else None
            raise KrakenError(
                f"HTTP {resp.status_code} from {endpoint}: {errors or text[:200]}",
                resp.status_code,
                errors if isinstance(errors, list) else [],
            )

        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload

    # ---------------------------------------------------------------- public
    def instrument_specs(self) -> Any:
        return self._request("GET", "/instrument-specs")

    def ticker(self, contract: str) -> Any:
        """contract e.g. 'XBTUSD-P' (perpetual)."""
        return self._request("GET", "/ticker", {"contract": contract})

    def candles(self, contract: str, since: Optional[int] = None, max_: int = 300) -> Any:
        """Real OHLC candles for a futures contract. since: ms epoch (inclusive)."""
        params: Dict[str, Any] = {"contract": contract, "max": max_}
        if since:
            params["since"] = since
        return self._request("GET", "/candles", params)

    def funding_rates(self, contract: str) -> Any:
        return self._request("GET", "/funding-rates", {"contract": contract})

    def order_book(self, contract: str) -> Any:
        return self._request("GET", "/order-book", {"contract": contract})

    def margin_info(self, contract: str) -> Any:
        return self._request("GET", "/margin-info", {"contract": contract})

    # -------------------------------------------------------------- private
    def positions(self) -> Any:
        return self._request("GET", "/positions", private=True)

    def account_balances(self) -> Any:
        return self._request("GET", "/account/balances", private=True)

    def open_orders(self, contract: Optional[str] = None) -> Any:
        params = {"contract": contract} if contract else None
        return self._request("GET", "/orders", params, private=True)

    def place_order(
        self,
        contract: str,
        side: str,  # 'buy' | 'sell'
        size: int,  # number of contracts (futures API uses whole contract units)
        order_type: str = "limit",  # 'market' | 'limit'
        price: Optional[float] = None,
        post_only: bool = False,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> Any:
        """Real futures order placement (isolated margin default)."""
        body: Dict[str, Any] = {
            "contract": contract,
            "side": side,
            "size": size,
            "type": order_type,
            "margin": "isolated",
            "timeInForce": "gtc",
        }
        if price is not None and order_type != "market":
            body["price"] = price
        if post_only:
            body["postOnly"] = True
        if reduce_only:
            body["reduceOnly"] = True
        if client_order_id:
            body["clOrdID"] = client_order_id
        return self._request("POST", "/order", json_body=body, private=True)

    def cancel_order(self, contract: str, order_id: str) -> Any:
        return self._request("POST", f"/order/cancel/{order_id}", json_body={"contract": contract}, private=True)

    def cancel_all(self, contract: str) -> Any:
        return self._request("POST", "/order/cancel-all", json_body={"contract": contract}, private=True)

    def close_position(self, contract: str, position_id: str) -> Any:
        return self._request("POST", f"/position/{position_id}/close", json_body={"contract": contract}, private=True)

    def set_leverage(self, contract: str, leverage: int) -> Any:
        return self._request("POST", "/leverage", json_body={"contract": contract, "leverage": leverage}, private=True)

    def trade_history(self, contract: Optional[str] = None, max_: int = 100) -> Any:
        params: Dict[str, Any] = {"max": max_}
        if contract:
            params["contract"] = contract
        return self._request("GET", "/trade-history", params, private=True)

    # ------------------------------------------------------------------ util
    @staticmethod
    def symbol_to_contract(symbol: str, perpetual: bool = True) -> str:
        """'BTC/USD' -> 'XBTUSD-P' · 'ETH/USD' -> 'ETHUSD-P'."""
        native = KrakenFuturesClient._spot_native(symbol)
        return f"{native}-P" if perpetual else f"{native}-M"

    @staticmethod
    def _spot_native(symbol: str) -> str:
        mapping = {"BTC": "XBT", "DOGE": "XDG", "LTC": "XLT"}
        base, _, quote = symbol.partition("/")
        return mapping.get(base.upper(), base.upper()) + quote.upper()
