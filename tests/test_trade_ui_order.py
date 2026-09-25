from app.api.routes import _trade_to_ui_order


def test_lake_trade_maps_price_and_total_for_dashboard():
    view = _trade_to_ui_order(
        {
            "id": "t1",
            "instance_id": "inst-1",
            "strategy_id": "mean-reversion",
            "mode": "paper",
            "pair": "BTC/USD",
            "side": "buy",
            "entry_time": "2026-09-25T10:00:00Z",
            "exit_time": "2026-09-25T11:00:00Z",
            "entry_price": 100.0,
            "exit_price": 105.5,
            "amount": 0.01,
            "notional_usd": 105.5,
            "net_pnl": 5.5,
        }
    )
    assert view["price"] == 105.5
    assert view["total"] == 105.5
    assert view["type"] == "buy"
    assert view["timestamp"] == "2026-09-25T11:00:00Z"
    assert view["strategyName"] == "mean-reversion"
    assert view["pnl"] == 5.5


def test_already_mapped_order_keeps_price_total():
    view = _trade_to_ui_order({"id": "o1", "type": "sell", "price": 12.5, "total": 25.0, "amount": 2})
    assert view["type"] == "sell"
    assert view["price"] == 12.5
    assert view["total"] == 25.0
