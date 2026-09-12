"""
Real Detrended Fluctuation Analysis (DFA) — the standard method for estimating
the Hurst exponent H of a price series.

    H > 0.5  -> persistent / trending
    H ~ 0.5  -> efficient random walk
    H < 0.5  -> anti-persistent / mean-reverting

Input convention: PRICE LEVELS (e.g. closes). Internally the estimator works
on LOG RETURNS — the standard market-regime definition — so a random walk
yields H ≈ 0.5 (white-noise increments), a persistent trend H > 0.5, a
mean-reverting (OU/AR(1)<0) process H < 0.5.

Algorithm (Kantelhardt et al.) applied to the return series r:
  1. Integrated profile Y(i) = cumsum(r - mean(r))
  2. For window sizes n (power-of-2 grid): split profile, fit & remove linear
     trend per window, compute fluctuation F(n) = RMS of detrended profile
  3. H = slope of log F(n) vs log n
"""
from __future__ import annotations

import math
from typing import List

import numpy as np


def hurst_dfa_with_curve(series: List[float], min_scale: int = 4, max_scale_factor: float = 0.25) -> tuple[float, List[Dict[str, float]], float]:
    """Like hurst_dfa but also returns the REAL DFA fluctuation curve
    (scale -> F(n)) and the R² of the log-log fit, for charting/inspection."""
    import math as _m

    prices = np.asarray(series, dtype=float)
    if len(prices) < 4 * min_scale + 1:
        return 0.5, [], 0.0
    prices = prices[~np.isnan(prices)]
    if len(prices) < 4 * min_scale + 1 or np.any(prices <= 0):
        return 0.5, [], 0.0
    x = np.diff(np.log(prices))
    if len(x) < 4 * min_scale:
        return 0.5, [], 0.0
    profile = np.cumsum(x - x.mean())
    max_scale = int(min(len(profile) // 2, len(profile) * max_scale_factor))
    if max_scale < 2 * min_scale:
        return 0.5, [], 0.0
    scales: List[int] = []
    n = min_scale
    while n <= max_scale:
        scales.append(n)
        n *= 2
    pairs: List[tuple] = []
    for scale in scales:
        fluctuations = []
        for start in range(0, len(profile), scale):
            window = profile[start : start + scale]
            if len(window) < scale:
                break
            t = np.arange(scale)
            slope = (scale * np.dot(t, window) - t.sum() * window.sum()) / (scale * (scale * (scale - 1) * (2 * scale - 1) / 6) - t.sum() ** 2)
            intercept = (window.sum() - slope * t.sum()) / scale
            detrended = window - (intercept + slope * t)
            fluctuations.append(detrended.var())
        if not fluctuations:
            continue
        f = math.sqrt(float(np.mean(fluctuations)))
        pairs.append((scale, f))
    if len(pairs) < 2:
        return 0.5, [], 0.0
    log_n = [math.log(s) for s, f in pairs if f > 0]
    log_f = [math.log(f) for s, f in pairs if f > 0]
    slope, intercept = np.polyfit(log_n, log_f, 1)
    # R² of the fit
    ss_res = sum((lf - (slope * ln + intercept)) ** 2 for ln, lf in zip(log_n, log_f))
    mean_f = sum(log_f) / len(log_f)
    ss_tot = sum((lf - mean_f) ** 2 for lf in log_f)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    import math as _m2

    curve = [
        {
            "scale": float(s),
            "fluctuation": round(f, 8),
            "fit": round(_m2.exp(intercept + slope * _m2.log(s)), 8),  # fitted F(s) = s^H (real fit)
        }
        for s, f in pairs
    ]
    return float(slope), curve, float(r2)


def hurst_dfa(series: List[float], min_scale: int = 4, max_scale_factor: float = 0.25) -> float:
    return hurst_dfa_with_curve(series, min_scale, max_scale_factor)[0]
    prices = np.asarray(series, dtype=float)
    if len(prices) < 4 * min_scale + 1:
        return 0.5  # insufficient data -> neutral (documented, not fabricated)
    prices = prices[~np.isnan(prices)]
    if len(prices) < 4 * min_scale + 1 or np.any(prices <= 0):
        return 0.5

    # Work on log returns — the market-regime definition of H
    x = np.diff(np.log(prices))
    if len(x) < 4 * min_scale:
        return 0.5

    profile = np.cumsum(x - x.mean())
    max_scale = int(min(len(profile) // 2, len(profile) * max_scale_factor))
    if max_scale < 2 * min_scale:
        return 0.5

    scales = []
    n = min_scale
    while n <= max_scale:
        scales.append(n)
        n *= 2

    pairs: List[tuple] = []
    for scale in scales:
        fluctuations = []
        for start in range(0, len(profile), scale):
            window = profile[start : start + scale]
            if len(window) < scale:
                break
            t = np.arange(scale)
            # least-squares linear fit
            slope = (scale * np.dot(t, window) - t.sum() * window.sum()) / (scale * (scale * (scale - 1) * (2 * scale - 1) / 6) - t.sum() ** 2)
            intercept = (window.sum() - slope * t.sum()) / scale
            detrended = window - (intercept + slope * t)
            fluctuations.append(detrended.var())
        if not fluctuations:
            continue
        f = math.sqrt(float(np.mean(fluctuations)))
        pairs.append((scale, f))

    if len(pairs) < 2:
        return 0.5
    log_n = [math.log(s) for s, f in pairs if f > 0]
    log_f = [math.log(f) for s, f in pairs if f > 0]
    if len(log_f) < 2:
        return 0.5
    slope, _intercept = np.polyfit(log_n, log_f, 1)
    return float(slope)


def hurst_regime(h: float) -> str:
    if h >= 0.65:
        return "persistent_trending"
    if h >= 0.55:
        return "weakly_trending"
    if h > 0.45:
        return "efficient_random_walk"
    if h > 0.35:
        return "mean_reverting"
    return "strongly_mean_reverting"
