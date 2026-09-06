import copy
import math
import pytest
from v099_ledger.accounting import account
from v099_ledger.demo import synthetic_inputs


def test_hand_calculated_long_and_short():
    market, fills = synthetic_inputs()
    result = account(market, fills, initial_cash=1000)
    # Long: +6 - .2 - .206 - 2.02 = +3.574.
    # Short: +3 - .1 - .097 - .98 = +1.823.
    assert result["trades"][0]["net_pnl"] == pytest.approx(3.574)
    assert result["trades"][1]["net_pnl"] == pytest.approx(1.823)
    assert result["summary"]["final_equity"] == pytest.approx(1005.397)
    assert result["equity"][0]["cash"] == pytest.approx(999.8)  # No principal debit.
    assert result["summary"]["fees"] == pytest.approx(0.603)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("rate", [0.01, -0.01])
def test_funding_sign_and_pre_fill_ownership(side, rate):
    market = [dict(timestamp=i, mark_price=100, funding_rate=rate) for i in range(3)]
    fills = [dict(timestamp=0, quantity=side, price=100, fee_rate=0),
             dict(timestamp=2, quantity=-side, price=100, fee_rate=0)]
    result = account(market, fills, initial_cash=1000)
    settlements = [e for e in result["ledger"] if e["kind"] == "funding"]
    assert [e["timestamp"] for e in settlements] == [1, 2]
    assert result["summary"]["funding_cashflow"] == pytest.approx(-side*100*rate*2)


def test_leaves_open_position_and_marks_unrealized_pnl():
    market, fills = synthetic_inputs()
    result = account(market[:3], fills[:1], initial_cash=1000)
    assert result["summary"]["position_quantity"] == 2
    assert result["summary"]["unrealized_pnl"] == 6
    assert result["summary"]["closed_trades"] == 0
    assert result["summary"]["final_cash"] == pytest.approx(997.78)
    assert result["summary"]["final_equity"] == pytest.approx(1003.78)


def test_future_prices_never_generate_or_change_fills():
    market, fills = synthetic_inputs()
    changed = copy.deepcopy(market)
    for row in changed[3:]:
        row["mark_price"] *= 2
    first = account(market, fills, initial_cash=1000)
    second = account(changed, fills, initial_cash=1000)
    assert first["equity"][:3] == second["equity"][:3]
    assert [(e["timestamp"], e["quantity"], e["price"]) for e in first["ledger"] if e["kind"] != "funding"] == [
        (e["timestamp"], e["quantity"], e["price"]) for e in second["ledger"] if e["kind"] != "funding"]


def test_no_fills_means_no_trading_even_when_prices_change():
    market, _ = synthetic_inputs()
    result = account(market, [], initial_cash=1000)
    assert not result["ledger"] and not result["trades"]
    assert all(p["equity"] == 1000 for p in result["equity"])


@pytest.mark.parametrize("quantity", [1, -1, -3])
def test_unsupported_scale_partial_or_reversal_rejected(quantity):
    market, fills = synthetic_inputs()
    fills[1]["quantity"] = quantity
    with pytest.raises(ValueError, match="full close"):
        account(market, fills, initial_cash=1000)


@pytest.mark.parametrize("mutation", ["duplicate_time", "unordered_time", "missing_time", "nan", "negative_mark", "zero_qty", "negative_fee", "extra_market_field", "extra_fill_field"])
def test_invalid_or_extra_input_fields_rejected(mutation):
    market, fills = synthetic_inputs()
    if mutation == "duplicate_time": market[1]["timestamp"] = 0
    elif mutation == "unordered_time": market[1], market[2] = market[2], market[1]
    elif mutation == "missing_time": fills[0]["timestamp"] = 1
    elif mutation == "nan": fills[0]["price"] = math.nan
    elif mutation == "negative_mark": market[0]["mark_price"] = -1
    elif mutation == "zero_qty": fills[0]["quantity"] = 0
    elif mutation == "negative_fee": fills[0]["fee_rate"] = -0.01
    elif mutation == "extra_market_field": market[0]["note"] = "not part of the public schema"
    else: fills[0]["note"] = "not part of the public schema"
    with pytest.raises(ValueError): account(market, fills, initial_cash=1000)


def test_same_time_close_and_open_follow_input_order():
    market = [dict(timestamp=0, mark_price=100, funding_rate=0), dict(timestamp=1, mark_price=101, funding_rate=0)]
    fills = [dict(timestamp=0, quantity=1, price=100, fee_rate=0),
             dict(timestamp=1, quantity=-1, price=101, fee_rate=0),
             dict(timestamp=1, quantity=-2, price=101, fee_rate=0)]
    result = account(market, fills, initial_cash=1000)
    assert result["summary"]["closed_trades"] == 1
    assert result["summary"]["position_quantity"] == -2
    assert result["summary"]["final_equity"] == 1001


@pytest.mark.parametrize("value", [-1, 0, True, float("inf")])
def test_invalid_initial_cash(value):
    market, fills = synthetic_inputs()
    with pytest.raises(ValueError): account(market, fills, initial_cash=value)

