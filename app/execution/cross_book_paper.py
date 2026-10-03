"""
Paper worker for CROSS_BOOK_KRAKEN_SPOT_PRO_PAPER.

One worker per symbol. The symbol is a parameter. This module names no pair.

Open both legs for the full shared quantity, or open neither leg.
Flatten only when the open gap is at or under 0.0031. If that gap is still
wider, neither leg closes. When both opposite tops can fill the full open
quantity, paper-close that full quantity on both legs. The half cap does not
limit a full close. Otherwise paper-close the same shortfall on both legs:
the lesser top, capped at half the open quantity. A zero shortfall, or missing
quotes, closes neither leg. No lot step is invented.

Order effects are SHA-256 deduped. Live create is refused. This module never
places a live order. Paper fills stay inside the paper book.

Paper learning ledger, trace alpha-paper-ledger-20261003. The append-only
file is data/memory/paper_learning.jsonl from the repository root. On Finn's
machine that same file is
/home/finn-powers/project-alpha/data/memory/paper_learning.jsonl.
One JSON object is written per line only after a cross paper flatten newly
commits and the in-memory position for that close is cleared. A partial
close counts: that position is cleared before a residual open is restored.
The line has seven keys. "what worked" is "paper flatten committed".
"what failed", "root cause", "strategy update", and "human feedback" are
empty strings. "confidence before" and "confidence after" are null. The
line has no fill id, clock, worker id, symbol, or price, and it is not
applied as a strategy update. A failed append leaves the paper fill in
place and leaves the flatten result unchanged. data/memory is created on
the first append. At the start of a tick, a non-empty ledger is read for
its last line. That line is not used to place an order, to change a gap
check, or to apply a strategy update. A missing, empty, or unreadable
ledger does not stop the tick. An open, a tick, a refused flatten, a
duplicate effect that did not newly commit, and stop_instance do not
append a line.
"""
from __future__ import annotations

import inspect
import json
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from app.kraken.futures_client import KrakenFuturesClient
from app.kraken.spot_client import KrakenError, KrakenSpotClient
from app.strategies.cross_book_kraken_spot_pro_paper import (
    FEE_HURDLE,
    FUTURES_PAPER_FEE_RATE,
    SPOT_PAPER_FEE_RATE,
    STRATEGY_NAME,
    TRACE_ID,
    CrossBookStateError,
    ExecutableTop,
    LiveCreateRefused,
    contract_size_from_instruments,
    effect_sha256,
    evaluate_cross,
    flatten_effect_payload,
    flatten_quotes,
    futures_book_from_orderbook,
    leg_fee,
    leg_pnl,
    normalize_symbol,
    open_effect_payload,
    open_gross_gap,
    opposite_side,
    position_from_open_payload,
    spot_book_from_depth,
)

_LIVE_REFUSED = "CROSS_BOOK_KRAKEN_SPOT_PRO_PAPER refuses live create"
_PAPER_LEARNING_LOCK = threading.Lock()


def paper_learning_path() -> Path:
    """Ledger path from the repository root: data/memory/paper_learning.jsonl."""
    return Path(__file__).resolve().parents[2] / "data" / "memory" / "paper_learning.jsonl"


def _committed_flatten_learning_record() -> Dict[str, Any]:
    return {
        "what worked": "paper flatten committed",
        "what failed": "",
        "root cause": "",
        "strategy update": "",
        "human feedback": "",
        "confidence before": None,
        "confidence after": None,
    }


def _called_from_stop_instance() -> bool:
    """A flatten requested by stop_instance does not append a learning line."""
    frame = inspect.currentframe()
    try:
        while frame is not None:
            if frame.f_code.co_name == "stop_instance":
                return True
            frame = frame.f_back
        return False
    finally:
        del frame


def _append_paper_learning_line() -> None:
    path = paper_learning_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        _committed_flatten_learning_record(),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    with _PAPER_LEARNING_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()


def _record_committed_paper_flatten() -> None:
    """Append one learning line. A failure leaves the committed fill alone."""
    try:
        if _called_from_stop_instance():
            return
        _append_paper_learning_line()
    except Exception:
        return


def _last_nonempty_line(text: str) -> Optional[str]:
    last: Optional[str] = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            last = stripped
    return last


