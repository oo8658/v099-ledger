import subprocess
import sys

import pytest

from v099_ledger.event_accounting import account_events
from v099_ledger.event_demo import synthetic_events
from v099_ledger.event_report import save_event_report
from v099_ledger.event_verification import EventVerificationError, verify_event_report
from v099_ledger.formats import read_json, sha256, write_json


@pytest.fixture
def report(tmp_path):
    events = synthetic_events()
    path = tmp_path/"report"
    save_event_report(path, events, account_events(events, initial_cash=1000), data_kind="synthetic")
    return path


def restamp(path):
    manifest = read_json(path/"manifest.json")
    manifest["files"] = {name: sha256(path/name) for name in manifest["files"]}
    write_json(path/"manifest.json", manifest)


def test_roundtrip_and_no_forced_close(report):
    checked = verify_event_report(report)
    assert (checked["events"], checked["supplied_fills"], checked["closed_trades"], checked["open_quantity"]) == (13, 6, 2, 1)
    assert checked["status"] == "PASS" and checked["scope"] == "accounting_consistency_only"


@pytest.mark.parametrize("file,key,change", [
    ("ledger.json", "position_quantity", 1),
    ("ledger.json", "funding_cashflow", 1),
    ("trades.json", "fees", 1),
    ("summary.json", "final_equity", 1),
    ("events.json", "quantity", 1),
])
def test_restamped_forgery_rejected(report, file, key, change):
    value = read_json(report/file)
    if file == "ledger.json":
        index = 8 if key == "funding_cashflow" else 1
        value[index][key] += change
    elif file == "trades.json":
        value[0][key] += change
    elif file == "events.json":
        value[1][key] += change
    else:
        value[key] += change
    write_json(report/file, value)
    restamp(report)
    with pytest.raises(EventVerificationError):
        verify_event_report(report)


def test_missing_extra_symlink_and_duplicate_json_rejected(report, tmp_path):
    (report/"extra.txt").write_text("x")
    with pytest.raises(EventVerificationError): verify_event_report(report)
    (report/"extra.txt").unlink()
    run = (report/"run.json").read_text()
    (report/"run.json").write_text(run.replace('"initial_cash": 1000.0', '"initial_cash": 1000.0, "initial_cash": 1'))
    restamp(report)
    with pytest.raises(EventVerificationError): verify_event_report(report)


def test_verifier_does_not_import_event_accounting(report):
    code = '''
import sys
class Block:
    def find_spec(self, name, *args):
        if name == "v099_ledger.event_accounting":
            raise RuntimeError("verifier imported accounting engine")
sys.meta_path.insert(0, Block())
from v099_ledger.event_verification import verify_event_report
print(verify_event_report(sys.argv[1])["status"])
'''
    process = subprocess.run([sys.executable, "-c", code, str(report)], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "PASS"


def test_optimized_python_still_rejects_forgery(report):
    value = read_json(report/"summary.json")
    value["fees"] += 1
    write_json(report/"summary.json", value)
    restamp(report)
    process = subprocess.run([sys.executable, "-O", "-m", "v099_ledger", "verify-events", str(report)], capture_output=True, text=True)
    assert process.returncode == 1 and '"status": "FAIL"' in process.stderr


def test_invalid_result_refused_before_publication(report, tmp_path):
    events = synthetic_events()
    result = account_events(events, initial_cash=1000)
    result["summary"]["fees"] += 1
    with pytest.raises(EventVerificationError):
        save_event_report(tmp_path/"bad", events, result, data_kind="synthetic")
    assert not (tmp_path/"bad").exists()
    assert not list(tmp_path.glob(".v099-ledger-v3-*"))
    with pytest.raises(FileExistsError):
        save_event_report(report, events, account_events(events, initial_cash=1000))
