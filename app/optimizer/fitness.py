"""
Multi-objective fitness — a faithful port of the blueprint's optimizer math
(src/optimizer/MultiObjectiveFitnessEngine.ts + CadenceFitnessModule.ts) into
Python, operating on REAL backtest results.

    fitness = DSR_net * ln(1 + annualizedNetReturn) * P_sample * P_complexity

Hard guardrails:
    - Trade starvation: N < 30  -> 0.0
    - Fee drag: netPnL <= 0    -> 0.0
Cadence bandpass:
    - Gaussian penalty around ideal 4.5 trades/day (3..6 target corridor)
    - rhythm CV of inter-trade intervals reported for inspection
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np

MIN_TRADES_ABSOLUTE = 30
MIN_TRADES_TARGET = 80
MAX_ALLOWED_RULES = 6
CADENCE_MIN = 3.0
CADENCE_MAX = 6.0
CADENCE_IDEAL = (CADENCE_MIN + CADENCE_MAX) / 2.0
CADENCE_SIGMA = 1.25


def evaluate_fitness(
    summary: Dict[str, Any],
    active_rule_count: int,
    evaluation_days: float,
) -> Dict[str, Any]:
    dsr = float(summary.get("deflatedSharpeRatio", 0.0))
    annual_ret = float(summary.get("annualizedReturnPercent", 0.0)) / 100.0
    net_pnl = float(summary["finalBalance"]) - float(summary["initialBalance"])
    n_trades = int(summary.get("totalTrades", 0))

    if n_trades < MIN_TRADES_ABSOLUTE:
        return {
            "fitnessScore": 0.0,
            "isValidCandidate": False,
            "rejectionReason": f"TRADE STARVATION: {n_trades} trades < {MIN_TRADES_ABSOLUTE}",
            "samplePenalty": 0.0,
            "complexityPenalty": 1.0,
        }
    if net_pnl <= 0:
        return {
            "fitnessScore": 0.0,
            "isValidCandidate": False,
            "rejectionReason": f"FEE DRAG DEATH: net PnL ${net_pnl:.2f} after ${summary.get('totalFeesUSD', 0):.2f} fees",
            "samplePenalty": 1.0,
            "complexityPenalty": 1.0,
        }

    sample_penalty = 1.0
    if n_trades < MIN_TRADES_TARGET:
        x = (n_trades - MIN_TRADES_ABSOLUTE) / (MIN_TRADES_TARGET - MIN_TRADES_ABSOLUTE)
        sample_penalty = x**2

    complexity_penalty = 1.0
    if active_rule_count > MAX_ALLOWED_RULES:
        complexity_penalty = math.exp(-0.15 * (active_rule_count - MAX_ALLOWED_RULES))

    net_return_factor = math.log(1.0 + max(0.0, annual_ret))
    raw = dsr * net_return_factor * sample_penalty * complexity_penalty
    final = max(0.0, raw)
    is_valid = final > 0.35 and dsr >= 0.95

    return {
        "fitnessScore": round(final, 4),
        "isValidCandidate": is_valid,
        "rejectionReason": None if is_valid else f"fitness {final:.4f} / DSR {dsr:.2f} below thresholds",
        "samplePenalty": round(sample_penalty, 4),
        "complexityPenalty": round(complexity_penalty, 4),
    }


def evaluate_cadence(trade_times: List[float], evaluation_days: float) -> Dict[str, Any]:
    """trade_times: epoch seconds of trade exits."""
    if evaluation_days <= 0 or not trade_times:
        return {"tradesPerDay": 0.0, "cadenceScore": 0.0, "isWithinTargetRange": False, "rhythmCv": 0.0, "rejectionReason": "no trades"}
    tpd = len(trade_times) / evaluation_days
    score = math.exp(-((tpd - CADENCE_IDEAL) ** 2) / (2 * CADENCE_SIGMA**2))
    cv = 1.0
    if len(trade_times) >= 3:
        ts = sorted(trade_times)
        intervals = np.diff(ts)
        mean_iv = float(np.mean(intervals))
        if mean_iv > 0:
            cv = float(np.std(intervals, ddof=0) / mean_iv)
    if tpd < CADENCE_MIN:
        reason = f"CADENCE DEFECTION: {tpd:.2f} trades/day below {CADENCE_MIN}"
    elif tpd > CADENCE_MAX:
        reason = f"CADENCE EXCESS: {tpd:.2f} trades/day above {CADENCE_MAX}"
    else:
        reason = None
    return {
        "tradesPerDay": round(tpd, 2),
        "cadenceScore": round(score, 4),
        "isWithinTargetRange": CADENCE_MIN <= tpd <= CADENCE_MAX,
        "rhythmCv": round(cv, 2),
        "rejectionReason": reason,
    }
