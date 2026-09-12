"""
Real DuckDB-backed data lake.

Tables:
  candles(symbol, interval_min, ts, open, high, low, close, volume)
  instances(id, strategy_type, name, symbol, interval_min, mode, status, params_json, ...)
  trades(id, instance_id, strategy_id, mode, pair, side, entry/exit times+prices,
         amount, notional, fees, funding, gross/net pnl, MFE/MAE, zone, r_multiple)
  vault_ledger(entry_id, timestamp, strategy_id, type, amount_usd, balance_snapshot)  # blueprint v1.2.0
  state_machine(instance_id, status, base_budget_usd, current_budget_usd, ...)        # M8
  events(id, ts, level, module, message, strategy_id)
  paper_accounts(mode, balance_usd, updated_at)

Everything is real persistence — no in-memory pretend state.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

import duckdb
import pyarrow as pa


SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol VARCHAR, interval_min INTEGER, ts BIGINT,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
    PRIMARY KEY (symbol, interval_min, ts)
);
CREATE TABLE IF NOT EXISTS instances (
    id VARCHAR PRIMARY KEY,
    strategy_type VARCHAR, name VARCHAR, symbol VARCHAR,
    interval_min INTEGER, mode VARCHAR, status VARCHAR,
    params_json VARCHAR, created_at BIGINT, stopped_at BIGINT,
    stop_reason VARCHAR, initial_balance DOUBLE, genome_source VARCHAR,
    description VARCHAR
);
CREATE TABLE IF NOT EXISTS trades (
    id VARCHAR PRIMARY KEY,
    instance_id VARCHAR, strategy_id VARCHAR, mode VARCHAR, pair VARCHAR,
    side VARCHAR, entry_time VARCHAR, exit_time VARCHAR,
    ts_open BIGINT, ts_close BIGINT,
    entry_price DOUBLE, exit_price DOUBLE, amount DOUBLE, notional_usd DOUBLE,
    fee_usd DOUBLE, funding_usd DOUBLE,
    gross_pnl DOUBLE, net_pnl DOUBLE, mfe_pct DOUBLE, mae_pct DOUBLE,
    exit_reason VARCHAR, r_multiple DOUBLE, zone VARCHAR
);
CREATE TABLE IF NOT EXISTS vault_ledger (
    entry_id VARCHAR PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    strategy_id VARCHAR, type VARCHAR,
    amount_usd DOUBLE, balance_snapshot DOUBLE
);
CREATE TABLE IF NOT EXISTS state_machine (
    instance_id VARCHAR PRIMARY KEY,
    status VARCHAR, base_budget_usd DOUBLE, current_budget_usd DOUBLE,
    consecutive_losses INTEGER, budget_multiplier DOUBLE, updated_at BIGINT
);
CREATE TABLE IF NOT EXISTS events (
    id BIGINT, ts BIGINT, level VARCHAR, module VARCHAR, message VARCHAR, strategy_id VARCHAR
);
CREATE TABLE IF NOT EXISTS paper_accounts (
    mode VARCHAR PRIMARY KEY, balance_usd DOUBLE, updated_at BIGINT
);
"""


