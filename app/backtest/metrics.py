"""
Real performance metrics from trades + equity curve.
Standard formulas only; every output is reproducible from the inputs.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Dict, List

import numpy as np

_N = NormalDist()


def max_drawdown(equity: List[float]) -> float:
    """Maximum peak-to-trough drawdown as a positive percentage."""
    if len(equity) < 2:
        return 0.0
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak * 100.0)
    return mdd


def sharpe_ratio(bar_returns: np.ndarray, periods_per_year: float) -> float:
    if len(bar_returns) < 2:
        return 0.0
    sd = float(np.std(bar_returns, ddof=1))
    if sd == 0:
        return 0.0
    return float(np.mean(bar_returns) / sd * math.sqrt(periods_per_year))


def sortino_ratio(bar_returns: np.ndarray, periods_per_year: float) -> float:
    if len(bar_returns) < 2:
        return 0.0
    downside = bar_returns[bar_returns < 0]
    if len(downside) == 0:
        return 0.0
    dstd = float(np.sqrt(np.mean(downside**2)))
    if dstd == 0:
        return 0.0
    return float(np.mean(bar_returns) / dstd * math.sqrt(periods_per_year))


def deflated_sharpe_ratio(
    bar_returns: np.ndarray,
    periods_per_year: float,
    n_trials: int,
) -> float:
    """Bailey & López de Pedraza (2014) Deflated Sharpe Ratio.

    DSR = P(SR_true > 0 | observed SR, number of trials) under the null of
    zero drift:
      se(SR)   = sqrt( (1 - skew*SR + (kurt-1)/4 * SR^2) / T )
      SR0      = sigma_SR * Phi^{-1}(1 - 1/N_trials)   (expected max under null)
      DSR      = Phi( (SR - SR0) / se )
    with sigma_SR = 1/sqrt(T) for i.i.d. normal returns.
    """
    if len(bar_returns) < 30:
        return 0.0
    T = len(bar_returns)
    sd = float(np.std(bar_returns, ddof=1))
    if sd == 0:
        return 0.0
    SR = float(np.mean(bar_returns) / sd * math.sqrt(periods_per_year))
    # higher moments of per-period returns
    r = (bar_returns - bar_returns.mean()) / sd
    skew = float(np.mean(r**3))
    kurt = float(np.mean(r**4))
    var_term = 1.0 - skew * (SR / math.sqrt(periods_per_year)) + (kurt - 1) / 4.0 * (SR / math.sqrt(periods_per_year)) ** 2
    if var_term <= 0:
        return 0.0
    se = math.sqrt(var_term / T)
    sr0 = (1.0 / math.sqrt(T)) * _N.inv_cdf(1.0 - 1.0 / max(2, n_trials))
    z = (SR - sr0) / se
    return float(_N.cdf(z))


def compute_metrics(
    trades: List[Any],  # app.backtest.engine.Trade
    equity_curve: List[Dict[str, Any]],
    initial_balance: float,
    bar_minutes: int,
    n_trials: int = 1,
) -> Dict[str, Any]:
    eq = [row["balance"] for row in equity_curve] or [initial_balance]
    eq_arr = np.array(eq, dtype=float)
    periods_per_year = 525600.0 / bar_minutes

    if len(eq_arr) >= 2:
        bar_returns = np.diff(eq_arr) / np.where(eq_arr[:-1] == 0, 1.0, eq_arr[:-1])
    else:
        bar_returns = np.array([])

    sharpe = sharpe_ratio(bar_returns, periods_per_year)
    sortino = sortino_ratio(bar_returns, periods_per_year)
    mdd = max_drawdown(list(eq_arr))
    calmar = (float(eq_arr[-1]) / initial_balance - 1.0) * (periods_per_year / max(1, len(eq_arr))) / mdd if mdd > 0 else 0.0

    net_pnls = np.array([t.net_pnl_usd for t in trades], dtype=float)
    wins = net_pnls[net_pnls > 0]
    losses = net_pnls[net_pnls <= 0]
    profit_factor = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else (float("inf") if len(wins) else 0.0)
    if math.isinf(profit_factor):
        profit_factor = 999.0

    total_fees = sum(t.fee_usd for t in trades)
    total_funding = sum(t.funding_usd for t in trades)
    final_balance = float(eq_arr[-1])
    total_return_pct = (final_balance / initial_balance - 1.0) * 100.0
    n_bars = max(1, len(eq_arr))
    annualized_return_pct = ((final_balance / initial_balance) ** (periods_per_year / n_bars) - 1.0) * 100.0 if final_balance > 0 else -100.0

    dsr = deflated_sharpe_ratio(bar_returns, periods_per_year, n_trials)

    return {
        "initialBalance": initial_balance,
        "finalBalance": round(final_balance, 2),
        "totalReturnUSD": round(final_balance - initial_balance, 2),
        "totalReturnPercent": round(total_return_pct, 4),
        "annualizedReturnPercent": round(annualized_return_pct, 4),
        "maxDrawdownPercent": round(mdd, 4),
        "sharpeRatio": round(sharpe, 4),
        "sortinoRatio": round(sortino, 4),
        "calmarRatio": round(calmar, 4),
        "deflatedSharpeRatio": round(dsr, 4),
        "winRate": round(100.0 * len(wins) / len(trades), 2) if trades else 0.0,
        "totalTrades": len(trades),
        "winningTrades": int(len(wins)),
        "losingTrades": int(len(losses)),
        "profitFactor": round(profit_factor, 4),
        "averageTradeReturn": round(float(net_pnls.mean()), 2) if len(net_pnls) else 0.0,
        "bestTradeUSD": round(float(net_pnls.max()), 2) if len(net_pnls) else 0.0,
        "worstTradeUSD": round(float(net_pnls.min()), 2) if len(net_pnls) else 0.0,
        "totalFeesUSD": round(total_fees, 4),
        "totalFundingUSD": round(total_funding, 4),
        "totalVolumeUSD": round(sum(t.notional_usd for t in trades), 2),
        "averageMFE_Pct": round(float(np.mean([t.mfe_pct for t in trades])), 4) if trades else 0.0,
        "averageMAE_Pct": round(float(np.mean([t.mae_pct for t in trades])), 4) if trades else 0.0,
    }
