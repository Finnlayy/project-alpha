"""
Integration test for the live TradingEngine.

The only stubbed layer is the network (this sandbox cannot reach Kraken):
  - REST OHLC -> raises KrakenError (forces the documented lake fallback)
  - WS mark   -> returns the last real candle close (deterministic)
Everything below that layer — strategy evaluation, M8 gating, churn guard,
leverage sizing, paper fills, MFE/MAE, autopsy zones, DuckDB persistence —
is the REAL production code path.
"""
import os
import tempfile
import time

import numpy as np
import pytest

from app.config import Settings
from app.execution.trading_engine import TradingEngine
from app.kraken.spot_client import KrakenError, KrakenSpotClient
from app.logbus import LogBus
from app.storage.lake import DataLake
from app.strategies.registry import EMA_TREND_RSI


class FakeWS:
    def __init__(self, prices):
        self.prices = prices

    def get_mark_price(self, symbol):
        return self.prices[symbol][-1] if self.prices.get(symbol) else None


def trending_candles(n=400, seed=42, start=100.0):
    rng = np.random.default_rng(seed)
    rows = []
    price = start
    t0 = 1_700_000_000
    for i in range(n):
        r = 0.002 + rng.normal(0, 0.001)
        o = price
        c = price * (1 + r)
        h = max(o, c) * 1.001
        l = min(o, c) * 0.999
        rows.append({"time": t0 + i * 900, "open": o, "high": h, "low": l, "close": c, "volume": 50.0})
        price = c
    return rows


@pytest.fixture
def engine_env():
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings()
        settings.db_path = os.path.join(tmp, "test.duckdb")
        settings.min_poll_seconds = 0.4
        settings.execution_mode = "paper"
        lake = DataLake(settings.db_path)
        bus = LogBus(capacity=256)
        engine = TradingEngine(settings, lake, bus)
        candles = trending_candles()
        engine.spot = KrakenSpotClient(settings)

        def _offline_ohlc(*a, **k):
            raise KrakenError("offline (test): Kraken REST stubbed")

        engine.spot.ohlc = _offline_ohlc
        prices = {"BTC/USD": [c["close"] for c in candles]}
        engine.set_ws_service(FakeWS(prices))
        lake.upsert_candles("BTC/USD", 1, candles)
        yield engine, lake, bus, prices
        lake.close()


def test_engine_full_paper_cycle(engine_env):
    engine, lake, bus, prices = engine_env
    row = engine.start_instance(
        strategy_type="EMA_TREND_RSI",
        name="trending-long",
        symbol="BTC/USD",
        interval_min=1,
        params=EMA_TREND_RSI().default_params(),
        mode="paper",
    )
    iid = row["id"]
    time.sleep(2.5)  # let the loop run a few ticks (0.4s poll)

    rt = engine.instances[iid]
    # strong uptrend -> EMA fast > slow -> long entry expected
    assert rt.position is not None, f"expected an open long position; last_signal={rt.last_signal}, err={rt.last_error}"
    assert rt.position["side"] == "long"
    events = [e for e in bus.buffer() if e.get("strategyId") == iid]
    assert any("OPEN" in e["message"] for e in events), "OPEN event must be emitted"

    # force a favorable mark so the close realizes profit
    prices["BTC/USD"].append(prices["BTC-USD"] if False else prices["BTC/USD"][-1] * 1.02)
    rt.last_mark = prices["BTC/USD"][-1]
    engine._close_position(rt, "TEST_CLOSE")

    trades = lake.trades_for(instance_id=iid)
    assert len(trades) == 1
    t = trades[0]
    assert t["exit_reason"] == "TEST_CLOSE"
    assert t["net_pnl"] > 0, "rising price must realize a positive net PnL"
    assert t["mfe_pct"] >= t["net_pnl"] / t["notional_usd"] * 100 - 1.0  # MFE bounds the captured PnL
    assert t["zone"] in ("GOOD", "GOLD", "SILVER", "BRONZE", "POOR", "BAD"), f"unexpected zone {t['zone']}"
    assert t["r_multiple"] > 0

    # M8 state persisted
    st = lake.fetch_state(iid)
    assert st["status"] in ("ACTIVE", "THROTTLED")

    # instance stopped cleanly
    engine.stop_instance(iid, "TEST_DONE")
    assert lake.get_instance(iid)["status"] == "stopped"


def test_engine_churn_guard_blocks_immediate_reentry(engine_env):
    engine, lake, bus, prices = engine_env
    row = engine.start_instance(
        strategy_type="EMA_TREND_RSI",
        name="churn-test",
        symbol="BTC/USD",
        interval_min=1,
        params=EMA_TREND_RSI().default_params(),
        mode="paper",
    )
    iid = row["id"]
    time.sleep(2.0)
    rt = engine.instances[iid]
    if rt.position:
        engine._close_position(rt, "TEST_CLOSE")
    else:
        pytest.skip("no position opened in uptrend fixture")
    # churn guard cooldown is active now: force a fresh tick — must NOT reopen
    cooldowns_before = engine.instances[iid].churn.last_close_timestamp.get(iid)
    assert cooldowns_before is not None
    rt.position = None
    engine._tick(rt)
    assert rt.position is None, "immediate re-entry after close must be blocked by the churn guard"
    engine.stop_instance(iid, "TEST_DONE")


def test_engine_no_data_never_fabricates(engine_env):
    engine, lake, bus, prices = engine_env
    # empty lake for a new symbol, no WS mark -> instance must idle, not invent prices
    prices.pop("BTC/USD")
    row = engine.start_instance(
        strategy_type="EMA_TREND_RSI",
        name="no-data",
        symbol="ETH/USD",
        interval_min=1,
        params=EMA_TREND_RSI().default_params(),
        mode="paper",
    )
    iid = row["id"]
    time.sleep(1.5)
    rt = engine.instances[iid]
    assert rt.position is None
    assert rt.waiting is True, "without real data the engine must wait, not fabricate"
    assert lake.trades_for(instance_id=iid) == []
    engine.stop_instance(iid, "TEST_DONE")


def test_worker_view_reflects_ledger(engine_env):
    engine, lake, bus, prices = engine_env
    row = engine.start_instance(
        strategy_type="EMA_TREND_RSI",
        name="worker-view",
        symbol="BTC/USD",
        interval_min=1,
        params=EMA_TREND_RSI().default_params(),
        mode="paper",
    )
    iid = row["id"]
    time.sleep(2.0)
    workers = engine.worker_view()
    w = next(x for x in workers if x["id"] == iid)
    assert w["openTrades"] == (1 if engine.instances[iid].position else 0)
    assert w["exchange"] == "Kraken (paper)"
    assert w["m8State"] in ("ACTIVE", "THROTTLED", "QUARANTINED")
    engine.stop_instance(iid, "TEST_DONE")


def test_cancel_all_stops_everything(engine_env):
    engine, lake, bus, prices = engine_env
    for name in ("a", "b"):
        engine.start_instance("EMA_TREND_RSI", name, "BTC/USD", 1, EMA_TREND_RSI().default_params(), "paper")
    time.sleep(1.5)
    res = engine.cancel_all()
    assert res["ok"]
    assert len(res["stoppedInstances"]) == 2
    for i in lake.list_instances(include_stopped=True):
        assert i["status"] == "stopped"
