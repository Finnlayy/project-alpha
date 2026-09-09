"""
Unit Tests für QuantOrchestrator & MCP Respawn Pipeline
Zero-Dummy Guarantee Verification
"""
import pytest
from app.execution.QuantOrchestrator import QuantOrchestrator
from app.mcp.QuantOrchestratorMCP import QuantOrchestratorMCP


def test_seed_and_query_historical_bots():
    orchestrator = QuantOrchestrator(db_path=":memory:")
    history = orchestrator.list_historical_bots()
    assert len(history) >= 3
    
    # Filter by regime
    trending = orchestrator.list_historical_bots(regime="persistent_trending")
    assert len(trending) >= 1
    assert trending[0]["pair"] == "BTC/USD.P"
    assert trending[0]["config"]["leverage"] == 5


def test_spawn_from_history_with_modifier():
    broadcast_events = []
    def on_broadcast(evt):
        broadcast_events.append(evt)

    orchestrator = QuantOrchestrator(db_path=":memory:", broadcast_callback=on_broadcast)
    
    # Spawn with AI modifier
    new_bot = orchestrator.spawn_from_history(
        "BOT-HIST-7742",
        modifier={
            "name": "Neo_Fable High-Vola Scaler",
            "leverage": 3, # reduced from 5 to 3
            "metrics": {
                "investment": 7500.0
            }
        }
    )

    assert new_bot["id"].startswith("BOT-")
    assert new_bot["name"] == "Neo_Fable High-Vola Scaler"
    assert new_bot["leverage"] == 3
    assert new_bot["status"] == "active"
    assert new_bot["metrics"]["investment"] == 7500.0
    assert new_bot["metrics"]["realizedProfit"] == 0.0 # reset for new run
    assert new_bot["totalProfit"] == 0.0
    assert new_bot["spawnedFrom"] == "BOT-HIST-7742"
    assert len(broadcast_events) == 1
    assert broadcast_events[0]["id"] == new_bot["id"]


def test_mcp_tool_execution():
    orchestrator = QuantOrchestrator(db_path=":memory:")
    mcp = QuantOrchestratorMCP(orchestrator)
    
    # Query tool
    query_res = mcp.execute_tool("query_historical_bots", {"pair": "ETH/USD"})
    assert query_res["success"] is True
    assert query_res["count"] >= 1
    hist_id = query_res["sessions"][0]["id"]

    # Spawn tool
    spawn_res = mcp.execute_tool("spawn_from_history", {
        "historical_bot_id": hist_id,
        "modifier": {"leverage": 1}
    })
    assert spawn_res["success"] is True
    assert spawn_res["action"] == "SPAWNED_FROM_HISTORY"
    assert spawn_res["leverage"] == 1
    assert spawn_res["bot_id"].startswith("BOT-")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
