"""Paper campaign loop for alpha-campaign-book-20261002.

Stage order is fixed:
frame → sanitize_sources → hypothesize_independent and hypothesize_veteran
(parallel) → challenge → book_write → test_paper (loop B, paper book only)
→ book_annotate → learn → evidence_in_sample → evidence_locked_vault
→ evidence_native_check → finn_promote.

finn_promote records a proposal. It does not start live trading and it does
not place an order. Missing cited paths are HOLD. This module does not
substitute another reader, store, or metric for a missing path.
"""
from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.backtest.engine import BacktestResult
from app.execution.M8StateEngine import (
    LUA_IDEMPOTENT_POST_TRADE_SCRIPT,
    M8StateEngine,
    StrategyState,
)
from app.quant.lead_lag import cross_impact

CAMPAIGN_ID = "alpha-campaign-book-20261002"
PAPER_BASE_BUDGET_USD = 50.0

STAGE_ORDER: Tuple[str, ...] = (
    "frame",
    "sanitize_sources",
    "hypothesize_independent",
    "hypothesize_veteran",
    "challenge",
    "book_write",
    "test_paper",
    "book_annotate",
    "learn",
    "evidence_in_sample",
    "evidence_locked_vault",
    "evidence_native_check",
    "finn_promote",
)

_ROOT = Path(__file__).resolve().parents[2]
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "data",
    "__pycache__",
}
_TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".md", ".json"}


def _excluded(path: Path) -> bool:
    if any(part in _SKIP_DIRS for part in path.parts):
        return True
    try:
        rel = path.relative_to(_ROOT)
    except ValueError:
        return True
    if rel.parts[:2] == ("app", "campaign") or rel.parts[:1] == ("tests",):
        return True
    return False


_MODULE_PATHS = (
    "server/playbookScreener.ts",
    "docs/pseudocode/00-types.md",
)
_FRAME_PATHS = (
    "app/data_layer/facade.py",
    "app/mcp_server.py",
)
_MEMORY_SCORECARD = "data/memory/playbook_scorecard.json"
_MEMORY_ATTRIBUTION = "data/memory/.attribution_processed_ids.json"
_BOOK_PATH = "app/registry/identity.py"
_QUESTION_PATH = "server/mcp/server.ts"
_PASSKEY_PATH = "src/optimizer/PasskeyWebAuthnClient.ts"
_M8_PATH = "app/execution/M8StateEngine.py"
_LEAD_LAG_PATH = "app/quant/lead_lag.py"
_BACKTEST_PATH = "app/backtest/engine.py"
_DRILL_IDS = ("DR-01", "DR-02", "DR-03", "DR-04", "DR-05")
_ENV_LIVE = "KRAKEN_LIVE_TRADING_ENABLED"


def _exists(rel: str) -> bool:
    return (_ROOT / rel).is_file()


def _find_filename(filename: str) -> List[str]:
    found: List[str] = []
    for path in _ROOT.rglob(filename):
        if _excluded(path):
            continue
        found.append(str(path.relative_to(_ROOT)))
    return found


def _repo_text() -> str:
    chunks: List[str] = []
    for path in _ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
            continue
        if _excluded(path):
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _symbol_present(symbol: str, corpus: str) -> bool:
    return symbol in corpus


