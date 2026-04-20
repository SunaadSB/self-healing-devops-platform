from fastapi import FastAPI
from prometheus_client import Counter, generate_latest
from fastapi.responses import Response
import logging

app = FastAPI()
REQUEST_COUNT = Counter("order_requests_total", "Total requests in order service")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order-service")

orders = []

@app.get("/")
def root():
    REQUEST_COUNT.inc()
    return {"message": "Order Service Running"}

@app.get("/health")
def health():
    REQUEST_COUNT.inc()
    return {"status": "ok"}

@app.post("/orders")
def create_order(item: str, quantity: int):
    REQUEST_COUNT.inc()
    order = {
        "id": len(orders) + 1,
        "item": item,
        "quantity": quantity
    }
    orders.append(order)
    logger.info(f"Order created: {order}")
    return order

@app.get("/orders")
def get_orders():
    REQUEST_COUNT.inc()
    return orders

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")