from pathlib import Path
import json
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

VERSIONS = {
    "V1": ROOT / "data" / "metrics_dataset.csv",
    "V2": ROOT / "data" / "metrics_dataset_v2.csv",
}

FEATURES = [
    "request_rate",
    "error_ratio",
    "p95_latency_seconds",
]

results = []
type_results = []

for version, dataset_path in VERSIONS.items():
    print(f"\n========== {version} EVALUATION ==========")

    df = pd.read_csv(dataset_path)
    df[FEATURES] = df[FEATURES].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["timestamp", "service", *FEATURES])

    version_predictions = []
    version_labels = []
    version_types = []

    for service, group in df.groupby("service", sort=True):
        group = group.sort_values("timestamp")
        X = group[FEATURES].to_numpy(dtype=float)

        if len(X) < 50:
            print(f"Skipping {service}: insufficient rows")
            continue

        split = int(len(X) * 0.70)
        X_train = X[:split]
        X_test = X[split:]

        model = make_pipeline(
            StandardScaler(),
            IsolationForest(
                n_estimators=200,
                contamination=0.02,
                random_state=42,
            ),
        )

        model.fit(X_train)

        # Held-out observations are provisionally treated as normal.
        normal_predictions = model.predict(X_test)
        normal_labels = np.zeros(len(X_test), dtype=int)

        version_predictions.extend((normal_predictions == -1).astype(int))
        version_labels.extend(normal_labels)
        version_types.extend(["normal"] * len(X_test))

        # Create three types of controlled synthetic anomalies.
        synthetic = X_test.copy()
        anomaly_types = np.arange(len(synthetic)) % 3

        for i, anomaly_type in enumerate(anomaly_types):
            if anomaly_type == 0:
                synthetic[i, 0] = max(X_train[:, 0].max(), 0.001) * 3
            elif anomaly_type == 1:
                synthetic[i, 1] = 0.20
            else:
                synthetic[i, 2] = max(X_train[:, 2].max(), 0.001) * 5

        anomaly_predictions = model.predict(synthetic)
        anomaly_detected = (anomaly_predictions == -1).astype(int)

        version_predictions.extend(anomaly_detected)
        version_labels.extend(np.ones(len(synthetic), dtype=int))

        type_names = np.array([
            "request_rate_spike",
            "error_ratio_spike",
            "latency_spike",
        ])

        version_types.extend(type_names[anomaly_types].tolist())

        for anomaly_type in type_names:
            mask = type_names[anomaly_types] == anomaly_type
            detected = int(anomaly_detected[mask].sum())
            total = int(mask.sum())

            type_results.append({
                "version": version,
                "service": service,
                "anomaly_type": anomaly_type,
                "total": total,
                "detected": detected,
                "detection_recall_percent": round(
                    100 * detected / total, 2
                ) if total else 0,
            })

        print(
            f"{service}: train={len(X_train)}, "
            f"normal_test={len(X_test)}, "
            f"synthetic_anomalies={len(synthetic)}"
        )

    y_true = np.array(version_labels)
    y_pred = np.array(version_predictions)

    tn, fp, fn, tp = confusion_matrix(
        y_true, y_pred, labels=[0, 1]
    ).ravel()

    result = {
        "version": version,
        "test_samples": int(len(y_true)),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
        "accuracy_percent": round(100 * accuracy_score(y_true, y_pred), 2),
        "precision_percent": round(100 * precision_score(y_true, y_pred, zero_division=0), 2),
        "recall_percent": round(100 * recall_score(y_true, y_pred, zero_division=0), 2),
        "f1_score_percent": round(100 * f1_score(y_true, y_pred, zero_division=0), 2),
        "false_positive_rate_percent": round(
            100 * fp / (fp + tn), 2
        ) if (fp + tn) else 0,
    }

    results.append(result)
    print(json.dumps(result, indent=2))

output_dir = ROOT / "data" / "evaluation"

pd.DataFrame(results).to_csv(
    output_dir / "detector_comparison.csv", index=False
)

pd.DataFrame(type_results).to_csv(
    output_dir / "anomaly_type_results.csv", index=False
)

with open(output_dir / "evaluation_summary.json", "w") as f:
    json.dump({
        "evaluation_method": "70/30 chronological split with synthetic anomalies",
        "results": results,
        "anomaly_types": type_results,
        "limitations": [
            "Held-out original observations are assumed normal, not independently verified.",
            "Synthetic anomalies are controlled injections, not confirmed production incidents.",
            "Results measure performance on this benchmark, not guaranteed real-world accuracy."
        ]
    }, f, indent=2)

print("\n========== FINAL COMPARISON ==========")
print(pd.DataFrame(results).to_string(index=False))
print(f"\nReports saved in: {output_dir}")
