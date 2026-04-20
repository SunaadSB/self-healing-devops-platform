from fastapi import FastAPI
from prometheus_client import Counter, generate_latest
from fastapi.responses import Response
import logging

app = FastAPI()
REQUEST_COUNT = Counter("user_requests_total", "Total requests in user service")
# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("user-service")

users = []

@app.get("/")
def root():
    REQUEST_COUNT.inc()
    logger.info("Root endpoint called")
    return {"message": "User Service Running"}

@app.get("/health")
def health():
    REQUEST_COUNT.inc()
    return {"status": "ok"}

@app.post("/users")
def create_user(name: str):
    REQUEST_COUNT.inc()
    user = {"id": len(users) + 1, "name": name}
    users.append(user)
    logger.info(f"User created: {user}")
    return user

@app.get("/users")
def get_users():
    REQUEST_COUNT.inc()
    return users

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")