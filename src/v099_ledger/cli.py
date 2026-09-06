"""Two offline commands: produce a synthetic demo, or verify a report."""

import argparse
import json
import sys
from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(prog="v099-ledger", description="Offline perpetual accounting and verification")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="write a new synthetic report (no network)")
    demo.add_argument("--output", required=True)
    verify = commands.add_parser("verify", help="independently reconstruct an existing report")
    verify.add_argument("report")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            from .verification import verify_report
            result = verify_report(args.report)
        else:
            from .report import save_report
            from .accounting import account
            from .demo import synthetic_inputs
            market, fills = synthetic_inputs()
            accounting = account(market, fills, initial_cash=1000)
            result = save_report(args.output, market, fills, accounting, data_kind="synthetic")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