def _read_last_paper_learning_line() -> None:
    """Read the last ledger line and do not feed it into trading."""
    try:
        path = paper_learning_path()
        if not path.is_file():
            return
        with _PAPER_LEARNING_LOCK:
            text = path.read_text(encoding="utf-8")
        last = _last_nonempty_line(text)
        if last is None:
            return
        _ = json.loads(last)
    except Exception:
        return


def futures_client(engine: Any) -> Any:
    cached = getattr(engine, "_futures", None)
    if cached is None:
        cached = KrakenFuturesClient(engine.settings)
        engine._futures = cached
    return cached


def _contract_cache(engine: Any) -> Dict[str, Decimal]:
    cache = getattr(engine, "_cross_book_contract_sizes", None)
    if cache is None:
        cache = {}
        engine._cross_book_contract_sizes = cache
    return cache


def start_cross_book_paper(
    engine: Any,
    name: str,
    symbol: str,
    interval_min: int,
    params: Dict[str, Any],
    mode: Optional[str],
    genome_source: str,
    initial_balance: Optional[float],
) -> Dict[str, Any]:
    resolved = (mode or engine.settings.execution_mode or "").strip().lower()
    if resolved != "paper":
        raise LiveCreateRefused(_LIVE_REFUSED)
    try:
        canonical = normalize_symbol(symbol)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    with engine._lock:
        try:
            existing = _find_worker(engine, canonical)
        except RuntimeError as exc:
            raise CrossBookStateError(str(exc)) from exc
        if existing is not None:
            return _ensure_runtime(engine, existing)
        return engine._commit_new_instance(
            strategy_type=STRATEGY_NAME,
            name=name or f"{STRATEGY_NAME} on {canonical}",
            symbol=canonical,
            interval_min=interval_min,
            params=dict(params or {}),
            mode="paper",
            genome_source=genome_source,
            initial_balance=initial_balance,
            description=f"{STRATEGY_NAME} trace={TRACE_ID} symbol={canonical} paper-only",
        )


def _find_worker(engine: Any, symbol: str) -> Optional[Dict[str, Any]]:
    for row in engine.lake.list_instances(include_stopped=True):
        if row.get("strategy_type") != STRATEGY_NAME or row.get("symbol") != symbol:
            continue
        if row.get("status") in ("active", "paused"):
            return row
    open_effect = engine.lake.unflattened_cross_open(symbol)
    if open_effect is None:
        return None
    row = engine.lake.get_instance(open_effect["instance_id"])
    if row is None:
        raise CrossBookStateError(
            f"unflattened paper cross for {symbol} has no instance; refusing to start another"
        )
    return row


def _ensure_runtime(engine: Any, row: Dict[str, Any]) -> Dict[str, Any]:
    if row.get("mode") != "paper":
        raise LiveCreateRefused(_LIVE_REFUSED)
    if row.get("status") == "stopped":
        engine.lake.set_instance_status(row["id"], "active", None)
        row = engine.lake.get_instance(row["id"]) or row
        row["status"] = "active"
    if row.get("status") == "paused":
        return row
    rt = engine.instances.get(row["id"])
    if rt is None:
        rt = engine._restore_instance(row)
    else:
        rt.spec["status"] = "active"
        engine._start_loop(rt)
    _restore_open_position(engine, rt)
    return engine.lake.get_instance(row["id"]) or row


def _position_from_open_effect(open_effect: Dict[str, Any]) -> Dict[str, Any]:
    remaining_text = open_effect.get("remaining_base_qty")
    remaining = Decimal(str(remaining_text)) if remaining_text not in (None, "") else None
    position = position_from_open_payload(open_effect["payload"], open_effect["effect_hash"], remaining)
    position["entry_epoch_ms"] = int(open_effect.get("created_at") or 0)
    return position


def _restore_open_position(engine: Any, rt: Any) -> None:
    if rt.position is not None:
        return
    open_effect = engine.lake.unflattened_cross_open(rt.spec["symbol"])
    if open_effect is None:
        return
    if open_effect["instance_id"] != rt.spec["id"]:
        raise CrossBookStateError("unflattened paper cross belongs to another instance")
    rt.position = _position_from_open_effect(open_effect)


