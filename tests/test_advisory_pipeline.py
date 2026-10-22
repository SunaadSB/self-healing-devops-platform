"""Regression tests for the safe anomaly-to-advisory pipeline."""
import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_advisory_pipeline.py"
FIELDS = [
    "timestamp", "service", "is_anomaly", "anomaly_score",
    "request_rate", "error_ratio", "p95_latency_seconds",
]


def write_synthetic_dataset(path: Path) -> None:
    path.write_text(
        "timestamp,service,request_rate,error_ratio,p95_latency_seconds\n"
        "2026-01-01T00:00:00Z,user-service,1,0,0.1\n",
        encoding="utf-8",
    )


def write_anomaly_report(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for second in range(3):
            writer.writerow({
                "timestamp": f"2026-01-01T00:00:{second:02d}Z",
                "service": "user-service",
                "is_anomaly": "True",
                "anomaly_score": "-0.2",
                "request_rate": "10",
                "error_ratio": "0",
                "p95_latency_seconds": "0.5",
            })


def run_pipeline(monkeypatch, dataset, model_dir, report, recommendations):
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--dataset", str(dataset), "--model-dir", str(model_dir),
        "--report", str(report), "--recommendations", str(recommendations),
    ])
    import importlib.util
    spec = importlib.util.spec_from_file_location("advisory_pipeline_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


def test_pipeline_passes_anomaly_report_to_advisory_engine(tmp_path, monkeypatch):
    dataset = tmp_path / "metrics.csv"
    model_dir = tmp_path / "models"
    report = tmp_path / "anomalies.csv"
    recommendations = tmp_path / "recommendations.csv"
    write_synthetic_dataset(dataset)

    import importlib.util
    spec = importlib.util.spec_from_file_location("advisory_pipeline_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--dataset", str(dataset), "--model-dir", str(model_dir),
        "--report", str(report), "--recommendations", str(recommendations),
    ])

    real_run = subprocess.run
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if str(command[0]) == sys.executable and command[1].endswith("detect_anomalies_v2.py"):
            write_anomaly_report(report)
            return subprocess.CompletedProcess(command, 0)
        return real_run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.main() == 0
    assert len(calls) == 2
    with recommendations.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["service"] == "user-service"
    assert rows[0]["recommendation"] == "review_recovery"
    assert rows[0]["status"] == "advisory_only"
    assert all("kubectl" not in " ".join(command).lower() for command in calls)


@pytest.mark.parametrize("collision", ["dataset", "report"])
def test_pipeline_rejects_colliding_output_paths(tmp_path, monkeypatch, capsys, collision):
    dataset = tmp_path / "metrics.csv"
    model_dir = tmp_path / "models"
    report = tmp_path / "anomalies.csv"
    recommendations = tmp_path / "recommendations.csv"
    write_synthetic_dataset(dataset)
    if collision == "dataset":
        recommendations = dataset
    else:
        recommendations = report

    import importlib.util
    spec = importlib.util.spec_from_file_location("advisory_pipeline_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--dataset", str(dataset), "--model-dir", str(model_dir),
        "--report", str(report), "--recommendations", str(recommendations),
    ])
    assert module.main() == 2
    assert "must be different" in capsys.readouterr().err
