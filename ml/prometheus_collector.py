
"""Collect service metrics from Prometheus."""

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL", "http://localhost:30090"
).rstrip("/")

SERVICES = ("user-service", "order-service", "payment-service")
SERVICE_FILTER = 'job=~"ai-self-healing-.*"'

ERROR_RATE_QUERY = (
    'sum by (service) (rate(http_requests_total'
    '{status=~"4..|5..",job=~"ai-self-healing-.*"}[5m]))'
)

QUERIES = {
    "request_rate": (
        "sum by (service) (rate(http_requests_total"
        f"{{{SERVICE_FILTER}}}[5m]))"
    ),
    "error_rate": ERROR_RATE_QUERY,
    "p95_latency_seconds": (
        "histogram_quantile(0.95, "
        "sum by (service, le) (rate("
        "http_request_duration_seconds_bucket"
        f"{{{SERVICE_FILTER}}}[5m])))"
    ),
}


class PrometheusError(RuntimeError):
    """Raised when a Prometheus query fails."""


def query_prometheus(expression, timeout=5):
    """Execute a Prometheus instant query."""
    url = (
        f"{PROMETHEUS_URL}/api/v1/query?"
        f"{urlencode({'query': expression})}"
    )

    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except (
        HTTPError, URLError, TimeoutError, OSError, ValueError
    ) as exc:
        raise PrometheusError(
            f"Prometheus query failed: {exc}"
        ) from exc

    if payload.get("status") != "success":
        raise PrometheusError("Prometheus returned a query error")

    data = payload.get("data", {})
    if data.get("resultType") != "vector":
        raise PrometheusError("Unexpected Prometheus result type")

    result = data.get("result")
    if not isinstance(result, list):
        raise PrometheusError("Missing Prometheus result vector")

    return result


def _series_by_service(series):
    """Convert valid Prometheus series into service-value mappings."""
    values = {}

    for item in series:
        metric = item.get("metric", {})
        service = metric.get("service")
        if service not in SERVICES:
            job = metric.get("job", "")
            prefix = "ai-self-healing-"
            if job.startswith(prefix):
                candidate = job[len(prefix):]
                if candidate in SERVICES:
                    service = candidate
            elif job in SERVICES:
                service = job

        sample = item.get("value")

        if service not in SERVICES:
            continue
        if not isinstance(sample, list) or len(sample) < 2:
            continue

        try:
            value = float(sample[1])
        except (TypeError, ValueError):
            continue

        if math.isfinite(value) and value >= 0:
            values[service] = value

    return values


def _calculate_error_ratios(request_rates, error_rates):
    """Calculate error/total rate.

    A missing error-rate series is unknown, not proof of zero errors:
    Prometheus can omit a series when instrumentation or scraping is absent.
    An explicitly returned zero remains a valid zero-error measurement.
    """
    ratios = {}

    for service in SERVICES:
        total = request_rates.get(service)
        errors = error_rates.get(service)

        # Without positive traffic or an explicit error-rate sample, the
        # ratio cannot be reliably calculated.
        if total is None or total <= 0 or errors is None:
            ratios[service] = None
            continue

        # Protect against inconsistent data or query-label issues.
        if errors > total:
            ratios[service] = None
        else:
            ratios[service] = errors / total

    return ratios


def collect_features():
    """Collect metrics and calculate an error ratio per service."""
    raw = {}

    for feature_name, expression in QUERIES.items():
        raw[feature_name] = _series_by_service(
            query_prometheus(expression)
        )

    ratios = _calculate_error_ratios(
        raw["request_rate"],
        raw["error_rate"],
    )

    return {
        service: {
            "request_rate": raw["request_rate"].get(service),
            "error_ratio": ratios[service],
            "p95_latency_seconds": raw[
                "p95_latency_seconds"
            ].get(service),
        }
        for service in SERVICES
    }



