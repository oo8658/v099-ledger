"""Hand-specified synthetic fills, not a trading strategy."""

import argparse
from v099_ledger.accounting import account
from v099_ledger.demo import synthetic_inputs
from v099_ledger.report import save_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    market, fills = synthetic_inputs()
    result = account(market, fills, initial_cash=1000)
    print(save_report(args.output, market, fills, result, data_kind="synthetic"))


if __name__ == "__main__":
    main()

