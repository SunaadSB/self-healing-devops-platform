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
        "rate(process_cpu_seconds_total[5m]) * 100",

    "memory":
        "process_resident_memory_bytes",

    "user_requests":
        "rate(user_requests_total[5m])",

    "order_requests":
        "rate(order_requests_total[5m])",

    "payment_requests":
        "rate(payment_requests_total[5m])"
}


# ============================================================
# COLLECT PROMETHEUS METRICS
# ============================================================

end_time = datetime.now()

start_time = (
    end_time - timedelta(hours=1)
)

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

            values = result[0]["values"]

            data[name] = [
                float(value[1])
                for value in values
            ]

            print(
                f"✅ {name}: "
                f"{len(data[name])} samples"
            )

        else:

            print(
                f"⚠️ {name}: no data"
            )

    except Exception as e:

        print(
            f"❌ {name}: {e}"
        )


# ============================================================
# VALIDATE DATA
# ============================================================

if not data:

    print(
        "❌ No Prometheus data returned."
    )

    log_event(
        "ERROR",
        "No Prometheus data returned"
    )

    raise SystemExit(1)


# ============================================================
# ALIGN METRIC LENGTHS
# ============================================================

min_length = min(
    len(values)
    for values in data.values()
)

if min_length == 0:

    print(
        "❌ Metrics contain no samples."
    )

    log_event(
        "ERROR",
        "Metrics contain no samples"
    )

    raise SystemExit(1)


for name in data:

    data[name] = (
        data[name][-min_length:]
    )


# ============================================================
# CREATE DATAFRAME
# ============================================================

df = pd.DataFrame(data)

print()
print(
    f"Collected samples: {len(df)}"
)

print(df.head())


# ============================================================
# CHECK REQUIRED FEATURES
# ============================================================

missing_features = [
    feature
    for feature in FEATURES
    if feature not in df.columns
]

if missing_features:

    print(
        f"❌ Missing features: "
        f"{missing_features}"
    )

    log_event(
        "ERROR",
        f"Missing features: {missing_features}"
    )

    raise SystemExit(1)


# ============================================================
# SAVE METRICS
# ============================================================

df.to_csv(
    METRICS_FILE,
    index=False
)

print(
    f"Saved real metrics to {METRICS_FILE}"
)


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


anomaly_count = 0


for attempt in range(
    REQUIRED_ANOMALIES
):

    prediction = model.predict(
        latest
    )

    if prediction[0] == -1:

        anomaly_count += 1

        print(
            f"🚨 Anomaly detected "
            f"({anomaly_count}/"
            f"{REQUIRED_ANOMALIES})"
        )

    else:

        print(
            "✅ System is NORMAL"
        )

        anomaly_count = 0

        break


# ============================================================
# SELF-HEALING DECISION
# ============================================================

print()
print("=" * 60)
print("SELF-HEALING DECISION")
print("=" * 60)


if anomaly_count >= REQUIRED_ANOMALIES:

    print(
        "🚨 CONFIRMED ANOMALY"
    )

    # Log anomaly

    log_event(
        "ANOMALY_DETECTED",
        (
            "Isolation Forest detected "
            f"{REQUIRED_ANOMALIES} "
            "consecutive anomalies"
        )
    )

    # Restart service

    try:

        restart_service(
            SERVICE_NAME
        )

        log_event(
            "SELF_HEALING_TRIGGERED",
            (
                f"Restarted "
                f"{SERVICE_NAME} deployment"
            )
        )

    except Exception as e:

        print(
            f"❌ Self-healing failed: {e}"
        )

        log_event(
            "SELF_HEALING_FAILED",
            str(e)
        )

        raise SystemExit(1)


    # Verify recovery

    recovered = verify_recovery(
        SERVICE_NAME
    )

    if recovered:

        log_event(
            "RECOVERY_SUCCESS",
            (
                f"{SERVICE_NAME} "
                "deployment recovered successfully"
            )
        )

        print(
            "✅ Self-healing and recovery "
            "completed successfully"
        )

    else:

        log_event(
            "RECOVERY_FAILED",
            (
                f"{SERVICE_NAME} "
                "did not recover within timeout"
            )
        )

        print(
            "❌ Self-healing recovery failed"
        )


else:

    print(
        "✅ No self-healing action required"
    )

    log_event(
        "SYSTEM_NORMAL",
        "No self-healing action required"
    )


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