"""Independent v3 reconstruction from supplied events, without the accounting engine."""

from decimal import Decimal
import math
from pathlib import Path
import re

from .event_formats import EVENT_MODEL, EVENT_REPORT_FILES, validate_events
from .formats import finite, read_json, sha256


class EventVerificationError(ValueError):
    """A v3 report failed validation."""


def _need(ok, message):
    if not ok:
        raise EventVerificationError(message)


def _d(value):
    return Decimal(str(value))


def _number(value):
    return float(value)


def _check(actual, expected, label):
    _need(isinstance(actual, dict) and set(actual) == set(expected), f"{label}: fields mismatch")
    for key, wanted in expected.items():
        got = actual[key]
        if type(wanted) is int:
            _need(type(got) is int and got == wanted, f"{label}.{key}: integer mismatch")
        elif type(wanted) is str or wanted is None:
            _need(got == wanted and (wanted is None or type(got) is str), f"{label}.{key}: value mismatch")
        else:
            number = finite(got, f"{label}.{key}")
            tolerance = 0 if key in {"funding_quantity", "mark_price", "position_quantity", "basis", "quantity", "entry_price", "exit_price"} else 1e-7
            _need(math.isclose(number, wanted, rel_tol=1e-10, abs_tol=tolerance), f"{label}.{key}: claimed {number}, expected {wanted}")


def verify_event_report(folder):
    try:
        return _verify(Path(folder))
    except EventVerificationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, ZeroDivisionError) as exc:
        raise EventVerificationError(f"invalid v3 report: {exc}") from exc