def tick_cross_book(engine: Any, rt: Any) -> None:
    """Read both books and paper-open a cross, or leave both legs untouched.

    The last paper-learning line is read first when the ledger exists.
    That line does not place an order, change a gap check, or update a strategy.
    """
    _read_last_paper_learning_line()
    spec = rt.spec
    if spec.get("mode") != "paper" or spec.get("strategy_type") != STRATEGY_NAME:
        rt.waiting = True
        rt.last_error = _LIVE_REFUSED
        engine._stop_loop(rt)
        return
    try:
        _restore_open_position(engine, rt)
    except CrossBookStateError as exc:
        rt.waiting = True
        rt.last_error = str(exc)
        return
    if rt.position is not None:
        rt.waiting = False
        rt.last_tick = time.time()
        rt.last_error = None
        return

    try:
        symbol = normalize_symbol(spec.get("symbol") or "")
    except ValueError as exc:
        rt.waiting = True
        rt.last_error = str(exc)
        return

    spot_native = KrakenSpotClient.pair_to_native(symbol)
    contract = KrakenFuturesClient.symbol_to_contract(symbol)
    try:
        spot_payload = engine.spot.depth(spot_native, count=10)
    except KrakenError as exc:
        rt.waiting = True
        rt.last_error = f"spot book unavailable: {exc}"
        return
    try:
        futures_payload = futures_client(engine).orderbook(contract)
    except KrakenError as exc:
        rt.waiting = True
        rt.last_error = f"futures book unavailable: {exc}"
        return

    spot_book = spot_book_from_depth(spot_payload, spot_native)
    futures_book = futures_book_from_orderbook(futures_payload, contract)
    if spot_book is None or futures_book is None:
        rt.waiting = True
        rt.last_error = "executable top of book missing; neither leg opened"
        rt.last_signal = {"enter": False, "reason": rt.last_error, "fee_hurdle": format(FEE_HURDLE, "f")}
        return

    rt.waiting = False
    rt.last_tick = time.time()
    rt.last_mark = float(spot_book.bid)

    contract_size = _contract_size(engine, contract)
    if contract_size is None:
        rt.last_error = "futures contractSize unavailable; entry refused"
        rt.last_signal = {"enter": False, "reason": rt.last_error}
        return

    decision = evaluate_cross(spot_book, futures_book, contract_size)
    rt.last_signal = decision.as_signal()
    if not decision.enter:
        rt.last_error = decision.reason
        return

    _paper_open(engine, rt, symbol, contract, decision)


def _contract_size(engine: Any, contract: str) -> Optional[Decimal]:
    cache = _contract_cache(engine)
    cached = cache.get(contract)
    if cached is not None:
        return cached
    try:
        payload = futures_client(engine).instruments()
    except KrakenError:
        return None
    size = contract_size_from_instruments(payload, contract)
    if size is None:
        return None
    cache[contract] = size
    return size


def _paper_open(engine: Any, rt: Any, symbol: str, contract: str, decision: Any) -> None:
    payload = open_effect_payload(symbol, rt.spec["id"], decision, contract)
    effect_hash = effect_sha256(payload)
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    claimed = engine.lake.claim_effect(effect_hash, rt.spec["id"], symbol, "open", payload_json)
    if not claimed:
        existing = engine.lake.unflattened_cross_open(symbol)
        if existing is not None and existing["effect_hash"] == effect_hash:
            rt.position = _position_from_open_effect(existing)
            rt.last_error = None
            return
        rt.last_error = "duplicate paper open refused"
        return
    rt.position = position_from_open_payload(payload, effect_hash)
    rt.position["entry_epoch_ms"] = int(time.time() * 1000)
    rt.last_error = None
    engine.bus.emit(
        "trade",
        "CrossBookPaper",
        (
            f"OPEN CROSS {symbol} spot {decision.spot_side} @ {payload['spot_price']} "
            f"futures {decision.futures_side} @ {payload['futures_price']} "
            f"qty={payload['base_qty']} gap={payload['gross_gap']} "
            f"fees={payload['spot_fee_rate']}+{payload['futures_fee_rate']} "
            f"effect={effect_hash} trace={TRACE_ID}"
        ),
        rt.spec["id"],
    )


