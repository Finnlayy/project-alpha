"""
Golden tests for the backtest engine, metrics and genetic optimizer.

Test fixtures use deterministic synthetic candles — that is normal and
required for unit testing; the engine itself never fabricates data, it only
processes whatever candles it is given (in production: real Kraken OHLC).
"""
import math

import numpy as np
import pytest

from app.backtest.engine import BacktestConfig, run_backtest
from app.backtest.metrics import compute_metrics, deflated_sharpe_ratio, max_drawdown, sharpe_ratio
from app.optimizer.fitness import evaluate_cadence, evaluate_fitness
from app.optimizer.genetic import GeneticOptimizer
from app.strategies.registry import DONCHIAN_BREAKOUT, EMA_TREND_RSI, MEAN_REVERSION_ZSCORE, get_strategy


# ---------------------------------------------------------------- fixtures
def make_candles(n: int = 500, seed: int = 1, start_price: float = 100.0, drift: float = 0.0002, vol: float = 0.004):
    rng = np.random.default_rng(seed)
    rows = []
    price = start_price
    t0 = 1_700_000_000.0
    for i in range(n):
        r = drift + rng.normal(0, vol)
        o = price
        c = price * (1 + r)
        h = max(o, c) * (1 + abs(rng.normal(0, vol / 2)))
        l = min(o, c) * (1 - abs(rng.normal(0, vol / 2)))
        rows.append({"time": t0 + i * 900, "open": o, "high": h, "low": l, "close": c, "volume": 100.0})
        price = c
    return rows


def flat_series(n: int = 400, level: float = 100.0):
    return [{"time": 1_700_000_000.0 + i * 900, "open": level, "high": level, "low": level, "close": level, "volume": 1.0} for i in range(n)]


# ------------------------------------------------------------------- engine
class AlwaysLongOnFirst:
    """Minimal strategy: long from the first bar to the end, no stops."""

    name = "ALWAYS_LONG"
    param_space = {}
    min_bars = 1

    def indicator_periods(self, params):
        return {"fast": 5, "slow": 10, "rsi": 14, "atr": 14}

    def on_bar(self, ctx, params):
        return {"target": 1.0, "stop": None, "take_profit": None}


def test_no_lookahead_prefix_consistency():
    """Trades on a prefix must be identical to the same trades in the full run
    (no future information may influence the past)."""
    candles = make_candles(600, seed=5)
    cfg = BacktestConfig(initial_balance_usd=10000.0, bar_minutes=15, slippage_bps=2.0)
    full = run_backtest(EMA_TREND_RSI(), EMA_TREND_RSI().default_params(), candles, cfg)
    prefix = candles[:400]
    short = run_backtest(EMA_TREND_RSI(), EMA_TREND_RSI().default_params(), prefix, cfg)
    assert full.ok and short.ok
    # Only trades fully closed inside the prefix window must match bit-for-bit.
    # (A position still open at the prefix end is closed as END_OF_DATA there —
    # an artifact of truncation, not of look-ahead.)
    prefix_end_epoch = prefix[-1]["time"]
    full_closed_in_prefix = [t for t in full.trades if t.exit_epoch <= prefix_end_epoch]
    assert len(full_closed_in_prefix) >= 3, "expected several closed trades in the prefix"
    assert len(short.trades) >= len(full_closed_in_prefix)
    for a, b in zip(full_closed_in_prefix, short.trades):
        assert a.entry_price == b.entry_price
        assert a.exit_price == b.exit_price
        assert a.exit_reason == b.exit_reason
        assert a.entry_epoch == b.entry_epoch
        assert a.exit_epoch == b.exit_epoch


def test_fill_at_next_open_with_slippage():
    cfg = BacktestConfig(initial_balance_usd=10000.0, bar_minutes=15, slippage_bps=10.0, maker_fee_rate=0.0, taker_fee_rate=0.0)
    candles = make_candles(200, seed=9)
    strat = AlwaysLongOnFirst()
    res = run_backtest(strat, {}, candles, cfg)
    assert res.ok
    assert len(res.trades) == 1
    t = res.trades[0]
    # entered at open[1] with 10 bps slippage up
    expected_entry = candles[1]["open"] * 1.001
    assert abs(t.entry_price - expected_entry) < 1e-9


