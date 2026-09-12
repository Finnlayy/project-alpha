"""
Strategy interface + pre-computed indicator context.

A strategy is a deterministic function of (indicator context at bar i, params).
No network, no randomness, no future data: the context at bar i contains only
values computed from data up to and including bar i (all indicators here are
causal by construction).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class StrategyContext:
    """Full indicator arrays + windowed access. `.at(i)` freezes the view at bar i."""

    opens: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
    volumes: np.ndarray
    times: np.ndarray
    ema_fast: np.ndarray
    ema_slow: np.ndarray
    rsi: np.ndarray
    atr: np.ndarray
    bar_minutes: int = 15

    def at(self, i: int) -> "StrategyContextView":
        return StrategyContextView(self, i)


class StrategyContextView:
    """Immutably-indexed view of the context at a single (closed) bar."""

    __slots__ = ("_c", "i")

    def __init__(self, c: StrategyContext, i: int):
        self._c = c
        self.i = i

    @property
    def close(self) -> float:
        return float(self._c.closes[self.i])

    @property
    def open(self) -> float:
        return float(self._c.opens[self.i])

    @property
    def high(self) -> float:
        return float(self._c.highs[self.i])

    @property
    def low(self) -> float:
        return float(self._c.lows[self.i])

    @property
    def volume(self) -> float:
        return float(self._c.volumes[self.i])

    @property
    def time(self) -> float:
        return float(self._c.times[self.i])

    def indicator(self, name: str) -> Optional[float]:
        arr = {
            "ema_fast": self._c.ema_fast,
            "ema_slow": self._c.ema_slow,
            "rsi": self._c.rsi,
            "atr": self._c.atr,
        }.get(name)
        if arr is None or self.i >= len(arr):
            return None
        v = float(arr[self.i])
        return None if np.isnan(v) else v

    def lookback_closes(self, k: int) -> np.ndarray:
        end = self.i + 1
        start = max(0, end - k)
        return self._c.closes[start:end]

    def log_return(self, bars: int) -> Optional[float]:
        if self.i - bars < 0:
            return None
        return float(np.log(self.close / self._c.closes[self.i - bars]))


class Strategy:
    """Base class. Subclasses declare their gene space and implement on_bar."""

    name: str = "BaseStrategy"
    description: str = ""
    param_space: Dict[str, tuple] = {}  # name -> (min, max, is_int)
    min_bars: int = 60
    default_risk_fraction: float = 1.0  # scales |target| (0.5 = half size)

    def indicator_periods(self, params: Dict[str, Any]) -> Dict[str, int]:
        """Which indicator windows to pre-compute for this parameter set."""
        return {
            "fast": int(params.get("ema_fast", 12)),
            "slow": int(params.get("ema_slow", 48)),
            "rsi": int(params.get("rsi_period", 14)),
            "atr": int(params.get("atr_period", 14)),
        }

    def default_params(self) -> Dict[str, Any]:
        out = {}
        for k, (lo, hi, is_int) in self.param_space.items():
            v = (lo + hi) / 2.0
            out[k] = int(round(v)) if is_int else v
        return out

    def on_bar(self, ctx: StrategyContextView, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return {'target': -1..1, 'stop': price|None, 'take_profit': price|None}."""
        raise NotImplementedError

    # convenience for the optimizer
    def clamp_genes(self, genes: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k, (lo, hi, is_int) in self.param_space.items():
            v = genes.get(k, (lo + hi) / 2)
            v = max(lo, min(hi, v))
            out[k] = int(round(v)) if is_int else float(v)
        # keep any extra (non-gene) params
        for k, v in genes.items():
            if k not in self.param_space:
                out[k] = v
        return out

    @property
    def active_rule_count(self) -> int:
        """Number of active decision rules (for the complexity penalty)."""
        return len(self.param_space)