def binding_report(corpus: Optional[str] = None) -> List[Dict[str, Any]]:
    """HOLD when a cited path or symbol is absent. Wired when it is present."""
    text = _repo_text() if corpus is None else corpus
    ohlc = _find_filename("ohlc_query.py")
    drills_present = all(_symbol_present(drill_id, text) for drill_id in _DRILL_IDS)
    career_types = _symbol_present("PASSED_DRILL", text) and _symbol_present("FAILED_DRILL", text)
    passkey_present = _exists(_PASSKEY_PATH) and _passkey_step_up_present()
    return [
        {
            "name": "module_path",
            "status": "wired" if all(_exists(p) for p in _MODULE_PATHS) else "HOLD",
            "paths": list(_MODULE_PATHS),
        },
        {
            "name": "frame_read",
            "status": "wired" if all(_exists(p) for p in _FRAME_PATHS) and bool(ohlc) else "HOLD",
            "paths": list(_FRAME_PATHS) + ["ohlc_query.py"],
        },
        {
            "name": "memory_playbook_scorecard",
            "status": "wired" if _exists(_MEMORY_SCORECARD) else "HOLD",
            "paths": [_MEMORY_SCORECARD],
        },
        {
            "name": "memory_attribution_ledger",
            "status": "wired" if _exists(_MEMORY_ATTRIBUTION) else "HOLD",
            "paths": [_MEMORY_ATTRIBUTION],
        },
        {
            "name": "career_book",
            "status": "wired" if _exists(_BOOK_PATH) and _symbol_present("get_career_book", text) else "HOLD",
            "paths": [_BOOK_PATH],
        },
        {
            "name": "drill_DR01_DR05",
            "status": "wired" if drills_present and career_types else "HOLD",
            "paths": list(_DRILL_IDS),
        },
        {
            "name": "BacktestResult",
            "status": "wired" if _exists(_BACKTEST_PATH) and BacktestResult.__name__ == "BacktestResult" else "HOLD",
            "paths": [_BACKTEST_PATH],
        },
        {
            "name": "ors-decision/1",
            "status": "wired" if _symbol_present("ors-decision/1", text) else "HOLD",
            "paths": ["ors-decision/1"],
        },
        {
            "name": "question_store",
            "status": "wired" if _question_store_wired() else "HOLD",
            "paths": [_QUESTION_PATH],
            "note": (
                "quant_review is in the cited file"
                if _question_store_wired()
                else "ABSENT. QuestionStore is not created. quant_review is not called."
            ),
        },
        {
            "name": "book_write_rollback",
            "status": "wired" if _exists(_BOOK_PATH) else "HOLD",
            "paths": [_BOOK_PATH],
        },
        {
            "name": "icEwma",
            "status": "wired" if _symbol_present("icEwma", text) else "HOLD",
            "paths": ["ScorecardRow.icEwma"],
        },
        {
            "name": "crossCorrelation",
            "status": "wired" if _exists(_LEAD_LAG_PATH) else "HOLD",
            "paths": [_LEAD_LAG_PATH],
        },
        {
            "name": "locked_vault",
            "status": "wired" if _exists(_M8_PATH) else "HOLD",
            "paths": [_M8_PATH],
        },
        {
            "name": "DataApproval_approveSymbol",
            "status": "wired" if _symbol_present("approveSymbol", text) and _symbol_present("DataApproval", text) else "HOLD",
            "paths": ["DataApproval", "approveSymbol"],
        },
        {
            "name": "PasskeyWebAuthnClient",
            "status": "wired" if passkey_present else "HOLD",
            "paths": [_PASSKEY_PATH],
        },
        {
            "name": "nativeBracketExits",
            "status": "wired" if _symbol_present("nativeBracketExits", text) else "HOLD",
            "paths": ["nativeBracketExits"],
        },
    ]


def _binding_status(report: List[Dict[str, Any]], name: str) -> str:
    for row in report:
        if row["name"] == name:
            return str(row["status"])
    return "HOLD"


def _question_store_wired() -> bool:
    path = _ROOT / _QUESTION_PATH
    if not path.is_file():
        return False
    return "quant_review" in path.read_text(encoding="utf-8")


def _passkey_step_up_present() -> bool:
    path = _ROOT / _PASSKEY_PATH
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    return "class PasskeyWebAuthnClient" in text and "navigator.credentials.get" in text


