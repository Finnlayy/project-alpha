"""
Real Kraken Futures (Pro) REST API v3 client (public + private).

Base URL:  https://futures.kraken.com/derivatives/api/v3
Docs:      https://docs.kraken.com/api/docs/futures-api/

Private endpoints use the documented Futures authentication scheme
(https://docs.futures.kraken.com/#http-api-http-api-introduction-authentication):

    headers:
        APIKey  = API key (public part)
        Nonce   = ms-precision nonce (the SAME nonce used in the signature)
        Authent = base64( HMAC-SHA512( base64decode(secret),
                                       SHA256(postData + nonce + endpointPath) ) )
    endpointPath = path WITHOUT the '/derivatives' prefix, e.g. '/api/v3/sendorder'
    postData     = urlencoded params (query string for GET, form body for POST)

Response envelope: {"result": "success"|"error", ...} — every private call must
check result == "error" and surface payload["error"].

Symbols: perpetuals are PF_XBTUSD / PF_ETHUSD (new) or PI_XBTUSD (legacy perp);
dated contracts FI_XBTUSD_YYMMDD; indices in_xbtusd. This client targets the
current PF_* perpetual symbols.
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
from app.kraken.spot_client import KrakenError, decode_api_secret


class KrakenFuturesClient:
    """Synchronous Kraken Futures (Pro) REST client."""

    API_PATH = "/derivatives/api/v3"   # on the wire
    SIGN_PREFIX = "/api/v3"            # what enters the Authent signature (no /derivatives)

    _nonce_lock = threading.Lock()
    _last_nonce = 0

    def __init__(self, settings: Settings, timeout: Optional[float] = None):
        self.settings = settings
        self.base = settings.futures_rest.rstrip("/")
        self.timeout = timeout or settings.request_timeout

    # ------------------------------------------------------------------ auth
    @classmethod
    def _next_nonce(cls) -> str:
        with cls._nonce_lock:
            ms = int(time.time() * 1000)
            if ms <= cls._last_nonce:
                ms = cls._last_nonce + 1
            cls._last_nonce = ms
            return str(ms)

    @staticmethod
    def sign_v3(post_data: str, nonce: str, endpoint_path: str, secret_b64: str) -> str:
        """Official Futures Authent.

        authent = base64(HMAC-SHA512(base64decode(secret), SHA256(postData + nonce + endpointPath)))
        endpointPath excludes '/derivatives', e.g. '/api/v3/sendorder'.
        """
        secret = decode_api_secret(secret_b64, "Futures")
        sha256 = hashlib.sha256(f"{post_data}{nonce}{endpoint_path}".encode("utf-8")).digest()
        mac = hmac.new(secret, sha256, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _request(
        self,
        method: str,
        endpoint: str,  # e.g. '/tickers' (relative to API_PATH)
        params: Optional[Dict[str, Any]] = None,
        private: bool = False,
    ) -> Dict[str, Any]:
        import json as _json

        clean = {k: v for k, v in (params or {}).items() if v is not None}
        # bools must serialize lowercase for urlencode
        for k, v in list(clean.items()):
            if isinstance(v, bool):
                clean[k] = "true" if v else "false"
        post_data = urlencode(clean)

        full_path = self.API_PATH + endpoint          # on the wire
        sign_path = self.SIGN_PREFIX + endpoint       # into the signature
        url = self.base + full_path
        headers: Dict[str, str] = {"Accept": "application/json"}

        if method == "GET" and post_data:
            url += "?" + post_data

        if private:
            creds: KrakenCredentials = self.settings.futures
            if not creds.configured:
                raise KrakenError("Kraken Futures credentials not configured (set KRAKEN_FUTURES_API_KEY / KRAKEN_FUTURES_PRIVATE_KEY).")
            nonce = self._next_nonce()
            headers.update(
                {
                    "APIKey": creds.api_key,
                    "Nonce": nonce,
                    "Authent": self.sign_v3(post_data, nonce, sign_path, creds.api_secret),
                }
            )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                if method == "GET":
                    resp = client.get(url, headers=headers)
                else:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    resp = client.post(url, content=post_data or None, headers=headers)
        except httpx.HTTPError as e:
            raise KrakenError(f"Kraken Futures network failure for {endpoint}: {type(e).__name__}: {str(e)[:160]}")

        text = resp.text
        try:
            payload = _json.loads(text) if text else {}
        except Exception:
            raise KrakenError(f"Non-JSON response from Kraken Futures (HTTP {resp.status_code}): {text[:200]}", resp.status_code)

        if resp.status_code != 200:
            err = payload.get("error") if isinstance(payload, dict) else None
            raise KrakenError(f"HTTP {resp.status_code} from {endpoint}: {err or text[:200]}", resp.status_code)

        if isinstance(payload, dict) and payload.get("result") == "error":
            raise KrakenError(f"Kraken Futures error for {endpoint}: {payload.get('error')}", resp.status_code)

        return payload if isinstance(payload, dict) else {"result": payload}

    # ---------------------------------------------------------------- public
    def tickers(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """All market tickers (mark price, bid/ask, funding, OI, 24h change).

        symbol filter is case-insensitive, e.g. 'PF_XBTUSD'.
        """
        params = {"symbol": symbol} if symbol else None
        return self._request("GET", "/tickers", params)

    def ticker(self, symbol: str) -> Dict[str, Any]:
        """Single-contract ticker. symbol e.g. 'PF_XBTUSD'."""
        payload = self._request("GET", "/tickers", {"symbol": symbol})
        rows = payload.get("tickers") or []
        if not rows:
            raise KrakenError(f"no ticker for symbol '{symbol}'")
        return rows[0]

    def instruments(self) -> Dict[str, Any]:
        """All tradeable instruments + contract specs (size, tick, margin levels)."""
        return self._request("GET", "/instruments")

    def instruments_status(self, instrument: Optional[str] = None) -> Dict[str, Any]:
        params = {"instrument": instrument} if instrument else None
        return self._request("GET", "/instruments/status", params)

    def orderbook(self, symbol: str) -> Dict[str, Any]:
        """L2 orderbook snapshot for a symbol, e.g. 'PF_XBTUSD'."""
        return self._request("GET", "/orderbook", {"symbol": symbol})

    def history(self, symbol: str, last_id: Optional[int] = None) -> Dict[str, Any]:
        """Public execution (trade) history for a symbol."""
        params: Dict[str, Any] = {"symbol": symbol}
        if last_id is not None:
            params["lastId"] = last_id
        return self._request("GET", "/history", params)

    def funding_rates(self, symbol: str) -> Dict[str, Any]:
        """Funding rate + prediction for a symbol (served from /tickers).

        Returns {"symbol","fundingRate","fundingRatePrediction","markPrice","indexPrice"}.
        """
        t = self.ticker(symbol)
        return {
            "symbol": t.get("symbol", symbol),
            "fundingRate": t.get("fundingRate"),
            "fundingRatePrediction": t.get("fundingRatePrediction"),
            "markPrice": t.get("markPrice"),
            "indexPrice": t.get("indexPrice"),
        }

    # -------------------------------------------------------------- private
    def accounts(self) -> Dict[str, Any]:
        """Wallets: per-currency balance, margin, PnL. Envelope: {"accounts": {...}}."""
        return self._request("GET", "/accounts", private=True)

    def open_positions(self) -> Dict[str, Any]:
        """Open positions. Envelope: {"openPositions": [...]}."""
        return self._request("GET", "/openpositions", private=True)

    def open_orders(self) -> Dict[str, Any]:
        """Open orders. Envelope: {"openOrders": [...]}."""
        return self._request("GET", "/openorders", private=True)

    def fills(self, last_fill_time: Optional[str] = None) -> Dict[str, Any]:
        """Account fills (execution history). Envelope: {"fills": [...]}."""
        params = {"lastFillTime": last_fill_time} if last_fill_time else None
        return self._request("GET", "/fills", params, private=True)

    def notifications(self) -> Dict[str, Any]:
        return self._request("GET", "/notifications", private=True)

    def account_log(self) -> Dict[str, Any]:
        return self._request("GET", "/accountLog", private=True)

    def send_order(
        self,
        symbol: str,
        side: str,  # 'buy' | 'sell'
        size: float,  # number of contracts
        order_type: str = "lmt",  # lmt|post|mkt|stp|take_profit|ioc|trailing_stop|fok
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reduce_only: bool = False,
        cli_ord_id: Optional[str] = None,
        trigger_signal: Optional[str] = None,  # mark|index|last
        leverage: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Real futures order placement. Returns {"sendStatus": {...order_id...}}."""
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        params: Dict[str, Any] = {
            "orderType": order_type,
            "symbol": symbol,
            "side": side,
            "size": size,
            "reduceOnly": reduce_only or None,
            "limitPrice": limit_price,
            "stopPrice": stop_price,
            "cliOrdId": cli_ord_id,
            "triggerSignal": trigger_signal,
            "leverage": leverage,
        }
        return self._request("POST", "/sendorder", params, private=True)

    def edit_order(
        self,
        order_id: Optional[str] = None,
        cli_ord_id: Optional[str] = None,
        symbol: Optional[str] = None,
        size: Optional[float] = None,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "orderId": order_id,
            "cliOrdId": cli_ord_id,
            "symbol": symbol,
            "size": size,
            "limitPrice": limit_price,
            "stopPrice": stop_price,
        }
        return self._request("POST", "/editorder", params, private=True)

    def cancel_order(
        self,
        order_id: Optional[str] = None,
        symbol: Optional[str] = None,
        cli_ord_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not order_id and not cli_ord_id:
            raise ValueError("cancel_order needs order_id or cli_ord_id")
        params: Dict[str, Any] = {"orderId": order_id, "symbol": symbol, "cliOrdId": cli_ord_id}
        return self._request("POST", "/cancelorder", params, private=True)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        params = {"symbol": symbol} if symbol else None
        return self._request("POST", "/cancelallorders", params, private=True)

    def close_position(self, symbol: str, size: Optional[float] = None) -> Dict[str, Any]:
        """Close (part of) a position with a reduce-only IOC order at mark.

        The v3 API has no dedicated close endpoint — closing is a real
        opposite-side reduceOnly order. size=None closes the full position.
        """
        payload = self.open_positions()
        matches = [p for p in (payload.get("openPositions") or []) if str(p.get("symbol", "")).upper() == symbol.upper()]
        if not matches:
            raise KrakenError(f"no open position in {symbol} to close")
        pos = matches[0]
        side = "sell" if str(pos.get("side", "")).lower() == "long" else "buy"
        qty = size if size is not None else float(pos.get("size") or 0)
        if qty <= 0:
            raise KrakenError(f"position in {symbol} has non-positive size ({pos.get('size')})")
        return self.send_order(symbol, side, qty, order_type="mkt", reduce_only=True)

    # ------------------------------------------------- compatibility aliases
    # (older internal call sites; canonical names above match the v3 docs)
    def positions(self) -> Dict[str, Any]:
        return self.open_positions()

    def account_balances(self) -> Dict[str, Any]:
        return self.accounts()

    def place_order(self, contract: str, side: str, size: float, order_type: str = "lmt",
                    price: Optional[float] = None, post_only: bool = False,
                    reduce_only: bool = False, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        otype = "post" if post_only and order_type == "lmt" else ("mkt" if order_type == "market" else order_type)
        return self.send_order(contract, side, size, order_type=otype, limit_price=price,
                               reduce_only=reduce_only, cli_ord_id=client_order_id)

    def cancel_all(self, contract: Optional[str] = None) -> Dict[str, Any]:
        return self.cancel_all_orders(symbol=contract)

    def trade_history(self, contract: Optional[str] = None, max_: int = 100) -> Dict[str, Any]:
        if contract:
            return self.history(contract)
        return self.fills()

    # ------------------------------------------------------------------ util
    @staticmethod
    def symbol_to_contract(symbol: str) -> str:
        """'BTC/USD' -> 'PF_XBTUSD' · 'ETH/USD' -> 'PF_ETHUSD'.

        Targets current perpetual (flexible futures) symbols. Case-insensitive
        on the wire; uppercase is canonical.
        """
        base, _, quote = symbol.partition("/")
        mapping = {"BTC": "XBT", "DOGE": "XDG", "LTC": "XLT"}
        b = mapping.get(base.strip().upper(), base.strip().upper())
        q = quote.strip().upper() or "USD"
        return f"PF_{b}{q}"

    @staticmethod
    def contract_to_symbol(contract: str) -> str:
        """'PF_XBTUSD' -> 'BTC/USD' (best-effort inverse of symbol_to_contract)."""
        core = contract.upper()
        for prefix in ("PF_", "PI_", "FF_"):
            if core.startswith(prefix):
                core = core[len(prefix):]
                break
        if core.startswith("FI_"):  # dated: FI_XBTUSD_260327
            core = core[3:].rsplit("_", 1)[0]
        rev = {"XBT": "BTC", "XDG": "DOGE", "XLT": "LTC"}
        for q in ("USD", "EUR", "GBP", "USDT", "USDC"):
            if core.endswith(q) and len(core) > len(q):
                b = core[: -len(q)]
                return f"{rev.get(b, b)}/{q}"
        return contract
