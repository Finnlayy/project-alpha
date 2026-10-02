"""CROSS_BOOK_KRAKEN_SPOT_PRO_PAPER: registration, paper start, live refusal, book cross."""
from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import strategies_create, strategies_update
from app.config import Settings
from app.execution.trading_engine import TradingEngine
from app.kraken.futures_client import KrakenFuturesClient
from app.kraken.spot_client import KrakenError, KrakenSpotClient
from app.logbus import LogBus
from app.storage.lake import DataLake
from app.strategies.cross_book_kraken_spot_pro_paper import (
    FEE_HURDLE,
    FUTURES_PAPER_FEE_RATE,
    SPOT_PAPER_FEE_RATE,
    STRATEGY_NAME,
    TRACE_ID,
    CrossDecision,
    ExecutableTop,
    LiveCreateRefused,
    contract_size_from_instruments,
    effect_sha256,
    evaluate_cross,
    executable_top,
    futures_book_from_orderbook,
    normalize_symbol,
    open_effect_payload,
    spot_book_from_depth,
)
from app.strategies.registry import REGISTRY, get_strategy


def test_fee_hurdle_is_the_verified_paper_sum():
    assert SPOT_PAPER_FEE_RATE == Decimal("0.0026")
    assert FUTURES_PAPER_FEE_RATE == Decimal("0.0005")
    assert FEE_HURDLE == Decimal("0.0031")
    assert FEE_HURDLE != Decimal("0.0002")


def test_strategy_is_registered_and_symbol_is_not_a_gene():
    assert STRATEGY_NAME in REGISTRY
    strategy = get_strategy(STRATEGY_NAME)
    assert strategy.paper_only is True
    assert strategy.book_worker is True
    assert strategy.param_space == {}
    assert "BTC" not in strategy.name
    assert normalize_symbol("eth/usd") == "ETH/USD"
    assert normalize_symbol("SOL/USD") == "SOL/USD"
    with pytest.raises(ValueError):
        normalize_symbol("BTCUSD")
    listing = strategy.code_listing({})
    assert TRACE_ID in listing
    assert "0.0026" in listing
    assert "0.0005" in listing


def _top(bid, bid_size, ask, ask_size) -> ExecutableTop:
    return ExecutableTop(
        bid=Decimal(bid),
        bid_size=Decimal(bid_size),
        ask=Decimal(ask),
        ask_size=Decimal(ask_size),
    )


def test_no_entry_when_gap_would_only_clear_a_two_bp_fee():
    # 4 bps clears 0.0002 and does not clear 0.0031.
    decision = evaluate_cross(
        _top("99", "1", "100", "1"),
        _top("100.04", "1", "100.10", "1"),
        Decimal("1"),
    )
    assert decision.enter is False


def test_exact_hurdle_does_not_enter():
    decision = evaluate_cross(
        _top("99", "1", "100", "1"),
        _top("100.31", "1", "100.50", "1"),
        Decimal("1"),
    )
    assert decision.enter is False
    assert decision.reason == "gross gap does not exceed fee hurdle 0.0031"


def test_buy_cheaper_spot_ask_and_sell_richer_futures_bid():
    decision = evaluate_cross(
        _top("99", "2", "100", "1.5"),
        _top("100.40", "1", "100.80", "2"),
        Decimal("1"),
    )
    assert decision.enter is True
    assert decision.spot_side == "buy"
    assert decision.futures_side == "sell"
    assert decision.spot_price == Decimal("100")
    assert decision.futures_price == Decimal("100.40")
    assert decision.base_qty == Decimal("1")
    assert decision.futures_contracts == Decimal("1")
    assert decision.gross_gap is not None and decision.gross_gap > FEE_HURDLE


def test_sell_richer_spot_bid_and_buy_cheaper_futures_ask():
    decision = evaluate_cross(
        _top("101", "2", "101.5", "2"),
        _top("100", "2", "100.20", "0.5"),
        Decimal("1"),
    )
    assert decision.enter is True
    assert decision.spot_side == "sell"
    assert decision.futures_side == "buy"
    assert decision.spot_price == Decimal("101")
    assert decision.futures_price == Decimal("100.20")
    assert decision.base_qty == Decimal("0.5")