def _await(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _module_id(module_id: Optional[str], moduleId: Optional[str]) -> Optional[str]:
    if module_id is not None and moduleId is not None and module_id != moduleId:
        return None
    if module_id is not None:
        return module_id
    return moduleId


def _frame(report: List[Dict[str, Any]]) -> Dict[str, Any]:
    status = _binding_status(report, "frame_read")
    return {
        "stage": "frame",
        "status": status,
        "reason": "market_data.get_candles and DuckDB read_parquet paths are missing",
    }


def _sanitize_sources(frame: Dict[str, Any]) -> Dict[str, Any]:
    if frame["status"] != "wired":
        return {
            "stage": "sanitize_sources",
            "status": "HOLD",
            "reason": "no frame sources to sanitize",
        }
    return {
        "stage": "sanitize_sources",
        "status": "HOLD",
        "reason": "frame binding is present but this loop has no sanitizer import",
    }


def _hypothesize_independent(barrier: threading.Barrier) -> Dict[str, Any]:
    thread_id = threading.get_ident()
    barrier.wait(timeout=5)
    return {
        "stage": "hypothesize_independent",
        "status": "HOLD",
        "thread_id": thread_id,
        "reason": "playbook screener and playbook scorecard are missing",
    }


def _hypothesize_veteran(barrier: threading.Barrier) -> Dict[str, Any]:
    thread_id = threading.get_ident()
    barrier.wait(timeout=5)
    return {
        "stage": "hypothesize_veteran",
        "status": "HOLD",
        "thread_id": thread_id,
        "reason": "career book and attribution ledger are missing",
    }


def _hypothesize_parallel() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        independent = pool.submit(_hypothesize_independent, barrier)
        veteran = pool.submit(_hypothesize_veteran, barrier)
        return independent.result(), veteran.result()


def _challenge(
    report: List[Dict[str, Any]],
    leader_candidate: Optional[Sequence[float]],
    follower_candidate: Optional[Sequence[float]],
    bar_minutes: Optional[int],
) -> Dict[str, Any]:
    ic_status = _binding_status(report, "icEwma")
    result: Dict[str, Any] = {
        "stage": "challenge",
        "icEwma": ic_status,
    }
    can_call = (
        _binding_status(report, "crossCorrelation") == "wired"
        and leader_candidate is not None
        and follower_candidate is not None
        and bar_minutes is not None
    )
    if not can_call:
        result["status"] = "HOLD"
        result["crossCorrelation"] = "HOLD"
        result["reason"] = "crossCorrelation is not called without both series and bar_minutes"
        return result
    impact = cross_impact(list(leader_candidate), list(follower_candidate), bar_minutes)
    result["status"] = "wired"
    result["crossCorrelation"] = impact["crossCorrelation"]
    return result


def _book_write(report: List[Dict[str, Any]]) -> Dict[str, Any]:
    status = _binding_status(report, "career_book")
    return {
        "stage": "book_write",
        "status": status,
        "rollback": _binding_status(report, "book_write_rollback"),
        "reason": "CareerEvent book is missing. No file is written. hash_prev/hash_curr is not rewritten.",
    }


def _test_paper(report: List[Dict[str, Any]]) -> Dict[str, Any]:
    backtest_status = _binding_status(report, "BacktestResult")
    ran = False
    return {
        "stage": "test_paper",
        "status": "HOLD",
        "loop": "B",
        "book": "paper",
        "BacktestResult": backtest_status,
        "backtest_ran": ran,
        "drill_DR01_DR05": _binding_status(report, "drill_DR01_DR05"),
        "ors-decision/1": _binding_status(report, "ors-decision/1"),
        "reason": "paper book is missing, so loop B does not run. BacktestResult is not executed.",
    }


def _book_annotate(report: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "stage": "book_annotate",
        "status": _binding_status(report, "career_book"),
        "reason": "career book is missing",
    }


def _learn(report: List[Dict[str, Any]]) -> Dict[str, Any]:
    present = _binding_status(report, "question_store") == "wired"
    return {
        "stage": "learn",
        "status": "skipped",
        "question_store": "wired" if present else "ABSENT",
        "quant_review_called": False,
        "reason": (
            "quant_review is present in the cited file and is not called from this paper loop"
            if present
            else "question store is ABSENT. quant_review is not called."
        ),
    }


def _evidence_in_sample(test_paper: Dict[str, Any]) -> Dict[str, Any]:
    if test_paper.get("backtest_ran") is True:
        return {
            "stage": "evidence_in_sample",
            "status": "wired",
            "BacktestResult": test_paper.get("BacktestResult"),
        }
    return {
        "stage": "evidence_in_sample",
        "status": "HOLD",
        "reason": "no in-sample BacktestResult was produced",
    }


def _evidence_locked_vault(report: List[Dict[str, Any]]) -> Dict[str, Any]:
    if _binding_status(report, "locked_vault") != "wired":
        return {"stage": "evidence_locked_vault", "status": "HOLD"}

    engine = M8StateEngine(redis_client=None)
    base = PAPER_BASE_BUDGET_USD
    path_id = f"{CAMPAIGN_ID}:paper-vault"
    hwm_id = f"{CAMPAIGN_ID}:paper-hwm"
    engine.states[path_id] = StrategyState(
        strategy_id=path_id,
        status="ACTIVE",
        base_budget_usd=base,
        current_budget_usd=base,
        budget_multiplier=1.0,
        consecutive_low_pf_days=0,
    )
    throttled = _await(engine.update_post_trade_state(path_id, -25.0, f"{CAMPAIGN_ID}:throttle"))
    quarantined = _await(engine.update_post_trade_state(path_id, -25.0, f"{CAMPAIGN_ID}:quarantine"))
    shadow = _await(engine.update_post_trade_state(path_id, 10.0, f"{CAMPAIGN_ID}:shadow"))

    hwm_before = 30.0
    hwm_pnl = 40.0
    engine.states[hwm_id] = StrategyState(
        strategy_id=hwm_id,
        status="ACTIVE",
        base_budget_usd=base,
        current_budget_usd=hwm_before,
        budget_multiplier=1.0,
        consecutive_low_pf_days=0,
    )
    refilled = _await(engine.update_post_trade_state(hwm_id, hwm_pnl, f"{CAMPAIGN_ID}:hwm"))
    retained = float(refilled["current_budget_usd"]) - hwm_before
    surplus = hwm_pnl - retained
    lua = LUA_IDEMPOTENT_POST_TRADE_SCRIPT
    return {
        "stage": "evidence_locked_vault",
        "status": "wired",
        "base_budget_usd": base,
        "throttled_status": throttled["status"],
        "throttled_current_budget_usd": throttled["current_budget_usd"],
        "throttled_budget_multiplier": throttled["budget_multiplier"],
        "quarantined_status": quarantined["status"],
        "quarantined_current_budget_usd": quarantined["current_budget_usd"],
        "quarantined_budget_multiplier": quarantined["budget_multiplier"],
        "shadow_trades_count": shadow["shadow_trades_count"],
        "shadow_wins": shadow["shadow_wins"],
        "shadow_current_budget_usd": shadow["current_budget_usd"],
        "hwm_current_budget_usd": refilled["current_budget_usd"],
        "surplus_usd": surplus,
        "consecutive_low_pf_days": refilled["consecutive_low_pf_days"],
        "profit_factor_throttle_called": False,
        "live_budget_refill": False,
        "lua_throttle": ("base_budget * 0.5" in lua) and ('status = "THROTTLED"' in lua),
        "lua_quarantine": ("current_budget <= 0.0" in lua) and ('status = "QUARANTINED"' in lua),
        "lua_shadow": ('status == "QUARANTINED"' in lua) and ("shadow_trades_count" in lua),
        "lua_hwm_refill": "math.min(pnl, needed)" in lua,
    }


def _evidence_native_check(report: List[Dict[str, Any]]) -> Dict[str, Any]:
    approval = _binding_status(report, "DataApproval_approveSymbol")
    brackets = _binding_status(report, "nativeBracketExits")
    passkey = _binding_status(report, "PasskeyWebAuthnClient")
    return {
        "stage": "evidence_native_check",
        "status": "wired" if passkey == "wired" else "HOLD",
        "entry_allowed": False,
        "DataApproval_approveSymbol": approval,
        "PasskeyWebAuthnClient": passkey,
        "passkey_invoked": False,
        "nativeBracketExits": brackets,
        "live_order": False,
    }


def _finn_promote(module_id: Optional[str]) -> Dict[str, Any]:
    return {
        "stage": "finn_promote",
        "status": "proposal",
        "proposal": {
            "campaign_id": CAMPAIGN_ID,
            "module_id": module_id,
            "paper_only": True,
            "order": False,
            "live_trading_started": False,
        },
    }


def run_campaign(
    *,
    module_id: Optional[str] = None,
    moduleId: Optional[str] = None,
    leader_candidate: Optional[Sequence[float]] = None,
    follower_candidate: Optional[Sequence[float]] = None,
    bar_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one paper pass of the campaign DAG. Never places an order."""
    env_before = os.environ.get(_ENV_LIVE)
    report = binding_report()
    resolved = _module_id(module_id, moduleId)
    frame = _frame(report)
    sanitize = _sanitize_sources(frame)
    independent, veteran = _hypothesize_parallel()
    challenge = _challenge(report, leader_candidate, follower_candidate, bar_minutes)
    book_write = _book_write(report)
    test_paper = _test_paper(report)
    book_annotate = _book_annotate(report)
    learn = _learn(report)
    in_sample = _evidence_in_sample(test_paper)
    locked_vault = _evidence_locked_vault(report)
    native_check = _evidence_native_check(report)
    promote = _finn_promote(resolved)
    stages = [
        frame,
        sanitize,
        independent,
        veteran,
        challenge,
        book_write,
        test_paper,
        book_annotate,
        learn,
        in_sample,
        locked_vault,
        native_check,
        promote,
    ]
    if [row["stage"] for row in stages] != list(STAGE_ORDER):
        raise RuntimeError("campaign stage order drifted")
    env_after = os.environ.get(_ENV_LIVE)
    if env_after != env_before:
        raise RuntimeError("campaign must not set KRAKEN_LIVE_TRADING_ENABLED")
    return {
        "campaign_id": CAMPAIGN_ID,
        "paper_only": True,
        "live_order_placed": False,
        "module_id": resolved,
        "module_resolved": False,
        "stages": stages,
        "bindings": report,
    }
