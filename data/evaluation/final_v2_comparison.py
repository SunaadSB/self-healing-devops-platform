from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, confusion_matrix
)

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "metrics_dataset_v2.csv"
OUTPUT = ROOT / "data" / "evaluation" / "final_v2_comparison.csv"

FEATURES = ["request_rate", "error_ratio", "p95_latency_seconds"]

CONFIGS = [
    {"name": "V2-original", "n_estimators": 200, "contamination": 0.02},
    {"name": "V2-tuned", "n_estimators": 400, "contamination": 0.055},
]

df = pd.read_csv(DATASET)
df[FEATURES] = df[FEATURES].apply(pd.to_numeric, errors="coerce")
df = df.dropna(subset=["timestamp", "service", *FEATURES])

results = []

for config in CONFIGS:
    y_true_all = []
    y_pred_all = []

    for service, group in df.groupby("service", sort=True):
        group = group.sort_values("timestamp")
        X = group[FEATURES].to_numpy(dtype=float)

        if len(X) < 50:
            continue

        split = int(len(X) * 0.70)
        X_train = X[:split]
        X_test = X[split:]

        model = make_pipeline(
            StandardScaler(),
            IsolationForest(
                n_estimators=config["n_estimators"],
                contamination=config["contamination"],
                random_state=42,
            ),
        )
        model.fit(X_train)

        normal_pred = (model.predict(X_test) == -1).astype(int)
        y_true_all.extend([0] * len(X_test))
        y_pred_all.extend(normal_pred.tolist())

        synthetic = X_test.copy()
        anomaly_types = np.arange(len(synthetic)) % 3

        for i, anomaly_type in enumerate(anomaly_types):
            if anomaly_type == 0:
                synthetic[i, 0] = max(X_train[:, 0].max(), 0.001) * 3
            elif anomaly_type == 1:
                synthetic[i, 1] = 0.20
            else:
                synthetic[i, 2] = max(X_train[:, 2].max(), 0.001) * 5

        anomaly_pred = (model.predict(synthetic) == -1).astype(int)
        y_true_all.extend([1] * len(synthetic))
        y_pred_all.extend(anomaly_pred.tolist())

    y_true = np.array(y_true_all)
    y_pred = np.array(y_pred_all)

    tn, fp, fn, tp = confusion_matrix(
        y_true, y_pred, labels=[0, 1]
    ).ravel()

    results.append({
        "configuration": config["name"],
        "n_estimators": config["n_estimators"],
        "contamination": config["contamination"],
        "test_samples": len(y_true),
        "TN": int(tn),
        "FP": int(fp),
        "FN": int(fn),
        "TP": int(tp),
        "accuracy_percent": round(100 * accuracy_score(y_true, y_pred), 2),
        "precision_percent": round(
            100 * precision_score(y_true, y_pred, zero_division=0), 2
        ),
        "recall_percent": round(
            100 * recall_score(y_true, y_pred, zero_division=0), 2
        ),
        "f1_percent": round(
            100 * f1_score(y_true, y_pred, zero_division=0), 2
        ),
        "false_positive_rate_percent": round(
            100 * fp / (fp + tn), 2
        ) if fp + tn else 0,
    })

result_df = pd.DataFrame(results)
result_df.to_csv(OUTPUT, index=False)

print("\n========== FINAL V2 COMPARISON ==========")
print(result_df.to_string(index=False))
print(f"\nSaved to: {OUTPUT}")
print("\nEvaluation uses a chronological 70/30 split and synthetic anomalies.")
print("Held-out normal observations are assumed normal, not independently verified.")
print("These metrics are benchmark results, not verified production accuracy.")
