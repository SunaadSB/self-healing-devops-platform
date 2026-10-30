from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "metrics_dataset_v2.csv"
MODEL_DIR = ROOT / "ml" / "models_v3"
OUT = ROOT / "data" / "evaluation"
FEATURES = ["request_rate", "error_ratio", "p95_latency_seconds"]
SEED = 42

def make_features(frame, baseline):
    x = np.asarray(frame, dtype=float)
    med = baseline["median"]
    scale = baseline["scale"]

    robust = (x - med) / scale
    relative = (x - med) / (np.abs(med) + scale * 0.1 + 1e-9)
    log_values = np.log1p(np.maximum(x, 0))

    return np.column_stack([robust, relative, log_values])

def inject_anomalies(X, train):
    result = X.copy()
    kinds = np.arange(len(result)) % 3
    request_limit = max(float(np.quantile(train[:, 0], .99)), .001)
    latency_limit = max(float(np.quantile(train[:, 2], .99)), .001)

    for i, kind in enumerate(kinds):
        if kind == 0:
            result[i, 0] = request_limit * 3
        elif kind == 1:
            result[i, 1] = .20
        else:
            result[i, 2] = latency_limit * 5
    return result, kinds

def make_eval(model, baseline, normal_raw, train_raw):
    normal_features = make_features(normal_raw, baseline)
    synthetic_raw, kinds = inject_anomalies(normal_raw, train_raw)
    synthetic_features = make_features(synthetic_raw, baseline)

    scores_normal = model.decision_function(normal_features)
    scores_anomaly = model.decision_function(synthetic_features)

    scores = np.concatenate([scores_normal, scores_anomaly])
    labels = np.concatenate([
        np.zeros(len(scores_normal), dtype=int),
        np.ones(len(scores_anomaly), dtype=int)
    ])
    types = np.concatenate([
        np.array(["normal"] * len(scores_normal)),
        np.array(["request_rate_spike", "error_ratio_spike",
                  "latency_spike"])[kinds]
    ])
    return scores, labels, types

def metrics(labels, predictions):
    tn, fp, fn, tp = confusion_matrix(
        labels, predictions, labels=[0, 1]
    ).ravel()
    return {
        "samples": int(len(labels)),
        "TN": int(tn), "FP": int(fp),
        "FN": int(fn), "TP": int(tp),
        "accuracy_percent": round(100 * accuracy_score(labels, predictions), 2),
        "precision_percent": round(100 * precision_score(labels, predictions, zero_division=0), 2),
        "recall_percent": round(100 * recall_score(labels, predictions, zero_division=0), 2),
        "f1_percent": round(100 * f1_score(labels, predictions, zero_division=0), 2),
        "false_positive_rate_percent": round(100 * fp / (fp + tn), 2) if fp + tn else 0
    }

