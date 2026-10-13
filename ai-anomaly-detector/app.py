from datetime import datetime, timedelta
import csv
import os
import time

import joblib
import pandas as pd
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect


# ============================================================
# CONFIGURATION
# ============================================================

PROMETHEUS_URL = "http://localhost:9090"
NAMESPACE = "default"
SERVICE_NAME = "user-service"
MODEL_FILE = "isolation_forest_model.pkl"

METRICS_FILE = "metrics.csv"
LOG_FILE = "self_healing_log.csv"


REQUIRED_ANOMALIES = 2
RECOVERY_TIMEOUT = 60

# Safety: do not restart Kubernetes during testing.
DRY_RUN = True


FEATURES = [
    "cpu",
    "memory",
    "user_requests",
    "order_requests",
    "payment_requests"
]


# ============================================================
# CONNECT TO PROMETHEUS
# ============================================================

prom = PrometheusConnect(
    url=PROMETHEUS_URL,
    disable_ssl=True
)


# ============================================================
# CONNECT TO KUBERNETES
# ============================================================

try:
    config.load_kube_config()
    apps_api = client.AppsV1Api()

    print("Kubernetes API connection successful")

except Exception as e:
    print(f"❌ Kubernetes connection failed: {e}")
    raise SystemExit(1)


# ============================================================
# EVENT LOGGER
# ============================================================

def log_event(event, details=""):
    file_exists = os.path.exists(LOG_FILE)

    with open(
        LOG_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "timestamp",
                "event",
                "details"
            ])

        writer.writerow([
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            event,
            details
        ])


# ============================================================
# RESTART KUBERNETES DEPLOYMENT
# ============================================================

def restart_service(deployment_name):

    print(
        f"Restarting {deployment_name}..."
    )

    body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "self-healing/restarted-at":
                            datetime.now().isoformat()
                    }
                }
            }
        }
    }

    apps_api.patch_namespaced_deployment(
        name=deployment_name,
        namespace=NAMESPACE,
        body=body
    )

    print(
        f"{deployment_name} restart triggered"
    )


# ============================================================
# VERIFY KUBERNETES RECOVERY
# ============================================================

def verify_recovery(
    deployment_name,
    timeout=RECOVERY_TIMEOUT
):

    print(
        f"Waiting for {deployment_name} to recover..."
    )

    start_time = time.time()

    while time.time() - start_time < timeout:

        try:

            deployment = (
                apps_api.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=NAMESPACE
                )
            )

            desired = (
                deployment.spec.replicas or 0
            )

            ready = (
                deployment.status.ready_replicas or 0
            )

            updated = (
                deployment.status.updated_replicas or 0
            )

            available = (
                deployment.status.available_replicas or 0
            )

            print(
                f"Recovery status: "
                f"ready={ready}/{desired}, "
                f"updated={updated}, "
                f"available={available}"
            )

            if (
                desired > 0
                and ready == desired
                and updated == desired
                and available == desired
            ):

                print(
                    "✅ Recovery successful"
                )

                return True

        except Exception as e:

            print(
                f"⚠️ Recovery check error: {e}"
            )

        time.sleep(2)

    print(
        "❌ Recovery failed or timed out"
    )

    return False


# ============================================================
# PROMETHEUS QUERIES
# ============================================================


queries = {
    "cpu":
        'sum(rate(process_cpu_seconds_total{job="user-service"}[5m])) * 100',

    "memory":
        'sum(process_resident_memory_bytes{job="user-service"})',

    "user_requests":
        'sum(rate(user_requests_total{job="user-service"}[5m]))',

    "order_requests":
        'sum(rate(order_requests_total{job="order-service"}[5m]))',

    "payment_requests":
        'sum(rate(payment_requests_total{job="payment-service"}[5m]))'
}



# ============================================================
# COLLECT PROMETHEUS METRICS
# ============================================================

end_time = datetime.now()
start_time = end_time - timedelta(hours=1)

data = {}

print()
print("=" * 60)
print("COLLECTING PROMETHEUS METRICS")
print("=" * 60)

for name, query in queries.items():
    try:
        result = prom.custom_query_range(
            query=query,
            start_time=start_time,
            end_time=end_time,
            step="1m"
        )

        if result:
            # Keep each sample's timestamp and value.
            samples = result[0].get("values", [])

            data[name] = [
                (float(timestamp), float(value))
                for timestamp, value in samples
            ]

            print(
                f"✅ {name}: {len(data[name])} samples"
            )
        else:
            print(f"⚠️ {name}: no data")

    except Exception as e:
        print(f"❌ {name}: {e}")


# ============================================================
# VALIDATE DATA
# ============================================================

if not data or any(not values for values in data.values()):
    message = "One or more Prometheus metrics contain no samples."
    print(f"❌ {message}")
    log_event("ERROR", message)
    raise SystemExit(1)

