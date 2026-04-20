from fastapi import FastAPI
import requests

app = FastAPI()

USER_SERVICE = "http://127.0.0.1:8001"
ORDER_SERVICE = "http://127.0.0.1:8002"
PAYMENT_SERVICE = "http://127.0.0.1:8003"

@app.get("/")
def root():
    return {"message": "API Gateway Running"}


# USER
@app.post("/users")
def create_user(name: str):
    return requests.post(f"{USER_SERVICE}/users", params={"name": name}).json()

@app.get("/users")
def get_users():
    return requests.get(f"{USER_SERVICE}/users").json()


# ORDER
@app.post("/orders")
def create_order(item: str, quantity: int):
    return requests.post(
        f"{ORDER_SERVICE}/orders",
        params={"item": item, "quantity": quantity}
    ).json()

@app.get("/orders")
def get_orders():
    return requests.get(f"{ORDER_SERVICE}/orders").json()


# PAYMENT
@app.post("/pay")
def make_payment(order_id: int, amount: float):
    return requests.post(
        f"{PAYMENT_SERVICE}/pay",
        params={"order_id": order_id, "amount": amount}
    ).json()

@app.get("/payments")
def get_payments():
    return requests.get(f"{PAYMENT_SERVICE}/payments").json()