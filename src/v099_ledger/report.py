"""Export only declared accounting fields to a self-contained data bundle."""

import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from . import __version__
from .formats import MODEL, MARKET_FIELDS, FILL_FIELDS, EQUITY_FIELDS, TRADE_FIELDS, REPORT_FILES, sha256, validate_inputs, write_csv, write_json


def save_report(folder, market, fills, result, *, symbol="SYNTH", data_kind="user_supplied"):
    target = Path(folder).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite {target}")
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9_-]{1,32}", symbol):
        raise ValueError("invalid symbol label")
    if data_kind not in ("synthetic", "user_supplied"):
        raise ValueError("data_kind must be synthetic or user_supplied")
    market, fills = validate_inputs(market, fills)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".v099-ledger-", dir=target.parent))
    published = False
    try:
        write_json(stage/"run.json", dict(schema_version=2, package_version=__version__, model=MODEL,
            symbol=symbol, data_kind=data_kind, initial_cash=result["initial_cash"], quantity_unit="base_asset",
            cash_unit="quote_asset", settlement_order="funding_then_fills"))
        write_csv(stage/"market.csv", MARKET_FIELDS, market)
        write_csv(stage/"fills.csv", FILL_FIELDS, fills)
        write_csv(stage/"equity.csv", EQUITY_FIELDS, result["equity"])
        write_csv(stage/"trades.csv", TRADE_FIELDS, result["trades"])
        (stage/"ledger.jsonl").write_text("".join(json.dumps(row, sort_keys=True, allow_nan=False)+"\n" for row in result["ledger"]), encoding="utf-8")
        write_json(stage/"summary.json", result["summary"])
        write_json(stage/"manifest.json", {"schema_version": 2, "files": {name: sha256(stage/name) for name in REPORT_FILES}})
        from .verification import verify_report
        verified = verify_report(stage)
        target.mkdir()
        published = True
        for path in stage.iterdir():
            os.replace(path, target/path.name)
        return verified
    except BaseException:
        if published:
            shutil.rmtree(target)
        raise
    finally:
        shutil.rmtree(stage)

