"""
Golden tests for the quant math: DFA Hurst, indicators, regime, lead-lag.
All reference values are either hand-computed or derived from the defining
mathematical properties of the estimators.
"""
import math
import random

import numpy as np
import pytest

from app.quant import indicators as ta
from app.quant.hurst import hurst_dfa, hurst_regime
from app.quant.lead_lag import cross_impact
from app.quant.regime import classify_regime
from app.quant.sentiment import sentiment_from_market_data


# --------------------------------------------------------------------- Hurst
def test_hurst_trending_series_above_half():
    # Persistent returns: AR(1) with phi=0.35 + positive drift
    rng = random.Random(7)
    price, r = 100.0, 0.001
    trend = [price]
    for _ in range(1023):
        r = 0.35 * r + 0.0008 + rng.gauss(0, 0.0006)
        price *= 1.0 + r
        trend.append(price)
    h = hurst_dfa(trend)
    assert h > 0.6, f"persistent AR(1) returns must be trending, got H={h}"


def test_hurst_random_walk_near_half_ensemble():
    # Ensemble of independent random walks: individual draws are noisy,
    # the estimator must center on 0.5 with no systematic bias.
    hs = []
    for seed in range(12):
        rng = random.Random(100 + seed)
        walk = [100.0]
        for _ in range(1023):
            walk.append(walk[-1] * (1 + rng.gauss(0, 0.002)))
        hs.append(hurst_dfa(walk))
    mean_h = sum(hs) / len(hs)
    assert 0.42 < mean_h < 0.58, f"ensemble mean of random-walk H should be ~0.5, got {mean_h}"
    assert max(hs) < 0.8 and min(hs) > 0.2, f"individual draws wildly off: {hs}"


def test_hurst_mean_reverting_below_half():
    # OU process with strong negative feedback (x += -0.5*(x-100) + noise)
    rng = random.Random(3)
    x = 100.0
    series = [x]
    for _ in range(1023):
        x += -0.5 * (x - 100.0) + rng.gauss(0, 0.8)
        series.append(max(x, 1.0))
    h = hurst_dfa(series)
    assert h < 0.5, f"mean-reverting OU process must be anti-persistent, got H={h}"


def test_hurst_insufficient_data_neutral():
    assert hurst_dfa([1.0, 2.0, 3.0]) == 0.5


def test_hurst_regime_labels():
    assert hurst_regime(0.7) == "persistent_trending"
    assert hurst_regime(0.5) == "efficient_random_walk"
    assert hurst_regime(0.3) == "strongly_mean_reverting"


# ---------------------------------------------------------------- indicators
def test_ema_matches_recursive_definition():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    period = 3
    out = ta.ema(np.array(values), period)
    k = 2 / (period + 1)
    expected = [None, None, np.mean(values[:3])]
    for i in range(3, len(values)):
        expected.append(values[i] * k + expected[-1] * (1 - k))
    for i in range(period - 1, len(values)):
        assert abs(out[i] - expected[i]) < 1e-12


def test_rsi_all_gains_is_100():
    up = np.array([float(i) for i in range(1, 40)])
    r = ta.rsi(up, 14)
    assert abs(r[-1] - 100.0) < 1e-9


def test_rsi_all_losses_is_0():
    down = np.array([float(40 - i) for i in range(39)])
    r = ta.rsi(down, 14)
    assert r[-1] < 1e-9


def test_rsi_matches_naive_wilder_reference():
    # Independent naive re-implementation of Wilder's RSI, compared pointwise
    rng = random.Random(17)
    closes = [100.0]
    for _ in range(199):
        closes.append(closes[-1] * (1 + rng.gauss(0, 0.008)))

    period = 14
    delta = [closes[i + 1] - closes[i] for i in range(len(closes) - 1)]
    gains = [max(d, 0.0) for d in delta]
    losses = [max(-d, 0.0) for d in delta]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period

    def naive_rsi_at(idx_delta):  # idx_delta: index in delta where the RSI closes
        if idx_delta == period - 1:
            g, l = sum(gains[:period]) / period, sum(losses[:period]) / period
        else:
            g = avg_g
            l = avg_l
            for i in range(period, idx_delta + 1):
                g = (g * (period - 1) + gains[i]) / period
                l = (l * (period - 1) + losses[i]) / period
        return 100.0 if l == 0 else 100.0 - 100.0 / (1 + g / l)

    r = ta.rsi(np.array(closes), period)
    for closes_idx in (period, period + 5, len(closes) - 1):
        assert abs(r[closes_idx] - naive_rsi_at(closes_idx - 1)) < 1e-9


