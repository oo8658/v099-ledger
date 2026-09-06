"""Book supplied executions. Never generate a signal, size, fill or exit."""

from .formats import TRADE_FIELDS, finite, validate_inputs


def account(market, fills, *, initial_cash):
    """Account for one linear perpetual with full-position opens and closes.

    ``market`` supplies valuation/settlement observations; ``fills`` supplies
    actual or synthetic signed fills with explicit prices and fee rates.
    Funding precedes fills at the same timestamp, in the declared convention.
    Open positions may remain open at the end; there is no forced exit.
    """
    market, fills = validate_inputs(market, fills)
    initial = finite(initial_cash, "initial_cash")
    if initial <= 0:
        raise ValueError("initial_cash must be positive")
    ledger, points, trades = [], [], []
    cash, q, basis = initial, 0.0, 0.0
    active = None
    tid, fi = 0, 0

    def record(timestamp, kind, quantity, price, *, fill_index=0, fee_rate=0.0,
               fee=0.0, funding_rate=0.0, funding_cashflow=0.0, realized_pnl=0.0):
        nonlocal cash
        delta = realized_pnl-fee+funding_cashflow
        cash += delta
        ledger.append(dict(sequence=len(ledger)+1, timestamp=timestamp, kind=kind, trade_id=tid,
            fill_index=fill_index, quantity=quantity, price=price, fee_rate=fee_rate, fee=fee,
            funding_rate=funding_rate, funding_cashflow=funding_cashflow, realized_pnl=realized_pnl, delta_cash=delta))

    for observation in market:
        t, mark, rate = (observation[k] for k in ("timestamp", "mark_price", "funding_rate"))
        funding = -q*mark*rate
        if funding != 0:
            record(t, "funding", q, mark, funding_rate=rate, funding_cashflow=funding)
            active["funding_cashflow"] += funding
        while fi < len(fills) and fills[fi]["timestamp"] == t:
            fill = fills[fi]
            qty, price, fee_rate = (fill[k] for k in ("quantity", "price", "fee_rate"))
            fi += 1
            fee = abs(qty)*price*fee_rate
            if q == 0:
                tid += 1
                q, basis = qty, price
                active = dict(trade_id=tid, side="long" if q > 0 else "short", entry_time=t,
                              quantity=q, entry_price=price, fees=fee, funding_cashflow=0.0)
                record(t, "open", qty, price, fill_index=fi, fee_rate=fee_rate, fee=fee)
            else:
                if qty != -q:
                    raise ValueError("only a full close is supported while a position is open; no scaling, partial close or one-fill reversal")
                gross = q*(price-basis)
                record(t, "close", qty, price, fill_index=fi, fee_rate=fee_rate, fee=fee, realized_pnl=gross)
                active["fees"] += fee
                active.update(exit_time=t, exit_price=price, gross_pnl=gross,
                              net_pnl=gross-active["fees"]+active["funding_cashflow"])
                trades.append({k: active[k] for k in TRADE_FIELDS})
                q, basis, active = 0.0, 0.0, None
        unrealized = q*(mark-basis)
        points.append(dict(timestamp=t, cash=cash, quantity=q, entry_price=basis,
                           unrealized_pnl=unrealized, equity=cash+unrealized))
    last = points[-1]
    summary = dict(initial_cash=initial, final_cash=cash, final_equity=last["equity"],
        position_quantity=q, entry_price=basis, unrealized_pnl=last["unrealized_pnl"],
        realized_pnl=sum(e["realized_pnl"] for e in ledger), fees=sum(e["fee"] for e in ledger),
        funding_cashflow=sum(e["funding_cashflow"] for e in ledger), net_pnl=last["equity"]-initial,
        closed_trades=len(trades), ledger_events=len(ledger))
    # Refuse non-finite results even if finite but extreme inputs overflowed.
    for collection in (ledger, points, trades, [summary]):
        for row in collection:
            for key, value in row.items():
                if not isinstance(value, str):
                    finite(value, key)
    return dict(initial_cash=initial, ledger=ledger, equity=points, trades=trades, summary=summary)

