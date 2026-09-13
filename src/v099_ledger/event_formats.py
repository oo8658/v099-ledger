"""Strict schema for caller-supplied accounting events; no decision rules."""

import re

from .formats import finite, integer


EVENT_REPORT_FILES = ("run.json", "events.json", "ledger.json", "trades.json", "summary.json")
EVENT_MODEL = "linear-perpetual-supplied-events-v3"
FUNDING_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
FIELDS = {
    "mark": frozenset(("timestamp", "kind", "price")),
    "fill": frozenset(("timestamp", "kind", "quantity", "price", "fee_rate")),
    "funding_due": frozenset(("timestamp", "kind", "id")),
    "funding_post": frozenset(("timestamp", "kind", "id", "rate", "settlement_mark")),
}


def validate_events(events):
    if not isinstance(events, (list, tuple)) or not events:
        raise ValueError("events must be a nonempty ordered list")
    cleaned = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each event must be an object")
        kind = event.get("kind")
        if not isinstance(kind, str) or kind not in FIELDS or set(event) != FIELDS[kind]:
            raise ValueError("event fields do not match the declared kind")
        row = {"timestamp": integer(event["timestamp"], "timestamp"), "kind": kind}
        if cleaned and row["timestamp"] < cleaned[-1]["timestamp"]:
            raise ValueError("event timestamps must be nondecreasing")
        if kind in ("mark", "fill"):
            row["price"] = finite(event["price"], "price")
            if row["price"] <= 0:
                raise ValueError("price must be positive")
        if kind == "fill":
            row["quantity"] = finite(event["quantity"], "quantity")
            row["fee_rate"] = finite(event["fee_rate"], "fee_rate")
            if row["quantity"] == 0 or not 0 <= row["fee_rate"] < 1:
                raise ValueError("quantity must be nonzero and fee_rate in [0,1)")
        if kind in ("funding_due", "funding_post"):
            if not isinstance(event["id"], str) or not FUNDING_ID.fullmatch(event["id"]):
                raise ValueError("invalid funding id")
            row["id"] = event["id"]
        if kind == "funding_post":
            row["rate"] = finite(event["rate"], "rate")
            row["settlement_mark"] = finite(event["settlement_mark"], "settlement_mark")
            if abs(row["rate"]) >= 1 or row["settlement_mark"] <= 0:
                raise ValueError("rate must be in (-1,1) and settlement_mark positive")
        cleaned.append(row)
    if cleaned[0]["kind"] != "mark":
        raise ValueError("the first event must supply a mark")
    return cleaned
