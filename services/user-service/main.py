import os
import re
import time
from threading import Lock

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

SERVICE_NAME = "user-service"

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "route", "status"],
)

ERRORS = Counter(
    "http_errors_total",
    "HTTP responses with status code 400 or higher",
    ["service", "method", "route", "status"],
)

ERROR_TYPES = Counter(
    "http_error_responses_total",
    "HTTP error responses categorized by client or server error",
    ["service", "method", "route", "error_type"],
)

LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

USERS_CREATED = Counter(
    "users_created_total",
    "Successfully created users",
)

app = FastAPI(title="User Service", version="0.1.0")
users: dict[str, dict] = {}
users_lock = Lock()


class UserCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)


def valid_user_id(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


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
        # Avoid unbounded metric labels for unknown dynamic paths.
        if route == request.url.path and route.startswith("/users/"):
            route = "/users/{user_id}"

        method = request.method
        status_text = str(status)

        REQUESTS.labels(
            SERVICE_NAME, method, route, status_text
        ).inc()

        if status >= 400:
            ERRORS.labels(
                SERVICE_NAME, method, route, status_text
            ).inc()
            error_type = "4xx" if status < 500 else "5xx"
            ERROR_TYPES.labels(
                SERVICE_NAME, method, route, error_type
            ).inc()

        LATENCY.labels(SERVICE_NAME, method, route).observe(
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
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.post("/users", status_code=201)
def create_user(payload: UserCreate):
    if not valid_user_id(payload.user_id):
        raise HTTPException(
            status_code=422,
            detail="user_id may contain only letters, numbers, hyphens, and underscores",
        )

    with users_lock:
        if payload.user_id in users:
            raise HTTPException(status_code=409, detail="User already exists")

        user = payload.model_dump()
        users[payload.user_id] = user
        USERS_CREATED.inc()
        return user


@app.get("/users/{user_id}")
def get_user(user_id: str):
    if not valid_user_id(user_id):
        raise HTTPException(status_code=422, detail="Invalid user_id")

    with users_lock:
        user = users.get(user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return user
