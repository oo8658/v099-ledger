"""Write and verify a self-contained v3 supplied-events report."""

import os
from pathlib import Path
import re
import shutil
import tempfile

from . import __version__
from .event_formats import EVENT_MODEL, EVENT_REPORT_FILES, validate_events
from .event_verification import verify_event_report
from .formats import finite, sha256, write_json


def save_event_report(folder, events, result, *, symbol="SYNTH", data_kind="user_supplied"):
    target = Path(folder).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite {target}")
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9_-]{1,32}", symbol):
        raise ValueError("invalid symbol label")
    if data_kind not in ("synthetic", "user_supplied"):
        raise ValueError("invalid data kind")
    events = validate_events(events)
    initial = finite(result["initial_cash"], "initial_cash")
    if initial <= 0:
        raise ValueError("initial_cash must be positive")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".v099-ledger-v3-", dir=target.parent))
    published = False
    try:
        write_json(stage/"run.json", dict(schema_version=3, package_version=__version__, model=EVENT_MODEL,
                   symbol=symbol, data_kind=data_kind, initial_cash=initial, quantity_unit="base_asset",
                   cash_unit="quote_asset", event_order="input_order"))
        write_json(stage/"events.json", events)
        write_json(stage/"ledger.json", result["ledger"])
        write_json(stage/"trades.json", result["trades"])
        write_json(stage/"summary.json", result["summary"])
        write_json(stage/"manifest.json", {"schema_version": 3,
                   "files": {name: sha256(stage/name) for name in EVENT_REPORT_FILES}})
        verified = verify_event_report(stage)
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
