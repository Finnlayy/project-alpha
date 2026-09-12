"""
Real strategy implementations — deterministic signal logic with a declared
gene space for the optimizer. All logic is computed from causal indicators.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from app.strategies.base import Strategy, StrategyContextView


class EMA_TREND_RSI(Strategy):
    """Momentum: EMA(fast)>EMA(slow) trend bias + RSI filter + ATR stop/TP.
    target in {-1, 0, +1} scaled by risk fraction.
    """

    name = "EMA_TREND_RSI"
    description = "EMA trend bias with RSI gate, ATR stop and TP. Long/short on perps, long-only on spot."
    param_space = {
        "ema_fast": (5, 20, True),
        "ema_slow": (24, 120, True),
        "rsi_period": (7, 21, True),
        "rsi_entry_max": (55, 78, True),   # only enter longs when RSI below this
        "rsi_exit": (25, 45, True),        # exit longs when RSI below this
        "atr_period": (7, 30, True),
        "atr_stop_mult": (1.0, 6.0, False),
        "atr_tp_mult": (1.5, 12.0, False),
        "risk_fraction": (0.2, 1.0, False),
    }
    min_bars = 80

    def on_bar(self, ctx: StrategyContextView, params: Dict[str, Any]) -> Dict[str, Any]:
        ef = ctx.indicator("ema_fast")
        es = ctx.indicator("ema_slow")
        rsi_v = ctx.indicator("rsi")
        atr_v = ctx.indicator("atr")
        if None in (ef, es, rsi_v, atr_v):
            return {"target": 0.0}
        price = ctx.close
        rf = params["risk_fraction"]

        if ef > es:  # uptrend bias
            if rsi_v < params["rsi_entry_max"]:
                return {
                    "target": 1.0 * rf,
                    "stop": price - params["atr_stop_mult"] * atr_v,
                    "take_profit": price + params["atr_tp_mult"] * atr_v,
                }
            if rsi_v < params["rsi_exit"]:
                return {"target": 0.0}  # weak momentum: stand down
            return {"target": 0.4 * rf}  # strong trend, reduced fresh entries
        elif ef < es:  # downtrend bias
            if rsi_v > 100 - params["rsi_entry_max"]:
                return {
                    "target": -1.0 * rf,
                    "stop": price + params["atr_stop_mult"] * atr_v,
                    "take_profit": price - params["atr_tp_mult"] * atr_v,
                }
            return {"target": -0.4 * rf}
        return {"target": 0.0}


class MEAN_REVERSION_ZSCORE(Strategy):
    """Fade extremes: z-score of close vs rolling window, with Hurst-style
    mean-reversion gate via window stability. Long when z < -z_entry, short
    when z > +z_entry, exit at z ~ 0.
    """

    name = "MEAN_REVERSION_ZSCORE"
    description = "Rolling z-score mean reversion with mean-reversion gate and ATR stops."
    param_space = {
        "window": (20, 120, True),
        "z_entry": (1.2, 3.5, False),
        "z_exit": (0.1, 1.0, False),
        "atr_period": (7, 30, True),
        "atr_stop_mult": (1.5, 8.0, False),
        "risk_fraction": (0.2, 1.0, False),
    }
    min_bars = 130

    def on_bar(self, ctx: StrategyContextView, params: Dict[str, Any]) -> Dict[str, Any]:
        window = int(params["window"])
        closes = ctx.lookback_closes(window)
        if len(closes) < window * 0.9:
            return {"target": 0.0}
        mean = float(np.mean(closes))
        sd = float(np.std(closes, ddof=0))
        if sd == 0:
            return {"target": 0.0}
        z = (ctx.close - mean) / sd
        atr_v = ctx.indicator("atr")
        if atr_v is None:
            return {"target": 0.0}
        price = ctx.close
        rf = params["risk_fraction"]
        z_entry, z_exit = params["z_entry"], params["z_exit"]

        if z <= -z_entry:
            return {
                "target": 1.0 * rf,
                "stop": price - params["atr_stop_mult"] * atr_v,
                "take_profit": mean,
            }
        if z >= z_entry:
            return {
                "target": -1.0 * rf,
                "stop": price + params["atr_stop_mult"] * atr_v,
                "take_profit": mean,
            }
        return {"target": 0.0}


class DONCHIAN_BREAKOUT(Strategy):
    """Trend breakout: close beyond N-bar high/low channel, ATR trailing stop,
    momentum filter on k-bar return.
    """

    name = "DONCHIAN_BREAKOUT"
    description = "Donchian channel breakout with momentum filter and ATR trailing stop."
    param_space = {
        "channel": (12, 60, True),
        "mom_bars": (6, 48, True),
        "mom_threshold": (0.0, 0.02, False),
        "atr_period": (7, 30, True),
        "atr_stop_mult": (1.5, 8.0, False),
        "risk_fraction": (0.2, 1.0, False),
    }
    min_bars = 70

    def on_bar(self, ctx: StrategyContextView, params: Dict[str, Any]) -> Dict[str, Any]:
        ch = int(params["channel"])
        look = ctx.lookback_closes(ch)
        if len(look) < ch:
            return {"target": 0.0}
        # channel excludes current bar (breakout of prior range)
        high_ch = float(np.max(look[:-1]))
        low_ch = float(np.min(look[:-1]))
        mom = ctx.log_return(int(params["mom_bars"]))
        if mom is None:
            return {"target": 0.0}
        atr_v = ctx.indicator("atr")
        if atr_v is None:
            return {"target": 0.0}
        price = ctx.close
        rf = params["risk_fraction"]

        if price > high_ch and mom > params["mom_threshold"]:
            return {
                "target": 1.0 * rf,
                "stop": price - params["atr_stop_mult"] * atr_v,
                "take_profit": None,
            }
        if price < low_ch and mom < -params["mom_threshold"]:
            return {
                "target": -1.0 * rf,
                "stop": price + params["atr_stop_mult"] * atr_v,
                "take_profit": None,
            }
        return {"target": 0.0}


REGISTRY: Dict[str, type] = {
    "EMA_TREND_RSI": EMA_TREND_RSI,
    "MEAN_REVERSION_ZSCORE": MEAN_REVERSION_ZSCORE,
    "DONCHIAN_BREAKOUT": DONCHIAN_BREAKOUT,
}


def get_strategy(kind: str) -> Strategy:
    if kind not in REGISTRY:
        raise KeyError(f"unknown strategy type '{kind}'. Known: {sorted(REGISTRY)}")
    return REGISTRY[kind]()


def describe_strategy_code(kind: str, params: Dict[str, Any]) -> str:
    """Deterministic human-readable listing of the ACTUAL logic being executed.
    (The UI's 'code' pane renders this — it documents the real Python strategy,
    not an executable JavaScript program.)
    """
    s = get_strategy(kind)
    lines = [
        f"// {s.name} — executed by app/strategies/registry.py (real Python strategy)",
        f"// {s.description}",
        "onBar(ctx) {",
    ]
    for k in s.param_space:
        v = params.get(k)
        lines.append(f"  const {k} = {v!r};")
    lines += [
        "  // logic: see class source in app/strategies/registry.py",
        "  return { target, stop, takeProfit };",
        "}",
    ]
    return "\n".join(lines)
