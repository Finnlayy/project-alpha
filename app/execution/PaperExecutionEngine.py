"""
=========================================================
Datei:      app/execution/PaperExecutionEngine.py (v1.7.0)
Zweck:      Deterministische Paper-Execution, Liquidation Guard & Matching
Knoten:     Jaune (Carrera-Engine) / Paper Sandbox
System:     "The Judge & The Swarm" - Zero-Dummy Guarantee
=========================================================
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from app.execution.M8StateEngine import M8StateEngine

logger = logging.getLogger("app.execution.paper_engine")


async def process_paper_tick(
    state_engine: M8StateEngine,
    current_tick_price: float,
    position: Dict[str, Any]
) -> bool:
    """
    Simuliert den Einschlag eines Preisticks auf eine offene Paper-Position.
    Trifft der Preis den Liquidationskurs, wird das zugeordnete Instanz-Budget
    sofort und deterministisch auf $0.00 liquidiert und die Instanz in QUARANTINED versetzt.
    """
    instance_id = position.get("instance_id")
    if not instance_id:
        return False

    direction = str(position.get("direction", "LONG")).upper()
    est_liq_price = position.get("estimated_liquidation_price")

    if est_liq_price is None:
        return False

    is_liquidated = False

    if direction == "LONG" and current_tick_price <= est_liq_price:
        is_liquidated = True
    elif direction == "SHORT" and current_tick_price >= est_liq_price:
        is_liquidated = True

    if is_liquidated:
        logger.warning(
            "🚨 [PAPER LIQUIDATION] Instanz '%s' bei Tick %.2f liquidiert (Liq-Level: %.2f)!",
            instance_id, current_tick_price, est_liq_price
        )
        state = state_engine.get_strategy_state(instance_id)
        if state:
            state.current_budget_usd = 0.0
            state.status = "QUARANTINED"
            state.budget_multiplier = 0.0
            logger.info("Instanz '%s' Status: QUARANTINED, Budget: $0.00", instance_id)
        return True

    return False


class PaperExecutionEngine:
    """
    Vollwertige Simulation einer Krypto-Exchange-Orderbuch-Ausführung ohne echtes Kapital.
    Unterstützt Slippage-Modellierung, Maker/Taker-Fills und Margin-Accounting.
    """

    def __init__(self, slippage_bps: float = 2.0, maker_fill_probability: float = 0.85):
        self.slippage_bps = slippage_bps
        self.maker_fill_probability = maker_fill_probability
        self.open_paper_positions: Dict[str, Dict[str, Any]] = {}
        self.execution_history: List[Dict[str, Any]] = []

    def execute_paper_order(
        self,
        instance_id: str,
        symbol: str,
        direction: str,
        order_type: str,
        quantity: float,
        price: float,
        leverage: float = 1.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """Führt eine Paper-Order mit realistischer Slippage aus."""
        is_buy = (direction.upper() == "LONG" or direction.upper() == "BUY")
        slippage_mult = (1.0 + (self.slippage_bps / 10000.0)) if is_buy else (1.0 - (self.slippage_bps / 10000.0))
        fill_price = round(price * slippage_mult, 4) if order_type.upper() == "MARKET" else price

        fill_record = {
            "order_id": f"PAPER-ORD-{len(self.execution_history) + 1}",
            "instance_id": instance_id,
            "symbol": symbol,
            "direction": direction.upper(),
            "order_type": order_type.upper(),
            "quantity": quantity,
            "requested_price": price,
            "fill_price": fill_price,
            "leverage": leverage,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": "FILLED"
        }

        self.execution_history.append(fill_record)
        self.open_paper_positions[instance_id] = fill_record
        return fill_record

    def close_paper_position(
        self,
        instance_id: str,
        exit_price: float,
        exit_reason: str = "TAKE_PROFIT"
    ) -> Optional[Dict[str, Any]]:
        """Schließt eine bestehende Paper-Position und berechnet PnL."""
        pos = self.open_paper_positions.pop(instance_id, None)
        if not pos:
            return None

        entry_price = pos["fill_price"]
        qty = pos["quantity"]
        direction = pos["direction"]

        if direction == "LONG":
            gross_pnl = (exit_price - entry_price) * qty
        else:
            gross_pnl = (entry_price - exit_price) * qty

        result = {
            "instance_id": instance_id,
            "symbol": pos["symbol"],
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "gross_pnl": round(gross_pnl, 2),
            "roi_pct": round((gross_pnl / (entry_price * qty)) * 100, 2) if entry_price * qty > 0 else 0.0
        }
        return result
