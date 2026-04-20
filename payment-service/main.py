from fastapi import FastAPI
from prometheus_client import Counter, generate_latest
from fastapi.responses import Response
import logging

app = FastAPI()
REQUEST_COUNT = Counter("payment_requests_total", "Total requests in payment service")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payment-service")

payments = []

@app.get("/")
def root():
    REQUEST_COUNT.inc()
    return {"message": "Payment Service Running"}

@app.get("/health")
def health():
    REQUEST_COUNT.inc()
    return {"status": "ok"}

@app.post("/pay")
def make_payment(order_id: int, amount: float):
    REQUEST_COUNT.inc()
    payment = {
        "id": len(payments) + 1,
        "order_id": order_id,
        "amount": amount,
        "status": "success"
    }
    payments.append(payment)
    logger.info(f"Payment processed: {payment}")
    return payment

@app.get("/payments")
def get_payments():
    REQUEST_COUNT.inc()
    return payments

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")