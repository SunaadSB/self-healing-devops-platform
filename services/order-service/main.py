import os
import re
import time
from threading import Lock

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

SERVICE_NAME = "order-service"
USER_SERVICE_URL = os.getenv(
    "USER_SERVICE_URL", "http://user-service:8000"
).rstrip("/")
PAYMENT_SERVICE_URL = os.getenv(
    "PAYMENT_SERVICE_URL", "http://payment-service:8000"
).rstrip("/")
DOWNSTREAM_TIMEOUT = float(os.getenv("DOWNSTREAM_TIMEOUT_SECONDS", "2.0"))

if not 0.1 <= DOWNSTREAM_TIMEOUT <= 30:
    raise ValueError("DOWNSTREAM_TIMEOUT_SECONDS must be between 0.1 and 30")

REGISTRY = CollectorRegistry()
REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "route", "status"],
    registry=REGISTRY,
)
ERRORS = Counter(
    "http_errors_total",
    "HTTP responses with status code 400 or higher",
    ["service", "method", "route", "status"],
    registry=REGISTRY,
)
ERROR_TYPES = Counter(
    "http_error_responses_total",
    "HTTP error responses categorized by client or server error",
    ["service", "method", "route", "error_type"],
    registry=REGISTRY,
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
DOWNSTREAM_REQUESTS = Counter(
    "downstream_requests_total",
    "HTTP requests made to downstream services",
    ["dependency", "operation", "outcome"],
    registry=REGISTRY,
)
DOWNSTREAM_LATENCY = Histogram(
    "downstream_request_duration_seconds",
    "Duration of downstream HTTP requests in seconds",
    ["dependency", "operation"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
ORDER_OUTCOMES = Counter(
    "order_outcomes_total",
    "Order creation workflow outcomes",
    ["outcome"],
    registry=REGISTRY,
)

app = FastAPI(title="Order Service", version="0.1.0")
orders: dict[str, dict] = {}
orders_lock = Lock()


class OrderCreate(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    amount: float = Field(gt=0, allow_inf_nan=False, le=1_000_000)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


def valid_id(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


async def get_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(DOWNSTREAM_TIMEOUT),
        follow_redirects=False,
    )


async def observe_downstream(dependency: str, operation: str, request_coro):
    """Observe one downstream HTTP call without recording IDs or URLs."""
    started = time.perf_counter()
    outcome = "success"
    try:
        response = await request_coro
        if response.status_code >= 500:
            outcome = "server_error"
        elif response.status_code >= 400:
            outcome = "client_error"
        return response
    except httpx.TimeoutException:
        outcome = "timeout"
        raise
    except httpx.RequestError:
        outcome = "connection_error"
        raise
    finally:
        DOWNSTREAM_REQUESTS.labels(dependency, operation, outcome).inc()
        DOWNSTREAM_LATENCY.labels(dependency, operation).observe(
            time.perf_counter() - started
        )


@app.middleware("http")
async def collect_metrics(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route_obj = request.scope.get("route")
        route = getattr(route_obj, "path", request.url.path)
        if route == request.url.path and route.startswith("/orders/"):
            route = "/orders/{order_id}"
        REQUESTS.labels(SERVICE_NAME, request.method, route, str(status)).inc()
        if status >= 400:
            ERRORS.labels(SERVICE_NAME, request.method, route, str(status)).inc()
            error_type = "4xx" if status < 500 else "5xx"
            ERROR_TYPES.labels(
                SERVICE_NAME, request.method, route, error_type
            ).inc()
        LATENCY.labels(SERVICE_NAME, request.method, route).observe(
            time.perf_counter() - started
        )


@app.get("/health/live")
def liveness():
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/health/ready")
def readiness():
    return {"status": "ready", "service": SERVICE_NAME}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.post("/orders", status_code=201)
async def create_order(
    payload: OrderCreate,
    client: httpx.AsyncClient = Depends(get_http_client),
):
    if not valid_id(payload.order_id) or not valid_id(payload.user_id):
        raise HTTPException(
            status_code=422,
            detail="IDs may contain only letters, numbers, hyphens, and underscores",
        )

    reserved = False

    try:
        # Open the HTTP client once for both downstream requests.
        async with client:
            user_response = await observe_downstream(
                "user-service",
                "get_user",
                client.get(f"{USER_SERVICE_URL}/users/{payload.user_id}"),
            )

            if user_response.status_code == 404:
                raise HTTPException(status_code=404, detail="User not found")
            if user_response.status_code != 200:
                raise HTTPException(
                    status_code=503, detail="User Service unavailable"
                )

            with orders_lock:
                if payload.order_id in orders:
                    raise HTTPException(
                        status_code=409, detail="Order already exists"
                    )
                orders[payload.order_id] = {"status": "processing"}
                reserved = True

            payment_response = await observe_downstream(
                "payment-service",
                "create_payment",
                client.post(
                    f"{PAYMENT_SERVICE_URL}/payments",
                    json={
                        "payment_id": payload.order_id,
                        "order_id": payload.order_id,
                        "user_id": payload.user_id,
                        "amount": payload.amount,
                        "currency": payload.currency,
                    },
                    headers={"Idempotency-Key": payload.order_id},
                ),
            )

            if payment_response.status_code == 402:
                raise HTTPException(status_code=402, detail="Payment declined")

            if payment_response.status_code not in (200, 201):
                raise HTTPException(
                    status_code=503, detail="Payment Service unavailable"
                )

            try:
                payment = payment_response.json()
            except ValueError:
                raise HTTPException(
                    status_code=503, detail="Invalid Payment Service response"
                )

            if payment.get("status") != "approved":
                raise HTTPException(
                    status_code=503,
                    detail="Payment outcome is not confirmed; reconcile before retrying",
                )

            order = {
                "order_id": payload.order_id,
                "user_id": payload.user_id,
                "amount": payload.amount,
                "currency": payload.currency,
                "status": "confirmed",
                "payment_id": payment.get("payment_id", payload.order_id),
            }
            with orders_lock:
                orders[payload.order_id] = order
            ORDER_OUTCOMES.labels("confirmed").inc()
            return order

    except HTTPException:
        ORDER_OUTCOMES.labels("failed").inc()
        if reserved:
            with orders_lock:
                orders.pop(payload.order_id, None)
        raise
    except (httpx.TimeoutException, httpx.RequestError):
        ORDER_OUTCOMES.labels("failed").inc()
        if reserved:
            with orders_lock:
                orders.pop(payload.order_id, None)
        raise HTTPException(
            status_code=503,
            detail="Payment outcome may be unknown; reconcile before retrying",
        )

@app.get("/orders/{order_id}")
def get_order(order_id: str):
    if not valid_id(order_id):
        raise HTTPException(status_code=422, detail="Invalid order_id")
    with orders_lock:
        order = orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") == "processing":
        raise HTTPException(status_code=409, detail="Order is still processing")
    return order

