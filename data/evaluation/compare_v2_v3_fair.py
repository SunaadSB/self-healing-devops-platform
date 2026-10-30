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
DATA = ROOT / "data" / "metrics_dataset_v2.csv"
OUT = ROOT / "data" / "evaluation"
FEATURES = ["request_rate", "error_ratio", "p95_latency_seconds"]
SEED = 42
CONTAMINATION = 0.055
MAX_VALIDATION_FPR = 0.05

def v3_features(x, median, scale):
    x = np.asarray(x, dtype=float)
    robust = (x - median) / scale
    relative = (x - median) / (np.abs(median) + scale * 0.1 + 1e-9)
    logged = np.log1p(np.maximum(x, 0))
    return np.column_stack([robust, relative, logged])

def inject(x, train):
    result = x.copy()
    kinds = np.arange(len(result)) % 3

    request_limit = max(float(np.max(train[:, 0])), 0.001)
    latency_limit = max(float(np.max(train[:, 2])), 0.001)

    for i, kind in enumerate(kinds):
        if kind == 0:
            result[i, 0] = request_limit * 3
        elif kind == 1:
            result[i, 1] = 0.20
        else:
            result[i, 2] = latency_limit * 5

    return result, kinds

def make_evaluation(model, method, normal, train, median, scale):
    synthetic, kinds = inject(normal, train)

    if method == "V2":
        normal_x = normal
        anomaly_x = synthetic
    else:
        normal_x = v3_features(normal, median, scale)
        anomaly_x = v3_features(synthetic, median, scale)

    normal_scores = model.decision_function(normal_x)
    anomaly_scores = model.decision_function(anomaly_x)

    scores = np.concatenate([normal_scores, anomaly_scores])
    labels = np.concatenate([
        np.zeros(len(normal), dtype=int),
        np.ones(len(synthetic), dtype=int)
    ])

    types = np.concatenate([
        np.array(["normal"] * len(normal)),
        np.array([
            "request_rate_spike",
            "error_ratio_spike",
            "latency_spike"
        ])[kinds]
    ])

    return scores, labels, types

def choose_threshold(scores, labels):
    normal_scores = scores[labels == 0]
    anomaly_scores = scores[labels == 1]

    # Thresholds are selected using validation data only.
    candidates = np.unique(np.concatenate([
        scores,
        [np.min(scores) - 1e-9, np.max(scores) + 1e-9]
    ]))

    best = None

    for threshold in candidates:
        fpr = float(np.mean(normal_scores < threshold))
        recall = float(np.mean(anomaly_scores < threshold))

        if fpr <= MAX_VALIDATION_FPR:
            candidate = (recall, -fpr, threshold)
            if best is None or candidate > best:
                best = candidate

    if best is None:
        raise RuntimeError("No threshold satisfies validation FPR constraint.")

    return float(best[2])

def calculate_metrics(labels, predictions):
    tn, fp, fn, tp = confusion_matrix(
        labels, predictions, labels=[0, 1]
    ).ravel()

    return {
        "samples": int(len(labels)),
        "TN": int(tn),
        "FP": int(fp),
        "FN": int(fn),
        "TP": int(tp),
        "accuracy_percent": round(
            100 * accuracy_score(labels, predictions), 2
        ),
        "precision_percent": round(
            100 * precision_score(labels, predictions, zero_division=0), 2
        ),
        "recall_percent": round(
            100 * recall_score(labels, predictions, zero_division=0), 2
        ),
        "f1_percent": round(
            100 * f1_score(labels, predictions, zero_division=0), 2
        ),
        "false_positive_rate_percent": round(
            100 * fp / (fp + tn), 2
        ) if fp + tn else 0
    }

