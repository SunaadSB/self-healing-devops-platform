import math
import os
import re
import threading
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.responses import Response

SERVICE_NAME = "payment-service"
PAYMENT_DECISION = os.getenv("PAYMENT_DECISION", "approve").strip().lower()
if PAYMENT_DECISION not in {"approve", "decline"}:
    raise RuntimeError("PAYMENT_DECISION must be approve or decline")

app = FastAPI(title=SERVICE_NAME, version="0.1.0")
registry = CollectorRegistry()
requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "route", "status"],
    registry=registry,
)
errors_total = Counter(
    "http_errors_total",
    "HTTP responses with status code 400 or higher",
    ["service", "method", "route", "status"],
    registry=registry,
)
error_types_total = Counter(
    "http_error_responses_total",
    "HTTP error responses categorized by client or server error",
    ["service", "method", "route", "error_type"],
    registry=registry,
)
latency_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)
payment_outcomes_total = Counter(
    "payment_outcomes_total",
    "New payment decisions by outcome",
    ["outcome"],
    registry=registry,
)

payments = {}
payments_lock = threading.Lock()
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_id: str = Field(min_length=1, max_length=64)
    order_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    amount: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


@app.middleware("http")
async def observe_requests(request, call_next):
    import time

    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - started
        route_info = request.scope.get("route")
        route = route_info.path if route_info else request.url.path

        requests_total.labels(
            SERVICE_NAME, request.method, route, str(status)
        ).inc()
        latency_seconds.labels(
            SERVICE_NAME, request.method, route
        ).observe(elapsed)

        if status >= 400:
            errors_total.labels(
                SERVICE_NAME, request.method, route, str(status)
            ).inc()
            error_type = "4xx" if status < 500 else "5xx"
            error_types_total.labels(
                SERVICE_NAME, request.method, route, error_type
            ).inc()


@app.get("/health/live")
def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/health/ready")
def ready():
    return {"status": "ready", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


@app.post("/payments", status_code=201)
def create_payment(
    payload: PaymentCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    from starlette.responses import JSONResponse

    if not all(ID_PATTERN.fullmatch(value) for value in (
        payload.payment_id, payload.order_id, payload.user_id
    )):
        raise HTTPException(
            status_code=422,
            detail="IDs may contain only letters, numbers, hyphens, and underscores",
        )
    if not idempotency_key or not ID_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(status_code=400, detail="Valid Idempotency-Key header required")
    if idempotency_key != payload.payment_id:
        raise HTTPException(status_code=409, detail="Idempotency key does not match payment_id")

    request_record = payload.model_dump()
    with payments_lock:
        existing = payments.get(idempotency_key)
        if existing is not None:
            if existing["request"] != request_record:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used with different payment data",
                )
            return JSONResponse(
                status_code=existing["status_code"],
                content=existing["body"],
            )

        status: Literal["approved", "declined"] = (
            "approved" if PAYMENT_DECISION == "approve" else "declined"
        )
        response = {
            "payment_id": payload.payment_id,
            "order_id": payload.order_id,
            "status": status,
            "amount": payload.amount,
            "currency": payload.currency,
        }

        if status == "declined":
            status_code = 402
            body = {"detail": "Payment declined"}
        else:
            status_code = 201
            body = response

        # Persist the decision and exact HTTP result together under the lock.
        payments[idempotency_key] = {
            "request": request_record,
            "response": response,
            "status_code": status_code,
            "body": body,
        }
        payment_outcomes_total.labels(status).inc()

    return JSONResponse(status_code=status_code, content=body)

@app.get("/payments/{payment_id}")
def get_payment(payment_id: str):
    if not ID_PATTERN.fullmatch(payment_id):
        raise HTTPException(status_code=422, detail="Invalid payment ID")
    with payments_lock:
        record = payments.get(payment_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Payment not found")
        return record["response"]

