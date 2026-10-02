"""Paper campaign loop: stage order, HOLD bindings, no live orders."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

from app.campaign.alpha_campaign_book import CAMPAIGN_ID, STAGE_ORDER, run_campaign
from app.strategies.registry import REGISTRY

_ROOT = Path(__file__).resolve().parents[1]
_CAMPAIGN_FILE = _ROOT / "app" / "campaign" / "alpha_campaign_book.py"
_ENV_LIVE = "KRAKEN_LIVE_TRADING_ENABLED"

_HOLD = {
    "module_path",
    "frame_read",
    "memory_playbook_scorecard",
    "memory_attribution_ledger",
    "career_book",
    "drill_DR01_DR05",
    "ors-decision/1",
    "question_store",
    "book_write_rollback",
    "icEwma",
    "DataApproval_approveSymbol",
    "nativeBracketExits",
}
_WIRED = {
    "BacktestResult",
    "crossCorrelation",
    "locked_vault",
    "PasskeyWebAuthnClient",
}


def _stage(report, name):
    return next(row for row in report["stages"] if row["stage"] == name)


def _binding_status(report):
    return {row["name"]: row["status"] for row in report["bindings"]}


def test_stage_order_and_parallel_hypotheses():
    report = run_campaign()
    assert report["campaign_id"] == CAMPAIGN_ID
    assert report["paper_only"] is True
    assert report["live_order_placed"] is False
    assert report["module_resolved"] is False
    names = [row["stage"] for row in report["stages"]]
    assert names == list(STAGE_ORDER)
    independent = _stage(report, "hypothesize_independent")
    veteran = _stage(report, "hypothesize_veteran")
    assert independent["status"] == "HOLD"
    assert veteran["status"] == "HOLD"
    assert independent["thread_id"] != veteran["thread_id"]


def test_bindings_hold_versus_wired():
    report = run_campaign()
    status = _binding_status(report)
    assert set(status) == _HOLD | _WIRED
    for name in _HOLD:
        assert status[name] == "HOLD", name
    for name in _WIRED:
        assert status[name] == "wired", name
    assert not (_ROOT / "server" / "playbookScreener.ts").exists()
    assert not (_ROOT / "docs" / "pseudocode" / "00-types.md").exists()
    assert not (_ROOT / "app" / "data_layer" / "facade.py").exists()
    assert not (_ROOT / "app" / "mcp_server.py").exists()
    assert not list(_ROOT.rglob("ohlc_query.py"))
    assert not (_ROOT / "data" / "memory" / "playbook_scorecard.json").exists()
    assert not (_ROOT / "data" / "memory" / ".attribution_processed_ids.json").exists()
    assert not (_ROOT / "app" / "registry" / "identity.py").exists()
    assert not (_ROOT / "server" / "mcp" / "server.ts").exists()


def test_module_id_is_not_resolved_against_the_registry():
    report = run_campaign(module_id="mean_reversion_rsi")
    assert report["module_id"] == "mean_reversion_rsi"
    assert report["module_resolved"] is False
    assert "mean_reversion_rsi" not in REGISTRY
    aliased = run_campaign(moduleId="mean_reversion_rsi")
    assert aliased["module_id"] == "mean_reversion_rsi"
    conflict = run_campaign(module_id="mean_reversion_rsi", moduleId="other")
    assert conflict["module_id"] is None


def test_challenge_uses_only_existing_cross_correlation():
    held = _stage(run_campaign(), "challenge")
    assert held["status"] == "HOLD"
    assert held["icEwma"] == "HOLD"
    assert held["crossCorrelation"] == "HOLD"

    rng = np.random.default_rng(9)
    base = rng.normal(0, 1, 600)
    follower = np.roll(base, 3)
    follower[:3] = base[:3]
    leader = 100 * np.exp(np.cumsum(base * 0.001))
    lagged = 100 * np.exp(np.cumsum(follower * 0.001))
    report = run_campaign(
        leader_candidate=list(leader),
        follower_candidate=list(lagged),
        bar_minutes=1,
    )
    challenge = _stage(report, "challenge")
    assert challenge["status"] == "wired"
    assert challenge["icEwma"] == "HOLD"
    assert challenge["crossCorrelation"] > 0.7
    assert set(challenge) == {"stage", "icEwma", "status", "crossCorrelation"}


def test_paper_book_loop_does_not_run_and_learn_skips_questions():
    report = run_campaign()
    test_paper = _stage(report, "test_paper")
    assert test_paper["loop"] == "B"
    assert test_paper["book"] == "paper"
    assert test_paper["status"] == "HOLD"
    assert test_paper["BacktestResult"] == "wired"
    assert test_paper["backtest_ran"] is False
    assert test_paper["drill_DR01_DR05"] == "HOLD"
    assert test_paper["ors-decision/1"] == "HOLD"
    assert _stage(report, "evidence_in_sample")["status"] == "HOLD"
    learn = _stage(report, "learn")
    assert learn["status"] == "skipped"
    assert learn["question_store"] == "ABSENT"
    assert learn["quant_review_called"] is False
    assert _stage(report, "book_write")["status"] == "HOLD"
    assert _stage(report, "book_annotate")["status"] == "HOLD"


def test_locked_vault_paper_evidence_does_not_touch_profit_factor():
    vault = _stage(run_campaign(), "evidence_locked_vault")
    assert vault["status"] == "wired"
    assert vault["base_budget_usd"] == 50.0
    assert vault["throttled_status"] == "THROTTLED"
    assert vault["throttled_current_budget_usd"] == 25.0
    assert vault["throttled_budget_multiplier"] == 0.5
    assert vault["quarantined_status"] == "QUARANTINED"
    assert vault["quarantined_current_budget_usd"] == 0.0
    assert vault["quarantined_budget_multiplier"] == 0.0
    assert vault["shadow_trades_count"] == 1
    assert vault["shadow_wins"] == 1
    assert vault["shadow_current_budget_usd"] == 0.0
    assert vault["hwm_current_budget_usd"] == 50.0
    assert vault["surplus_usd"] == 20.0
    assert vault["consecutive_low_pf_days"] == 0
    assert vault["profit_factor_throttle_called"] is False
    assert vault["live_budget_refill"] is False
    assert vault["lua_throttle"] is True
    assert vault["lua_quarantine"] is True
    assert vault["lua_shadow"] is True
    assert vault["lua_hwm_refill"] is True


def test_native_check_does_not_invoke_passkey_or_allow_entry():
    native = _stage(run_campaign(), "evidence_native_check")
    assert native["PasskeyWebAuthnClient"] == "wired"
    assert native["passkey_invoked"] is False
    assert native["DataApproval_approveSymbol"] == "HOLD"
    assert native["nativeBracketExits"] == "HOLD"
    assert native["entry_allowed"] is False
    assert native["live_order"] is False
    promote = _stage(run_campaign(), "finn_promote")
    assert promote["status"] == "proposal"
    assert promote["proposal"]["order"] is False
    assert promote["proposal"]["live_trading_started"] is False
    assert promote["proposal"]["paper_only"] is True


def test_campaign_does_not_set_live_trading_or_write_a_book(monkeypatch):
    monkeypatch.delenv(_ENV_LIVE, raising=False)
    data = _ROOT / "data"
    before = {path.relative_to(data) for path in data.rglob("*")} if data.exists() else set()
    loaded_before = set(sys.modules)
    report = run_campaign()
    loaded = set(sys.modules) - loaded_before
    assert _ENV_LIVE not in os.environ
    assert report["live_order_placed"] is False
    after = {path.relative_to(data) for path in data.rglob("*")} if data.exists() else set()
    assert after == before
    assert not any(name.startswith("app.kraken") for name in loaded)
    assert "app.execution.trading_engine" not in loaded
    assert "app.execution.PaperExecutionEngine" not in loaded
    assert "app.execution.TradeChurnGuard" not in loaded
    assert "app.storage.lake" not in loaded

    monkeypatch.setenv(_ENV_LIVE, "leave-me")
    run_campaign()
    assert os.environ[_ENV_LIVE] == "leave-me"


def test_campaign_source_does_not_place_orders_or_touch_forbidden_surfaces():
    source = _CAMPAIGN_FILE.read_text(encoding="utf-8")
    for token in (
        "add_order",
        "send_order",
        "close_position",
        "execute_paper_order",
        "sweep_vault",
        "update_eod_profit_factor",
        "CROSS_BOOK",
        "Sigma",
        "0.0031",
        "class QuestionStore",
        "os.replace",
        "KRAKEN_LIVE_TRADING_ENABLED\"]",
        "spawn_from_history",
    ):
        assert token not in source, token
