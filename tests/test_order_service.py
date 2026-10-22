import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "services" / "order-service"
spec = importlib.util.spec_from_file_location(
    "order_service_main", SERVICE_DIR / "main.py"
)
service = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = service
spec.loader.exec_module(service)


@pytest.fixture
def client():
    service.app.dependency_overrides.clear()
    service.orders.clear()
    with TestClient(service.app) as test_client:
        yield test_client
    service.app.dependency_overrides.clear()


def configure(client, handler):
    service.app.dependency_overrides[service.get_http_client] = (
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def successful_handler(request):
    if request.url.path == "/users/user-1":
        return httpx.Response(200, json={
            "user_id": "user-1", "name": "Test", "email": "test@example.com"
        })
    if request.url.path == "/payments":
        return httpx.Response(201, json={
            "payment_id": "order-1", "status": "approved"
        })
    return httpx.Response(404)


def payload(**overrides):
    data = {
        "order_id": "order-1",
        "user_id": "user-1",
        "amount": 19.99,
        "currency": "USD",
    }
    data.update(overrides)
    return data


def test_health_and_metrics(client):
    assert client.get("/health/live").json()["status"] == "alive"
    assert client.get("/health/ready").json()["status"] == "ready"
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"http_requests_total" in response.content


def test_order_is_confirmed_after_payment_approval(client):
    configure(client, successful_handler)
    response = client.post("/orders", json=payload())
    assert response.status_code == 201
    assert response.json()["status"] == "confirmed"
    assert response.json()["payment_id"] == "order-1"
    assert client.get("/orders/order-1").status_code == 200


def test_unknown_user_does_not_trigger_payment(client):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(404) if request.url.path.startswith("/users/") \
            else httpx.Response(201, json={"status": "approved"})

    configure(client, handler)
    response = client.post("/orders", json=payload())
    assert response.status_code == 404
    assert "/payments" not in calls


def test_payment_decline_is_not_confirmed(client):
    def handler(request):
        if request.url.path.startswith("/users/"):
            return httpx.Response(200, json={"user_id": "user-1"})
        return httpx.Response(402, json={"status": "declined"})

    configure(client, handler)
    response = client.post("/orders", json=payload())
    assert response.status_code == 402
    assert client.get("/orders/order-1").status_code == 404


def test_payment_timeout_returns_503_without_retry(client):
    payment_calls = []

    def handler(request):
        if request.url.path.startswith("/users/"):
            return httpx.Response(200, json={"user_id": "user-1"})
        payment_calls.append(request.url.path)
        raise httpx.ReadTimeout("simulated timeout", request=request)

    configure(client, handler)
    response = client.post("/orders", json=payload())
    assert response.status_code == 503
    assert len(payment_calls) == 1
    assert client.get("/orders/order-1").status_code == 404


def test_duplicate_order_is_rejected(client):
    configure(client, successful_handler)
    assert client.post("/orders", json=payload()).status_code == 201
    assert client.post("/orders", json=payload()).status_code == 409


def test_invalid_id_is_rejected(client):
    configure(client, successful_handler)
    response = client.post("/orders", json=payload(order_id="../bad"))
    assert response.status_code == 422


def test_invalid_amount_is_rejected(client):
    configure(client, successful_handler)
    response = client.post("/orders", json=payload(amount=-1))
    assert response.status_code == 422

def _metric_value(metric_name, labels):
    from prometheus_client import generate_latest
    from prometheus_client.parser import text_string_to_metric_families

    exposition = generate_latest(service.REGISTRY).decode("utf-8")
    for family in text_string_to_metric_families(exposition):
        for sample in family.samples:
            if sample.name == metric_name and all(
                sample.labels.get(key) == value
                for key, value in labels.items()
            ):
                return sample.value
    return 0


def test_order_metrics_record_confirmed_workflow_and_downstream_calls(client):
    configure(client, successful_handler)

    confirmed_before = _metric_value(
        "order_outcomes_total", {"outcome": "confirmed"}
    )
    response = client.post("/orders", json=payload())
    assert response.status_code == 201
    assert _metric_value(
        "order_outcomes_total", {"outcome": "confirmed"}
    ) == confirmed_before + 1

    for dependency, operation in (
        ("user-service", "get_user"),
        ("payment-service", "create_payment"),
    ):
        assert _metric_value(
            "downstream_requests_total",
            {
                "dependency": dependency,
                "operation": operation,
                "outcome": "success",
            },
        ) >= 1

        # The latency histogram should have observations for each dependency.
        assert _metric_value(
            "downstream_request_duration_seconds_count",
            {"dependency": dependency, "operation": operation},
        ) >= 1


def test_order_metrics_record_failed_workflow_and_client_error(client):
    configure(client, lambda request: httpx.Response(404))

    failed_before = _metric_value(
        "order_outcomes_total", {"outcome": "failed"}
    )
    response = client.post("/orders", json=payload())
    assert response.status_code == 404
    assert _metric_value(
        "order_outcomes_total", {"outcome": "failed"}
    ) == failed_before + 1

    assert _metric_value(
        "downstream_requests_total",
        {
            "dependency": "user-service",
            "operation": "get_user",
            "outcome": "client_error",
        },
    ) >= 1

    labels = {
        "service": "order-service",
        "method": "POST",
        "route": "/orders",
        "error_type": "4xx",
    }
    assert _metric_value("http_error_responses_total", labels) >= 1
    exposition = service.generate_latest(service.REGISTRY).decode("utf-8")
    assert 'le="0.005"' in exposition


def test_order_downstream_timeout_has_bounded_outcome_label(client):
    def handler(request):
        if request.url.path.startswith("/users/"):
            return httpx.Response(200, json={"user_id": "user-1"})
        raise httpx.ReadTimeout("simulated timeout", request=request)

    configure(client, handler)
    response = client.post(
        "/orders",
        json=payload(order_id="metrics-timeout-order"),
    )
    assert response.status_code == 503
    assert _metric_value(
        "downstream_requests_total",
        {
            "dependency": "payment-service",
            "operation": "create_payment",
            "outcome": "timeout",
        },
    ) >= 1