def test_zero_size_top_is_not_executable_and_missing_size_refuses():
    assert executable_top([["100", "0", 1], ["99", "2", 1]]) == (Decimal("99"), Decimal("2"))
    assert executable_top([["100", "0", 1]]) is None
    decision = evaluate_cross(
        _top("99", "1", "100", "0"),
        _top("110", "1", "111", "1"),
        Decimal("1"),
    )
    assert decision.enter is False


def test_missing_contract_size_refuses_entry():
    decision = evaluate_cross(_top("99", "1", "100", "1"), _top("110", "1", "111", "1"), None)
    assert decision.enter is False
    assert "contractSize" in decision.reason
    assert contract_size_from_instruments({"instruments": []}, "PF_XBTUSD") is None
    assert contract_size_from_instruments(
        {"instruments": [{"symbol": "PF_ETHUSD", "contractSize": 1}]},
        "PF_ETHUSD",
    ) == Decimal("1")


def test_crossed_book_is_rejected():
    payload = {"result": {"XBTUSD": {"bids": [["100", "1", 1]], "asks": [["100", "1", 1]]}}}
    assert spot_book_from_depth(payload, "XBTUSD") is None
    assert futures_book_from_orderbook(
        {"orderBook": {"bids": [[100, 1]], "asks": [[99, 1]]}, "symbol": "PF_XBTUSD"},
        "PF_XBTUSD",
    ) is None


def test_effect_hash_is_stable_and_order_independent():
    decision = CrossDecision(
        True,
        "buy spot ask, sell futures bid",
        spot_side="buy",
        futures_side="sell",
        spot_price=Decimal("100"),
        futures_price=Decimal("100.40"),
        base_qty=Decimal("1"),
        futures_contracts=Decimal("1"),
        gross_gap=Decimal("0.004"),
        contract_size=Decimal("1"),
    )
    first = open_effect_payload("BTC/USD", "inst-a", decision, "PF_XBTUSD")
    second = {key: first[key] for key in reversed(list(first))}
    assert effect_sha256(first) == effect_sha256(second)
    assert len(effect_sha256(first)) == 64


class Books:
    def __init__(self):
        self.spot = {
            "error": [],
            "result": {"XBTUSD": {"bids": [["99", "2", 1]], "asks": [["100", "2", 1]]}},
        }
        self.futures = {
            "result": "success",
            "symbol": "PF_XBTUSD",
            "orderBook": {"bids": [[100.05, 2]], "asks": [[100.20, 2]]},
        }
        self.instrument_catalog = {
            "instruments": [
                {"symbol": "PF_XBTUSD", "contractSize": 1},
                {"symbol": "PF_ETHUSD", "contractSize": 1},
                {"symbol": "PF_XRPUSD", "contractSize": 1},
            ]
        }
        self.fail_futures = False

    def depth(self, pair, count=10):
        return self.spot

    def orderbook(self, symbol):
        if self.fail_futures:
            raise KrakenError("futures book down")
        return self.futures

    def instruments(self):
        return self.instrument_catalog


def _quiesce(engine, instance_id):
    rt = engine.instances[instance_id]
    engine._stop_loop(rt)
    if rt._thread is not None:
        rt._thread.join(timeout=5)
        assert not rt._thread.is_alive()
    return rt


@pytest.fixture
def engine_env():
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings()
        settings.db_path = os.path.join(tmp, "test.duckdb")
        settings.min_poll_seconds = 30
        settings.execution_mode = "paper"
        settings.request_timeout = 0.2
        lake = DataLake(settings.db_path)
        bus = LogBus(capacity=256)
        engine = TradingEngine(settings, lake, bus)
        books = Books()

        def _refuse_live(*_args, **_kwargs):
            raise AssertionError("live order refused")

        engine.spot.depth = books.depth
        engine.spot.add_order = _refuse_live
        books.send_order = _refuse_live
        engine._futures = books
        yield engine, lake, books
        for rt in list(engine.instances.values()):
            engine._stop_loop(rt)
            if rt._thread is not None:
                rt._thread.join(timeout=5)
        lake.close()


