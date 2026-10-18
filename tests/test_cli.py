import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_command_writes_reconciled_results(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "battery_dispatch.cli", "--output", str(tmp_path)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert json.loads(completed.stdout) == summary
    with (tmp_path / "dispatch.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == summary["half_hour_periods"] == 336
    assert summary["trading_profit_gbp"] == pytest.approx(1239.63906398892, abs=0.01)
    assert sum(float(row["profit_gbp"]) for row in rows) == pytest.approx(summary["trading_profit_gbp"])
    assert summary["grid_export_mwh"] == pytest.approx(summary["grid_import_mwh"] * 0.95**2)


def test_invalid_run_does_not_write_results(tmp_path):
    output = tmp_path / "invalid"
    completed = subprocess.run(
        [sys.executable, "-m", "battery_dispatch.cli", "--days", "0", "--output", str(output)],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    assert completed.returncode == 1
    assert "Days must be positive" in completed.stderr
    assert not output.exists()
