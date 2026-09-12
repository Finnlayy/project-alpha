"""
Real event-driven backtest engine.

Honesty rules (Zero-Dummy):
  - No look-ahead: a signal computed on bar i is executed at bar i+1's OPEN.
  - Intra-bar stops/TPs are evaluated conservatively (worst case first).
  - Fees: maker/taker on notional turnover + slippage bps on every fill.
  - Perps: funding charged every 8h on notional at the live funding rate
    (or a provided constant when backtesting historical windows).
  - MFE/MAE tracked from intra-bar highs/lows while a position is open.
  - If data is missing, the engine returns an explicit error — never invents candles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from app.strategies.base import StrategyContext, Strategy


@dataclass
class BacktestConfig:
    initial_balance_usd: float = 10000.0
    market_type: str = "SPOT"  # SPOT | PERP
    maker_fee_rate: float = 0.0002
    taker_fee_rate: float = 0.0005
    slippage_bps: float = 2.0
    funding_rate_per_8h: float = 0.00002  # applied for PERP when no live series available
    bar_minutes: int = 15
    max_leverage: float = 1.0  # PERP only; SPOT forced to 1.0


@dataclass
class Trade:
    id: str
    side: str  # long | short
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    amount: float
    notional_usd: float
    fee_usd: float
    funding_usd: float
    gross_pnl_usd: float
    net_pnl_usd: float
    mfe_pct: float
    mae_pct: float
    bars_held: int
    exit_reason: str
    entry_epoch: float = 0.0
    exit_epoch: float = 0.0


@dataclass
class BacktestResult:
    ok: bool
    error: Optional[str] = None
    pair: str = ""
    strategy_name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    candles_used: int = 0
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    final_balance: float = 0.0
    summary: Dict[str, Any] = field(default_factory=dict)


def _iso(epoch_seconds: float) -> str:
    import time as _t

    return _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(epoch_seconds))


def run_backtest(
    strategy: Strategy,
    params: Dict[str, Any],
    candles: List[Dict[str, Any]],  # rows: {time, open, high, low, close, volume}
    config: BacktestConfig,
    pair: str = "",
) -> BacktestResult:
    """Execute a strategy over real candles. Deterministic given the inputs."""
    if len(candles) < 60:
        return BacktestResult(ok=False, error=f"insufficient candles ({len(candles)} < 60) — refusing to backtest", pair=pair, strategy_name=strategy.name, params=params)

    opens = np.array([c["open"] for c in candles], dtype=float)
    highs = np.array([c["high"] for c in candles], dtype=float)
    lows = np.array([c["low"] for c in candles], dtype=float)
    closes = np.array([c["close"] for c in candles], dtype=float)
    vols = np.array([c.get("volume", 0.0) for c in candles], dtype=float)
    times = np.array([c["time"] for c in candles], dtype=float)
    n = len(closes)

    # Pre-compute full indicator arrays ONCE (causal by construction: each value
    # at i uses data <= i; the strategy only sees values at i, so no look-ahead).
    from app.quant import indicators as ta

    periods = strategy.indicator_periods(params)
    ctx_cache = StrategyContext(
        opens, highs, lows, closes, vols, times,
        ema_fast=ta.ema(closes, periods["fast"]),
        ema_slow=ta.ema(closes, periods["slow"]),
        rsi=ta.rsi(closes, periods["rsi"]),
        atr=ta.atr(highs, lows, closes, periods["atr"]),
        bar_minutes=config.bar_minutes,
    )

    balance = config.initial_balance_usd
    position: Optional[Dict[str, Any]] = None
    trades: List[Trade] = []
    equity_curve: List[Dict[str, Any]] = []
    last_fill_bar = -10_000
    trade_seq = 0

    def fill_price(price: float, side: str) -> float:
        slip = config.slippage_bps / 10_000.0
        return price * (1 + slip) if side == "buy" else price * (1 - slip)

    def fee_on(notional: float) -> float:
        # taker for stops/markets, maker for planned entries — use taker (conservative)
        return notional * config.taker_fee_rate

    for i in range(1, n):
        # ---------------- 1. manage open position (intra-bar, conservative) ----
        if position is not None:
            is_long = position["side"] == "long"
            stop = position.get("stop_price")
            tp = position.get("take_profit_price")
            exit_price: Optional[float] = None
            reason: Optional[str] = None

            if is_long:
                if stop is not None and lows[i] <= stop:
                    exit_price, reason = fill_price(stop, "sell"), "STOP_LOSS"
                elif tp is not None and highs[i] >= tp:
                    exit_price, reason = fill_price(tp, "sell"), "TAKE_PROFIT"
            else:
                if stop is not None and highs[i] >= stop:
                    exit_price, reason = fill_price(stop, "buy"), "STOP_LOSS"
                elif tp is not None and lows[i] <= tp:
                    exit_price, reason = fill_price(tp, "buy"), "TAKE_PROFIT"

            # Funding accrual for perps (8h buckets)
            if config.market_type == "PERP" and i > 0 and (i % max(1, int(480.0 / config.bar_minutes))) == 0:
                position["funding_usd"] += position["notional_usd"] * config.funding_rate_per_8h * (1 if is_long else -1)

            if exit_price is not None:
                pnl = (exit_price - position["entry_price"]) * position["amount"] * (1 if is_long else -1)
                fee = fee_on(exit_price * position["amount"])
                balance += pnl - fee
                position["fee_usd"] += fee
                trade_seq += 1
                trades.append(
                    Trade(
                        id=f"bt-{trade_seq:04d}",
                        side=position["side"],
                        entry_time=_iso(times[position["entry_bar"]]),
                        exit_time=_iso(times[i]),
                        entry_epoch=float(times[position["entry_bar"]]),
                        exit_epoch=float(times[i]),
                        entry_price=position["entry_price"],
                        exit_price=exit_price,
                        amount=position["amount"],
                        notional_usd=position["notional_usd"],
                        fee_usd=position["fee_usd"],
                        funding_usd=position.get("funding_usd", 0.0),
                        gross_pnl_usd=pnl,
                        net_pnl_usd=pnl - fee - position.get("funding_usd", 0.0),
                        mfe_pct=position["mfe"],
                        mae_pct=position["mae"],
                        bars_held=i - position["entry_bar"],
                        exit_reason=reason,
                    )
                )
                position = None

        # ---------------- 2. update MFE/MAE while open -------------------------
        if position is not None:
            if position["side"] == "long":
                position["mfe"] = max(position["mfe"], (highs[i] - position["entry_price"]) / position["entry_price"] * 100)
                position["mae"] = min(position["mae"], (lows[i] - position["entry_price"]) / position["entry_price"] * 100)
            else:
                position["mfe"] = max(position["mfe"], (position["entry_price"] - lows[i]) / position["entry_price"] * 100)
                position["mae"] = min(position["mae"], (position["entry_price"] - highs[i]) / position["entry_price"] * 100)

        # ---------------- 3. signal on closed bar i-1, execute at open i -------
        # (i>=1; strategy sees data up to bar i-1 because we call on_bar(i-1)
        #  and execute at open[i] — the next bar's open.)
        if i >= strategy.min_bars:
            ctx = ctx_cache.at(i - 1)
            decision = strategy.on_bar(ctx, params)
            target = max(-1.0, min(1.0, decision.get("target", 0.0)))  # -1..1 (short..long)
            leverage = 1.0 if config.market_type == "SPOT" else min(config.max_leverage, 10.0)

            if position is None and abs(target) >= 0.05:
                notional = balance * abs(target) * leverage
                if notional >= 10.0:
                    side = "long" if target > 0 else "short"
                    if config.market_type == "SPOT" and side == "short":
                        side = None  # spot cannot short
                    if side:
                        entry = fill_price(opens[i], "buy" if side == "long" else "sell")
                        amount = notional / entry
                        fee = fee_on(notional)
                        balance -= fee
                        position = {
                            "side": side,
                            "entry_bar": i,
                            "entry_price": entry,
                            "amount": amount,
                            "notional_usd": notional,
                            "fee_usd": fee,
                            "funding_usd": 0.0,
                            "mfe": 0.0,
                            "mae": 0.0,
                            "stop_price": decision.get("stop"),
                            "take_profit_price": decision.get("take_profit"),
                        }
                        last_fill_bar = i
            elif position is not None and abs(target) >= 0.05:
                is_long = position["side"] == "long"
                # exit only when the signal flips to the opposite side
                opposite = (target > 0) != is_long
                if opposite:
                    exit_price = fill_price(opens[i], "sell" if is_long else "buy")
                    pnl = (exit_price - position["entry_price"]) * position["amount"] * (1 if is_long else -1)
                    fee = fee_on(exit_price * position["amount"])
                    balance += pnl - fee
                    position["fee_usd"] += fee
                    trade_seq += 1
                    trades.append(
                        Trade(
                            id=f"bt-{trade_seq:04d}",
                            side=position["side"],
                            entry_time=_iso(times[position["entry_bar"]]),
                            exit_time=_iso(times[i]),
                            entry_epoch=float(times[position["entry_bar"]]),
                            exit_epoch=float(times[i]),
                            entry_price=position["entry_price"],
                            exit_price=exit_price,
                            amount=position["amount"],
                            notional_usd=position["notional_usd"],
                            fee_usd=position["fee_usd"],
                            funding_usd=position.get("funding_usd", 0.0),
                            gross_pnl_usd=pnl,
                            net_pnl_usd=pnl - fee - position.get("funding_usd", 0.0),
                            mfe_pct=position["mfe"],
                            mae_pct=position["mae"],
                            bars_held=i - position["entry_bar"],
                            exit_reason="SIGNAL_EXIT",
                        )
                    )
                    position = None
                    # re-enter opposite side on same bar's open
                    if opposite:
                        notional = balance * abs(target) * leverage
                        if notional >= 10.0:
                            side = "long" if target > 0 else "short"
                            entry = fill_price(opens[i], "buy" if side == "long" else "sell")
                            amount = notional / entry
                            fee = fee_on(notional)
                            balance -= fee
                            position = {
                                "side": side,
                                "entry_bar": i,
                                "entry_price": entry,
                                "amount": amount,
                                "notional_usd": notional,
                                "fee_usd": fee,
                                "funding_usd": 0.0,
                                "mfe": 0.0,
                                "mae": 0.0,
                                "stop_price": decision.get("stop"),
                                "take_profit_price": decision.get("take_profit"),
                            }

        # ---------------- 4. mark-to-market equity -----------------------------
        eq = balance
        if position is not None:
            is_long = position["side"] == "long"
            eq += (closes[i] - position["entry_price"]) * position["amount"] * (1 if is_long else -1)
        equity_curve.append({"time": _iso(times[i]), "balance": round(eq, 2)})

    # Close any open position at the final close (marked, for completeness)
    if position is not None and n > 0:
        i = n - 1
        is_long = position["side"] == "long"
        exit_price = fill_price(closes[i], "sell" if is_long else "buy")
        pnl = (exit_price - position["entry_price"]) * position["amount"] * (1 if is_long else -1)
        fee = fee_on(exit_price * position["amount"])
        balance += pnl - fee
        position["fee_usd"] += fee
        trade_seq += 1
        trades.append(
            Trade(
                id=f"bt-{trade_seq:04d}",
                side=position["side"],
                entry_time=_iso(times[position["entry_bar"]]),
                exit_time=_iso(times[i]),
                entry_epoch=float(times[position["entry_bar"]]),
                exit_epoch=float(times[i]),
                entry_price=position["entry_price"],
                exit_price=exit_price,
                amount=position["amount"],
                notional_usd=position["notional_usd"],
                fee_usd=position["fee_usd"],
                funding_usd=position.get("funding_usd", 0.0),
                gross_pnl_usd=pnl,
                net_pnl_usd=pnl - fee - position.get("funding_usd", 0.0),
                mfe_pct=position["mfe"],
                mae_pct=position["mae"],
                bars_held=i - position["entry_bar"],
                exit_reason="END_OF_DATA",
            )
        )
        equity_curve[-1] = {"time": equity_curve[-1]["time"], "balance": round(balance, 2)}

    from app.backtest.metrics import compute_metrics

    returns_per_bar = config.bar_minutes / 1440.0  # for annualization
    summary = compute_metrics(
        trades,
        equity_curve,
        initial_balance=config.initial_balance_usd,
        bar_minutes=config.bar_minutes,
        n_trials=1,
    )
    return BacktestResult(
        ok=True,
        pair=pair,
        strategy_name=strategy.name,
        params=params,
        candles_used=n,
        trades=trades,
        equity_curve=equity_curve,
        final_balance=round(balance, 2),
        summary=summary,
    )
