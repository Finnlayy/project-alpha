"""
Real lead-lag cross-impact analysis between two assets.

Computes the cross-correlation of 1-bar log returns over lags -L..+L and
reports the leader, follower, optimal lag and correlation strength.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from app.quant import indicators as ta


def cross_impact(
    leader_candidate: List[float],
    follower_candidate: List[float],
    bar_minutes: int,
    max_lag_bars: int = 30,
) -> Dict[str, Any]:
    a = np.asarray(leader_candidate, dtype=float)
    b = np.asarray(follower_candidate, dtype=float)
    m = min(len(a), len(b))
    if m < 100:
        return {
            "leader": None,
            "follower": None,
            "lagBars": 0,
            "lagSeconds": 0,
            "crossCorrelation": 0.0,
            "barsUsed": m,
            "error": "insufficient data (need >= 100 aligned bars per series)",
        }
    a, b = a[-m:], b[-m:]
    ra = np.diff(np.log(np.clip(a, 1e-12, None)))
    rb = np.diff(np.log(np.clip(b, 1e-12, None)))
    lags = min(max_lag_bars, len(ra) // 3)
    corrs, best_lag = ta.cross_correlation(ra, rb, lags)
    corr = float(corrs[int(np.argmax(np.abs(corrs)))])

    if best_lag >= 0:
        leader, follower = "A (leader candidate)", "B (follower candidate)"
    else:
        leader, follower = "B (follower candidate)", "A (leader candidate)"
    corr = abs(corr)  # magnitude; leader/follower fields carry direction

    return {
        "leader": leader,
        "follower": follower,
        "lagBars": abs(best_lag),
        "lagSeconds": abs(best_lag) * bar_minutes * 60,
        "crossCorrelation": round(corr, 4),
        "barsUsed": len(ra),
        "maxLagBars": lags,
        "method": "cross-correlation of 1-bar log returns, |max| selection",
    }
