"""
=========================================================
Datei:      app/execution/TradeChurnGuard.py (v1.7.0)
Zweck:      Schutz vor Over-Trading, Micro-Chatter & Fee Drag
Knoten:     Jaune (Carrera-Engine) / Risk Gateway
System:     "The Judge & The Swarm" - Zero-Dummy Guarantee
=========================================================
"""
from __future__ import annotations
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("app.execution.trade_churn_guard")


@dataclass
class ChurnGuardConfig:
    min_holding_seconds: int = 180
    cooldown_seconds: int = 300
    max_daily_trades: int = 12
    min_fee_hurdle_multiple: float = 2.5


class TradeChurnGuard:
    """
    Verhindert übermäßiges Handeln ("Churn"), Mikro-Trading bei zu geringer Spanne
    relativ zu den Börsengebühren und stellt Mindesthaltedauern sicher.
    """

    def __init__(self, config: Optional[ChurnGuardConfig] = None):
        self.config = config or ChurnGuardConfig()
        self.last_close_timestamp: Dict[str, float] = {}
        self.daily_trade_counts: Dict[str, Tuple[int, str]] = {}

    def _get_current_date_str(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def record_trade_close(
        self,
        instance_id: str,
        holding_time_seconds: float,
        pnl_usd: float
    ) -> None:
        """Registriert das Ende eines Trades für Cooldown- und Tageslimit-Zähler."""
        now = time.time()
        self.last_close_timestamp[instance_id] = now
        
        today = self._get_current_date_str()
        current_count, recorded_date = self.daily_trade_counts.get(instance_id, (0, today))
        if recorded_date != today:
            self.daily_trade_counts[instance_id] = (1, today)
        else:
            self.daily_trade_counts[instance_id] = (current_count + 1, today)

        logger.info(
            "Trade Close für '%s' registriert (Haltedauer: %.1fs, PnL: $%.2f). Zähler heute: %d",
            instance_id, holding_time_seconds, pnl_usd, self.daily_trade_counts[instance_id][0]
        )

    def can_open_position(self, instance_id: str) -> Tuple[bool, Optional[str]]:
        """Prüft Cooldown und Tageslimit vor Eröffnung einer Position."""
        now = time.time()
        
        # 1. Cooldown nach Schließung prüfen
        last_close = self.last_close_timestamp.get(instance_id)
        if last_close:
            elapsed = now - last_close
            if elapsed < self.config.cooldown_seconds:
                remaining = self.config.cooldown_seconds - elapsed
                return False, f"COOLDOWN_ACTIVE: Noch {remaining:.1f}s Sperre aktiv"

        # 2. Maximales Tageslimit prüfen
        today = self._get_current_date_str()
        current_count, recorded_date = self.daily_trade_counts.get(instance_id, (0, today))
        if recorded_date == today and current_count >= self.config.max_daily_trades:
            return False, f"MAX_DAILY_TRADES_EXCEEDED: Tageslimit von {self.config.max_daily_trades} Trades erreicht"

        return True, None

    def validate_entry_signal(
        self,
        instance_id: str,
        entry_price: float,
        target_price: float,
        fee_rate: float,
        fee_hurdle_multiple: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validiert ein Entry-Signal anhand der Gebührenhürde ("Fee Hurdle").
        Der projizierte Zielgewinn muss mindestens ein Vielfaches der
        Round-Trip-Maker/Taker-Gebühren betragen, um Trade-Churn und Fee Drag abzuwehren.
        """
        # 1. Basis-Prüfungen auf Cooldown / Tageslimit
        can_open, reason = self.can_open_position(instance_id)
        if not can_open:
            return False, reason

        # 2. Fee Hurdle Berechnung
        hurdle_mult = fee_hurdle_multiple if fee_hurdle_multiple is not None else self.config.min_fee_hurdle_multiple
        target_distance = abs(target_price - entry_price)
        round_trip_fee = 2.0 * fee_rate * entry_price
        required_hurdle = hurdle_mult * round_trip_fee

        if target_distance < required_hurdle:
            reject_msg = (
                f"FEE HURDLE REJECT: Target distance ({target_distance:.4f}) < "
                f"Required hurdle ({required_hurdle:.4f} = {hurdle_mult}x round-trip fee)"
            )
            logger.warning("Signal für '%s' abgelehnt: %s", instance_id, reject_msg)
            return False, reject_msg

        return True, None

    def is_micro_chatter(self, instance_id: str, holding_time_seconds: float) -> bool:
        """Erkennt, ob ein Trade unzulässig kurz gehalten wurde (< min_holding_seconds)."""
        return holding_time_seconds < self.config.min_holding_seconds

    def get_guard_metrics(self, instance_id: str) -> Dict[str, Any]:
        """Gibt Diagnosedaten für die UI und das Monitoring zurück."""
        today = self._get_current_date_str()
        current_count, recorded_date = self.daily_trade_counts.get(instance_id, (0, today))
        trades_today = current_count if recorded_date == today else 0

        last_close = self.last_close_timestamp.get(instance_id)
        now = time.time()
        cooldown_remaining = max(0.0, self.config.cooldown_seconds - (now - last_close)) if last_close else 0.0

        return {
            "instance_id": instance_id,
            "trades_today": trades_today,
            "max_daily_trades": self.config.max_daily_trades,
            "cooldown_remaining_seconds": round(cooldown_remaining, 1),
            "is_in_cooldown": cooldown_remaining > 0.0
        }
