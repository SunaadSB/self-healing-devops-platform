from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from recovery.recovery_metrics import calculate_recovery_metrics

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = Path(__file__).resolve().parent
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:30090")
AUDIT_PATH = Path(os.getenv("RECOVERY_AUDIT_PATH", str(ROOT / "logs" / "recovery_audit.jsonl")))
RECOMMENDATIONS_PATH = Path(os.getenv("RECOMMENDATIONS_PATH", str(ROOT / "data" / "recovery_recommendations_v2.csv")))
PIPELINE_RUNS_PATH = Path(os.getenv("PIPELINE_RUNS_PATH", str(ROOT / "data" / "pipeline_runs.jsonl")))
ANOMALY_REPORT_PATH = Path(os.getenv("ANOMALY_REPORT_PATH", str(ROOT / "data" / "anomaly_report_v2.csv")))

SERVICES = [
    {"name": "user-service", "url": os.getenv("USER_SERVICE_URL", "http://localhost:31478")},
    {"name": "order-service", "url": os.getenv("ORDER_SERVICE_URL", "http://localhost:32040")},
    {"name": "payment-service", "url": os.getenv("PAYMENT_SERVICE_URL", "http://localhost:30441")},
]

app = FastAPI(title="Self-Healing DevOps Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR / "static")), name="static")


def get_json(url: str, timeout: float = 3.0) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "self-healing-dashboard/0.1"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(url: str, timeout: float = 3.0) -> str:
    req = Request(url, headers={"User-Agent": "self-healing-dashboard/0.1"})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def check_service(service: dict[str, str]) -> dict[str, Any]:
    checks = {}
    for endpoint in ("/health/live", "/health/ready"):
        try:
            req = Request(service["url"] + endpoint, headers={"User-Agent": "self-healing-dashboard/0.1"})
            with urlopen(req, timeout=2.5) as response:
                checks[endpoint] = {"ok": 200 <= response.status < 300, "status": response.status}
        except HTTPError as exc:
            checks[endpoint] = {"ok": False, "status": exc.code}
        except (URLError, TimeoutError, OSError) as exc:
            checks[endpoint] = {"ok": False, "status": None, "error": str(exc)}
    ready = bool(checks.get("/health/ready", {}).get("ok"))
    live = bool(checks.get("/health/live", {}).get("ok"))
    return {
        "name": service["name"],
        "base_url": service["url"],
        "status": "healthy" if ready and live else "degraded",
        "checks": checks,
    }


def prom_query(expr: str) -> dict[str, Any]:
    try:
        url = PROMETHEUS_URL.rstrip("/") + "/api/v1/query?" + urlencode({"query": expr})
        data = get_json(url, timeout=3.5)
        if data.get("status") != "success":
            return {"ok": False, "value": None, "error": "Prometheus query was not successful"}
        results = data.get("data", {}).get("result", [])
        if not results:
            return {"ok": True, "value": None, "series": 0}
        # Preserve series for breakdowns; numeric scalar-like queries use first sample.
        values = []
        for item in results:
            sample = item.get("value") or (item.get("values") or [[None, None]])[-1]
            try:
                values.append({"metric": item.get("metric", {}), "value": float(sample[1])})
            except (TypeError, ValueError, IndexError):
                continue
        return {"ok": True, "value": values[0]["value"] if len(values) == 1 else None, "series": len(values), "results": values[:30]}
    except Exception as exc:
        return {"ok": False, "value": None, "error": str(exc)}


def read_audit(limit: int = 30) -> list[dict[str, Any]]:
    if not AUDIT_PATH.exists():
        return []
    rows = []
    try:
        with AUDIT_PATH.open("r", encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
                except json.JSONDecodeError:
                    rows.append({"raw": line, "status": "unparsed"})
    except OSError:
        return []
    return rows[-limit:][::-1]


def read_recommendations(limit: int = 30) -> list[dict[str, Any]]:
    if not RECOMMENDATIONS_PATH.exists():
        return []
    try:
        with RECOMMENDATIONS_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            return list(reader)[-limit:][::-1]
    except (OSError, csv.Error):
        return []


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (DASHBOARD_DIR / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    services = [check_service(service) for service in SERVICES]
    try:
        target_data = get_json(PROMETHEUS_URL.rstrip("/") + "/api/v1/targets", timeout=3.5)
        targets = [
            {
                "job": target.get("scrapePool") or target.get("labels", {}).get("job", "unknown"),
                "health": target.get("health", "unknown"),
                "scrape_url": target.get("scrapeUrl", ""),
                "last_error": target.get("lastError", ""),
            }
            for target in target_data.get("data", {}).get("activeTargets", [])
        ]
        prom_ok = target_data.get("status") == "success"
    except Exception as exc:
        targets, prom_ok = [], False
        prom_error = str(exc)
    else:
        prom_error = None

    # Generic PromQL queries. If the app's metric names differ, UI reports no data rather than inventing values.
    metric_queries = {
        "request_rate": 'sum(rate(http_requests_total{job=~"ai-self-healing-.*"}[5m]))',
        "error_rate": 'sum(rate(http_requests_total{job=~"ai-self-healing-.*",status=~"4..|5.."}[5m]))',
        "p95_latency": 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job=~"ai-self-healing-.*"}[5m])))',
    }
    metrics = {name: prom_query(expr) for name, expr in metric_queries.items()}
    audit = read_audit()
    recovery_metrics = calculate_recovery_metrics(AUDIT_PATH)

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "services": services,
        "prometheus": {"ok": prom_ok, "url": PROMETHEUS_URL, "targets": targets, "error": prom_error},
        "metrics": metrics,
        "recommendations": read_recommendations(),
        "audit": audit,
        "recovery": {
            **recovery_metrics,
            "rate_percent": recovery_metrics["recovery_rate_percent"],
            "note": (
                "Rate is based on completed live attempts with recorded recovery outcomes. "
                "Dry runs are excluded; unresolved attempts are reported separately."
                if recovery_metrics["eligible_attempts"]
                else "Not yet measured: no completed, eligible live recovery outcomes."
            ),
        },
    }




