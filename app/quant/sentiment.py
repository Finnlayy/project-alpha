"""
Real funding-flow sentiment score.

Crucially honest: there is no external "news sentiment API" here. This score
is computed from REAL, observable market data available without credentials:

  1. Futures funding rates (Kraken Pro public /funding-rates) — persistent
     positive funding means longs pay shorts (crowded longs → contrarian bear
     pressure); negative funding → crowded shorts.
  2. 24h momentum from real spot tickers (RSI-style position of the move).
  3. Spread pressure from the real ticker frame (spread vs price).

Weighted blend -> score in [-1, +1], positive = bullish lean.
Every input is traceable to an exchange payload; if the feed is offline the
score reports 'unavailable' instead of inventing a number.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def sentiment_from_market_data(
    funding_rates: Optional[List[float]],
    momentum_score: Optional[float],
    spread_score: Optional[float],
    weights: Dict[str, float] = None,
) -> Dict[str, Any]:
    weights = weights or {"funding": 0.5, "momentum": 0.3, "spread": 0.2}

    components: Dict[str, Optional[float]] = {}

    if funding_rates:
        fr = [f for f in funding_rates if f is not None]
        if fr:
            # funding per period, e.g. ~0.01% = 0.0001; normalize: 0.05% sustained = extreme
            mean_fr = sum(fr) / len(fr)
            components["funding"] = max(-1.0, min(1.0, -mean_fr / 0.0005))  # contrarian
        else:
            components["funding"] = None
    else:
        components["funding"] = None

    components["momentum"] = max(-1.0, min(1.0, momentum_score)) if momentum_score is not None else None
    components["spread"] = max(-1.0, min(1.0, spread_score)) if spread_score is not None else None

    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return {
            "score": None,
            "sentiment": "unavailable",
            "components": components,
            "note": "No live market data (funding/momentum/spread) — score withheld rather than fabricated.",
        }

    wsum = sum(weights[k] for k in available)
    score = sum(weights[k] * v for k, v in available.items()) / wsum
    if score >= 0.25:
        label = "bullish"
    elif score <= -0.25:
        label = "bearish"
    else:
        label = "neutral"
    return {
        "score": round(score, 4),
        "sentiment": label,
        "components": {k: (round(v, 4) if v is not None else None) for k, v in components.items()},
        "weights": weights,
        "method": "contrarian funding + 24h momentum + spread pressure (all real exchange data)",
    }