def flatten_cross_book(engine: Any, rt: Any, reason: str) -> None:
    """Paper-close both legs, or close neither.

    A full close runs when both opposite tops can fill the open quantity.
    A shortfall close runs the same quantity on both legs, at most half the
    open quantity. The open gap must be at or under 0.0031.
    """
    position = rt.position
    if not position or position.get("kind") != "cross_book":
        return
    if rt.spec.get("mode") != "paper":
        rt.last_error = _LIVE_REFUSED
        return
    symbol = position.get("symbol") or rt.spec.get("symbol") or ""
    try:
        symbol = normalize_symbol(symbol)
    except ValueError as exc:
        rt.last_error = str(exc)
        return
    contract = position.get("contract") or KrakenFuturesClient.symbol_to_contract(symbol)
    spot_native = KrakenSpotClient.pair_to_native(symbol)
    try:
        spot_payload = engine.spot.depth(spot_native, count=10)
        futures_payload = futures_client(engine).orderbook(contract)
    except KrakenError as exc:
        rt.last_error = f"flatten refused; book unavailable: {exc}"
        return
    spot_book = spot_book_from_depth(spot_payload, spot_native)
    futures_book = futures_book_from_orderbook(futures_payload, contract)
    if spot_book is None or futures_book is None:
        rt.last_error = "flatten refused; executable top missing; neither leg closed"
        return
    try:
        gap = open_gross_gap(position, spot_book, futures_book)
    except CrossBookStateError as exc:
        rt.last_error = str(exc)
        return
    if gap is None:
        rt.last_error = "flatten refused; open gap unavailable; neither leg closed"
        return
    if gap > FEE_HURDLE:
        rt.last_error = "flatten refused; open gap still exceeds 0.0031; neither leg closed"
        return
    try:
        quotes = flatten_quotes(position, spot_book, futures_book)
    except CrossBookStateError as exc:
        rt.last_error = str(exc)
        return
    if quotes is None:
        rt.last_error = "flatten refused; shortfall quantity is zero; neither leg closed"
        return
    refusal = _close_refusal(position, quotes)
    if refusal is not None:
        rt.last_error = refusal
        return
    _commit_flatten(engine, rt, position, quotes, reason, spot_book, futures_book)


def _close_refusal(position: Dict[str, Any], quotes: Dict[str, Any]) -> Optional[str]:
    """Refuse a close that would touch one leg, exceed the open, or exceed the half cap."""
    closed = quotes.get("base_qty")
    closed_contracts = quotes.get("futures_contracts")
    open_qty = position.get("base_qty")
    open_contracts = position.get("futures_contracts")
    contract_size = position.get("contract_size")
    if (
        not isinstance(closed, Decimal)
        or not isinstance(closed_contracts, Decimal)
        or not isinstance(open_qty, Decimal)
        or not isinstance(open_contracts, Decimal)
        or not isinstance(contract_size, Decimal)
    ):
        return "flatten refused; shortfall quantity is zero; neither leg closed"
    if closed <= 0 or closed_contracts <= 0 or closed > open_qty or closed_contracts > open_contracts:
        return "flatten refused; shortfall quantity is zero; neither leg closed"
    if closed_contracts * contract_size != closed:
        return "flatten refused; legs would close different quantities; neither leg closed"
    spot_exit = quotes.get("spot_exit_side")
    futures_exit = quotes.get("futures_exit_side")
    try:
        spot_ok = spot_exit == opposite_side(str(position.get("spot_side")))
        futures_ok = futures_exit == opposite_side(str(position.get("futures_side")))
    except CrossBookStateError:
        return "flatten refused; open cross sides cannot be flattened; neither leg closed"
    if not spot_ok or not futures_ok:
        return "flatten refused; legs would close different quantities; neither leg closed"
    full = quotes.get("full") is True
    half = open_qty * Decimal("0.5")
    if full:
        if closed != open_qty or closed_contracts != open_contracts:
            return "flatten refused; full close quantity does not match the open quantity; neither leg closed"
    elif closed > half:
        return "flatten refused; shortfall exceeds half the open quantity; neither leg closed"
    return None