# ============================================================
# ALIGN METRICS BY TIMESTAMP
# ============================================================

metric_frames = {}

for name, samples in data.items():
    metric_frames[name] = pd.Series(
        {timestamp: value for timestamp, value in samples},
        name=name,
        dtype=float
    )

# Retain only timestamps shared by all metrics.
aligned_data = pd.concat(
    list(metric_frames.values()),
    axis=1,
    join="inner"
).sort_index()

if aligned_data.empty:
    message = "No shared timestamps across Prometheus metrics."
    print(f"❌ {message}")
    log_event("ERROR", message)
    raise SystemExit(1)

# The model expects numeric features, not timestamps.
df = aligned_data.reset_index(drop=True)

print()
print(f"✅ Aligned samples: {len(df)}")
print(df.head())

# ============================================================
# CHECK REQUIRED FEATURES
# ============================================================

missing_features = [
    feature for feature in FEATURES
    if feature not in df.columns
]

if missing_features:
    message = f"Missing features: {missing_features}"
    print(f"❌ {message}")
    log_event("ERROR", message)
    raise SystemExit(1)

# ============================================================
# SAVE METRICS
# ============================================================

df.to_csv(METRICS_FILE, index=False)

print(f"Saved aligned metrics to {METRICS_FILE}")


# ============================================================
# LOAD AI MODEL
# ============================================================

try:

    model = joblib.load(
        MODEL_FILE
    )

    print(
        "Isolation Forest model loaded successfully"
    )

except Exception as e:

    print(
        f"❌ Could not load model: {e}"
    )

    log_event(
        "ERROR",
        f"Could not load model: {e}"
    )

    raise SystemExit(1)


# ============================================================
# GET LATEST METRICS
# ============================================================

latest = df[
    FEATURES
].iloc[[-1]]


print()
print("Current metrics:")
print(latest)



# ============================================================
# AI ANOMALY DETECTION
# ============================================================

print()
print("=" * 60)
print("AI ANOMALY DETECTION")
print("=" * 60)

# Use distinct historical metric samples, not repeated
# predictions on the same latest sample.
recent = df[FEATURES].tail(REQUIRED_ANOMALIES)

if len(recent) < REQUIRED_ANOMALIES:
    message = (
        f"Need {REQUIRED_ANOMALIES} distinct samples; "
        f"only {len(recent)} available"
    )
    print(f"Insufficient data: {message}")
    log_event("ERROR", message)
    raise SystemExit(1)

predictions = model.predict(recent)

# Count only the consecutive anomalous observations ending
# at the newest sample. A normal sample resets the count.
anomaly_count = 0

for prediction in predictions:
    if prediction == -1:
        anomaly_count += 1
        print(
            f"Anomaly detected "
            f"({anomaly_count}/{REQUIRED_ANOMALIES})"
        )
    else:
        anomaly_count = 0
        print("System is NORMAL")

print(
    f"Consecutive anomalies in recent samples: "
    f"{anomaly_count}/{REQUIRED_ANOMALIES}"
)




# ============================================================
# SELF-HEALING DECISION
# ============================================================

print()
print("=" * 60)
print("SELF-HEALING DECISION")
print("=" * 60)

if anomaly_count >= REQUIRED_ANOMALIES:
    print("🚨 CONFIRMED ANOMALY")

    log_event(
        "ANOMALY_DETECTED",
        f"Isolation Forest detected {REQUIRED_ANOMALIES} consecutive anomalies"
    )

    if DRY_RUN:
        print(
            f"🛡️ DRY RUN: would restart "
            f"{SERVICE_NAME} deployment; no restart performed."
        )
        log_event(
            "DRY_RUN",
            f"Would restart {SERVICE_NAME} deployment"
        )
    else:
        try:
            restart_service(SERVICE_NAME)
            log_event(
                "SELF_HEALING_TRIGGERED",
                f"Restarted {SERVICE_NAME} deployment"
            )
        except Exception as e:
            print(f"❌ Self-healing failed: {e}")
            log_event("SELF_HEALING_FAILED", str(e))
            raise SystemExit(1)

        recovered = verify_recovery(SERVICE_NAME)

        if recovered:
            log_event(
                "RECOVERY_SUCCESS",
                f"{SERVICE_NAME} deployment recovered successfully"
            )
            print("✅ Self-healing and recovery completed successfully")
        else:
            log_event(
                "RECOVERY_FAILED",
                f"{SERVICE_NAME} did not recover within timeout"
            )
            print("❌ Self-healing recovery failed")
else:
    print("✅ No self-healing action required")
    log_event("SYSTEM_NORMAL", "No self-healing action required")


# ============================================================
# COMPLETE
# ============================================================

print()
print("=" * 60)
print("EXECUTION COMPLETED")
print("=" * 60)

print(
    f"Metrics: {METRICS_FILE}"
)

print(
    f"Event log: {LOG_FILE}"
)