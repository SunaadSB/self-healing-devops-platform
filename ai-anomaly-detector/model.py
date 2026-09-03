import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

# Load real Prometheus data
df = pd.read_csv("metrics.csv")

features = [
    "cpu",
    "memory",
    "user_requests",
    "order_requests",
    "payment_requests"
]

X = df[features]

# Train anomaly detector
model = IsolationForest(
    contamination=0.1,
    random_state=42
)

model.fit(X)
joblib.dump(model, "isolation_forest_model.pkl")
print("Model saved successfully")

# Detect anomalies
df["anomaly"] = model.predict(X)

df["status"] = df["anomaly"].map({
    1: "Normal",
    -1: "Anomaly"
})

print(df[features + ["status"]])

print("\nAnomalies detected:",
      (df["anomaly"] == -1).sum())

df.to_csv("metrics_with_anomalies.csv", index=False)

print("\nSaved results to metrics_with_anomalies.csv")