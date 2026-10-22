import os
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1] / "services" / "payment-service"
sys.path.insert(0, str(SERVICE_DIR))

from fastapi.testclient import TestClient
import main as payment_main


def setup_function():
    with payment_main.payments_lock:
        payment_main.payments.clear()


def test_health_and_metrics():
    client = TestClient(payment_main.app)
    assert client.get("/health/live").json()["status"] == "alive"
    assert client.get("/health/ready").status_code == 200
    assert client.get("/metrics").status_code == 200


def payload(**overrides):
    data = {
        "payment_id": "pay-1",
        "order_id": "order-1",
        "user_id": "user-1",
        "amount": 19.99,
        "currency": "USD",
    }
    data.update(overrides)
    return data


def send(client, data=None, key="pay-1"):
    return client.post(
        "/payments",
        json=data or payload(),
        headers={"Idempotency-Key": key},
    )


def test_payment_is_approved_and_retrievable():
    client = TestClient(payment_main.app)
    response = send(client)
    assert response.status_code == 201
    assert response.json()["status"] == "approved"
    assert client.get("/payments/pay-1").json()["status"] == "approved"


def test_idempotent_retry_returns_same_result():
    client = TestClient(payment_main.app)
    first = send(client)
    second = send(client)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()


def test_idempotency_key_cannot_be_reused_for_different_data():
    client = TestClient(payment_main.app)
    assert send(client).status_code == 201
    changed = send(client, payload(amount=25.00))
    assert changed.status_code == 409


def test_missing_idempotency_key_rejected():
    client = TestClient(payment_main.app)
    response = client.post("/payments", json=payload())
    assert response.status_code == 400


def test_idempotency_key_must_match_payment_id():
    client = TestClient(payment_main.app)
    assert send(client, key="different-key").status_code == 409


def test_invalid_amount_rejected():
    client = TestClient(payment_main.app)
    assert send(client, payload(amount=-1)).status_code == 422


def test_payment_decline_is_stable_on_retry(monkeypatch):
    monkeypatch.setattr(payment_main, "PAYMENT_DECISION", "decline")
    client = TestClient(payment_main.app)
    first = send(client)
    second = send(client)
    assert first.status_code == second.status_code == 402
    assert client.get("/payments/pay-1").json()["status"] == "declined"

def _metric_value(metric_name, labels):
    from prometheus_client.parser import text_string_to_metric_families

    exposition = payment_main.generate_latest(payment_main.registry).decode("utf-8")
    for family in text_string_to_metric_families(exposition):
        for sample in family.samples:
            if sample.name != metric_name:
                continue
            if all(sample.labels.get(key) == value for key, value in labels.items()):
                return sample.value
    return 0


def test_payment_metrics_use_normalized_routes_and_classify_errors():
    client = TestClient(payment_main.app)

    response = client.get("/payments/missing-metric-test")
    assert response.status_code == 404

    labels = {
        "service": "payment-service",
        "method": "GET",
        "route": "/payments/{payment_id}",
        "status": "404",
    }
    assert _metric_value("http_requests_total", labels) >= 1
    assert _metric_value("http_errors_total", labels) >= 1

    error_labels = {
        "service": "payment-service",
        "method": "GET",
        "route": "/payments/{payment_id}",
        "error_type": "4xx",
    }
    assert _metric_value("http_error_responses_total", error_labels) >= 1

    bucket_labels = {
        "service": "payment-service",
        "method": "GET",
        "route": "/payments/{payment_id}",
        "le": "0.005",
    }
    assert _metric_value("http_request_duration_seconds_bucket", bucket_labels) >= 1

    exposition = payment_main.generate_latest(payment_main.registry).decode("utf-8")
    assert 'route="/payments/missing-metric-test"' not in exposition


def test_payment_outcome_metric_counts_idempotent_payment_once(monkeypatch):
    monkeypatch.setattr(payment_main, "PAYMENT_DECISION", "approve")
    client = TestClient(payment_main.app)

    labels = {"outcome": "approved"}
    before = _metric_value("payment_outcomes_total", labels)

    test_payload = payload(payment_id="metric-idempotency-test")
    first = send(client, data=test_payload, key="metric-idempotency-test")
    second = send(client, data=test_payload, key="metric-idempotency-test")

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert _metric_value("payment_outcomes_total", labels) == before + 1

