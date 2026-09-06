import copy
import json
import subprocess
import sys
import pytest
from v099_ledger.accounting import account
from v099_ledger.demo import synthetic_inputs
from v099_ledger.formats import read_json, sha256, write_json
from v099_ledger.report import save_report
from v099_ledger.verification import VerificationError, verify_report


@pytest.fixture
def report(tmp_path):
    market, fills = synthetic_inputs()
    path = tmp_path/"report"
    save_report(path, market, fills, account(market, fills, initial_cash=1000), data_kind="synthetic")
    return path


def restamp(path):
    manifest = read_json(path/"manifest.json")
    manifest["files"] = {name: sha256(path/name) for name in manifest["files"]}
    write_json(path/"manifest.json", manifest)


def events(path):
    return [json.loads(line) for line in (path/"ledger.jsonl").read_text().splitlines()]


def write_events(path, rows):
    for i, row in enumerate(rows, 1): row["sequence"] = i
    (path/"ledger.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))


def test_roundtrip(report):
    checked = verify_report(report)
    assert checked["status"] == "PASS"
    assert (checked["observations"], checked["supplied_fills"], checked["closed_trades"], checked["ledger_events"]) == (6, 4, 2, 6)
    assert checked["scope"] == "accounting_consistency_only"


@pytest.mark.parametrize("mutation", ["quantity", "fee", "price", "cash", "funding", "missing_funding", "extra_funding", "fill_identity"])
def test_restamped_ledger_still_rejected(report, mutation):
    rows = events(report)
    funding = next(row for row in rows if row["kind"] == "funding")
    if mutation == "quantity": rows[0]["quantity"] *= 2
    elif mutation == "fee": rows[0]["fee"] += 1
    elif mutation == "price": rows[0]["price"] += 1
    elif mutation == "cash": rows[0]["delta_cash"] += 1
    elif mutation == "funding": funding["funding_cashflow"] *= -1
    elif mutation == "missing_funding": rows.remove(funding)
    elif mutation == "extra_funding": rows.insert(rows.index(funding), copy.deepcopy(funding))
    else: rows[0]["fill_index"] += 1
    write_events(report, rows)
    restamp(report)
    with pytest.raises(VerificationError): verify_report(report)


@pytest.mark.parametrize("name", ["equity.csv", "trades.csv", "fills.csv", "market.csv", "summary.json"])
def test_changed_inputs_or_derived_totals_cannot_keep_old_report(report, name):
    path = report/name
    if name.endswith("json"):
        result = read_json(path); result["net_pnl"] += 1; write_json(path, result)
    else:
        rows = path.read_text().splitlines()
        columns = rows[-1].split(","); columns[-1] = str(float(columns[-1])+0.01)
        rows[-1] = ",".join(columns); path.write_text("\n".join(rows)+"\n")
    restamp(report)
    with pytest.raises(VerificationError): verify_report(report)


@pytest.mark.parametrize("mutation", ["missing_file", "missing_hash", "path", "unknown_model", "duplicate_json", "nan", "oversized_csv", "symlink"])
def test_malformed_reports_fail(report, tmp_path, mutation):
    if mutation == "missing_file": (report/"fills.csv").unlink()
    elif mutation in ("missing_hash", "path"):
        value = read_json(report/"manifest.json")
        if mutation == "missing_hash": del value["files"]["fills.csv"]
        else: value["files"]["../outside.csv"] = "0"*64
        write_json(report/"manifest.json", value)
    elif mutation == "unknown_model":
        value = read_json(report/"run.json"); value["model"] = "unknown"; write_json(report/"run.json", value); restamp(report)
    elif mutation == "duplicate_json":
        p = report/"run.json"; p.write_text(p.read_text().replace('"initial_cash": 1000.0', '"initial_cash": 1000.0, "initial_cash": 1')); restamp(report)
    elif mutation == "nan":
        rows = events(report); rows[0]["fee"] = float("nan"); write_events(report, rows); restamp(report)
    elif mutation == "oversized_csv":
        p = report/"equity.csv"; p.write_text(p.read_text()+"9"*200_000+"\n"); restamp(report)
    else:
        outside = tmp_path/"outside.csv"; (report/"fills.csv").rename(outside); (report/"fills.csv").symlink_to(outside)
    with pytest.raises(VerificationError): verify_report(report)


def test_unrestamped_edit_fails_hash(report):
    p = report/"summary.json"; p.write_text(p.read_text()+" ")
    with pytest.raises(VerificationError, match="hash mismatch"): verify_report(report)


def test_tiny_quantity_mismatch_is_not_hidden_by_cash_tolerance(tmp_path):
    market, fills = synthetic_inputs()
    for fill in fills: fill["quantity"] *= 1e-10
    path = tmp_path/"tiny"
    save_report(path, market, fills, account(market, fills, initial_cash=1000), data_kind="synthetic")
    rows = events(path); rows[0]["quantity"] *= 0.5; write_events(path, rows); restamp(path)
    with pytest.raises(VerificationError, match="quantity"): verify_report(path)


@pytest.mark.parametrize("mode", ["cash", "open"])
def test_no_forced_close_or_trades(tmp_path, mode):
    market, fills = synthetic_inputs()
    fills = [] if mode == "cash" else fills[:1]
    result = save_report(tmp_path/mode, market, fills, account(market, fills, initial_cash=1000), data_kind="synthetic")
    assert result["closed_trades"] == 0
    assert result["open_quantity"] == (0 if mode == "cash" else 2)


def test_verifier_does_not_import_accounting_module(report):
    code = '''
import sys
class BlockAccounting:
    def find_spec(self, fullname, *args):
        if fullname == 'v099_ledger.accounting':
            raise RuntimeError('verification imported accounting')
sys.meta_path.insert(0, BlockAccounting())
from v099_ledger.verification import verify_report
print(verify_report(sys.argv[1])['status'])
'''
    p = subprocess.run([sys.executable, "-c", code, str(report)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "PASS"


def test_optimized_python_does_not_skip_checks(report):
    value = read_json(report/"summary.json"); value["fees"] += 1; write_json(report/"summary.json", value); restamp(report)
    p = subprocess.run([sys.executable, "-O", "-m", "v099_ledger", "verify", str(report)], capture_output=True, text=True)
    assert p.returncode == 1 and '"status": "FAIL"' in p.stderr and "Traceback" not in p.stderr


def test_output_refuses_overwrite_and_invalid_result_cleans_stage(report, tmp_path):
    market, fills = synthetic_inputs(); result = account(market, fills, initial_cash=1000)
    before = sha256(report/"manifest.json")
    with pytest.raises(FileExistsError): save_report(report, market, fills, result)
    assert sha256(report/"manifest.json") == before
    result["equity"][0]["cash"] += 1
    with pytest.raises(VerificationError): save_report(tmp_path/"bad", market, fills, result)
    assert not (tmp_path/"bad").exists() and not list(tmp_path.glob(".v099-ledger-*"))


def test_cli_demo_is_deterministic(tmp_path):
    for name in ("one", "two"):
        p = subprocess.run([sys.executable, "-m", "v099_ledger", "demo", "--output", str(tmp_path/name)], capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
    for p in (tmp_path/"one").iterdir(): assert p.read_bytes() == (tmp_path/"two"/p.name).read_bytes()
    p = subprocess.run([sys.executable, "-m", "v099_ledger", "demo", "--output", str(tmp_path/"one")], capture_output=True, text=True)
    assert p.returncode == 1