class DataLake:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._conn = duckdb.connect(path)
        for stmt in SCHEMA.strip().split(";"):
            if stmt.strip():
                self._conn.execute(stmt)
        self._event_seq = self._next_event_id()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ candles
    def upsert_candles(self, symbol: str, interval_min: int, rows: List[Dict[str, Any]]) -> int:
        """rows: {time (epoch s), open, high, low, close, volume}."""
        if not rows:
            return 0
        data = [(symbol, interval_min, int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r.get("volume", 0.0))) for r in rows]
        with self._lock:
            self._conn.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)", data)
        return len(data)

    def fetch_candles(self, symbol: str, interval_min: int, limit: int = 1000, since_ts: Optional[int] = None) -> List[Dict[str, Any]]:
        q = "SELECT ts, open, high, low, close, volume FROM candles WHERE symbol=? AND interval_min=?"
        args: list = [symbol, interval_min]
        if since_ts:
            q += " AND ts >= ?"
            args.append(since_ts)
        q += " ORDER BY ts ASC"
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        if len(rows) > limit:
            rows = rows[-limit:]
        return [{"time": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])} for r in rows]

    # ---------------------------------------------------------------- instances
    def upsert_instance(self, inst: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO instances VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    inst["id"], inst.get("strategy_type", ""), inst.get("name", ""), inst.get("symbol", ""),
                    int(inst.get("interval_min", 15)), inst.get("mode", "paper"), inst.get("status", "active"),
                    json.dumps(inst.get("params", {})), int(inst.get("created_at", time.time() * 1000)),
                    int(inst.get("stopped_at", 0)) or None, inst.get("stop_reason"),
                    float(inst.get("initial_balance", 0.0)), inst.get("genome_source"),
                    inst.get("description", ""),
                ],
            )

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM instances WHERE id=?", [instance_id]).fetchone()
        return self._row_to_instance(row) if row else None

    def list_instances(self, include_stopped: bool = False) -> List[Dict[str, Any]]:
        q = "SELECT * FROM instances"
        if not include_stopped:
            q += " WHERE status IN ('active','paused')"
        with self._lock:
            rows = self._conn.execute(q + " ORDER BY created_at ASC").fetchall()
        return [self._row_to_instance(r) for r in rows]

    def set_instance_status(self, instance_id: str, status: str, stop_reason: Optional[str] = None) -> None:
        stopped_at = int(time.time() * 1000) if status == "stopped" else None
        with self._lock:
            self._conn.execute(
                "UPDATE instances SET status=?, stopped_at=COALESCE(?, stopped_at), stop_reason=COALESCE(?, stop_reason) WHERE id=?",
                [status, stopped_at, stop_reason, instance_id],
            )

    @staticmethod
    def _row_to_instance(row) -> Dict[str, Any]:
        cols = ("id", "strategy_type", "name", "symbol", "interval_min", "mode", "status", "params_json", "created_at", "stopped_at", "stop_reason", "initial_balance", "genome_source", "description")
        d = dict(zip(cols, row))
        d["params"] = json.loads(d.pop("params_json") or "{}")
        return d

    # ------------------------------------------------------------------- trades
    def add_trade(self, t: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    t["id"], t.get("instance_id"), t.get("strategy_id"), t.get("mode"), t.get("pair"),
                    t.get("side"), t.get("entry_time"), t.get("exit_time"),
                    int(t.get("ts_open", 0)), int(t.get("ts_close", 0)),
                    float(t.get("entry_price", 0)), float(t.get("exit_price", 0)), float(t.get("amount", 0)),
                    float(t.get("notional_usd", 0)), float(t.get("fee_usd", 0)), float(t.get("funding_usd", 0)),
                    float(t.get("gross_pnl", 0)), float(t.get("net_pnl", 0)), float(t.get("mfe_pct", 0)),
                    float(t.get("mae_pct", 0)), t.get("exit_reason"), t.get("r_multiple"), t.get("zone"),
                ],
            )

    def trades_for(self, instance_id: Optional[str] = None, mode: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        q = "SELECT id, instance_id, strategy_id, mode, pair, side, entry_time, exit_time, entry_price, exit_price, amount, notional_usd, fee_usd, funding_usd, gross_pnl, net_pnl, mfe_pct, mae_pct, exit_reason, r_multiple, zone, ts_open, ts_close FROM trades"
        where, args = [], []
        if instance_id:
            where.append("instance_id=?")
            args.append(instance_id)
        if mode:
            where.append("mode=?")
            args.append(mode)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY ts_close ASC"
        with self._lock:
            rows = self._conn.execute(q + f" LIMIT {int(limit)}", args).fetchall()
        cols = ("id", "instance_id", "strategy_id", "mode", "pair", "side", "entry_time", "exit_time", "entry_price", "exit_price", "amount", "notional_usd", "fee_usd", "funding_usd", "gross_pnl", "net_pnl", "mfe_pct", "mae_pct", "exit_reason", "r_multiple", "zone", "ts_open", "ts_close")
        return [dict(zip(cols, r)) for r in rows]

    # -------------------------------------------------------------------- vault
    def sweep_vault(self, entry_id: str, strategy_id: str, amount_usd: float, balance_snapshot: float, vtype: str = "PROFIT_SWEEP") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO vault_ledger VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?)",
                [entry_id, strategy_id, vtype, amount_usd, balance_snapshot],
            )

    def vault_total(self) -> float:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM vault_ledger WHERE type='PROFIT_SWEEP'").fetchone()
        return float(row[0])

    # ------------------------------------------------------------------- state
    def upsert_state(self, instance_id: str, status: str, base_budget: float, current_budget: float, consecutive_losses: int, multiplier: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO state_machine VALUES (?,?,?,?,?,?,?)",
                [instance_id, status, base_budget, current_budget, consecutive_losses, multiplier, int(time.time() * 1000)],
            )

    def fetch_state(self, instance_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM state_machine WHERE instance_id=?", [instance_id]).fetchone()
        if not row:
            return None
        cols = ("instance_id", "status", "base_budget_usd", "current_budget_usd", "consecutive_losses", "budget_multiplier", "updated_at")
        return dict(zip(cols, row))

    # ------------------------------------------------------------------ events
    def _next_event_id(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()
            return int(row[0]) + 1

    def log_event(self, level: str, module: str, message: str, strategy_id: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?)",
                [self._event_seq, int(time.time() * 1000), level, module, message[:2000], strategy_id],
            )
            self._event_seq += 1

    def recent_events(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, level, module, message, strategy_id FROM events ORDER BY id DESC LIMIT ?", [limit]
            ).fetchall()
        return [{"id": r[0], "ts": r[1], "level": r[2], "module": r[3], "message": r[4], "strategy_id": r[5]} for r in reversed(rows)]

    # ----------------------------------------------------------------- accounts
    def set_paper_balance(self, mode: str, balance: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO paper_accounts VALUES (?,?,?)", [mode, balance, int(time.time() * 1000)]
            )

    def get_paper_balance(self, mode: str) -> Optional[float]:
        with self._lock:
            row = self._conn.execute("SELECT balance_usd FROM paper_accounts WHERE mode=?", [mode]).fetchone()
        return float(row[0]) if row else None

    # ------------------------------------------------------------------ summary
    def summary(self) -> Dict[str, Any]:
        with self._lock:
            candle_rows = self._conn.execute(
                "SELECT symbol, interval_min, COUNT(*), MIN(ts), MAX(ts) FROM candles GROUP BY symbol, interval_min"
            ).fetchall()
            n_candles = sum(int(r[2]) for r in candle_rows)
            n_trades = int(self._conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0])
            n_instances = int(self._conn.execute("SELECT COUNT(*) FROM instances").fetchone()[0])
            n_events = int(self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        file_size = 0
        try:
            file_size = __import__("os").path.getsize(self.path)
        except OSError:
            pass
        return {
            "totalParquetFiles": 0,
            "duckdbFileBytes": file_size,
            "totalSizeBytes": file_size,
            "total_size_mb": round(file_size / 1048576.0, 2),
            "totalRows": n_candles + n_trades + n_events,
            "total_rows": n_candles + n_trades + n_events,
            "totalCandles": n_candles,
            "totalTrades": n_trades,
            "totalInstances": n_instances,
            "symbols": [
                {"symbol": r[0], "intervalMin": int(r[1]), "rows": int(r[2]), "start_time": r[3], "end_time": r[4]} for r in candle_rows
            ],
            "oldestTimestamp": min((r[3] for r in candle_rows), default=None),
            "newestTimestamp": max((r[4] for r in candle_rows), default=None),
            "status": "healthy",
        }

    # ------------------------------------------------------------------ parquet
    def export_candles_parquet(self, symbol: str, interval_min: int, out_path: str) -> int:
        from app.execution.StorageUtils import write_parquet_atomically

        rows = self.fetch_candles(symbol, interval_min, limit=10_000_000)
        if not rows:
            return 0
        table = pa.Table.from_pylist(
            [{"ts": r["time"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"], "volume": r["volume"]} for r in rows]
        )
        write_parquet_atomically(out_path, table)
        return len(rows)

    def import_candles_parquet(self, symbol: str, interval_min: int, in_path: str) -> int:
        import pyarrow.parquet as pq

        t = pq.read_table(in_path)
        rows = t.to_pylist()
        return self.upsert_candles(symbol, interval_min, [{"time": r["ts"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"], "volume": r["volume"]} for r in rows])