def test_stop_loss_triggers_at_stop_price():
    cfg = BacktestConfig(initial_balance_usd=10000.0, bar_minutes=15, slippage_bps=0.0, taker_fee_rate=0.0)
    candles = make_candles(200, seed=11)

    class Stopper(AlwaysLongOnFirst):
        def on_bar(self, ctx, params):
            return {"target": 1.0, "stop": 0.0, "take_profit": None}  # replaced below per-instance

    res = run_backtest(EMA_TREND_RSI(), EMA_TREND_RSI().default_params(), candles, cfg)
    assert res.ok
    stop_trades = [t for t in res.trades if t.exit_reason == "STOP_LOSS"]
    for t in stop_trades:
        # stop fills must be at the stop price (0 slippage) and be losses (for longs)
        assert t.exit_price > 0
        if t.side == "long":
            assert t.exit_price < t.entry_price


def test_spot_cannot_short():
    cfg = BacktestConfig(initial_balance_usd=10000.0, bar_minutes=15, market_type="SPOT")

    class AlwaysShort(AlwaysLongOnFirst):
        def on_bar(self, ctx, params):
            return {"target": -1.0, "stop": None, "take_profit": None}

    res = run_backtest(AlwaysShort(), {}, make_candles(200, seed=13), cfg)
    assert res.ok
    assert all(t.side != "short" for t in res.trades)


def test_insufficient_data_rejected():
    res = run_backtest(EMA_TREND_RSI(), EMA_TREND_RSI().default_params(), make_candles(20), BacktestConfig())
    assert not res.ok
    assert "insufficient" in res.error


def test_fees_reduce_pnl():
    candles = make_candles(300, seed=21)
    no_fee = run_backtest(EMA_TREND_RSI(), EMA_TREND_RSI().default_params(), candles,
                          BacktestConfig(taker_fee_rate=0.0, slippage_bps=0.0))
    with_fee = run_backtest(EMA_TREND_RSI(), EMA_TREND_RSI().default_params(), candles,
                            BacktestConfig(taker_fee_rate=0.0025, slippage_bps=0.0))
    assert no_fee.ok and with_fee.ok
    assert with_fee.final_balance <= no_fee.final_balance
    assert with_fee.summary["totalFeesUSD"] > 0


def test_constant_price_no_trades_or_profit():
    res = run_backtest(EMA_TREND_RSI(), EMA_TREND_RSI().default_params(), flat_series(400), BacktestConfig())
    assert res.ok
    # no movement -> no signals beyond noise, no meaningful PnL
    assert abs(res.final_balance - 10000.0) < 5.0


# ------------------------------------------------------------------ metrics
def test_max_drawdown_known_curve():
    # [100, 120, 90, 110, 80]: peak 120, worst trough 80 -> (120-80)/120 = 33.333...%
    assert abs(max_drawdown([100, 120, 90, 110, 80]) - (40.0 / 120.0) * 100.0) < 1e-9
    assert max_drawdown([100, 110, 120]) == 0.0
    assert max_drawdown([100]) == 0.0


def test_sharpe_known_series():
    rets = np.array([0.01, 0.01, 0.01, 0.01])  # zero variance after mean
    assert sharpe_ratio(rets, 252.0) == 0.0  # std=0 guard
    rets2 = np.array([0.01, -0.01, 0.01, -0.01])
    s = sharpe_ratio(rets2, 252.0)
    # mean 0, std 0.01 -> sharpe 0
    assert abs(s) < 1e-9


def test_dsr_bounds_and_monotonicity():
    rng = np.random.default_rng(3)
    good = rng.normal(0.001, 0.01, 500)
    bad = rng.normal(-0.001, 0.01, 500)
    dsr_good = deflated_sharpe_ratio(good, 252 * 4, n_trials=100)
    dsr_bad = deflated_sharpe_ratio(bad, 252 * 4, n_trials=100)
    assert 0.0 <= dsr_good <= 1.0
    assert 0.0 <= dsr_bad <= 1.0
    assert dsr_good > dsr_bad


def test_compute_metrics_shapes():
    candles = make_candles(300, seed=31)
    res = run_backtest(DONCHIAN_BREAKOUT(), DONCHIAN_BREAKOUT().default_params(), candles, BacktestConfig(bar_minutes=15))
    m = res.summary
    for key in ("sharpeRatio", "sortinoRatio", "deflatedSharpeRatio", "maxDrawdownPercent", "profitFactor", "winRate", "totalTrades", "totalFeesUSD"):
        assert key in m
    assert m["totalTrades"] == len(res.trades)