def _commit_flatten(
    engine: Any,
    rt: Any,
    position: Dict[str, Any],
    quotes: Dict[str, Any],
    reason: str,
    spot_book: ExecutableTop,
    futures_book: ExecutableTop,
) -> None:
    open_payload = position.get("open_payload")
    open_hash = position.get("effect_hash")
    if not isinstance(open_payload, dict) or not isinstance(open_hash, str):
        rt.last_error = "flatten refused; open effect payload missing"
        return
    closed = quotes["base_qty"]
    closed_contracts = quotes["futures_contracts"]
    open_qty = position["base_qty"]
    if not isinstance(closed, Decimal) or not isinstance(open_qty, Decimal) or open_qty <= 0:
        rt.last_error = "flatten refused; shortfall quantity is zero; neither leg closed"
        return
    payload = flatten_effect_payload(
        open_payload,
        open_hash,
        quotes["spot_exit_side"],
        quotes["spot_exit_price"],
        quotes["futures_exit_side"],
        quotes["futures_exit_price"],
        closed,
        closed_contracts,
        open_qty,
    )
    effect_hash = effect_sha256(payload)
    spot_pnl = leg_pnl(position["spot_side"], position["spot_entry"], quotes["spot_exit_price"], closed)
    futures_pnl = leg_pnl(
        position["futures_side"], position["futures_entry"], quotes["futures_exit_price"], closed
    )
    exit_fee = leg_fee(quotes["spot_exit_price"], closed, SPOT_PAPER_FEE_RATE) + leg_fee(
        quotes["futures_exit_price"], closed, FUTURES_PAPER_FEE_RATE
    )
    entry_slice = position["entry_fee"] * (closed / open_qty)
    gross = spot_pnl + futures_pnl
    net = gross - entry_slice - exit_fee
    now = time.time()
    opened_ms = int(position.get("entry_epoch_ms") or 0)
    trade = {
        "id": effect_hash,
        "instance_id": rt.spec["id"],
        "strategy_id": rt.spec.get("name") or STRATEGY_NAME,
        "mode": "paper",
        "pair": position.get("symbol") or rt.spec.get("symbol"),
        "side": "cross",
        "entry_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(opened_ms / 1000.0)) if opened_ms else "",
        "exit_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "ts_open": opened_ms,
        "ts_close": int(now * 1000),
        "entry_price": float(position["spot_entry"]),
        "exit_price": float(quotes["spot_exit_price"]),
        "amount": float(closed),
        "notional_usd": float(position["spot_entry"] * closed + position["futures_entry"] * closed),
        "fee_usd": float(entry_slice + exit_fee),
        "funding_usd": 0.0,
        "gross_pnl": float(gross),
        "net_pnl": float(net),
        "mfe_pct": 0.0,
        "mae_pct": 0.0,
        "exit_reason": reason,
        "r_multiple": None,
        "zone": None,
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    committed = engine.lake.commit_cross_flatten(effect_hash, rt.spec["id"], payload["symbol"], payload_json, trade)
    if not committed and not engine.lake.effect_exists(effect_hash):
        rt.last_error = "flatten effect refused"
        return
    rt.position = None
    try:
        _restore_open_position(engine, rt)
    except CrossBookStateError as exc:
        rt.last_error = str(exc)
        if committed:
            _record_committed_paper_flatten()
        return
    rt.last_error = None
    rt.last_mark = float(spot_book.bid)
    rt.last_signal = {
        "enter": False,
        "flattened": True,
        "full_close": quotes.get("full") is True and rt.position is None,
        "reason": reason,
        "closed_base_qty": payload["base_qty"],
        "spot_exit": payload["spot_exit_price"],
        "futures_exit": payload["futures_exit_price"],
        "effect": effect_hash,
        "spot_bid": format(spot_book.bid, "f"),
        "futures_bid": format(futures_book.bid, "f"),
    }
    if committed:
        engine.bus.emit(
            "trade",
            "CrossBookPaper",
            (
                f"FLATTEN CROSS {payload['symbol']} spot {payload['spot_exit_side']} @ {payload['spot_exit_price']} "
                f"futures {payload['futures_exit_side']} @ {payload['futures_exit_price']} "
                f"qty={payload['base_qty']} net={float(net):.8f} effect={effect_hash} trace={TRACE_ID}"
            ),
            rt.spec["id"],
        )
        _record_committed_paper_flatten()
