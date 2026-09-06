"""Strict data formats and serialization, with no trading decisions."""

import csv
import hashlib
import json
import math
from pathlib import Path

MARKET_FIELDS = ("timestamp", "mark_price", "funding_rate")
FILL_FIELDS = ("timestamp", "quantity", "price", "fee_rate")
EQUITY_FIELDS = ("timestamp", "cash", "quantity", "entry_price", "unrealized_pnl", "equity")
TRADE_FIELDS = ("trade_id", "side", "entry_time", "exit_time", "quantity", "entry_price", "exit_price",
                "gross_pnl", "fees", "funding_cashflow", "net_pnl")
EVENT_FIELDS = ("sequence", "timestamp", "kind", "trade_id", "fill_index", "quantity", "price", "fee_rate", "fee",
                "funding_rate", "funding_cashflow", "realized_pnl", "delta_cash")
REPORT_FILES = ("run.json", "market.csv", "fills.csv", "ledger.jsonl", "equity.csv", "trades.csv", "summary.json")
MODEL = "linear-perpetual-supplied-fills-v2"


def finite(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label}: boolean is not a number")
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{label}: invalid number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label}: non-finite number")
    return value


def integer(value, label):
    value = finite(value, label)
    if value != int(value) or not 0 <= value <= 2**53-1:
        raise ValueError(f"{label}: expected a non-negative exact integer")
    return int(value)


def validate_inputs(market, fills):
    cleaned_market, cleaned_fills = [], []
    for row in market:
        if set(row) != set(MARKET_FIELDS):
            raise ValueError("market fields do not match schema")
        r = {k: integer(row[k], k) if k == "timestamp" else finite(row[k], k) for k in MARKET_FIELDS}
        if r["mark_price"] <= 0 or abs(r["funding_rate"]) >= 1:
            raise ValueError("mark_price must be positive; funding_rate must be in (-1,1)")
        if cleaned_market and r["timestamp"] <= cleaned_market[-1]["timestamp"]:
            raise ValueError("market timestamps must be unique and increasing")
        cleaned_market.append(r)
    if not cleaned_market:
        raise ValueError("at least one valuation observation is required")
    times = {r["timestamp"] for r in cleaned_market}
    for row in fills:
        if set(row) != set(FILL_FIELDS):
            raise ValueError("fill fields do not match schema")
        r = {k: integer(row[k], k) if k == "timestamp" else finite(row[k], k) for k in FILL_FIELDS}
        if r["timestamp"] not in times or (cleaned_fills and r["timestamp"] < cleaned_fills[-1]["timestamp"]):
            raise ValueError("fills must be time ordered and match valuation timestamps")
        if r["quantity"] == 0 or r["price"] <= 0 or not 0 <= r["fee_rate"] < 1:
            raise ValueError("fill quantity must be nonzero, price positive, fee_rate in [0,1)")
        cleaned_fills.append(r)
    return cleaned_market, cleaned_fills


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def parse_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject(value):
        raise ValueError(f"non-finite JSON value: {value}")

    return json.loads(text, object_pairs_hook=unique, parse_constant=reject)


def read_json(path):
    return parse_json(Path(path).read_text(encoding="utf-8"))


def write_csv(path, fields, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path, fields):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(fields):
            raise ValueError(f"{Path(path).name}: unexpected CSV header")
        rows = list(reader)
    if any(set(row) != set(fields) or any(v is None or v == "" for v in row.values()) for row in rows):
        raise ValueError(f"{Path(path).name}: malformed CSV row")
    return rows

