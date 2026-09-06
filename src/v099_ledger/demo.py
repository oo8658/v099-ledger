"""Artificial valuations and explicitly prescribed fills; no strategy logic."""


def synthetic_inputs():
    # Round numbers are chosen solely for hand calculation. Timestamps are
    # artificial milliseconds, not a market history or trading schedule.
    market = [
        {"timestamp": 0, "mark_price": 100.0, "funding_rate": 0.0},
        {"timestamp": 1000, "mark_price": 101.0, "funding_rate": 0.01},
        {"timestamp": 2000, "mark_price": 103.0, "funding_rate": 0.0},
        {"timestamp": 3000, "mark_price": 100.0, "funding_rate": 0.0},
        {"timestamp": 4000, "mark_price": 98.0, "funding_rate": -0.01},
        {"timestamp": 5000, "mark_price": 97.0, "funding_rate": 0.0},
    ]
    fills = [
        {"timestamp": 0, "quantity": 2.0, "price": 100.0, "fee_rate": 0.001},
        {"timestamp": 2000, "quantity": -2.0, "price": 103.0, "fee_rate": 0.001},
        {"timestamp": 3000, "quantity": -1.0, "price": 100.0, "fee_rate": 0.001},
        {"timestamp": 5000, "quantity": 1.0, "price": 97.0, "fee_rate": 0.001},
    ]
    return market, fills

