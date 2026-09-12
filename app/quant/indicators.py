"""
Real technical indicators — pure NumPy implementations with standard formulas.
No randomness, no look-ahead: every value at index i uses data up to i only.
"""
from __future__ import annotations

import numpy as np


def sma(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if period <= 0 or len(values) < period:
        return out
    csum = np.cumsum(np.insert(values, 0, 0.0))
    out[period - 1 :] = (csum[period:] - csum[:-period]) / period
    return out


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """Standard EMA with SMA seed. out[i] valid for i >= period-1."""
    out = np.full(len(values), np.nan)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    seed = float(np.mean(values[:period]))
    out[period - 1] = seed
    for i in range(period, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1.0 - k)
    return out


def rsi(values: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's RSI."""
    out = np.full(len(values), np.nan)
    if len(values) <= period:
        return out
    delta = np.diff(values)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = float(np.mean(gain[:period]))
    avg_loss = float(np.mean(loss[:period]))
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gain[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i - 1]) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = np.concatenate(([close[0]], close[:-1]))
    return np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's ATR."""
    tr = true_range(high, low, close)
    out = np.full(len(close), np.nan)
    if len(close) <= period:
        return out
    out[period] = float(np.mean(tr[1 : period + 1]))
    for i in range(period + 1, len(close)):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def bollinger(values: np.ndarray, period: int = 20, num_std: float = 2.0):
    mid = sma(values, period)
    sd = np.full(len(values), np.nan)
    for i in range(period - 1, len(values)):
        sd[i] = float(np.std(values[i - period + 1 : i + 1], ddof=0))
    upper = mid + num_std * sd
    lower = mid - num_std * sd
    return upper, mid, lower


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's ADX (trend strength 0..100)."""
    out = np.full(len(close), np.nan)
    if len(close) <= 2 * period:
        return out
    up = np.diff(high)
    down = -np.diff(low)
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(high, low, close)[1:]
    atr_ = np.full(len(tr), np.nan)
    atr_[period - 1] = float(np.sum(tr[:period]))
    for i in range(period, len(tr)):
        atr_[i] = atr_[i - 1] - atr_[i - 1] / period + tr[i]
    plus_di = np.full(len(close), np.nan)
    minus_di = np.full(len(close), np.nan)
    pdm_s = float(np.sum(plus_dm[:period]))
    mdm_s = float(np.sum(minus_dm[:period]))
    for i in range(period - 1, len(tr)):
        if i > period - 1:
            pdm_s = pdm_s - pdm_s / period + plus_dm[i]
            mdm_s = mdm_s - mdm_s / period + minus_dm[i]
        if atr_[i - 1] > 0:
            plus_di[i + 1] = 100.0 * pdm_s / atr_[i - 1]
            minus_di[i + 1] = 100.0 * mdm_s / atr_[i - 1]
    dx = np.where(
        (plus_di + minus_di) > 0,
        100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di),
        0.0,
    )
    valid = ~np.isnan(dx)
    if valid.sum() >= period:
        idxs = np.where(valid)[0]
        out[period] = float(np.mean(dx[idxs[0] : idxs[0] + period]))
        for i in range(period + 1, len(close)):
            if np.isnan(out[i - 1]):
                continue
            out[i] = (out[i - 1] * (period - 1) + (dx[i] if not np.isnan(dx[i]) else 0.0)) / period
    return out


def realized_volatility(returns: np.ndarray, periods_per_year: float) -> float:
    """Annualized realized volatility from log returns."""
    if len(returns) < 2:
        return 0.0
    return float(np.std(returns, ddof=1) * np.sqrt(periods_per_year))


def bandpass_power(values: np.ndarray, fs: float, low_hz: float, high_hz: float) -> float:
    """Fraction of spectral power inside [low_hz, high_hz] (FFT bandpass).
    Used by the cadence bandpass strategy: high value = rhythmic oscillation.
    """
    x = np.asarray(values, dtype=float)
    if len(x) < 16:
        return 0.0
    x = x - x.mean()
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), d=1.0 / fs)
    total = spectrum.sum()
    if total <= 0:
        return 0.0
    in_band = spectrum[(freqs >= low_hz) & (freqs <= high_hz)].sum()
    return float(in_band / total)


def cross_correlation(a: np.ndarray, b: np.ndarray, max_lag: int) -> tuple[np.ndarray, int]:
    """Cross-correlation of two return series across lags -max_lag..+max_lag.

    Convention: positive lag = a LEADS b.
      lag = +k  -> corr( r_a[t], r_b[t+k] )
      lag = -k  -> corr( r_a[t+k], r_b[t] )
    """
    a = a - a.mean()
    b = b - b.mean()
    n = min(len(a), len(b))
    a, b = a[-n:], b[-n:]
    lags = np.arange(-max_lag, max_lag + 1)
    corrs = np.zeros(len(lags))
    for i, lag in enumerate(lags):
        if lag >= 0:
            x, y = a[: n - lag], b[lag:]
        else:
            x, y = a[-lag:], b[: n + lag]
        if len(x) < 10:
            continue
        if np.std(x) == 0 or np.std(y) == 0:
            continue
        corrs[i] = float(np.corrcoef(x, y)[0, 1])
    best = int(np.argmax(np.abs(corrs)))
    return corrs, int(lags[best])
