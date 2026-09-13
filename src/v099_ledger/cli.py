"""Offline synthetic demos and independent report verification."""

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
    event_demo = commands.add_parser("demo-events", help="write a new synthetic v3 supplied-events report")
    event_demo.add_argument("--output", required=True)
    event_verify = commands.add_parser("verify-events", help="independently reconstruct a v3 report")
    event_verify.add_argument("report")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            from .verification import verify_report
            result = verify_report(args.report)
        elif args.command == "verify-events":
            from .event_verification import verify_event_report
            result = verify_event_report(args.report)
        elif args.command == "demo-events":
            from .event_report import save_event_report
            from .event_accounting import account_events
            from .event_demo import synthetic_events
            events = synthetic_events()
            accounting = account_events(events, initial_cash=1000)
            result = save_event_report(args.output, events, accounting, data_kind="synthetic")
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
