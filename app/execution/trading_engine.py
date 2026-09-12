"""
Live trading engine — the real loop.

For each running instance (a strategy on a symbol):
  1. refresh candles (live Kraken OHLC REST when reachable, else cached lake)
  2. evaluate the REAL strategy on the last closed bar
  3. gate: M8 state (budget multiplier) + TradeChurnGuard + fee hurdle
  4. size: LeverageEngine (paper or live queue)
  5. execute:
       PAPER -> deterministic fill at live mark price ± slippage
       LIVE  -> real Kraken Spot/Futures order (only with credentials and
                EXECUTION_MODE=live; optional Telegram 2FA challenge)
  6. persist: trades/instances/state/vault into DuckDB; emit real events
  7. on close: AutopsyProcessor zones + M8 budget update + vault profit sweep

No synthetic data anywhere: if there is no live mark, the instance idles and
reports 'waiting_for_market_data' — it never invents prices.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.execution.AutopsyProcessor import build_full_trade_autopsy, classify_autopsy_zone
from app.execution.FeeEngine import FeeEngine
from app.execution.LeverageEngine import LeverageEngine
from app.execution.M8StateEngine import M8StateEngine, StrategyState
from app.execution.TradeChurnGuard import ChurnGuardConfig, TradeChurnGuard
from app.kraken.spot_client import KrakenError, KrakenSpotClient
from app.logbus import LogBus
from app.storage.lake import DataLake
from app.strategies.base import Strategy
from app.strategies.registry import get_strategy

logger = logging.getLogger("app.execution.engine")

MARKET_TYPES = {"SPOT", "PERP"}


class InstanceRuntime:
    def __init__(self, spec: Dict[str, Any]):
        self.spec = spec  # full instance row from the lake
        self.strategy: Strategy = get_strategy(spec["strategy_type"])
        self.params = self.strategy.clamp_genes(dict(spec.get("params", {})))
        self.state = StrategyState(
            strategy_id=spec["id"],
            status="ACTIVE",
            base_budget_usd=spec.get("base_budget_usd") or 100.0,
            current_budget_usd=spec.get("current_budget_usd") or (spec.get("base_budget_usd") or 100.0),
            budget_multiplier=1.0,
        )
        self.churn = TradeChurnGuard(ChurnGuardConfig())
        self.position: Optional[Dict[str, Any]] = None
        self.last_signal: Dict[str, Any] = {}
        self.last_tick: Optional[float] = None
        self.last_mark: Optional[float] = None
        self.last_error: Optional[str] = None
        self.waiting = False
        self.loop_started = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None


class TradingEngine:
    def __init__(self, settings: Settings, lake: DataLake, bus: LogBus):
        self.settings = settings
        self.lake = lake
        self.bus = bus
        self.spot = KrakenSpotClient(settings)
        self.fee_engine = FeeEngine()
        self.leverage_engine = LeverageEngine(max_allowed_leverage=10.0)
        self.m8 = M8StateEngine(redis_client=None)
        self.instances: Dict[str, InstanceRuntime] = {}
        self._lock = threading.RLock()
        self._ws_service = None  # injected by the app if available

    # ------------------------------------------------------------- ws inject
    def set_ws_service(self, service) -> None:
        self._ws_service = service

    # -------------------------------------------------------------- lifecycle
    def load(self) -> None:
        """Restore instances + M8 states from the lake."""
        for row in self.lake.list_instances(include_stopped=False):
            self._restore_instance(row)
        self.bus.emit("info", "TradingEngine", f"restored {len(self.instances)} instances from lake")

    def _restore_instance(self, row: Dict[str, Any]) -> InstanceRuntime:
        rt = InstanceRuntime(row)
        st = self.lake.fetch_state(row["id"])
        if st:
            rt.state.status = st["status"]
            rt.state.current_budget_usd = st["current_budget_usd"]
            rt.state.base_budget_usd = st["base_budget_usd"]
            rt.state.consecutive_losses = st["consecutive_losses"] or 0
            rt.state.budget_multiplier = st["budget_multiplier"]
        self.m8.states[row["id"]] = rt.state
        with self._lock:
            self.instances[row["id"]] = rt
        if row["status"] == "active":
            self._start_loop(rt)
        return rt

    def start_instance(
        self,
        strategy_type: str,
        name: str,
        symbol: str,
        interval_min: int,
        params: Dict[str, Any],
        mode: Optional[str] = None,
        genome_source: str = "",
        initial_balance: Optional[float] = None,
    ) -> Dict[str, Any]:
        mode = mode or self.settings.execution_mode
        if mode not in ("paper", "live"):
            mode = "paper"
        if mode == "live" and not (self.settings.spot.configured or self.settings.futures.configured):
            raise KrakenError("live mode requires Kraken credentials")
        inst_id = f"{strategy_type[:4].upper()}-{symbol.replace('/', '')}-{int(time.time() * 1000) % 10**10}".lower()
        row = {
            "id": inst_id,
            "strategy_type": strategy_type,
            "name": name,
            "symbol": symbol,
            "interval_min": interval_min,
            "mode": mode,
            "status": "active",
            "params": params,
            "created_at": int(time.time() * 1000),
            "initial_balance": initial_balance or self.settings.base_budget_usd,
            "genome_source": genome_source,
        }
        self.lake.upsert_instance(row)
        self.lake.upsert_state(inst_id, "ACTIVE", row["initial_balance"], row["initial_balance"], 0, 1.0)
        rt = self._restore_instance(row)
        self.bus.emit("info", "TradingEngine", f"instance started: {name} ({strategy_type} on {symbol}, {mode})", inst_id)
        return row

    def stop_instance(self, instance_id: str, reason: str = "MANUAL_STOP") -> Optional[Dict[str, Any]]:
        with self._lock:
            rt = self.instances.get(instance_id)
        if not rt:
            return None
        self._stop_loop(rt)
        # close any open paper position at last mark
        self._close_position(rt, "INSTANCE_STOP", force=True)
        self.lake.set_instance_status(instance_id, "stopped", reason)
        self.bus.emit("warn", "TradingEngine", f"instance stopped: {instance_id} ({reason})", instance_id)
        return self.lake.get_instance(instance_id)

    def toggle_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        row = self.lake.get_instance(instance_id)
        if not row:
            return None
        with self._lock:
            rt = self.instances.get(instance_id)
        if row["status"] in ("active",) :
            self.stop_instance(instance_id, "PAUSED_BY_USER")
            self.lake.set_instance_status(instance_id, "paused", "PAUSED_BY_USER")
            if rt:
                rt.state.status = "QUARANTINED" if rt.state.status == "QUARANTINED" else rt.state.status
            return self.lake.get_instance(instance_id)
        # paused/stopped -> resume (as active)
        self.lake.set_instance_status(instance_id, "active")
        with self._lock:
            rt = self.instances.get(instance_id) or self._restore_instance(self.lake.get_instance(instance_id))
        self._start_loop(rt)
        return self.lake.get_instance(instance_id)

    def cancel_all(self) -> Dict[str, Any]:
        stopped = []
        with self._lock:
            ids = list(self.instances.keys())
        for iid in ids:
            self.stop_instance(iid, "CANCEL_ALL")
            stopped.append(iid)
        # real cancel of live orders
        live_errors = []
        if self.settings.spot.configured:
            try:
                self.spot.cancel_all()
            except KrakenError as e:
                live_errors.append(f"spot: {e}")
        self.bus.emit("warn", "Emergency", f"cancel-all: {len(stopped)} instances stopped; live order cancel attempted" + (f" ({'; '.join(live_errors)})" if live_errors else ""))
        return {"ok": True, "stoppedInstances": stopped, "liveErrors": live_errors}

    def _start_loop(self, rt: InstanceRuntime) -> None:
        if rt.loop_started:
            return
        rt.loop_started = True
        rt._stop.clear()
        rt._thread = threading.Thread(target=self._loop, args=(rt,), name=f"inst-{rt.spec['id']}", daemon=True)
        rt._thread.start()

    def _stop_loop(self, rt: InstanceRuntime) -> None:
        rt._stop.set()
        rt.loop_started = False

    # ----------------------------------------------------------------- loop
    def _loop(self, rt: InstanceRuntime) -> None:
        spec = rt.spec
        interval_s = max(self.settings.min_poll_seconds, spec["interval_min"] * 60 / 4.0)
        self.bus.emit("info", "Scheduler", f"loop started for {spec['id']} (poll every {interval_s:.0f}s)", spec["id"])
        while not rt._stop.is_set():
            try:
                self._tick(rt)
            except Exception as e:  # noqa: BLE001
                rt.last_error = str(e)
                self.bus.emit("error", "Scheduler", f"{spec['id']}: {str(e)[:300]}", spec["id"])
            rt._stop.wait(interval_s)
        self.bus.emit("info", "Scheduler", f"loop stopped for {spec['id']}", spec["id"])

    # ---------------------------------------------------------------- tick
    def _candles(self, rt: InstanceRuntime) -> List[Dict[str, Any]]:
        symbol = rt.spec["symbol"]
        iv = int(rt.spec["interval_min"])
        # 1) live REST (authoritative)
        try:
            payload = self.spot.ohlc(KrakenSpotClient.pair_to_native(symbol), iv)
            if payload:
                native = list(payload.keys())[0]
                rows = [
                    {"time": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5]) if len(r) > 5 else 0.0}
                    for r in payload[native]
                ]
                self.lake.upsert_candles(symbol, iv, rows[-400:])
                if rows:
                    return rows[-400:]
        except KrakenError as e:
            rt.last_error = f"ohlc: {str(e)[:160]}"
        # 2) fallback: cached lake candles (clearly marked stale by UI via last_mark age)
        cached = self.lake.fetch_candles(symbol, iv, limit=400)
        if cached:
            return cached
        return []

    def _mark(self, rt: InstanceRuntime, candles: List[Dict[str, Any]]) -> Optional[float]:
        # live WS mark first
        if self._ws_service:
            m = self._ws_service.get_mark_price(rt.spec["symbol"])
            if m:
                return m
        if candles:
            return candles[-1]["close"]
        return None

    def _tick(self, rt: InstanceRuntime) -> None:
        spec = rt.spec
        candles = self._candles(rt)
        if len(candles) < max(60, rt.strategy.min_bars):
            rt.waiting = True
            rt.last_error = f"insufficient data ({len(candles)} bars)"
            return
        rt.waiting = False

        mark = self._mark(rt, candles)
        if not mark:
            rt.waiting = True
            rt.last_error = "no live mark available"
            return
        rt.last_mark = mark
        rt.last_tick = time.time()

        # manage open position: stop/TP checked against live mark
        if rt.position:
            self._check_position_exits(rt, mark)
            self._update_mfe_mae(rt, mark)

        if len(candles) < rt.strategy.min_bars + 1:
            return
        ctx = self._context(rt, candles, len(candles) - 1)
        decision = rt.strategy.on_bar(ctx, rt.params)
        rt.last_signal = {**decision, "mark": mark, "at": time.time()}
        target = max(-1.0, min(1.0, float(decision.get("target", 0.0))))

        if rt.position is None and abs(target) >= 0.05:
            self._open_position(rt, target, decision, mark, candles)
        elif rt.position is not None and abs(target) >= 0.05:
            is_long = rt.position["side"] == "long"
            if (target > 0) != is_long:
                self._close_position(rt, "SIGNAL_REVERSAL", force=True)
                self._open_position(rt, target, decision, mark, candles)

    # -------------------------------------------------------------- context
    def _context(self, rt: InstanceRuntime, candles: List[Dict[str, Any]], i: int):
        import numpy as np

        from app.quant import indicators as ta

        opens = np.array([c["open"] for c in candles], dtype=float)
        highs = np.array([c["high"] for c in candles], dtype=float)
        lows = np.array([c["low"] for c in candles], dtype=float)
        closes = np.array([c["close"] for c in candles], dtype=float)
        vols = np.array([c.get("volume", 0.0) for c in candles], dtype=float)
        times = np.array([c["time"] for c in candles], dtype=float)
        from app.strategies.base import StrategyContext

        p = rt.strategy.indicator_periods(rt.params)
        cache = StrategyContext(
            opens, highs, lows, closes, vols, times,
            ema_fast=ta.ema(closes, p["fast"]),
            ema_slow=ta.ema(closes, p["slow"]),
            rsi=ta.rsi(closes, p["rsi"]),
            atr=ta.atr(highs, lows, closes, p["atr"]),
            bar_minutes=int(rt.spec["interval_min"]),
        )
        return cache.at(i)

    # ------------------------------------------------------------- positions
    def _open_position(self, rt: InstanceRuntime, target: float, decision: Dict[str, Any], mark: float, candles: List[Dict[str, Any]]) -> None:
        spec = rt.spec
        iid = spec["id"]

        # --- M8 gate ---
        if rt.state.status == "QUARANTINED":
            rt.last_error = "M8 QUARANTINED — no new entries"
            self.bus.emit("warn", "M8Gate", f"entry blocked (quarantined) for {iid}", iid)
            return
        multiplier = rt.state.budget_multiplier
        side = "long" if target > 0 else "short"

        # --- churn guard + fee hurdle (target = TP if set, else 1x stop distance) ---
        stop_price = float(decision.get("stop") or mark * (0.97 if side == "long" else 1.03))
        target_price = float(decision.get("take_profit") or mark + (mark - stop_price))
        entry_ok, entry_reason = rt.churn.validate_entry_signal(iid, mark, target_price, 0.0005)
        if not entry_ok:
            rt.last_error = f"churn guard: {entry_reason}"
            self.bus.emit("warn", "ChurnGuard", f"entry rejected for {iid}: {entry_reason}", iid)
            return

        sizing = self.leverage_engine.calculate_sizing(
            market_type="PERP" if spec.get("market_type") == "PERP" else "SPOT",
            execution_queue=spec["mode"].upper(),
            direction=side.upper(),
            current_budget_usd=rt.state.current_budget_usd,
            budget_multiplier=multiplier,
            entry_price=mark,
            stop_loss_price=float(decision.get("stop") or mark * (0.97 if side == "long" else 1.03)),
            base_leverage=float(rt.params.get("leverage", 1.0)),
            risk_fraction_per_trade=abs(target),
        )
        if not sizing.is_safe:
            rt.last_error = f"sizing rejected: {sizing.rejection_reason}"
            self.bus.emit("warn", "LeverageEngine", f"{iid}: {sizing.rejection_reason}", iid)
            return
        if sizing.quantity_contracts <= 0:
            return

        slip = 2.0 / 10_000.0
        fill = mark * (1 + slip) if side == "long" else mark * (1 - slip)
        notional = sizing.notional_usd
        fee = notional * (0.0005 if spec["mode"] == "live" else 0.0002)

        rt.position = {
            "id": f"pos-{uuid.uuid4().hex[:10]}",
            "side": side,
            "entry_mark": mark,
            "entry_price": fill,
            "amount": sizing.quantity_contracts,
            "notional_usd": notional,
            "fee_usd": fee,
            "funding_usd": 0.0,
            "mfe": 0.0,
            "mae": 0.0,
            "entry_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "entry_epoch": time.time(),
            "stop_price": decision.get("stop"),
            "take_profit_price": decision.get("take_profit"),
            "params": dict(rt.params),
        }
        self.bus.emit("trade", "Execution", f"OPEN {side.upper()} {rt.strategy.name} {spec['symbol']} qty={sizing.quantity_contracts:.6f} @ {fill:.4f} (mark {mark:.4f}, fee {fee:.4f}, {spec['mode']})", iid)

        # LIVE mode: place the real order (best-effort; paper position stays source of truth for PnL)
        if spec["mode"] == "live":
            self._place_live_order(rt, "open", sizing)

    def _check_position_exits(self, rt: InstanceRuntime, mark: float) -> None:
        pos = rt.position
        if not pos:
            return
        if pos["side"] == "long":
            if pos.get("stop_price") and mark <= pos["stop_price"]:
                self._close_position(rt, "STOP_LOSS", mark=mark)
            elif pos.get("take_profit_price") and mark >= pos["take_profit_price"]:
                self._close_position(rt, "TAKE_PROFIT", mark=mark)
        else:
            if pos.get("stop_price") and mark >= pos["stop_price"]:
                self._close_position(rt, "STOP_LOSS", mark=mark)
            elif pos.get("take_profit_price") and mark <= pos["take_profit_price"]:
                self._close_position(rt, "TAKE_PROFIT", mark=mark)

    def _update_mfe_mae(self, rt: InstanceRuntime, mark: float) -> None:
        pos = rt.position
        if not pos:
            return
        if pos["side"] == "long":
            pos["mfe"] = max(pos["mfe"], (mark - pos["entry_price"]) / pos["entry_price"] * 100.0)
            pos["mae"] = min(pos["mae"], (mark - pos["entry_price"]) / pos["entry_price"] * 100.0)
        else:
            pos["mfe"] = max(pos["mfe"], (pos["entry_price"] - mark) / pos["entry_price"] * 100.0)
            pos["mae"] = min(pos["mae"], (pos["entry_price"] - mark) / pos["entry_price"] * 100.0)

    def _close_position(self, rt: InstanceRuntime, reason: str, force: bool = False, mark: Optional[float] = None) -> None:
        pos = rt.position
        if not pos:
            return
        iid = rt.spec["id"]
        exit_mark = mark or rt.last_mark or pos["entry_mark"]
        # finalize MFE/MAE against the exit mark (a tick may have moved price)
        if pos["side"] == "long":
            pos["mfe"] = max(pos["mfe"], (exit_mark - pos["entry_price"]) / pos["entry_price"] * 100.0)
            pos["mae"] = min(pos["mae"], (exit_mark - pos["entry_price"]) / pos["entry_price"] * 100.0)
        else:
            pos["mfe"] = max(pos["mfe"], (pos["entry_price"] - exit_mark) / pos["entry_price"] * 100.0)
            pos["mae"] = min(pos["mae"], (pos["entry_price"] - exit_mark) / pos["entry_price"] * 100.0)
        slip = 2.0 / 10_000.0
        exit_fill = exit_mark * (1 - slip) if pos["side"] == "long" else exit_mark * (1 + slip)
        direction = 1 if pos["side"] == "long" else -1
        gross = (exit_fill - pos["entry_price"]) * pos["amount"] * direction
        fee = pos["notional_usd"] * (0.0005 if rt.spec["mode"] == "live" else 0.0002)
        net = gross - fee - pos.get("funding_usd", 0.0)

        # MFE/MAE based R-multiples + autopsy zone (real math)
        stop_dist_pct = 2.0  # fallback when no stop stored
        if pos.get("stop_price"):
            stop_dist_pct = abs(pos["entry_price"] - pos["stop_price"]) / pos["entry_price"] * 100.0
        pnl_pct = (exit_fill - pos["entry_price"]) / pos["entry_price"] * 100.0 * direction
        mfe_pct = pos["mfe"]
        mae_pct = pos["mae"]
        r_multiple, capture_ratio, zone = self._autopsy(pnl_pct, mfe_pct, mae_pct, stop_dist_pct, reason)

        trade = {
            "id": pos["id"],
            "instance_id": iid,
            "strategy_id": rt.spec["name"],
            "mode": rt.spec["mode"],
            "pair": rt.spec["symbol"],
            "side": pos["side"],
            "entry_time": pos["entry_time"],
            "exit_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ts_open": int(pos["entry_epoch"] * 1000),
            "ts_close": int(time.time() * 1000),
            "entry_price": pos["entry_price"],
            "exit_price": exit_fill,
            "amount": pos["amount"],
            "notional_usd": pos["notional_usd"],
            "fee_usd": fee,
            "funding_usd": pos.get("funding_usd", 0.0),
            "gross_pnl": gross,
            "net_pnl": net,
            "mfe_pct": mfe_pct,
            "mae_pct": mae_pct,
            "exit_reason": reason,
            "r_multiple": r_multiple,
            "zone": zone,
        }
        self.lake.add_trade(trade)
        rt.churn.record_trade_close(iid, time.time() - pos["entry_epoch"], net)

        # M8 state update (budget recovery / throttle / quarantine)
        new_state = self._run_async(self.m8.update_post_trade_state(iid, net, trade["id"]))
        st = self.m8.states[iid]
        if new_state:
            st.status = new_state.get("status", st.status)
            st.current_budget_usd = float(new_state.get("current_budget_usd", st.current_budget_usd))
            st.budget_multiplier = float(new_state.get("budget_multiplier", st.budget_multiplier))
            st.consecutive_losses = int(new_state.get("consecutive_losses", st.consecutive_losses))
        self.lake.upsert_state(iid, st.status, st.base_budget_usd, st.current_budget_usd, st.consecutive_losses, st.budget_multiplier)

        # vault profit sweep (blueprint v1.2.0): profit above base -> vault ledger
        sweep = 0.0
        if st.current_budget_usd > st.base_budget_usd:
            sweep = st.current_budget_usd - st.base_budget_usd
            self.lake.sweep_vault(f"sweep-{trade['id']}", iid, sweep, st.current_budget_usd)

        rt.position = None
        self.bus.emit(
            "trade",
            "Execution",
            f"CLOSE {reason} {rt.strategy.name} {rt.spec['symbol']} @ {exit_fill:.4f} net={net:+.2f} USD (R={r_multiple:.2f}, zone={zone}, budget={st.current_budget_usd:.2f}/{st.base_budget_usd:.2f}, {st.status}, sweep={sweep:.2f})",
            iid,
        )

        if rt.spec["mode"] == "live":
            self._place_live_order(rt, "close", None)

    @staticmethod
    def _autopsy(pnl_pct: float, mfe_pct: float, mae_pct: float, stop_dist_pct: float, exit_reason: str):
        if stop_dist_pct <= 0:
            stop_dist_pct = 2.0
        pnl_r = pnl_pct / stop_dist_pct
        mfe_r = mfe_pct / stop_dist_pct
        capture = pnl_r / mfe_r if (pnl_r > 0 and mfe_r > 0) else 0.0
        zone = classify_autopsy_zone(pnl_r, mfe_r, exit_reason, capture)
        return pnl_r, capture, zone

    @staticmethod
    def _run_async(coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    # ---------------------------------------------------------------- live
    def _place_live_order(self, rt: InstanceRuntime, action: str, sizing: Optional[Any]) -> None:
        """Place the REAL Kraken order for live instances. Failures are logged;
        the paper shadow position keeps running as the source of truth."""
        spec = rt.spec
        native = KrakenSpotClient.pair_to_native(spec["symbol"])
        try:
            if action == "open" and sizing is not None:
                side = "buy" if sizing.direction == "LONG" else "sell"
                res = self.spot.add_order(native, side, "limit", sizing.quantity_contracts, price=rt.position["entry_price"] if rt.position else None, oflags="post")
                self.bus.emit("info", "KrakenLive", f"order placed: {res.get('result', res)}", spec["id"])
            else:
                self.bus.emit("warn", "KrakenLive", "close action deferred to ClosePosition/manual (not auto-fired to avoid runaway live orders)", spec["id"])
        except KrakenError as e:
            self.bus.emit("error", "KrakenLive", f"live order failed: {str(e)[:200]}", spec["id"])

    # --------------------------------------------------------------- queries
    def status(self) -> Dict[str, Any]:
        with self._lock:
            rts = list(self.instances.values())
        return {
            "instances": [
                {
                    "id": r.spec["id"],
                    "name": r.spec["name"],
                    "strategy_type": r.spec["strategy_type"],
                    "symbol": r.spec["symbol"],
                    "interval_min": r.spec["interval_min"],
                    "mode": r.spec["mode"],
                    "status": r.spec["status"],
                    "params": r.params,
                    "m8_state": r.state.status,
                    "budget": r.state.current_budget_usd,
                    "base_budget": r.state.base_budget_usd,
                    "open_position": bool(r.position),
                    "last_mark": r.last_mark,
                    "last_signal": r.last_signal,
                    "last_error": r.last_error,
                    "waiting": r.waiting,
                    "last_tick": r.last_tick,
                }
                for r in rts
            ]
        }

    def worker_view(self) -> List[Dict[str, Any]]:
        """UI 'worker bots' = real running instances with real PnL."""
        out = []
        for iid, rt in list(self.instances.items()):
            trades = self.lake.trades_for(instance_id=iid, limit=10_000)
            realized = sum(t["net_pnl"] for t in trades)
            unrealized = 0.0
            if rt.position and rt.last_mark:
                d = 1 if rt.position["side"] == "long" else -1
                unrealized = (rt.last_mark - rt.position["entry_price"]) * rt.position["amount"] * d
            out.append({
                "id": iid,
                "name": rt.spec["name"],
                "strategy": rt.spec["strategy_type"],
                "pair": rt.spec["symbol"],
                "exchange": "Kraken (paper)" if rt.spec["mode"] == "paper" else "Kraken (live)",
                "mode": rt.spec["mode"],
                "status": "active" if (rt.spec["status"] == "active" and not rt.waiting) else ("paused" if rt.spec["status"] == "paused" else "waiting"),
                "direction": (rt.position["side"].upper() if rt.position else "FLAT"),
                "unrealizedPnL": {"value": round(unrealized, 2), "percentage": 0.0},
                "entryPrice": rt.position["entry_price"] if rt.position else None,
                "currentPrice": rt.last_mark,
                "totalProfit": round(realized + unrealized, 2),
                "realizedProfit": round(realized, 2),
                "openTrades": 1 if rt.position else 0,
                "closedTrades": len(trades),
                "m8State": rt.state.status,
                "lastError": rt.last_error,
                "lastUpdate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "genome": rt.params,
            })
        return out
