"""Account only explicitly supplied marks, fills, and funding events."""

from decimal import Decimal

from .event_formats import validate_events
from .formats import finite


def _decimal(value):
    return Decimal(str(value))


def _output(value):
    number = float(value)
    return finite(number, "accounting result")


def _new_cycle(identifier, timestamp, quantity, price, fee):
    return dict(trade_id=identifier, side="long" if quantity > 0 else "short",
                entry_time=timestamp, exit_time=None, quantity=quantity,
                entry_abs=abs(quantity), entry_notional=abs(quantity)*price,
                exit_abs=Decimal(0), exit_notional=Decimal(0),
                gross=Decimal(0), fees=fee, funding=Decimal(0))


def _trade_row(cycle):
    return dict(trade_id=cycle["trade_id"], side=cycle["side"],
                entry_time=cycle["entry_time"], exit_time=cycle["exit_time"],
                quantity=_output(cycle["quantity"]),
                entry_price=_output(cycle["entry_notional"]/cycle["entry_abs"]),
                exit_price=_output(cycle["exit_notional"]/cycle["exit_abs"]),
                gross_pnl=_output(cycle["gross"]), fees=_output(cycle["fees"]),
                funding_cashflow=_output(cycle["funding"]),
                net_pnl=_output(cycle["gross"]-cycle["fees"]+cycle["funding"]))


def account_events(events, *, initial_cash):
    """Replay one linear perpetual in input order without creating any event.

    A funding_due records the quantity and position cycle at that instant;
    funding_post later supplies the actual rate and settlement mark. Every due
    must have one post before the report ends. Same-time ordering is exactly
    the caller's order. Open positions at the end are permitted.
    """
    events = validate_events(events)
    initial = finite(initial_cash, "initial_cash")
    if initial <= 0:
        raise ValueError("initial_cash must be positive")
    initial_d = _decimal(initial)
    cash, position, basis, mark = initial_d, Decimal(0), Decimal(0), None
    realized_total = fee_total = funding_total = Decimal(0)
    trade_id = 0
    active = None
    cycles = {}
    closed = []
    pending = {}
    posted = set()
    ledger = []

    for index, event in enumerate(events, 1):
        kind, timestamp = event["kind"], event["timestamp"]
        fee = realized = funding = due_quantity = Decimal(0)
        funding_id = None
        if kind == "mark":
            mark = _decimal(event["price"])
        elif kind == "funding_due":
            funding_id = event["id"]
            if funding_id in pending or funding_id in posted:
                raise ValueError("duplicate funding id")
            due_quantity = position
            pending[funding_id] = (position, active["trade_id"] if active else 0)
        elif kind == "funding_post":
            funding_id = event["id"]
            if funding_id not in pending:
                raise ValueError("funding post has no unposted due")
            due_quantity, owner = pending.pop(funding_id)
            posted.add(funding_id)
            funding = -due_quantity*_decimal(event["settlement_mark"])*_decimal(event["rate"])
            cash += funding
            funding_total += funding
            if owner:
                cycles[owner]["funding"] += funding
        else:
            delta = _decimal(event["quantity"])
            price, rate = _decimal(event["price"]), _decimal(event["fee_rate"])
            fee = abs(delta)*price*rate
            cash -= fee
            fee_total += fee
            if position == 0 or position*delta > 0:
                if position == 0:
                    trade_id += 1
                    active = _new_cycle(trade_id, timestamp, delta, price, fee)
                    cycles[trade_id] = active
                    position, basis = delta, price
                else:
                    old_abs = abs(position)
                    basis = (old_abs*basis+abs(delta)*price)/(old_abs+abs(delta))
                    position += delta
                    active["quantity"] += delta
                    active["entry_abs"] += abs(delta)
                    active["entry_notional"] += abs(delta)*price
                    active["fees"] += fee
            else:
                old_sign = 1 if position > 0 else -1
                closing = min(abs(position), abs(delta))
                closed_fee = fee*closing/abs(delta)
                realized = closing*(price-basis)*old_sign
                cash += realized
                realized_total += realized
                active["gross"] += realized
                active["fees"] += closed_fee
                active["exit_abs"] += closing
                active["exit_notional"] += closing*price
                position += -old_sign*closing
                if position == 0:
                    active["exit_time"] = timestamp
                    closed.append(active)
                    active = None
                    basis = Decimal(0)
                remainder = abs(delta)-closing
                if remainder:
                    opening = delta+old_sign*closing
                    trade_id += 1
                    active = _new_cycle(trade_id, timestamp, opening, price, fee-closed_fee)
                    cycles[trade_id] = active
                    position, basis = opening, price
        unrealized = position*(mark-basis)
        ledger.append(dict(index=index, timestamp=timestamp, kind=kind, trade_id=active["trade_id"] if active else trade_id,
                           funding_id=funding_id, funding_quantity=_output(due_quantity), pending_count=len(pending),
                           mark_price=_output(mark), position_quantity=_output(position), basis=_output(basis),
                           cash=_output(cash), unrealized_pnl=_output(unrealized), equity=_output(cash+unrealized),
                           fee=_output(fee), realized_pnl=_output(realized), funding_cashflow=_output(funding)))
    if pending:
        raise ValueError("unposted funding due at end of report")
    final_unrealized = position*(mark-basis)
    summary = dict(initial_cash=initial, final_cash=_output(cash), final_equity=_output(cash+final_unrealized),
                   position_quantity=_output(position), entry_price=_output(basis), unrealized_pnl=_output(final_unrealized),
                   realized_pnl=_output(realized_total), fees=_output(fee_total), funding_cashflow=_output(funding_total),
                   net_pnl=_output(cash+final_unrealized-initial_d), closed_trades=len(closed), events=len(events))
    return dict(initial_cash=initial, ledger=ledger, trades=[_trade_row(c) for c in closed], summary=summary)
