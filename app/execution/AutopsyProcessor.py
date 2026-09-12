"""
=========================================================
Datei:      app/execution/AutopsyProcessor.py (v1.7.0)
Zweck:      Klassifikation von Autopsie-Zonen, R-Multiples & Slippage-Auditing
Knoten:     Jaune (Carrera-Engine) / Post-Trade Autopsy Core
System:     "The Judge & The Swarm" - Zero-Dummy Guarantee
=========================================================
"""
from __future__ import annotations
import logging
from typing import Any, Dict

logger = logging.getLogger("app.execution.autopsy_processor")


def calculate_r_multiples(
    pnl_pct: float,
    mfe_pct: float,
    mae_pct: float,
    stop_distance_pct: float
) -> Dict[str, float]:
    """
    Berechnet die R-Multiples für einen abgeschlossenen Trade:
    - pnl_r: Realisierte Rendite relativ zum Initial-Risk
    - mfe_r: Maximum Favorable Excursion (maximaler Buchgewinn)
    - mae_r: Maximum Adverse Excursion (maximaler Buchverlust)
    - capture_ratio: Effizienz der Gewinnsicherung (pnl_r / mfe_r)
    """
    if stop_distance_pct <= 0.0:
        raise ValueError("stop_distance_pct muss > 0 sein")

    pnl_r = pnl_pct / stop_distance_pct
    mfe_r = mfe_pct / stop_distance_pct
    mae_r = mae_pct / stop_distance_pct

    capture_ratio = (pnl_r / mfe_r) if mfe_r > 0.0 else 0.0

    return {
        "pnl_r": round(pnl_r, 4),
        "mfe_r": round(mfe_r, 4),
        "mae_r": round(mae_r, 4),
        "capture_ratio": round(capture_ratio, 4)
    }


def calculate_stop_slippage(
    trigger_price: float,
    fill_price: float,
    exit_reason: str,
    threshold_bps: float = 15.0
) -> bool:
    """
    Prüft, ob bei einer Stop-Loss-Order eine signifikante Slippage über der Schwelle (bps) auftrat.
    """
    if exit_reason.upper() != "STOP_LOSS":
        return False

    if trigger_price <= 0.0:
        return False

    slippage_bps = (abs(fill_price - trigger_price) / trigger_price) * 10000.0
    return slippage_bps >= threshold_bps


def classify_autopsy_zone(
    pnl_r: float,
    mfe_r: float,
    exit_reason: str,
    capture_ratio: float
) -> str:
    """
    Klassifiziert die Ausführungsqualität eines Trades in Zonen:
    - GOOD: Profitabel mit hoher Gewinnschöpfung (Capture Ratio >= 0.55)
    - WATCH: Profitabel, aber Gewinne wurden im Rücklauf stark verschenkt
    - BAD: MFE >= 0.5R, aber Trade endete im Verlust (fehlender Trailing Stop!)
    - CLEAN_LOSS: Geplanter Stop-Loss ohne nennenswerte Zwischengewinne
    - NEUTRAL_LOSS: Sonstiger Verlust (z.B. Time-Stop oder Regime-Cut)
    """
    if pnl_r > 0.0:
        return "GOOD" if capture_ratio >= 0.55 else "WATCH"
    else:
        if mfe_r >= 0.5:
            return "BAD"
        elif exit_reason.upper() == "STOP_LOSS":
            return "CLEAN_LOSS"
        else:
            return "NEUTRAL_LOSS"


def build_full_trade_autopsy(
    trade_id: str,
    instance_id: str,
    entry_price: float,
    exit_price: float,
    stop_price: float,
    highest_price: float,
    lowest_price: float,
    direction: str,
    exit_reason: str
) -> Dict[str, Any]:
    """Generiert einen vollständigen post-mortem Autopsie-Bericht."""
    is_long = direction.upper() == "LONG"

    if is_long:
        pnl_pct = (exit_price - entry_price) / entry_price
        stop_dist_pct = abs(entry_price - stop_price) / entry_price
        mfe_pct = max(0.0, (highest_price - entry_price) / entry_price)
        mae_pct = min(0.0, (lowest_price - entry_price) / entry_price)
    else:
        pnl_pct = (entry_price - exit_price) / entry_price
        stop_dist_pct = abs(stop_price - entry_price) / entry_price
        mfe_pct = max(0.0, (entry_price - lowest_price) / entry_price)
        mae_pct = min(0.0, (entry_price - highest_price) / entry_price)

    r_metrics = calculate_r_multiples(pnl_pct, mfe_pct, mae_pct, max(stop_dist_pct, 0.0001))
    zone = classify_autopsy_zone(r_metrics["pnl_r"], r_metrics["mfe_r"], exit_reason, r_metrics["capture_ratio"])
    has_high_slippage = calculate_stop_slippage(stop_price, exit_price, exit_reason, 15.0)

    return {
        "trade_id": trade_id,
        "instance_id": instance_id,
        "direction": direction.upper(),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "pnl_pct": round(pnl_pct * 100, 2),
        "r_metrics": r_metrics,
        "zone": zone,
        "has_high_slippage": has_high_slippage
    }