def main():
    if not DATA.exists():
        raise SystemExit(f"Dataset not found: {DATA}")

    df = pd.read_csv(DATA)
    df[FEATURES] = df[FEATURES].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["timestamp", "service", *FEATURES])

    all_results = []
    type_results = []

    for service, group in df.groupby("service", sort=True):
        group = group.sort_values("timestamp")
        raw = group[FEATURES].to_numpy(dtype=float)

        n = len(raw)
        a = int(n * 0.60)
        b = int(n * 0.80)

        train = raw[:a]
        validation = raw[a:b]
        test = raw[b:]

        if min(len(train), len(validation), len(test)) < 20:
            print(f"Skipping {service}: insufficient data")
            continue

        median = np.median(train, axis=0)
        mad = np.median(np.abs(train - median), axis=0)
        std = np.std(train, axis=0)
        scale = np.maximum(
            np.where(mad > 1e-9, 1.4826 * mad, std),
            1e-6
        )

        for method in ["V2", "V3"]:
            if method == "V2":
                train_x = train
            else:
                train_x = v3_features(train, median, scale)

            model = make_pipeline(
                StandardScaler(),
                IsolationForest(
                    n_estimators=400,
                    contamination=CONTAMINATION,
                    random_state=SEED,
                    n_jobs=-1
                )
            )
            model.fit(train_x)

            val_scores, val_labels, _ = make_evaluation(
                model, method, validation, train, median, scale
            )

            threshold = choose_threshold(val_scores, val_labels)

            test_scores, test_labels, test_types = make_evaluation(
                model, method, test, train, median, scale
            )

            predictions = (test_scores < threshold).astype(int)

            result = {
                "version": method,
                "service": service,
                "train_rows": len(train),
                "validation_rows": len(validation),
                "test_rows": len(test),
                "validation_threshold": threshold,
                **calculate_metrics(test_labels, predictions)
            }

            all_results.append(result)

            for kind in [
                "request_rate_spike",
                "error_ratio_spike",
                "latency_spike"
            ]:
                mask = test_types == kind
                total = int(mask.sum())
                detected = int(predictions[mask].sum())

                type_results.append({
                    "version": method,
                    "service": service,
                    "anomaly_type": kind,
                    "total": total,
                    "detected": detected,
                    "recall_percent": round(
                        100 * detected / total, 2
                    ) if total else 0
                })

            print(f"\n{method} | {service}")
            print(json.dumps(result, indent=2))

    if not all_results:
        raise SystemExit("No comparison results generated.")

    results_df = pd.DataFrame(all_results)
    types_df = pd.DataFrame(type_results)

    # Combine service confusion-matrix counts for overall metrics.
    overall = []

    for method in ["V2", "V3"]:
        subset = results_df[results_df["version"] == method]

        counts = {
            "TN": int(subset["TN"].sum()),
            "FP": int(subset["FP"].sum()),
            "FN": int(subset["FN"].sum()),
            "TP": int(subset["TP"].sum())
        }

        tn, fp, fn, tp = (
            counts["TN"], counts["FP"],
            counts["FN"], counts["TP"]
        )

        total = tn + fp + fn + tp

        overall.append({
            "version": method,
            "samples": total,
            **counts,
            "accuracy_percent": round(
                100 * (tn + tp) / total, 2
            ),
            "precision_percent": round(
                100 * tp / (tp + fp), 2
            ) if tp + fp else 0,
            "recall_percent": round(
                100 * tp / (tp + fn), 2
            ) if tp + fn else 0,
            "f1_percent": round(
                200 * tp / (2 * tp + fp + fn), 2
            ) if 2 * tp + fp + fn else 0,
            "false_positive_rate_percent": round(
                100 * fp / (fp + tn), 2
            ) if fp + tn else 0
        })

    results_df.to_csv(
        OUT / "fair_v2_v3_service_results.csv", index=False
    )
    types_df.to_csv(
        OUT / "fair_v2_v3_anomaly_types.csv", index=False
    )

    summary = {
        "evaluation": "Identical chronological 60/20/20 splits and synthetic anomalies",
        "threshold_selection": "Maximum validation recall subject to validation FPR <= 5%",
        "seed": SEED,
        "contamination": CONTAMINATION,
        "overall_test_results": overall,
        "per_service_results": all_results,
        "per_anomaly_type_results": type_results,
        "limitations": [
            "Original test observations are assumed normal.",
            "Injected anomalies are synthetic, not confirmed incidents.",
            "Error ratio is constant in the source dataset.",
            "Validation FPR constraint does not guarantee test FPR <= 5%.",
            "Benchmark performance is not production accuracy."
        ]
    }

    with open(OUT / "fair_v2_v3_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n========== FAIR OVERALL TEST COMPARISON ==========")
    print(pd.DataFrame(overall).to_string(index=False))

    print("\n========== PER-ANOMALY RECALL ==========")
    print(types_df.to_string(index=False))

    print("\nReports saved in:", OUT)

if __name__ == "__main__":
    main()
