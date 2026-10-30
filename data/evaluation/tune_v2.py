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
OUTPUT = ROOT / "data" / "evaluation" / "v2_tuning_results.csv"
TYPE_OUTPUT = ROOT / "data" / "evaluation" / "v2_tuning_by_type.csv"

FEATURES = ["request_rate", "error_ratio", "p95_latency_seconds"]

# Include the current production configuration as the baseline.
CONFIGS = [
    (200, 0.04),
    (200, 0.045),
    (200, 0.05),
    (200, 0.055),
    (200, 0.06),
    (400, 0.045),
    (400, 0.05),
    (400, 0.055),
]

df = pd.read_csv(DATASET)
df[FEATURES] = df[FEATURES].apply(pd.to_numeric, errors="coerce")
df = df.dropna(subset=["timestamp", "service", *FEATURES])

all_results = []
all_type_results = []

for estimators, contamination in CONFIGS:
    y_true_all = []
    y_pred_all = []
    type_counts = {}

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
                n_estimators=estimators,
                contamination=contamination,
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

        names = ["request_rate_spike", "error_ratio_spike", "latency_spike"]

        for index, name in enumerate(names):
            mask = anomaly_types == index
            detected = int(anomaly_pred[mask].sum())
            total = int(mask.sum())

            key = (service, name)
            type_counts[key] = (detected, total)

    y_true = np.array(y_true_all)
    y_pred = np.array(y_pred_all)

    tn, fp, fn, tp = confusion_matrix(
        y_true, y_pred, labels=[0, 1]
    ).ravel()

    result = {
        "n_estimators": estimators,
        "contamination": contamination,
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
    }
    all_results.append(result)

    for (service, anomaly_type), (detected, total) in type_counts.items():
        all_type_results.append({
            "n_estimators": estimators,
            "contamination": contamination,
            "service": service,
            "anomaly_type": anomaly_type,
            "detected": detected,
            "total": total,
            "recall_percent": round(100 * detected / total, 2) if total else 0,
        })

results_df = pd.DataFrame(all_results).sort_values(
    ["f1_percent", "recall_percent"],
    ascending=False
)
types_df = pd.DataFrame(all_type_results)

results_df.to_csv(OUTPUT, index=False)
types_df.to_csv(TYPE_OUTPUT, index=False)

print("\n========== V2 TUNING RESULTS ==========")
print(results_df.to_string(index=False))
print("\n========== PER-TYPE DETECTION ==========")
print(types_df.to_string(index=False))
print(f"\nSaved: {OUTPUT}")
print(f"Saved: {TYPE_OUTPUT}")

