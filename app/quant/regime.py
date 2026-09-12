"""
Real market-regime classifier (Ampel / traffic-light).

Inputs are computed from REAL price history only:
  - DFA Hurst exponent   -> persistence vs mean-reversion
  - Wilder ADX(14)       -> trend strength
  - Annualized realized vol (30 bars) -> volatility gate
  - Momentum: log return over lookback
Deterministic output: state GREEN/AMBER/RED + component scores + suggested bias.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from app.quant import indicators as ta
from app.quant.hurst import hurst_dfa, hurst_regime


def classify_regime(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    bar_minutes: int,
    momentum_lookback: int = 288,
) -> Dict[str, Any]:
    c = np.asarray(closes, dtype=float)
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    n = len(c)

    result: Dict[str, Any] = {
        "symbol": None,
        "state": "UNKNOWN",
        "trendScore": 0.0,
        "meanReversionScore": 0.0,
        "volatilityScore": 0.0,
        "signal": "NO_DATA",
        "details": {},
        "bars": n,
    }
    if n < 60:
        return result

    hurst = hurst_dfa(list(c[-512:]))
    adx_arr = ta.adx(h, l, c, 14)
    adx_now = float(adx_arr[-1]) if not np.isnan(adx_arr[-1]) else 0.0
    rets = np.diff(np.log(np.clip(c, 1e-12, None)))
    ppy = 525600.0 / bar_minutes  # periods per year
    vol30 = ta.realized_volatility(rets[-30:], ppy) if len(rets) >= 30 else 0.0
    lookback = min(momentum_lookback, n - 1)
    mom = float(np.log(c[-1] / c[-lookback - 1])) if lookback > 0 else 0.0

    # Component scores in [0,1]
    trend_score = min(1.0, max(0.0, (adx_now - 10.0) / 30.0)) * (1.0 if hurst > 0.5 else 0.5)
    mr_score = min(1.0, (0.5 - hurst) / 0.15) if hurst < 0.5 else 0.0
    vol_score = min(1.0, vol30 / 1.5)  # 150% annualized vol = max

    # Traffic light
    directional = (1.0 if mom >= 0 else -1.0) * min(1.0, abs(mom) * 10.0)
    if trend_score >= 0.5 and adx_now >= 20:
        state, signal = "GREEN", ("MOMENTUM_LONG" if mom >= 0 else "MOMENTUM_SHORT")
    elif vol_score >= 0.85:
        state, signal = "RED", "FLAT_HIGHER_VOL"
    elif mr_score >= 0.4:
        state, signal = "AMBER", ("FADE_EXTREMES_LONG" if mom < 0 else "FADE_EXTREMES_SHORT")
    else:
        state, signal = "AMBER", "STAND_BY"

    result.update(
        {
            "state": state,
            "trendScore": round(trend_score, 4),
            "meanReversionScore": round(mr_score, 4),
            "volatilityScore": round(vol_score, 4),
            "signal": signal,
            "details": {
                "hurst": round(hurst, 4),
                "hurstRegime": hurst_regime(hurst),
                "adx14": round(adx_now, 2),
                "realizedVolAnnualized": round(vol30, 4),
                "momentumLogReturn": round(mom, 6),
                "directionalPressure": round(directional, 4),
                "method": "DFA + ADX(14) + realized vol (30 bars) — real data only",
            },
        }
    )
    return result
