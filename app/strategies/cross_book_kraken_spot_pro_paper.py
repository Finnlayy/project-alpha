"""
CROSS_BOOK_KRAKEN_SPOT_PRO_PAPER — paper cross of Kraken spot vs Kraken futures.

Trace: alpha-p2-20261002-1209

The symbol is an instance parameter. This module does not bind a symbol.
Executable top of book only: buy the cheaper ask, sell the richer bid.
Entry requires the gross gap to exceed the paper fee hurdle
0.0026 (spot) + 0.0005 (futures) = 0.0031.
Live create is refused. No live order is sent from this module.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.kraken.spot_client import KrakenSpotClient
from app.strategies.base import Strategy, StrategyContextView

STRATEGY_NAME = "CROSS_BOOK_KRAKEN_SPOT_PRO_PAPER"
TRACE_ID = "alpha-p2-20261002-1209"

# Paper rates verified by Finn 2026-10-02. Do not substitute 0.0002.
SPOT_PAPER_FEE_RATE = Decimal("0.0026")
FUTURES_PAPER_FEE_RATE = Decimal("0.0005")
FEE_HURDLE = SPOT_PAPER_FEE_RATE + FUTURES_PAPER_FEE_RATE


class LiveCreateRefused(ValueError):
    """The create path was asked for a mode other than paper."""


class CrossBookStateError(RuntimeError):
    """Persisted cross-book state cannot be traded safely."""


@dataclass(frozen=True)
class ExecutableTop:
    bid: Decimal
    bid_size: Decimal
    ask: Decimal
    ask_size: Decimal


@dataclass(frozen=True)
class CrossDecision:
    enter: bool
    reason: str
    spot_side: Optional[str] = None
    futures_side: Optional[str] = None
    spot_price: Optional[Decimal] = None
    futures_price: Optional[Decimal] = None
    base_qty: Optional[Decimal] = None
    futures_contracts: Optional[Decimal] = None
    gross_gap: Optional[Decimal] = None
    contract_size: Optional[Decimal] = None

    def as_signal(self) -> Dict[str, Any]:
        return {
            "enter": self.enter,
            "reason": self.reason,
            "spot_side": self.spot_side,
            "futures_side": self.futures_side,
            "spot_price": _canon(self.spot_price) if self.spot_price is not None else None,
            "futures_price": _canon(self.futures_price) if self.futures_price is not None else None,
            "base_qty": _canon(self.base_qty) if self.base_qty is not None else None,
            "futures_contracts": _canon(self.futures_contracts) if self.futures_contracts is not None else None,
            "gross_gap": _canon(self.gross_gap) if self.gross_gap is not None else None,
            "fee_hurdle": _canon(FEE_HURDLE),
            "spot_fee_rate": _canon(SPOT_PAPER_FEE_RATE),
            "futures_fee_rate": _canon(FUTURES_PAPER_FEE_RATE),
        }


def normalize_symbol(symbol: str) -> str:
    """BASE/QUOTE. Alphanumeric only so the value never reaches a shell unsanitized."""
    raw = (symbol or "").strip().upper()
    base, sep, quote = raw.partition("/")
    if sep != "/" or not base or not quote or "/" in quote:
        raise ValueError("symbol must be BASE/QUOTE")
    if not base.isalnum() or not quote.isalnum():
        raise ValueError("symbol must be alphanumeric BASE/QUOTE")
    return f"{base}/{quote}"


def _canon(value: Decimal) -> str:
    return format(value, "f")


def _positive_decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        number = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            number = Decimal(text)
        except Exception:
            return None
    if not number.is_finite() or number <= 0:
        return None
    return number


def _level_price_size(level: Any) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    if isinstance(level, (list, tuple)) and len(level) >= 2:
        return _positive_decimal(level[0]), _positive_decimal(level[1])
    if isinstance(level, dict):
        price = level.get("price", level.get("px"))
        size = level.get("qty", level.get("size", level.get("volume")))
        return _positive_decimal(price), _positive_decimal(size)
    return None, None


def executable_top(levels: Any) -> Optional[Tuple[Decimal, Decimal]]:
    """Best price with a positive size. Zero-size placeholders are not executable."""
    if not isinstance(levels, list):
        return None
    for level in levels:
        price, size = _level_price_size(level)
        if price is not None and size is not None:
            return price, size
    return None


def _book_from_levels(bids: Any, asks: Any) -> Optional[ExecutableTop]:
    bid = executable_top(bids)
    ask = executable_top(asks)
    if bid is None or ask is None:
        return None
    if bid[0] >= ask[0]:
        return None
    return ExecutableTop(bid=bid[0], bid_size=bid[1], ask=ask[0], ask_size=ask[1])


def spot_book_from_depth(payload: Any, native_pair: str) -> Optional[ExecutableTop]:
    """Parse a Kraken Spot Depth payload down to the executable top."""
    if not isinstance(payload, dict):
        return None
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    if not isinstance(result, dict):
        return None
    wanted = KrakenSpotClient.native_to_pair(native_pair)
    matched: List[Dict[str, Any]] = []
    for key, value in result.items():
        if key == "last" or not isinstance(value, dict):
            continue
        if "bids" not in value and "asks" not in value:
            continue
        key_text = str(key)
        if key_text == native_pair or KrakenSpotClient.native_to_pair(key_text) == wanted:
            matched.append(value)
    if len(matched) != 1:
        return None
    book = matched[0]
    return _book_from_levels(book.get("bids"), book.get("asks"))


def futures_book_from_orderbook(payload: Any, contract: str) -> Optional[ExecutableTop]:
    """Parse a Kraken Futures v3 orderbook payload down to the executable top."""
    if not isinstance(payload, dict):
        return None
    book = payload.get("orderBook") if isinstance(payload.get("orderBook"), dict) else None
    if book is None and ("bids" in payload or "asks" in payload):
        book = payload
    if not isinstance(book, dict):
        return None
    declared = payload.get("symbol") or book.get("symbol")
    if declared is not None and str(declared).upper() != contract.upper():
        return None
    return _book_from_levels(book.get("bids"), book.get("asks"))


def contract_size_from_instruments(payload: Any, contract: str) -> Optional[Decimal]:
    """Read contractSize for one futures symbol. Missing or ambiguous → None."""
    if not isinstance(payload, dict):
        return None
    rows = payload.get("instruments")
    if not isinstance(rows, list):
        return None
    matches = [
        row for row in rows
        if isinstance(row, dict) and str(row.get("symbol", "")).upper() == contract.upper()
    ]
    if len(matches) != 1:
        return None
    return _positive_decimal(matches[0].get("contractSize"))


def _full_fill_qty(
    spot_size: Decimal,
    futures_size: Decimal,
    contract_size: Decimal,
) -> Optional[Tuple[Decimal, Decimal]]:
    """Base quantity both executable tops can fill in full, and the futures contracts.

    The quantity is the intersection of the two tops. It is not a budget and it
    is not resized after a partial fill.
    """
    if contract_size <= 0 or spot_size <= 0 or futures_size <= 0:
        return None
    futures_base = futures_size * contract_size
    base_qty = spot_size if spot_size <= futures_base else futures_base
    if base_qty <= 0:
        return None
    contracts = base_qty / contract_size
    if contracts <= 0 or contracts > futures_size or base_qty > spot_size:
        return None
    return base_qty, contracts


def evaluate_cross(
    spot: ExecutableTop,
    futures: ExecutableTop,
    contract_size: Optional[Decimal],
) -> CrossDecision:
    """Buy the cheaper ask and sell the richer bid, or refuse."""
    if contract_size is None or contract_size <= 0:
        return CrossDecision(False, "futures contractSize unavailable; entry refused")

    candidates: List[CrossDecision] = []

    if futures.bid > spot.ask:
        gap = (futures.bid - spot.ask) / spot.ask
        if gap > FEE_HURDLE:
            filled = _full_fill_qty(spot.ask_size, futures.bid_size, contract_size)
            if filled is None:
                return CrossDecision(False, "spot ask or futures bid cannot paper-fill; neither leg opened")
            base_qty, contracts = filled
            candidates.append(
                CrossDecision(
                    True,
                    "buy spot ask, sell futures bid",
                    spot_side="buy",
                    futures_side="sell",
                    spot_price=spot.ask,
                    futures_price=futures.bid,
                    base_qty=base_qty,
                    futures_contracts=contracts,
                    gross_gap=gap,
                    contract_size=contract_size,
                )
            )

    if spot.bid > futures.ask:
        gap = (spot.bid - futures.ask) / futures.ask
        if gap > FEE_HURDLE:
            filled = _full_fill_qty(spot.bid_size, futures.ask_size, contract_size)
            if filled is None:
                return CrossDecision(False, "futures ask or spot bid cannot paper-fill; neither leg opened")
            base_qty, contracts = filled
            candidates.append(
                CrossDecision(
                    True,
                    "sell spot bid, buy futures ask",
                    spot_side="sell",
                    futures_side="buy",
                    spot_price=spot.bid,
                    futures_price=futures.ask,
                    base_qty=base_qty,
                    futures_contracts=contracts,
                    gross_gap=gap,
                    contract_size=contract_size,
                )
            )

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return CrossDecision(False, "both cross directions executable; entry refused")
    return CrossDecision(False, "gross gap does not exceed fee hurdle 0.0031")


def leg_fee(price: Decimal, qty: Decimal, rate: Decimal) -> Decimal:
    return price * qty * rate


def leg_pnl(side: str, entry: Decimal, exit_price: Decimal, qty: Decimal) -> Decimal:
    if side == "buy":
        return (exit_price - entry) * qty
    if side == "sell":
        return (entry - exit_price) * qty
    raise CrossBookStateError(f"unhandled side {side!r}")


def effect_sha256(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def open_effect_payload(
    symbol: str,
    instance_id: str,
    decision: CrossDecision,
    contract: str,
) -> Dict[str, str]:
    if not decision.enter or decision.spot_price is None or decision.futures_price is None:
        raise CrossBookStateError("open effect requires an entry decision")
    if decision.base_qty is None or decision.futures_contracts is None or decision.contract_size is None:
        raise CrossBookStateError("open effect requires a full-fill quantity")
    if decision.gross_gap is None or decision.spot_side is None or decision.futures_side is None:
        raise CrossBookStateError("open effect requires sides and gross gap")
    return {
        "action": "open",
        "base_qty": _canon(decision.base_qty),
        "contract": contract,
        "contract_size": _canon(decision.contract_size),
        "futures_contracts": _canon(decision.futures_contracts),
        "futures_fee_rate": _canon(FUTURES_PAPER_FEE_RATE),
        "futures_price": _canon(decision.futures_price),
        "futures_side": decision.futures_side,
        "gross_gap": _canon(decision.gross_gap),
        "instance_id": instance_id,
        "spot_fee_rate": _canon(SPOT_PAPER_FEE_RATE),
        "spot_price": _canon(decision.spot_price),
        "spot_side": decision.spot_side,
        "strategy": STRATEGY_NAME,
        "symbol": symbol,
        "trace": TRACE_ID,
    }


def flatten_effect_payload(
    open_payload: Dict[str, str],
    open_hash: str,
    spot_exit_side: str,
    spot_exit_price: Decimal,
    futures_exit_side: str,
    futures_exit_price: Decimal,
) -> Dict[str, str]:
    return {
        "action": "flatten",
        "base_qty": open_payload["base_qty"],
        "contract": open_payload["contract"],
        "contract_size": open_payload["contract_size"],
        "futures_contracts": open_payload["futures_contracts"],
        "futures_exit_price": _canon(futures_exit_price),
        "futures_exit_side": futures_exit_side,
        "futures_fee_rate": open_payload["futures_fee_rate"],
        "instance_id": open_payload["instance_id"],
        "opens_effect_hash": open_hash,
        "spot_exit_price": _canon(spot_exit_price),
        "spot_exit_side": spot_exit_side,
        "spot_fee_rate": open_payload["spot_fee_rate"],
        "strategy": STRATEGY_NAME,
        "symbol": open_payload["symbol"],
        "trace": TRACE_ID,
    }


def _require_decimal(payload: Dict[str, Any], key: str) -> Decimal:
    number = _positive_decimal(payload.get(key))
    if number is None:
        raise CrossBookStateError(f"open effect missing {key}")
    return number


def position_from_open_payload(payload: Dict[str, Any], effect_hash: str) -> Dict[str, Any]:
    if payload.get("action") != "open" or payload.get("strategy") != STRATEGY_NAME:
        raise CrossBookStateError("open effect payload is not a cross-book open")
    spot_side = payload.get("spot_side")
    futures_side = payload.get("futures_side")
    if spot_side not in ("buy", "sell") or futures_side not in ("buy", "sell"):
        raise CrossBookStateError("open effect has an unhandled side")
    if spot_side == futures_side:
        raise CrossBookStateError("open effect sides are not a cross")
    spot_price = _require_decimal(payload, "spot_price")
    futures_price = _require_decimal(payload, "futures_price")
    base_qty = _require_decimal(payload, "base_qty")
    contracts = _require_decimal(payload, "futures_contracts")
    contract_size = _require_decimal(payload, "contract_size")
    spot_rate = _positive_decimal(payload.get("spot_fee_rate"))
    futures_rate = _positive_decimal(payload.get("futures_fee_rate"))
    if spot_rate != SPOT_PAPER_FEE_RATE or futures_rate != FUTURES_PAPER_FEE_RATE:
        raise CrossBookStateError("open effect fee rates are not the verified paper rates")
    entry_fee = leg_fee(spot_price, base_qty, SPOT_PAPER_FEE_RATE) + leg_fee(
        futures_price, base_qty, FUTURES_PAPER_FEE_RATE
    )
    return {
        "id": effect_hash,
        "kind": "cross_book",
        "side": "long" if spot_side == "buy" else "short",
        "entry_price": float(spot_price),
        "amount": float(base_qty),
        "notional_usd": float(spot_price * base_qty + futures_price * base_qty),
        "effect_hash": effect_hash,
        "open_payload": {k: str(v) for k, v in payload.items()},
        "spot_side": spot_side,
        "futures_side": futures_side,
        "spot_entry": spot_price,
        "futures_entry": futures_price,
        "base_qty": base_qty,
        "futures_contracts": contracts,
        "contract_size": contract_size,
        "contract": str(payload.get("contract") or ""),
        "entry_fee": entry_fee,
        "symbol": str(payload.get("symbol") or ""),
    }


def opposite_side(side: str) -> str:
    if side == "buy":
        return "sell"
    if side == "sell":
        return "buy"
    raise CrossBookStateError(f"unhandled side {side!r}")


def flatten_quotes(
    position: Dict[str, Any],
    spot: ExecutableTop,
    futures: ExecutableTop,
) -> Optional[Dict[str, Any]]:
    """Opposite executable tops that can fill the original quantity in full.

    A thinner top is not a partial fill and is not compensated. Both legs stay open.
    """
    spot_side = position.get("spot_side")
    futures_side = position.get("futures_side")
    base_qty = position.get("base_qty")
    contracts = position.get("futures_contracts")
    if not isinstance(base_qty, Decimal) or not isinstance(contracts, Decimal):
        return None
    if spot_side == "buy" and futures_side == "sell":
        spot_exit_side, spot_price, spot_size = "sell", spot.bid, spot.bid_size
        futures_exit_side, futures_price, futures_size = "buy", futures.ask, futures.ask_size
    elif spot_side == "sell" and futures_side == "buy":
        spot_exit_side, spot_price, spot_size = "buy", spot.ask, spot.ask_size
        futures_exit_side, futures_price, futures_size = "sell", futures.bid, futures.bid_size
    else:
        raise CrossBookStateError("open cross sides cannot be flattened")
    if spot_size < base_qty or futures_size < contracts:
        return None
    return {
        "spot_exit_side": spot_exit_side,
        "spot_exit_price": spot_price,
        "futures_exit_side": futures_exit_side,
        "futures_exit_price": futures_price,
    }


class CROSS_BOOK_KRAKEN_SPOT_PRO_PAPER(Strategy):
    """Paper-only cross of Kraken spot and Kraken futures executable tops.

    Candle `on_bar` does not trade. The paper worker reads the books.
    """

    name = STRATEGY_NAME
    description = (
        "Paper-only Kraken spot vs Kraken futures (PF) cross. "
        "Buy the cheaper executable ask, sell the richer executable bid. "
        "Gross gap must exceed 0.0026 + 0.0005. Symbol is an instance parameter. "
        f"Trace {TRACE_ID}."
    )
    param_space: Dict[str, tuple] = {}
    min_bars = 0
    paper_only = True
    book_worker = True

    def on_bar(self, ctx: StrategyContextView, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "target": 0.0,
            "reason": "CROSS_BOOK_KRAKEN_SPOT_PRO_PAPER trades executable books, not candles",
        }

    def code_listing(self, params: Dict[str, Any]) -> str:
        return "\n".join(
            [
                f"// {self.name}",
                f"// trace {TRACE_ID}",
                "// symbol: instance parameter (not a module constant)",
                "// books: Kraken spot Depth vs Kraken futures orderbook (PF_)",
                "// executable top of book only",
                "// buy the cheaper ask, sell the richer bid",
                "// enter only when (rich_bid - cheap_ask) / cheap_ask > 0.0026 + 0.0005",
                "// paper-fill both legs or neither",
                "// live create refused; no live order",
                f"// params ignored for sizing: {sorted(params)}",
            ]
        )