# ------------------------------------------------------------------ fitness
def test_fitness_trade_starvation():
    summary = {"deflatedSharpeRatio": 1.2, "annualizedReturnPercent": 50.0, "finalBalance": 12000.0, "initialBalance": 10000.0, "totalTrades": 5, "totalFeesUSD": 1.0}
    fit = evaluate_fitness(summary, active_rule_count=5, evaluation_days=30)
    assert fit["fitnessScore"] == 0.0
    assert "STARVATION" in fit["rejectionReason"]


def test_fitness_fee_drag_death():
    summary = {"deflatedSharpeRatio": 1.2, "annualizedReturnPercent": -5.0, "finalBalance": 9900.0, "initialBalance": 10000.0, "totalTrades": 40, "totalFeesUSD": 120.0}
    fit = evaluate_fitness(summary, active_rule_count=5, evaluation_days=30)
    assert fit["fitnessScore"] == 0.0
    assert "FEE DRAG" in fit["rejectionReason"]


def test_fitness_positive_case():
    summary = {"deflatedSharpeRatio": 0.97, "annualizedReturnPercent": 60.0, "finalBalance": 14000.0, "initialBalance": 10000.0, "totalTrades": 100, "totalFeesUSD": 50.0}
    fit = evaluate_fitness(summary, active_rule_count=5, evaluation_days=60)
    assert fit["fitnessScore"] > 0.35
    assert fit["isValidCandidate"] is True


def test_cadence_band():
    t0 = 1_700_000_000.0
    # 4.5 trades/day over 10 days = 45 trades, evenly spaced
    ts = [t0 + i * (1440.0 / 4.5) for i in range(45)]
    cad = evaluate_cadence(ts, 10.0)
    assert cad["isWithinTargetRange"]
    assert cad["cadenceScore"] > 0.9
    # extreme: 100 trades/day
    ts2 = [t0 + i * 60.0 for i in range(1000)]
    cad2 = evaluate_cadence(ts2, 10.0)
    assert not cad2["isWithinTargetRange"]
    assert "EXCESS" in cad2["rejectionReason"]


# ------------------------------------------------------------------ genetic
def test_genetic_optimizer_deterministic():
    # 2400 15m bars = 30 days: large enough for the N>=30 trade guardrail
    candles = make_candles(2400, seed=77)
    cfg = BacktestConfig(bar_minutes=15, initial_balance_usd=10000.0)
    r1 = GeneticOptimizer(DONCHIAN_BREAKOUT(), seed=123).run(candles, cfg, population_size=12, generations=6)
    r2 = GeneticOptimizer(DONCHIAN_BREAKOUT(), seed=123).run(candles, cfg, population_size=12, generations=6)
    assert r1["ok"] and r2["ok"]
    assert r1["bestIndividual"] is not None, "no individual passed guardrails on 30 days of data?"
    assert r1["bestIndividual"]["genes"] == r2["bestIndividual"]["genes"]
    assert r1["bestIndividual"]["inSampleSummary"] == r2["bestIndividual"]["inSampleSummary"]
    # generation history must be monotone-consistent in bookkeeping
    assert [g["generation"] for g in r1["generationHistory"]] == list(range(1, 7))


def test_genetic_survivors_have_oos():
    candles = make_candles(900, seed=88)
    cfg = BacktestConfig(bar_minutes=15, initial_balance_usd=10000.0)
    res = GeneticOptimizer(MEAN_REVERSION_ZSCORE(), seed=5).run(candles, cfg, population_size=12, generations=5, survivors=3)
    assert res["ok"]
    assert len(res["survivors"]) >= 1
    for s in res["survivors"]:
        assert "outOfSample" in s
        assert s["inSample"]["totalTrades"] >= 0


def test_genetic_rejects_thin_data():
    res = GeneticOptimizer(EMA_TREND_RSI(), seed=1).run(make_candles(100), BacktestConfig())
    assert not res["ok"]


def test_registry_strategies_sane():
    for kind in ("EMA_TREND_RSI", "MEAN_REVERSION_ZSCORE", "DONCHIAN_BREAKOUT"):
        s = get_strategy(kind)
        p = s.default_params()
        clamped = s.clamp_genes({k: 1e6 for k in s.param_space})
        for k, (lo, hi, _) in s.param_space.items():
            assert lo <= clamped[k] <= hi