def test_atr_positive_and_finite():
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 0.5, 200))
    high = close + np.abs(rng.normal(0, 0.4, 200))
    low = close - np.abs(rng.normal(0, 0.4, 200))
    a = ta.atr(high, low, close, 14)
    assert np.all(a[14:] > 0)
    assert np.all(np.isfinite(a[14:]))


def test_bollinger_bounds():
    values = np.sin(np.linspace(0, 4 * math.pi, 100)) + 1.5
    upper, mid, lower = ta.bollinger(values, 20, 2.0)
    valid = ~np.isnan(mid)
    assert np.all(upper[valid] >= mid[valid])
    assert np.all(lower[valid] <= mid[valid])


def test_bandpass_power_concentrated_in_band():
    t = np.arange(400) / 400.0  # 1s at fs=400Hz
    x = np.sin(2 * math.pi * 10 * t) + 0.05 * np.random.default_rng(2).normal(0, 1, 400)
    power = ta.bandpass_power(x, fs=400.0, low_hz=8, high_hz=12)
    assert power > 0.8, f"10Hz tone in [8,12]Hz band, got {power}"
    out_of_band = ta.bandpass_power(x, fs=400.0, low_hz=50, high_hz=60)
    assert out_of_band < 0.05


def test_cross_correlation_detects_lag():
    rng = np.random.default_rng(5)
    a = rng.normal(0, 1, 500)
    lag = 5
    b = np.roll(a, lag)  # b[i] = a[i-lag]  ->  a leads b by `lag`
    corrs, best = ta.cross_correlation(a, b, 10)
    assert best == lag, f"expected a to lead by {lag}, got {best}"


# -------------------------------------------------------------------- regime
def test_regime_trending_is_green():
    rng = random.Random(11)
    price, r = 100.0, 0.001
    closes = [price]
    for _ in range(399):
        r = 0.35 * r + 0.0009 + rng.gauss(0, 0.0006)
        price *= 1.0 + r
        closes.append(price)
    highs = [c * 1.001 for c in closes]
    lows = [c * 0.999 for c in closes]
    result = classify_regime(closes, highs, lows, bar_minutes=15)
    assert result["bars"] == 400
    assert result["state"] == "GREEN", f"strong persistent uptrend must be GREEN, got {result['state']} ({result['details']})"
    assert result["signal"].startswith("MOMENTUM")
    assert result["details"]["hurst"] > 0.55


def test_regime_insufficient_data():
    r = classify_regime([1, 2, 3], [1, 2, 3], [1, 2, 3], 5)
    assert r["signal"] == "NO_DATA"


# ------------------------------------------------------------------ lead-lag
def test_cross_impact_detects_leader():
    rng = np.random.default_rng(9)
    base = rng.normal(0, 1, 600)
    follower = np.roll(base, 3)
    follower[:3] = base[:3]
    a = 100 * np.exp(np.cumsum(base * 0.001))
    b = 100 * np.exp(np.cumsum(follower * 0.001))
    res = cross_impact(list(a), list(b), bar_minutes=1, max_lag_bars=10)
    assert res["leader"].startswith("A")
    assert res["lagBars"] == 3
    assert res["crossCorrelation"] > 0.7


def test_cross_impact_insufficient_data():
    res = cross_impact([1, 2, 3], [1, 2, 3], 5)
    assert res.get("error")


# ----------------------------------------------------------------- sentiment
def test_sentiment_contradictory_inputs():
    res = sentiment_from_market_data(funding_rates=[0.0004, 0.0005], momentum_score=0.5, spread_score=-0.5)
    assert res["score"] is not None
    assert -1.0 <= res["score"] <= 1.0
    # positive funding (crowded longs) should drag the contrarian component negative
    assert res["components"]["funding"] < 0


def test_sentiment_no_data_withheld():
    res = sentiment_from_market_data(funding_rates=None, momentum_score=None, spread_score=None)
    assert res["score"] is None
    assert res["sentiment"] == "unavailable"