def test_paper_start_is_idempotent_per_symbol_and_refuses_live(engine_env):
    engine, lake, _books = engine_env
    first = engine.start_instance(STRATEGY_NAME, "btc", "btc/usd", 1, {}, "paper")
    second = engine.start_instance(STRATEGY_NAME, "btc-again", "BTC/USD", 1, {}, "paper")
    eth = engine.start_instance(STRATEGY_NAME, "eth", "ETH/USD", 1, {}, "paper")
    assert first["id"] == second["id"]
    assert first["symbol"] == "BTC/USD"
    assert first["mode"] == "paper"
    assert first["strategy_type"] == STRATEGY_NAME
    assert eth["id"] != first["id"]
    assert eth["symbol"] == "ETH/USD"
    assert lake.get_instance(first["id"])["status"] == "active"
    with pytest.raises(LiveCreateRefused):
        engine.start_instance(STRATEGY_NAME, "live", "BTC/USD", 1, {}, "live")
    engine.settings.execution_mode = "live"
    with pytest.raises(LiveCreateRefused):
        engine.start_instance(STRATEGY_NAME, "default-live", "SOL/USD", 1, {}, None)


def test_paper_open_requires_both_books_and_dedups(engine_env):
    engine, lake, books = engine_env
    row = engine.start_instance(STRATEGY_NAME, "btc", "BTC/USD", 1, {}, "paper")
    rt = _quiesce(engine, row["id"])
    assert rt.position is None

    books.fail_futures = True
    from app.execution.cross_book_paper import tick_cross_book

    tick_cross_book(engine, rt)
    assert rt.position is None
    assert "futures book unavailable" in (rt.last_error or "")

    books.fail_futures = False
    books.futures = {
        "result": "success",
        "symbol": "PF_XBTUSD",
        "orderBook": {"bids": [[100.40, 1]], "asks": [[100.80, 2]]},
    }
    tick_cross_book(engine, rt)
    assert rt.position is not None
    assert rt.position["kind"] == "cross_book"
    assert rt.position["spot_side"] == "buy"
    assert rt.position["futures_side"] == "sell"
    assert rt.position["base_qty"] == Decimal("1")
    opened = rt.position["effect_hash"]

    rt.position = None
    tick_cross_book(engine, rt)
    assert rt.position is not None
    assert rt.position["effect_hash"] == opened
    opens = lake._conn.execute(
        "SELECT COUNT(*) FROM effect_dedup WHERE symbol=? AND action='open'",
        ["BTC/USD"],
    ).fetchone()
    assert opens[0] == 1


def test_flatten_closes_both_legs_or_neither(engine_env):
    engine, lake, books = engine_env
    row = engine.start_instance(STRATEGY_NAME, "btc", "BTC/USD", 1, {}, "paper")
    rt = _quiesce(engine, row["id"])
    books.futures = {
        "result": "success",
        "symbol": "PF_XBTUSD",
        "orderBook": {"bids": [[100.40, 1]], "asks": [[100.80, 2]]},
    }
    from app.execution.cross_book_paper import tick_cross_book

    tick_cross_book(engine, rt)
    assert rt.position is not None

    books.futures = {
        "result": "success",
        "symbol": "PF_XBTUSD",
        "orderBook": {"bids": [[100.40, 0.1]], "asks": [[100.50, 0.1]]},
    }
    engine._close_position(rt, "INSTANCE_STOP")
    assert rt.position is not None
    assert lake.trades_for(instance_id=row["id"]) == []
    assert "neither leg closed" in (rt.last_error or "")

    books.spot = {
        "error": [],
        "result": {"XBTUSD": {"bids": [["100.10", "2", 1]], "asks": [["100.20", "2", 1]]}},
    }
    books.futures = {
        "result": "success",
        "symbol": "PF_XBTUSD",
        "orderBook": {"bids": [[100.00, 2]], "asks": [[100.30, 2]]},
    }
    engine._close_position(rt, "INSTANCE_STOP")
    assert rt.position is None
    trades = lake.trades_for(instance_id=row["id"])
    assert len(trades) == 1
    assert trades[0]["mode"] == "paper"
    assert trades[0]["side"] == "cross"
    assert trades[0]["exit_reason"] == "INSTANCE_STOP"
    # spot bought at 100 and sold at 100.10; futures sold at 100.40 and bought at 100.30.
    assert trades[0]["net_pnl"] != 0
    engine._close_position(rt, "INSTANCE_STOP")
    assert len(lake.trades_for(instance_id=row["id"])) == 1