def main():
    if not DATA.exists():
        raise SystemExit(f"Dataset not found: {DATA}")

    df = pd.read_csv(DATA)
    df[FEATURES] = df[FEATURES].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["timestamp", "service", *FEATURES])
    df = df.sort_values(["service", "timestamp"])

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    results = []
    type_results = []

    for service, group in df.groupby("service", sort=True):
        group = group.sort_values("timestamp")
        raw = group[FEATURES].to_numpy(dtype=float)
        n = len(raw)

        a, b = int(n * .60), int(n * .80)
        train, validation, test = raw[:a], raw[a:b], raw[b:]

        if len(train) < 50 or len(validation) < 20 or len(test) < 20:
            print(f"Skipping {service}: insufficient rows")
            continue

        median = np.median(train, axis=0)
        mad = np.median(np.abs(train - median), axis=0)
        std = np.std(train, axis=0)
        scale = np.where(mad > 1e-9, 1.4826 * mad, std)
        scale = np.maximum(scale, 1e-6)
        baseline = {"median": median, "scale": scale}

        X_train = make_features(train, baseline)
        X_val = make_eval(
            IsolationForest(
                n_estimators=400,
                contamination="auto",
                random_state=SEED,
                max_samples="auto",
                n_jobs=-1
            ).fit(X_train),
            baseline, validation, train
        )

        # Refit a fresh model for final validation and test.
        model = IsolationForest(
            n_estimators=400,
            contamination="auto",
            random_state=SEED,
            max_samples="auto",
            n_jobs=-1
        )
        model.fit(X_train)

        val_scores, val_labels, val_types = make_eval(
            model, baseline, validation, train
        )

        # Choose threshold on validation only, preferring maximum F1
        # while limiting normal false-positive rate to 5%.
        candidates = np.unique(np.quantile(
            val_scores, np.linspace(0, 1, 501)
        ))
        best = None
        for threshold in candidates:
            pred = (val_scores < threshold).astype(int)
            m = metrics(val_labels, pred)
            if m["false_positive_rate_percent"] <= 5.0:
                if best is None or m["f1_percent"] > best["f1_percent"]:
                    best = {
                        "threshold": float(threshold),
                        **m
                    }

        if best is None:
            threshold = float(np.quantile(val_scores, .05))
        else:
            threshold = best["threshold"]

        test_scores, test_labels, test_types = make_eval(
            model, baseline, test, train
        )
        test_predictions = (test_scores < threshold).astype(int)
        result = {
            "service": service,
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "threshold": threshold,
            **metrics(test_labels, test_predictions)
        }
        results.append(result)

        for kind in ["request_rate_spike", "error_ratio_spike", "latency_spike"]:
            mask = test_types == kind
            detected = int(test_predictions[mask].sum())
            total = int(mask.sum())
            type_results.append({
                "service": service,
                "anomaly_type": kind,
                "total": total,
                "detected": detected,
                "recall_percent": round(100 * detected / total, 2) if total else 0
            })

        joblib.dump({
            "model": model,
            "features": FEATURES,
            "service": service,
            "baseline_median": median,
            "baseline_scale": scale,
            "threshold": threshold,
            "version": "V3"
        }, MODEL_DIR / f"{service}-isolation-forest-v3.joblib")

        print(f"\n{service}")
        print(json.dumps(result, indent=2))

    if not results:
        raise SystemExit("No service models were evaluated.")

    # Combined test metrics across all services.
    combined_scores = []
    combined_labels = []
    combined_predictions = []
    for service, group in df.groupby("service", sort=True):
        r = next((x for x in results if x["service"] == service), None)
        if r is None:
            continue
        raw = group.sort_values("timestamp")[FEATURES].to_numpy(dtype=float)
        a, b = int(len(raw) * .60), int(len(raw) * .80)
        train, test = raw[:a], raw[b:]
        median = np.median(train, axis=0)
        mad = np.median(np.abs(train - median), axis=0)
        std = np.std(train, axis=0)
        scale = np.maximum(np.where(mad > 1e-9, 1.4826 * mad, std), 1e-6)
        model_data = joblib.load(MODEL_DIR / f"{service}-isolation-forest-v3.joblib")
        model = model_data["model"]
        baseline = {"median": median, "scale": scale}
        scores, labels, _ = make_eval(model, baseline, test, train)
        combined_scores.extend(scores.tolist())
        combined_labels.extend(labels.tolist())
        combined_predictions.extend((scores < r["threshold"]).astype(int).tolist())

    overall = metrics(
        np.array(combined_labels),
        np.array(combined_predictions)
    )

    pd.DataFrame(results).to_csv(OUT / "v3_service_results.csv", index=False)
    pd.DataFrame(type_results).to_csv(OUT / "v3_anomaly_type_results.csv", index=False)

    summary = {
        "version": "V3",
        "method": "Chronological 60/20/20 split; per-service Isolation Forest; robust median/MAD features; validation-selected threshold",
        "overall_test_metrics": overall,
        "per_service": results,
        "per_anomaly_type": type_results,
        "limitations": [
            "Original held-out observations are assumed normal, not independently verified.",
            "Injected anomalies are synthetic and do not represent confirmed incidents.",
            "error_ratio is constant in the source dataset; its injected spike is an artificial feature-shift test.",
            "The benchmark score is not production accuracy."
        ]
    }

    with open(OUT / "v3_evaluation_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n========== V3 OVERALL HELD-OUT TEST ==========")
    print(json.dumps(overall, indent=2))
    print("\n========== ANOMALY TYPE RESULTS ==========")
    print(pd.DataFrame(type_results).to_string(index=False))
    print("\nV3 models:", MODEL_DIR)
    print("V3 reports:", OUT)

if __name__ == "__main__":
    main()