def _verify(folder):
    _need(folder.is_dir() and not folder.is_symlink(), "report directory missing or symlinked")
    expected_names = {"manifest.json", *EVENT_REPORT_FILES}
    _need({p.name for p in folder.iterdir()} == expected_names, "unexpected or missing report file")
    for name in expected_names:
        path = folder/name
        _need(path.is_file() and not path.is_symlink(), f"required regular file missing: {name}")
    manifest = read_json(folder/"manifest.json")
    _need(type(manifest) is dict and set(manifest) == {"schema_version", "files"} and
          type(manifest["schema_version"]) is int and manifest["schema_version"] == 3 and
          type(manifest["files"]) is dict and set(manifest["files"]) == set(EVENT_REPORT_FILES), "invalid v3 manifest")
    for name in EVENT_REPORT_FILES:
        digest = manifest["files"][name]
        _need(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) and sha256(folder/name) == digest,
              f"hash mismatch: {name}")
    run = read_json(folder/"run.json")
    _need(type(run) is dict and set(run) == {"schema_version", "package_version", "model", "symbol", "data_kind",
                                             "initial_cash", "quantity_unit", "cash_unit", "event_order"}, "invalid run fields")
    _need(type(run["schema_version"]) is int and run["schema_version"] == 3 and run["model"] == EVENT_MODEL,
          "unsupported v3 model")
    _need(run["quantity_unit"] == "base_asset" and run["cash_unit"] == "quote_asset" and
          run["event_order"] == "input_order", "unsupported units or order")
    _need(type(run["package_version"]) is str and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", run["package_version"]),
          "invalid package version")
    _need(type(run["symbol"]) is str and re.fullmatch(r"[A-Z0-9_-]{1,32}", run["symbol"]), "invalid symbol")
    _need(run["data_kind"] in ("synthetic", "user_supplied"), "invalid data kind")
    initial = finite(run["initial_cash"], "initial_cash")
    _need(initial > 0, "initial_cash must be positive")
    events = validate_events(read_json(folder/"events.json"))
    ledger = read_json(folder/"ledger.json")
    trades = read_json(folder/"trades.json")
    summary = read_json(folder/"summary.json")
    _need(type(ledger) is list and len(ledger) == len(events), "ledger length mismatch")
    _need(type(trades) is list, "trades must be a list")

    cash, quantity, signed_cost, mark = _d(initial), Decimal(0), Decimal(0), Decimal(0)
    fee_total = realized_total = funding_total = Decimal(0)
    serial = 0
    active_id = 0
    cycles = {}
    closed = []
    due = {}
    used_ids = set()
    for index, item in enumerate(events, 1):
        kind, timestamp = item["kind"], item["timestamp"]
        fee = realized = funding = due_qty = Decimal(0)
        funding_id = None
        if kind == "mark":
            mark = _d(item["price"])
        elif kind == "funding_due":
            funding_id = item["id"]
            _need(funding_id not in used_ids, "duplicate funding id")
            used_ids.add(funding_id)
            due_qty = quantity
            due[funding_id] = (quantity, active_id)
        elif kind == "funding_post":
            funding_id = item["id"]
            _need(funding_id in due, "funding post without due")
            due_qty, owner = due.pop(funding_id)
            funding = -due_qty*_d(item["settlement_mark"])*_d(item["rate"])
            cash += funding
            funding_total += funding
            if owner:
                cycles[owner]["funding"] += funding
        else:
            change, price = _d(item["quantity"]), _d(item["price"])
            fee = abs(change)*price*_d(item["fee_rate"])
            cash -= fee
            fee_total += fee
            old = quantity
            old_basis = signed_cost/old if old else Decimal(0)
            if old == 0 or old*change > 0:
                if old == 0:
                    serial += 1
                    active_id = serial
                    cycles[serial] = dict(id=serial, side="long" if change > 0 else "short", opened=timestamp,
                                          ended=None, opening_quantity=change, bought=abs(change),
                                          buy_value=abs(change)*price, sold=Decimal(0), sell_value=Decimal(0),
                                          gross=Decimal(0), fees=fee, funding=Decimal(0))
                else:
                    cycle = cycles[active_id]
                    cycle["opening_quantity"] += change
                    cycle["bought"] += abs(change)
                    cycle["buy_value"] += abs(change)*price
                    cycle["fees"] += fee
                quantity = old+change
                signed_cost += change*price
            else:
                size = min(abs(old), abs(change))
                realized = size*(price-old_basis)*(1 if old > 0 else -1)
                cash += realized
                realized_total += realized
                cycle = cycles[active_id]
                cycle["gross"] += realized
                cycle["fees"] += fee*size/abs(change)
                cycle["sold"] += size
                cycle["sell_value"] += size*price
                quantity = old-(size if old > 0 else -size)
                signed_cost = quantity*old_basis
                if quantity == 0:
                    cycle["ended"] = timestamp
                    closed.append(active_id)
                    active_id = 0
                leftover = change+(size if old > 0 else -size)
                if leftover:
                    serial += 1
                    active_id = serial
                    cycles[serial] = dict(id=serial, side="long" if leftover > 0 else "short", opened=timestamp,
                                          ended=None, opening_quantity=leftover, bought=abs(leftover),
                                          buy_value=abs(leftover)*price, sold=Decimal(0), sell_value=Decimal(0),
                                          gross=Decimal(0), fees=fee*(abs(leftover)/abs(change)), funding=Decimal(0))
                    quantity = leftover
                    signed_cost = leftover*price
        basis = signed_cost/quantity if quantity else Decimal(0)
        floating = quantity*mark-signed_cost
        expected = dict(index=index, timestamp=timestamp, kind=kind, trade_id=active_id or serial,
                        funding_id=funding_id, funding_quantity=_number(due_qty), pending_count=len(due),
                        mark_price=_number(mark), position_quantity=_number(quantity), basis=_number(basis),
                        cash=_number(cash), unrealized_pnl=_number(floating), equity=_number(cash+floating),
                        fee=_number(fee), realized_pnl=_number(realized), funding_cashflow=_number(funding))
        _check(ledger[index-1], expected, f"ledger[{index}]")
    _need(not due, "unposted funding due")
    _need(len(trades) == len(closed), "closed trade count mismatch")
    for row, identifier in zip(trades, closed):
        c = cycles[identifier]
        _check(row, dict(trade_id=identifier, side=c["side"], entry_time=c["opened"], exit_time=c["ended"],
                         quantity=_number(c["opening_quantity"]), entry_price=_number(c["buy_value"]/c["bought"]),
                         exit_price=_number(c["sell_value"]/c["sold"]), gross_pnl=_number(c["gross"]),
                         fees=_number(c["fees"]), funding_cashflow=_number(c["funding"]),
                         net_pnl=_number(c["gross"]-c["fees"]+c["funding"])), f"trade[{identifier}]")
    floating = quantity*mark-signed_cost
    _check(summary, dict(initial_cash=initial, final_cash=_number(cash), final_equity=_number(cash+floating),
                         position_quantity=_number(quantity), entry_price=_number(signed_cost/quantity) if quantity else 0.0,
                         unrealized_pnl=_number(floating), realized_pnl=_number(realized_total), fees=_number(fee_total),
                         funding_cashflow=_number(funding_total), net_pnl=_number(cash+floating-_d(initial)),
                         closed_trades=len(closed), events=len(events)), "summary")
    return dict(status="PASS", model=EVENT_MODEL, data_kind=run["data_kind"], events=len(events),
                supplied_fills=sum(e["kind"] == "fill" for e in events), closed_trades=len(closed),
                final_equity=_number(cash+floating), open_quantity=_number(quantity),
                checks=["file_integrity", "input_schema", "partial_fill_accounting", "funding_due_post",
                        "equity", "trade_totals", "summary"], scope="accounting_consistency_only")
