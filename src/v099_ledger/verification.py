"""Independent reconstruction from supplied valuations and fills.

Only schema/serialization helpers are shared with the accounting module.
No strategy, executable report input or accounting-engine import is used.
"""

import csv
import math
from pathlib import Path
import re
from .formats import (MODEL, MARKET_FIELDS, FILL_FIELDS, EQUITY_FIELDS, TRADE_FIELDS, EVENT_FIELDS,
                      REPORT_FILES, finite, integer, parse_json, read_csv, read_json, sha256, validate_inputs)


class VerificationError(ValueError):
    """A required verification failed; never an implicit skipped pass."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def compare(actual, expected, label, *, absolute=1e-7):
    actual = finite(actual, label)
    require(math.isfinite(expected) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=absolute),
            f"{label}: claimed {actual:.12g}, expected {expected:.12g}")
    return abs(actual-expected)


def verify_report(folder):
    try:
        return _verify(Path(folder))
    except VerificationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, csv.Error) as exc:
        raise VerificationError(f"invalid report: {exc}") from exc


def _verify(folder):
    for name in ("manifest.json", *REPORT_FILES):
        path = folder/name
        require(path.is_file() and not path.is_symlink(), f"required regular file missing: {name}")
    manifest = read_json(folder/"manifest.json")
    require(set(manifest) == {"schema_version", "files"} and type(manifest["schema_version"]) is int and manifest["schema_version"] == 2,
            "unsupported manifest schema")
    require(set(manifest["files"]) == set(REPORT_FILES), "manifest must cover every required report file")
    for name in REPORT_FILES:
        digest = manifest["files"][name]
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), f"invalid SHA256: {name}")
        require(sha256(folder/name) == digest, f"hash mismatch: {name}")
    run = read_json(folder/"run.json")
    require(set(run) == {"schema_version", "package_version", "model", "symbol", "data_kind", "initial_cash",
                         "quantity_unit", "cash_unit", "settlement_order"}, "unexpected run fields")
    require(type(run["schema_version"]) is int and run["schema_version"] == 2 and run["model"] == MODEL, "unsupported accounting model")
    require(run["quantity_unit"] == "base_asset" and run["cash_unit"] == "quote_asset" and run["settlement_order"] == "funding_then_fills", "unsupported units or settlement order")
    require(isinstance(run["symbol"], str) and re.fullmatch(r"[A-Z0-9_-]{1,32}", run["symbol"]), "invalid symbol")
    require(run["data_kind"] in ("synthetic", "user_supplied"), "invalid data_kind")
    require(isinstance(run["package_version"], str), "invalid package_version")
    initial = finite(run["initial_cash"], "initial_cash")
    require(initial > 0, "initial_cash must be positive")
    market, fills = validate_inputs(read_csv(folder/"market.csv", MARKET_FIELDS), read_csv(folder/"fills.csv", FILL_FIELDS))
    events = [parse_json(line) for line in (folder/"ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    points = read_csv(folder/"equity.csv", EQUITY_FIELDS)
    reported_trades = read_csv(folder/"trades.csv", TRADE_FIELDS)
    require(len(points) == len(market), "valuation row count mismatch")
    cash, position, entry = initial, 0.0, 0.0
    event_cursor, fill_cursor, trade_id = 0, 0, 0
    current = None
    trades = []
    total_fees = total_funding = total_realized = 0.0
    max_error = 0.0

    def check_event(expected):
        nonlocal event_cursor
        require(event_cursor < len(events), "missing ledger event")
        actual = events[event_cursor]
        require(set(actual) == set(EVENT_FIELDS), "event fields do not match schema")
        expected["sequence"] = event_cursor+1
        for key in EVENT_FIELDS:
            if key == "kind":
                require(actual[key] == expected[key], "unexpected ledger event kind/order")
            elif key in {"sequence", "timestamp", "trade_id", "fill_index"}:
                require(integer(actual[key], key) == expected[key], f"event {key} mismatch")
            else:
                compare(actual[key], expected[key], f"event {key}", absolute=0 if key in {"quantity", "price", "fee_rate", "funding_rate"} else 1e-7)
        event_cursor += 1

    for row_index, observation in enumerate(market):
        t = observation["timestamp"]
        mark, rate = observation["mark_price"], observation["funding_rate"]
        # Reconstruct the expected settlement from the position before fills.
        settlement = -position*mark*rate
        if settlement != 0:
            check_event(dict(timestamp=t, kind="funding", trade_id=trade_id, fill_index=0,
                quantity=position, price=mark, fee_rate=0.0, fee=0.0, funding_rate=rate,
                funding_cashflow=settlement, realized_pnl=0.0, delta_cash=settlement))
            cash += settlement
            total_funding += settlement
            current["funding_cashflow"] += settlement
        while fill_cursor < len(fills) and fills[fill_cursor]["timestamp"] == t:
            fill = fills[fill_cursor]
            qty, price, fee_rate = fill["quantity"], fill["price"], fill["fee_rate"]
            fill_cursor += 1
            fee = abs(qty)*price*fee_rate
            if position == 0:
                trade_id += 1
                gross = 0.0
                kind = "open"
                current = dict(trade_id=trade_id, side="long" if qty > 0 else "short", entry_time=t,
                               quantity=qty, entry_price=price, fees=fee, funding_cashflow=0.0)
                position, entry = qty, price
            else:
                require(qty == -position, "fill does not fully close the existing position")
                gross = position*(price-entry)
                kind = "close"
                current["fees"] += fee
                current.update(exit_time=t, exit_price=price, gross_pnl=gross,
                               net_pnl=gross-current["fees"]+current["funding_cashflow"])
                trades.append(current)
                position, entry, current = 0.0, 0.0, None
            check_event(dict(timestamp=t, kind=kind, trade_id=trade_id, fill_index=fill_cursor,
                quantity=qty, price=price, fee_rate=fee_rate, fee=fee, funding_rate=0.0,
                funding_cashflow=0.0, realized_pnl=gross, delta_cash=gross-fee))
            cash += gross-fee
            total_fees += fee
            total_realized += gross
        unrealized = position*(mark-entry)
        equity = cash+unrealized
        point = points[row_index]
        require(integer(point["timestamp"], "equity timestamp") == t, "equity timestamp mismatch")
        for key, value in dict(cash=cash, quantity=position, entry_price=entry, unrealized_pnl=unrealized, equity=equity).items():
            max_error = max(max_error, compare(point[key], value, key, absolute=0 if key in {"quantity", "entry_price"} else 1e-7))
    require(event_cursor == len(events), "extra ledger event")
    require(len(reported_trades) == len(trades), "closed trade count mismatch")
    for actual, expected in zip(reported_trades, trades):
        for key in TRADE_FIELDS:
            if key == "side":
                require(actual[key] == expected[key], "trade side mismatch")
            elif key in {"trade_id", "entry_time", "exit_time"}:
                require(integer(actual[key], key) == expected[key], f"trade {key} mismatch")
            else:
                compare(actual[key], expected[key], f"trade {key}", absolute=0 if key in {"quantity", "entry_price", "exit_price"} else 1e-7)
    summary = read_json(folder/"summary.json")
    expected_summary = dict(initial_cash=initial, final_cash=cash, final_equity=equity,
        position_quantity=position, entry_price=entry, unrealized_pnl=unrealized, realized_pnl=total_realized,
        fees=total_fees, funding_cashflow=total_funding, net_pnl=equity-initial,
        closed_trades=len(trades), ledger_events=len(events))
    require(set(summary) == set(expected_summary), "unexpected summary fields")
    for key, value in expected_summary.items():
        if key in {"closed_trades", "ledger_events"}:
            require(integer(summary[key], key) == value, f"summary {key} mismatch")
        else:
            compare(summary[key], value, f"summary {key}", absolute=0 if key in {"position_quantity", "entry_price"} else 1e-7)
    return dict(status="PASS", model=MODEL, data_kind=run["data_kind"], observations=len(market),
                supplied_fills=len(fills), closed_trades=len(trades), ledger_events=len(events),
                final_equity=equity, open_quantity=position, max_state_error=max_error,
                checks=["file_integrity", "input_schema", "supplied_fill_accounting", "funding_completeness", "equity", "trade_totals", "summary"],
                scope="accounting_consistency_only")

