import csv
import json

from fastapi.testclient import TestClient

from dashboard import dashboard_app


client = TestClient(dashboard_app.app)


def test_pipeline_endpoint_returns_advisory_safety_status(tmp_path, monkeypatch):
    runs_path = tmp_path / "pipeline_runs.jsonl"
    runs_path.write_text(
        json.dumps({
            "run_id": "test-run",
            "status": "success",
            "mode": "advisory_only",
            "recovery_actions_executed": 0,
            "stages": [
                {"stage": "collect", "status": "success"},
                {"stage": "detect", "status": "success"},
                {"stage": "recommend", "status": "success"},
            ],
        }) + "\n",
        encoding="utf-8",
    )

    recommendations_path = tmp_path / "recommendations.csv"
    recommendations_path.write_text(
        "service,recommendation\norder-service,investigate\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(dashboard_app, "PIPELINE_RUNS_PATH", runs_path)
    monkeypatch.setattr(dashboard_app, "RECOMMENDATIONS_PATH", recommendations_path)
    monkeypatch.setattr(
        dashboard_app,
        "ANOMALY_REPORT_PATH",
        tmp_path / "missing-anomalies.csv",
    )

    response = client.get("/api/pipeline")
    assert response.status_code == 200
    data = response.json()

    assert data["latest"]["run_id"] == "test-run"
    assert data["safety"]["mode"] == "advisory_only"
    assert data["safety"]["automatic_recovery_enabled"] is False
    assert data["safety"]["recovery_actions_executed"] == 0
    assert data["recommendations"][0]["service"] == "order-service"


def test_pipeline_history_is_newest_first_and_limits_results(tmp_path, monkeypatch):
    runs_path = tmp_path / "pipeline_runs.jsonl"
    runs_path.write_text(
        "\n".join(
            json.dumps({"run_id": f"run-{i}", "status": "success"})
            for i in range(3)
        ) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "PIPELINE_RUNS_PATH", runs_path)

    response = client.get("/api/pipeline/history?limit=2")
    assert response.status_code == 200
    data = response.json()

    assert data["limit"] == 2
    assert [run["run_id"] for run in data["runs"]] == ["run-2", "run-1"]


def test_pipeline_anomalies_counts_service_flags(tmp_path, monkeypatch):
    report_path = tmp_path / "anomalies.csv"
    with report_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["service", "is_anomaly"],
        )
        writer.writeheader()
        writer.writerows([
            {"service": "order-service", "is_anomaly": "1"},
            {"service": "order-service", "is_anomaly": "0"},
            {"service": "payment-service", "is_anomaly": "-1"},
        ])

    monkeypatch.setattr(dashboard_app, "ANOMALY_REPORT_PATH", report_path)

    response = client.get("/api/pipeline/anomalies")
    assert response.status_code == 200
    data = response.json()

    assert data["total_rows"] == 3
    assert data["total_flagged"] == 2
    assert data["by_service"]["order-service"]["flagged"] == 1
    assert data["by_service"]["payment-service"]["flagged"] == 1
