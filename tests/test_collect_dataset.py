"""Offline tests for dataset collection safeguards."""
import csv
from pathlib import Path
from unittest.mock import patch

from ml import collect_dataset


def test_write_snapshot_preserves_unknown_error_ratio_as_blank(tmp_path):
    output = tmp_path / "metrics.csv"
    snapshot = {
        "user-service": {
            "request_rate": 1.25,
            "error_ratio": None,
            "p95_latency_seconds": 0.12,
        },
        "order-service": {
            "request_rate": 0.5,
            "error_ratio": 0.0,
            "p95_latency_seconds": 0.08,
        },
    }

    with patch.object(collect_dataset, "OUTPUT_FILE", output), \
         patch.object(collect_dataset, "collect_features", return_value=snapshot):
        rows_written = collect_dataset.write_snapshot()

    assert rows_written == 2
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["service"] == "user-service"
    assert rows[0]["error_ratio"] == ""
    assert rows[1]["service"] == "order-service"
    assert rows[1]["error_ratio"] == "0.0"


def test_write_snapshot_appends_without_duplicate_header(tmp_path):
    output = tmp_path / "metrics.csv"
    snapshot = {
        "payment-service": {
            "request_rate": 2.0,
            "error_ratio": 0.02,
            "p95_latency_seconds": 0.2,
        }
    }

    with patch.object(collect_dataset, "OUTPUT_FILE", output), \
         patch.object(collect_dataset, "collect_features", return_value=snapshot):
        assert collect_dataset.write_snapshot() == 1
        assert collect_dataset.write_snapshot() == 1

    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert sum(line.startswith("timestamp,service,") for line in lines) == 1
