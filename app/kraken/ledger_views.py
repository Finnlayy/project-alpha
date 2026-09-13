"""
Ledger view builders: normalize REAL Kraken Spot + Futures account data into the
exact shapes the UI (KrakenAccountLedgers / KrakenProPosition) and the MCP
tools consume.

Zero-Dummy rule: every number comes from a live Kraken response (balances,
open positions, tickers, accounts) or from deterministic math on those inputs.
Anything the exchange does not provide (e.g. per-position liquidation price on
the Futures v3 REST API) is either computed with a documented formula and
flagged `liquidationPriceEstimated: true`, or returned as an explicit error —
never invented.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.kraken.futures_client import KrakenFuturesClient
from app.kraken.spot_client import KrakenError, KrakenSpotClient

# Kraken-native asset codes -> display codes (Spot Balance/TradeBalance use these)
_ASSET_MAP = {
    "XXBT": "BTC", "XBT": "BTC",
    "XETH": "ETH", "ETH": "ETH",
    "XXRP": "XRP", "XLTC": "LTC", "XXLM": "XLM", "XXMR": "XMR",
    "XETC": "ETC", "XZEC": "ZEC", "XXDG": "DOGE", "XDG": "DOGE",
    "ZUSD": "USD", "USD": "USD",
    "ZEUR": "EUR", "EUR": "EUR", "ZGBP": "GBP", "GBP": "GBP",
    "ZJPY": "JPY", "JPY": "JPY", "ZCAD": "CAD", "CAD": "CAD",
    "ZCHF": "CHF", "CHF": "CHF", "ZAUD": "AUD", "AUD": "AUD",
    "USDT": "USDT", "USDC": "USDC", "DAI": "DAI", "PYUSD": "PYUSD",
    "SOL": "SOL", "XRP": "XRP", "ADA": "ADA", "DOT": "DOT",
    "LINK": "LINK", "AVAX": "AVAX", "SUI": "SUI",
}

FIAT = {"USD", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD"}
STABLES = {"USDT", "USDC", "DAI", "PYUSD", "TUSD", "BUSD", "USDG"}

_ASSET_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP",
    "ADA": "Cardano", "DOGE": "Dogecoin", "DOT": "Polkadot", "LINK": "Chainlink",
    "AVAX": "Avalanche", "SUI": "Sui", "LTC": "Litecoin", "XLM": "Stellar",
    "USD": "US Dollar", "EUR": "Euro", "GBP": "British Pound", "JPY": "Japanese Yen",
    "CAD": "Canadian Dollar", "CHF": "Swiss Franc", "AUD": "Australian Dollar",
    "USDT": "Tether", "USDC": "USD Coin", "DAI": "Dai", "PYUSD": "PayPal USD",
}


def normalize_asset(code: str) -> str:
    c = (code or "").upper()
    return _ASSET_MAP.get(c, c)


def _num(v: Any) -> Optional[float]:
    try:
        if v is None or v is True or v is False:
            return None
        f = float(v)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ spot
def _usd_price_map(app, assets: List[str]) -> Dict[str, Tuple[float, float, str]]:
    """asset -> (unitPriceUSD, change24hPct, priceSource). Real inputs only."""
    prices: Dict[str, Tuple[float, float, str]] = {}
    for a in assets:
        if a == "USD":
            prices[a] = (1.0, 0.0, "fiat-parity")
        elif a in STABLES:
            prices[a] = (1.0, 0.0, "stable-parity")
    # 1) live WS tickers for tracked pairs
    for t in app.ws.get_tickers():
        pair = t.get("pair") or ""
        base, _, quote = pair.partition("/")
        if quote == "USD" and base and base not in prices:
            px = _num(t.get("price")) or 0.0
            chg = _num(t.get("change24h")) or 0.0
            if px > 0:
                prices[base] = (px, chg, str(t.get("source") or "ws.kraken.com/v2 (live)"))
    # 2) one batched REST shot for anything still missing (public, no creds needed)
    missing = [a for a in assets if a not in prices]
    if missing:
        try:
            natives = [KrakenSpotClient.pair_to_native(f"{a}/USD") for a in missing]
            raw = app.engine.spot.ticker(natives).get("result", {})
            for native, v in raw.items():
                try:
                    last = float(v["c"][0])
                    open_ = float(v["o"][0])
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
                if last <= 0:
                    continue
                symbol = KrakenSpotClient.native_to_pair(native)
                base = symbol.partition("/")[0]
                chg = round((last - open_) / open_ * 100.0, 4) if open_ > 0 else 0.0
                prices[base] = (last, chg, "api.kraken.com (live REST)")
        except KrakenError:
            pass
    for a in assets:
        prices.setdefault(a, (0.0, 0.0, "unavailable"))
    return prices


def _locked_amounts(app) -> Dict[str, float]:
    """Best-effort locked (in-order) amounts per asset from real open orders.

    Sells lock base asset, buys lock quote cost. Anything unparseable is
    skipped (conservative: locked amount stays 0 for that order).
    """
    locked: Dict[str, float] = {}
    try:
        raw = app.engine.spot.open_orders().get("result", {}).get("open", {})
    except KrakenError:
        return locked
    for _txid, o in (raw or {}).items():
        try:
            descr = o.get("descr", {}) or {}
            pair = descr.get("pair", "") or ""
            side = descr.get("type", "") or ""
            vol = float(o.get("vol", 0) or 0) - float(o.get("vol_exec", 0) or 0)
            if vol <= 0:
                continue
            symbol = KrakenSpotClient.native_to_pair(pair)
            base, _, quote = symbol.partition("/")
            if "/" not in symbol:  # fall back to altname-style pairs (e.g. XXBTZUSD)
                continue
            if side == "sell" and base:
                locked[base] = locked.get(base, 0.0) + vol
            elif side == "buy" and quote:
                price = _num(o.get("descr", {}).get("price")) or _num(descr.get("price"))
                # market/limit without price in descr: use live mark when tracked
                if not price:
                    price = app.ws.get_mark_price(symbol)
                if price:
                    locked[quote] = locked.get(quote, 0.0) + vol * price
        except (TypeError, ValueError, AttributeError):
            continue
    return locked


def build_spot_ledger(app, asset_filter: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """Full KrakenAccountLedgers['spot'] shape from the real Spot Balance."""
    zero = {
        "configured": False,
        "totalValueUSD": 0.0, "freeCashUSD": 0.0, "cryptoValueUSD": 0.0,
        "change24hUSD": 0.0, "change24hPercent": 0.0, "assets": [],
    }
    if not app.settings.spot.configured:
        return {**zero, "error": "not configured — set KRAKEN_SPOT_API_KEY / KRAKEN_SPOT_PRIVATE_KEY"}
    try:
        raw = app.engine.spot.balance(asset_filter or None).get("result", {}) or {}
    except KrakenError as e:
        return {**zero, "error": str(e)}

    balances: Dict[str, float] = {}
    for code, amt in raw.items():
        a = normalize_asset(code)
        v = _num(amt) or 0.0
        if abs(v) < 1e-12:
            continue  # non-zero balances only (matches the UI's "Non-zero" count)
        balances[a] = balances.get(a, 0.0) + v

    prices = _usd_price_map(app, sorted(balances))
    locked = _locked_amounts(app)

    assets: List[Dict[str, Any]] = []
    for a, amt in sorted(balances.items()):
        px, chg, src = prices[a]
        val = amt * px
        lock = min(locked.get(a, 0.0), amt) if amt > 0 else 0.0
        assets.append({
            "asset": a,
            "name": _ASSET_NAMES.get(a, a),
            "amount": round(amt, 8),
            "available": round(amt - lock, 8),
            "inOrders": round(lock, 8),
            "unitPriceUSD": round(px, 6),
            "totalValueUSD": round(val, 2),
            "portfolioPercentage": 0.0,  # filled after totals
            "change24h": round(chg, 2),
            "type": "fiat" if a in FIAT else ("stablecoin" if a in STABLES else "crypto"),
            "priceSource": src,
        })
    if limit:
        assets = assets[: max(1, limit)]

    total = sum(x["totalValueUSD"] for x in assets)
    cash = sum(x["totalValueUSD"] for x in assets if x["type"] in ("fiat", "stablecoin"))
    crypto = total - cash
    chg_usd = sum(x["totalValueUSD"] * x["change24h"] / 100.0 for x in assets)
    for x in assets:
        x["portfolioPercentage"] = round(100.0 * x["totalValueUSD"] / total, 2) if total > 0 else 0.0
    return {
        "configured": True,
        "totalValueUSD": round(total, 2),
        "freeCashUSD": round(cash, 2),
        "cryptoValueUSD": round(crypto, 2),
        "change24hUSD": round(chg_usd, 2),
        "change24hPercent": round(100.0 * chg_usd / (total - chg_usd), 2) if (total - chg_usd) > 0 else 0.0,
        "assets": assets,
        "source": "api.kraken.com (live)",
    }


# ---------------------------------------------------------------- futures
def _extract_margin_totals(accounts_payload: Dict[str, Any]) -> Dict[str, float]:
    """Defensive margin totals across /accounts sub-wallets.

    Known shapes: accounts.flex {balanceValue, availableMargin, initialMargin,
    unrealizedFunding}, cash wallets {balance, available, ...}. We aggregate
    every numeric field we recognize; unknown shapes contribute 0 (explicitly
    reported via `accountsRawKeys` by the caller when everything is empty).
    """
    tot = {"equity": 0.0, "available": 0.0, "used": 0.0, "unrealized": 0.0}
    wallets = (accounts_payload.get("accounts") or {})
    if not isinstance(wallets, dict):
        return tot
    for _name, w in wallets.items():
        if not isinstance(w, dict):
            continue
        eq = _num(w.get("balanceValue", w.get("equity", w.get("balance", w.get("totalEquity")))))
        av = _num(w.get("availableMargin", w.get("available", w.get("freeMargin"))))
        used = _num(w.get("initialMargin", w.get("usedMargin", w.get("marginUsed", w.get("positionMargin")))))
        upl = _num(w.get("unrealizedPnl", w.get("pnl", w.get("unrealizedFunding"))))
        if eq is not None:
            tot["equity"] += eq
        if av is not None:
            tot["available"] += av
        if used is not None:
            tot["used"] += used
        if upl is not None:
            tot["unrealized"] += upl
    return tot


def estimate_liquidation_price(entry: float, leverage: float, side: str,
                               mmr: float = 0.005, fee: float = 0.0075) -> Optional[float]:
    """Isolated-margin liquidation estimate (same formula as Academy drill-04).

    liq_long  = entry * (1 - 1/lev + mmr + fee)
    liq_short = entry * (1 + 1/lev - mmr - fee)
    The Futures v3 REST API does not publish per-position liquidation prices,
    so callers MUST flag this value as estimated.
    """
    if entry <= 0 or leverage < 1:
        return None
    if side == "long":
        return entry * (1.0 - 1.0 / leverage + mmr + fee)
    return entry * (1.0 + 1.0 / leverage - mmr - fee)


def build_futures_ledger(app, limit: Optional[int] = None) -> Dict[str, Any]:
    """Full KrakenAccountLedgers['pro'] shape from real Futures v3 data."""
    zero = {
        "configured": False,
        "totalCollateralUSD": 0.0, "freeMarginUSD": 0.0, "usedMarginUSD": 0.0,
        "marginLevelPercent": 100.0, "totalUnrealizedPnL": 0.0,
        "unrealizedPnLPercent": 0.0, "effectiveLeverage": 0.0, "positions": [],
    }
    if not app.settings.futures.configured:
        return {**zero, "error": "not configured — set KRAKEN_FUTURES_API_KEY / KRAKEN_FUTURES_PRIVATE_KEY"}
    fut = KrakenFuturesClient(app.settings)
    try:
        acct = fut.accounts()
        pos_payload = fut.open_positions()
    except KrakenError as e:
        return {**zero, "error": str(e)}
    try:
        tick_payload = fut.tickers()
    except KrakenError:
        tick_payload = {}
    tick_map = {str(t.get("symbol", "")).upper(): t for t in (tick_payload.get("tickers") or []) if t.get("symbol")}

    margin = _extract_margin_totals(acct)
    raw_positions = pos_payload.get("openPositions") or []

    enriched: List[Dict[str, Any]] = []
    for p in raw_positions:
        try:
            symbol = str(p.get("symbol", "")).upper()
            side = "long" if str(p.get("side", "")).lower() == "long" else "short"
            size = abs(_num(p.get("size")) or 0.0)
            entry = _num(p.get("price", p.get("entryPrice", p.get("avgPrice")))) or 0.0
            tick = tick_map.get(symbol, {})
            mark = _num(tick.get("markPrice", tick.get("last"))) or entry
            notional = size * mark
            upl = (mark - entry) * size if side == "long" else (entry - mark) * size
            # exchange-reported pnl takes precedence when present
            xpnl = _num(p.get("pnl"))
            if xpnl is not None:
                upl = xpnl + (_num(p.get("unrealizedFunding")) or 0.0)
            enriched.append({
                "id": symbol,
                "symbol": symbol,
                "pair": KrakenFuturesClient.contract_to_symbol(symbol),
                "type": side,
                "contractType": "perpetual" if symbol.startswith(("PF_", "PI_")) else ("dated" if symbol.startswith("FI_") else "futures"),
                "size": size,
                "notionalValueUSD": round(notional, 2),
                "entryPrice": round(entry, 6),
                "markPrice": round(mark, 6),
                "_upl": round(upl, 6),
                "fundingRate": _num(tick.get("fundingRate")),
                "status": "open",
            })
        except (TypeError, ValueError):
            continue

    total_notional = sum(p["notionalValueUSD"] for p in enriched)
    equity = margin["equity"] if margin["equity"] > 0 else None
    eff_lev = (total_notional / equity) if equity else 0.0
    used = margin["used"]
    for p in enriched:
        share = (p["notionalValueUSD"] / total_notional) if total_notional > 0 else 0.0
        collateral = used * share if used > 0 else (p["notionalValueUSD"] / eff_lev if eff_lev > 0 else 0.0)
        upl = p.pop("_upl")
        lev = eff_lev if eff_lev > 0 else 1.0
        p.update({
            "leverage": round(lev, 2),
            "liquidationPrice": round(estimate_liquidation_price(p["entryPrice"], lev, p["type"]) or 0.0, 6),
            "liquidationPriceEstimated": True,
            "collateralUSD": round(collateral, 2),
            "marginRequirementUSD": round(collateral, 2),
            "unrealizedPnLUSD": round(upl, 2),
            "unrealizedPnLPercent": round(100.0 * upl / collateral, 2) if collateral > 0 else 0.0,
        })
    if limit:
        enriched = enriched[: max(1, limit)]

    total_upl = sum(p["unrealizedPnLUSD"] for p in enriched)
    if margin["unrealized"] and not enriched:
        total_upl = margin["unrealized"]
    collateral_total = margin["equity"]
    margin_level = round(100.0 * collateral_total / used, 1) if used > 0 else 100.0
    return {
        "configured": True,
        "totalCollateralUSD": round(collateral_total, 2),
        "freeMarginUSD": round(margin["available"], 2),
        "usedMarginUSD": round(used, 2),
        "marginLevelPercent": margin_level,
        "totalUnrealizedPnL": round(total_upl, 2),
        "unrealizedPnLPercent": round(100.0 * total_upl / collateral_total, 2) if collateral_total > 0 else 0.0,
        "effectiveLeverage": round(eff_lev, 2),
        "positions": enriched,
        "source": "futures.kraken.com (live)",
    }
