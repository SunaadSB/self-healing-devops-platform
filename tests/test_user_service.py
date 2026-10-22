import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "user-service"
    / "main.py"
)

spec = importlib.util.spec_from_file_location("user_service_main", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

client = TestClient(module.app)


def test_health_endpoints():
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").json()["status"] == "ready"


def test_create_and_retrieve_user():
    user_id = "test-user-001"
    created = client.post(
        "/users",
        json={
            "user_id": user_id,
            "name": "Test User",
            "email": "test@example.com",
        },
    )
    assert created.status_code == 201
    assert client.get(f"/users/{user_id}").json()["name"] == "Test User"


def test_duplicate_user_rejected():
    payload = {
        "user_id": "duplicate-user",
        "name": "Duplicate",
        "email": "duplicate@example.com",
    }
    assert client.post("/users", json=payload).status_code == 201
    assert client.post("/users", json=payload).status_code == 409


def test_missing_user_returns_404():
    response = client.get("/users/does-not-exist")
    assert response.status_code == 404


def test_invalid_user_id_rejected():
    response = client.post(
        "/users",
        json={
            "user_id": "invalid/id",
            "name": "Invalid",
            "email": "invalid@example.com",
        },
    )
    assert response.status_code == 422


def test_metrics_exposed():
    client.get("/health/live")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "http_request_duration_seconds" in response.text

def _metric_value(metric_name, labels):
    from prometheus_client.parser import text_string_to_metric_families

    exposition = module.generate_latest().decode("utf-8")
    for family in text_string_to_metric_families(exposition):
        for sample in family.samples:
            if sample.name == metric_name and all(
                sample.labels.get(key) == value
                for key, value in labels.items()
            ):
                return sample.value
    return 0


def test_user_creation_metric_counts_only_successful_creation():
    user_id = "metrics-user-regression"
    before = _metric_value("users_created_total", {})

    payload = {
        "user_id": user_id,
        "name": "Metrics Test",
        "email": "metrics-test@example.com",
    }
    assert client.post("/users", json=payload).status_code == 201
    assert _metric_value("users_created_total", {}) == before + 1

    # A duplicate is rejected and must not increase the successful-create count.
    assert client.post("/users", json=payload).status_code == 409
    assert _metric_value("users_created_total", {}) == before + 1


def test_user_http_metrics_classify_4xx_and_normalize_routes():
    response = client.get("/users/metrics-missing-user")
    assert response.status_code == 404

    labels = {
        "service": "user-service",
        "method": "GET",
        "route": "/users/{user_id}",
        "error_type": "4xx",
    }
    assert _metric_value("http_error_responses_total", labels) >= 1

    exposition = module.generate_latest().decode("utf-8")
    assert 'le="0.005"' in exposition