@app.get("/api/metrics/history")
def metrics_history(
    service: str = "all",
    minutes: int = 60,
    step: int = 30,
) -> dict[str, Any]:
    """Read genuine historical time series from Prometheus."""
    import math

    allowed = {"all", "user-service", "order-service", "payment-service"}
    if service not in allowed:
        return {"ok": False, "error": "Unsupported service", "series": {}}

    minutes = max(5, min(int(minutes), 360))
    step = max(15, min(int(step), 300))
    end = time.time()
    start = end - minutes * 60

    if service == "all":
        selector = '{job=~"ai-self-healing-.*"}'
        error_selector = '{job=~"ai-self-healing-.*",status=~"4..|5.."}'
    else:
        job = "ai-self-healing-" + service
        selector = '{job="' + job + '"}'
        error_selector = (
            '{job="' + job + '",status=~"4..|5.."}'
        )

    total_selector = (
        '{job=~"ai-self-healing-.*"}'
        if service == "all"
        else '{job="ai-self-healing-' + service + '"}'
    )

    queries = {
        "request_rate": "sum(rate(http_requests_total" + selector + "[5m]))",
        "error_rate": (
            "sum(rate(http_requests_total" + error_selector + "[5m])) "
            "or (sum(rate(http_requests_total" + total_selector + "[5m])) * 0)"
        ),
        "p95_latency": (
            "histogram_quantile(0.95, sum by (le) "
            "(rate(http_request_duration_seconds_bucket" + selector + "[5m])))"
        ),
    }

    series: dict[str, Any] = {}

    for name, expression in queries.items():
        url = PROMETHEUS_URL.rstrip("/") + "/api/v1/query_range?" + urlencode({
            "query": expression,
            "start": str(start),
            "end": str(end),
            "step": str(step),
        })

        try:
            payload = get_json(url, timeout=8.0)
            if payload.get("status") != "success":
                series[name] = {
                    "ok": False,
                    "available": False,
                    "points": [],
                    "error": "Prometheus query failed",
                }
                continue

            points: list[dict[str, float]] = []
            results = payload.get("data", {}).get("result", [])

            for result in results:
                for sample in result.get("values", []):
                    try:
                        timestamp = float(sample[0])
                        value = float(sample[1])
                        if math.isfinite(timestamp) and math.isfinite(value):
                            points.append({"time": timestamp, "value": value})
                    except (TypeError, ValueError, IndexError):
                        continue

            points.sort(key=lambda point: point["time"])
            series[name] = {
                "ok": True,
                "available": bool(points),
                "points": points,
                "query": expression,
            }

        except Exception as exc:
            series[name] = {
                "ok": False,
                "available": False,
                "points": [],
                "error": str(exc),
            }

    return {
        "ok": all(item["ok"] for item in series.values()),
        "service": service,
        "minutes": minutes,
        "step": step,
        "generated_at": time.time(),
        "series": series,
    }


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "dashboard"})

