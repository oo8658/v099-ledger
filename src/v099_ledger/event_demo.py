"""Arithmetic-only synthetic inputs; every event is written explicitly."""


def synthetic_events():
    return [
        {"timestamp": 0, "kind": "mark", "price": 100},
        {"timestamp": 0, "kind": "fill", "quantity": 2, "price": 100, "fee_rate": 0.001},
        {"timestamp": 1000, "kind": "funding_due", "id": "F1"},
        {"timestamp": 1000, "kind": "mark", "price": 101},
        {"timestamp": 1000, "kind": "fill", "quantity": 1, "price": 102, "fee_rate": 0.001},
        {"timestamp": 2000, "kind": "fill", "quantity": -1, "price": 103, "fee_rate": 0.001},
        {"timestamp": 2000, "kind": "mark", "price": 103},
        {"timestamp": 3000, "kind": "fill", "quantity": -2, "price": 104, "fee_rate": 0.001},
        {"timestamp": 4000, "kind": "funding_post", "id": "F1", "rate": 0.01, "settlement_mark": 102},
        {"timestamp": 4000, "kind": "mark", "price": 104},
        {"timestamp": 5000, "kind": "fill", "quantity": -1, "price": 105, "fee_rate": 0.001},
        {"timestamp": 6000, "kind": "fill", "quantity": 2, "price": 100, "fee_rate": 0.001},
        {"timestamp": 6000, "kind": "mark", "price": 100},
    ]
