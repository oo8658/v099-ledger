"""Hand-checkable v3 accounting cases, separate from the demo."""

import pytest

from v099_ledger.event_accounting import account_events


def mark(price=100):
    return {"timestamp": 0, "kind": "mark", "price": price}


def fill(quantity, price, time=0, fee_rate=0):
    return {"timestamp": time, "kind": "fill", "quantity": quantity, "price": price, "fee_rate": fee_rate}


def test_add_partial_close_and_delayed_funding_after_full_close():
    events = [mark(), fill(2, 100), fill(1, 106, 1),
              {"timestamp": 2, "kind": "funding_due", "id": "due"},
              fill(-1, 109, 3), fill(-2, 110, 4),
              {"timestamp": 5, "kind": "funding_post", "id": "due", "rate": 0.01, "settlement_mark": 100},
              {"timestamp": 5, "kind": "mark", "price": 110}]
    result = account_events(events, initial_cash=1000)
    assert result["ledger"][2]["basis"] == 102
    assert result["ledger"][4]["position_quantity"] == 2
    assert result["ledger"][4]["realized_pnl"] == 7
    assert result["trades"][0]["gross_pnl"] == 23
    assert result["trades"][0]["funding_cashflow"] == -3
    assert result["summary"]["final_cash"] == 1020
    assert result["summary"]["closed_trades"] == 1


def test_single_fill_reversal_splits_fee_and_keeps_open_position():
    result = account_events([mark(), fill(-1, 100, fee_rate=0.01),
                             fill(3, 90, 1, fee_rate=0.01),
                             {"timestamp": 1, "kind": "mark", "price": 95}], initial_cash=1000)
    trade = result["trades"][0]
    assert (trade["side"], trade["gross_pnl"], trade["fees"], trade["net_pnl"]) == ("short", 10, 1.9, 8.1)
    assert result["summary"]["position_quantity"] == 2
    assert result["summary"]["entry_price"] == 90
    assert result["summary"]["final_equity"] == pytest.approx(1016.3)


@pytest.mark.parametrize("events", [
    [fill(1, 100)],
    [mark(), fill(0, 100)],
    [mark(), fill(1, 100), {"timestamp": 1, "kind": "funding_due", "id": "x"}],
    [mark(), {"timestamp": 1, "kind": "funding_post", "id": "x", "rate": 0.01, "settlement_mark": 100}],
    [mark(), {"timestamp": 1, "kind": "funding_due", "id": "x"},
     {"timestamp": 2, "kind": "funding_post", "id": "x", "rate": 0.01, "settlement_mark": 100},
     {"timestamp": 3, "kind": "funding_post", "id": "x", "rate": 0.01, "settlement_mark": 100}],
    [mark(), {"timestamp": 1, "kind": "mark", "price": 100, "signal": "buy"}],
])
def test_incomplete_or_policy_bearing_inputs_rejected(events):
    with pytest.raises(ValueError):
        account_events(events, initial_cash=1000)