def read_pipeline_runs(limit: int = 20) -> list[dict[str, Any]]:
    """Read recent pipeline run records, newest first."""
    if not PIPELINE_RUNS_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with PIPELINE_RUNS_PATH.open("r", encoding="utf-8-sig") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-max(1, limit):][::-1]


def read_anomaly_counts() -> dict[str, Any]:
    """Summarize detector predictions from the latest anomaly report."""
    counts: dict[str, dict[str, int]] = {}
    total_rows = 0
    total_flagged = 0

    if not ANOMALY_REPORT_PATH.exists():
        return {
            "available": False,
            "total_rows": 0,
            "total_flagged": 0,
            "by_service": {},
            "note": "Anomaly report is not available yet.",
        }

    try:
        with ANOMALY_REPORT_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                service = (row.get("service") or "unknown").strip()
                counts.setdefault(service, {"rows": 0, "flagged": 0})
                counts[service]["rows"] += 1
                total_rows += 1

                raw_flag = row.get("is_anomaly", row.get("anomaly", row.get("anomaly_flag", "")))
                flagged = str(raw_flag).strip().lower() in {
                    "1", "true", "yes", "anomaly", "-1"
                }
                if flagged:
                    counts[service]["flagged"] += 1
                    total_flagged += 1
    except (OSError, csv.Error):
        return {
            "available": False,
            "total_rows": 0,
            "total_flagged": 0,
            "by_service": {},
            "note": "Anomaly report could not be read.",
        }

    return {
        "available": True,
        "total_rows": total_rows,
        "total_flagged": total_flagged,
        "by_service": counts,
        "note": "Flags are model predictions, not confirmed incidents.",
    }


def pipeline_payload() -> dict[str, Any]:
    runs = read_pipeline_runs()
    latest = runs[0] if runs else None
    return {
        "latest": latest,
        "history": runs,
        "anomalies": read_anomaly_counts(),
        "recommendations": read_recommendations(),
        "safety": {
            "mode": "advisory_only",
            "automatic_recovery_enabled": False,
            "recovery_actions_executed": 0,
            "message": "Advisory only — no automatic recovery actions are executed by this dashboard.",
        },
    }


@app.get("/api/pipeline")
def pipeline() -> dict[str, Any]:
    """Return the latest pipeline run and its read-only artifacts."""
    return pipeline_payload()


@app.get("/api/pipeline/history")
def pipeline_history(limit: int = 20) -> dict[str, Any]:
    """Return recent pipeline execution records."""
    safe_limit = max(1, min(limit, 100))
    return {"runs": read_pipeline_runs(safe_limit), "limit": safe_limit}


@app.get("/api/pipeline/anomalies")
def pipeline_anomalies() -> dict[str, Any]:
    """Return anomaly counts derived from the latest detector report."""
    return read_anomaly_counts()