def test_api_create_starts_paper_and_refuses_live(engine_env):
    engine, _lake, _books = engine_env

    class Request:
        def __init__(self, body):
            self._body = body
            self.app = SimpleNamespace(
                state=SimpleNamespace(
                    alpha=SimpleNamespace(engine=engine, settings=engine.settings, lake=engine.lake)
                )
            )

        async def json(self):
            return self._body

    with pytest.raises(HTTPException) as live_err:
        asyncio.run(
            strategies_create(
                Request({"strategyType": STRATEGY_NAME, "assetPair": "BTC/USD", "executionMode": "live"})
            )
        )
    assert live_err.value.status_code == 422
    assert "refuses live" in live_err.value.detail

    with pytest.raises(HTTPException) as missing:
        asyncio.run(strategies_create(Request({"strategyType": STRATEGY_NAME, "executionMode": "paper"})))
    assert missing.value.status_code == 422

    created = asyncio.run(
        strategies_create(
            Request({"strategyType": STRATEGY_NAME, "assetPair": "XRP/USD", "executionMode": "paper", "name": "xrp-paper"})
        )
    )
    assert created["strategyType"] == STRATEGY_NAME
    assert created["assetPair"] == "XRP/USD"
    assert created["executionMode"] == "paper"

    with pytest.raises(HTTPException) as update_err:
        asyncio.run(strategies_update(Request({"executionMode": "live"}), created["id"]))
    assert update_err.value.status_code == 422
    assert engine.lake.get_instance(created["id"])["mode"] == "paper"


def test_stopped_open_cross_reuses_the_same_worker(engine_env):
    engine, _lake, books = engine_env
    row = engine.start_instance(STRATEGY_NAME, "btc", "BTC/USD", 1, {}, "paper")
    rt = _quiesce(engine, row["id"])
    books.futures = {
        "result": "success",
        "symbol": "PF_XBTUSD",
        "orderBook": {"bids": [[100.40, 1]], "asks": [[100.80, 2]]},
    }
    from app.execution.cross_book_paper import tick_cross_book

    tick_cross_book(engine, rt)
    assert rt.position is not None
    books.futures = {
        "result": "success",
        "symbol": "PF_XBTUSD",
        "orderBook": {"bids": [[100.40, 0.01]], "asks": [[100.50, 0.01]]},
    }
    stopped = engine.stop_instance(row["id"], "INSTANCE_STOP")
    assert stopped["status"] == "stopped"
    assert rt.position is not None
    again = engine.start_instance(STRATEGY_NAME, "btc-2", "BTC/USD", 1, {}, "paper")
    assert again["id"] == row["id"]
    assert again["status"] == "active"
    assert engine.instances[row["id"]].position["effect_hash"] == rt.position["effect_hash"]


def test_native_pair_mapping_stays_on_the_kraken_clients():
    assert KrakenSpotClient.pair_to_native("XRP/USD") == "XRPUSD"
    assert KrakenFuturesClient.symbol_to_contract("XRP/USD") == "PF_XRPUSD"
    book = spot_book_from_depth(
        {"result": {"XRPUSD": {"bids": [["1.0", "3", 1]], "asks": [["1.1", "3", 1]]}}},
        "XRPUSD",
    )
    assert book is not None and book.ask == Decimal("1.1")
    fut = futures_book_from_orderbook(
        {"orderBook": {"bids": [[1.2, 3]], "asks": [[1.3, 3]]}},
        "PF_XRPUSD",
    )
    assert fut is not None and fut.bid == Decimal("1.2")
