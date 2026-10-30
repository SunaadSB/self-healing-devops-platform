from pathlib import Path
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler


ROOT = Path(__file__).resolve().parents[1]

DATASET = Path(os.getenv(
    "DATASET_PATH",
    str(ROOT / "data" / "metrics_dataset.csv")
)).resolve()

MODEL_DIR = ROOT / "ml" / "models_v3_temporal"
OUTPUT_DIR = ROOT / "data" / "evaluation" / "v3_temporal"

BASE_FEATURES = [
    "request_rate",
    "error_ratio",
    "p95_latency_seconds",
]

TEMPORAL_FEATURES = [
    "request_rate",
    "error_ratio",
    "p95_latency_seconds",
    "request_rate_roll5_mean",
    "request_rate_roll5_std",
    "request_rate_roll15_mean",
    "request_rate_roll15_std",
    "request_rate_change",
    "request_rate_deviation",
    "latency_roll5_mean",
    "latency_roll5_std",
    "latency_roll15_mean",
    "latency_roll15_std",
    "latency_change",
    "latency_deviation",
]

RANDOM_STATE = 42
CONTAMINATION = 0.05
MIN_ROWS = 100


def create_temporal_features(group):
    group = group.sort_values("timestamp").copy()

    for column in BASE_FEATURES:
        group[column] = pd.to_numeric(
            group[column], errors="coerce"
        )

    # Rolling windows use current and past observations only.
    for column, prefix in [
        ("request_rate", "request_rate"),
        ("p95_latency_seconds", "latency"),
    ]:
        series = group[column]

        group[f"{prefix}_roll5_mean"] = (
            series.rolling(5, min_periods=1).mean()
        )
        group[f"{prefix}_roll5_std"] = (
            series.rolling(5, min_periods=2).std().fillna(0)
        )
        group[f"{prefix}_roll15_mean"] = (
            series.rolling(15, min_periods=1).mean()
        )
        group[f"{prefix}_roll15_std"] = (
            series.rolling(15, min_periods=2).std().fillna(0)
        )

        group[f"{prefix}_change"] = (
            series.pct_change(fill_method=None)
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0)
            .clip(-10, 10)
        )

        denominator = (
            group[f"{prefix}_roll5_mean"].abs() + 1e-8
        )

        group[f"{prefix}_deviation"] = (
            (series - group[f"{prefix}_roll5_mean"]) / denominator
        ).replace([np.inf, -np.inf], 0).fillna(0)

    return group.replace([np.inf, -np.inf], np.nan)


def main():
    if not DATASET.exists():
        raise SystemExit(f"Dataset not found: {DATASET}")

    df = pd.read_csv(DATASET)

    required = ["timestamp", "service", *BASE_FEATURES]
    missing = sorted(set(required) - set(df.columns))

    if missing:
        raise SystemExit(f"Missing columns: {missing}")

    df = df[required].copy()
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce"
    )

    for column in BASE_FEATURES:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=required)
    df = df.sort_values(["service", "timestamp"])

    if (df[BASE_FEATURES] < 0).any().any():
        raise SystemExit("Negative metric values detected.")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []
    summary = {
        "version": "V3_TEMPORAL",
        "dataset": str(DATASET),
        "features": TEMPORAL_FEATURES,
        "services": {},
        "limitations": [
            "No confirmed incident labels in the source dataset.",
            "Validation threshold is calibrated on normal observations.",
            "Anomaly predictions are not confirmed incidents.",
            "Synthetic anomaly evaluation must be performed separately.",
        ],
    }

    for service, original in df.groupby("service", sort=True):
        group = create_temporal_features(original)

        group = group.dropna(
            subset=TEMPORAL_FEATURES
        ).reset_index(drop=True)

        n = len(group)

        if n < MIN_ROWS:
            print(f"Skipping {service}: only {n} usable rows.")
            continue

        train_end = int(n * 0.70)
        validation_end = int(n * 0.85)

        train = group.iloc[:train_end].copy()
        validation = group.iloc[train_end:validation_end].copy()
        test = group.iloc[validation_end:].copy()

        X_train = train[TEMPORAL_FEATURES]
        X_validation = validation[TEMPORAL_FEATURES]
        X_test = test[TEMPORAL_FEATURES]

        model = make_pipeline(
            RobustScaler(),
            IsolationForest(
                n_estimators=500,
                contamination=CONTAMINATION,
                random_state=RANDOM_STATE,
                max_samples="auto",
                n_jobs=-1,
            ),
        )

        model.fit(X_train)

        # Higher score means more anomalous.
        validation_scores = -model.decision_function(X_validation)

        threshold = float(
            np.quantile(validation_scores, 0.95)
        )

        train["anomaly_score"] = -model.decision_function(X_train)
        validation["anomaly_score"] = validation_scores
        test["anomaly_score"] = -model.decision_function(X_test)

        for part in [train, validation, test]:
            part["is_anomaly"] = (
                part["anomaly_score"] > threshold
            )
            part["model_version"] = "V3_TEMPORAL"
            part["model_service"] = service

        model_path = (
            MODEL_DIR / f"{service}-isolation-forest-temporal.joblib"
        )

        bundle = {
            "model": model,
            "features": TEMPORAL_FEATURES,
            "base_features": BASE_FEATURES,
            "service": service,
            "threshold": threshold,
            "version": "V3_TEMPORAL",
            "contamination": CONTAMINATION,
            "random_state": RANDOM_STATE,
            "rolling_windows": [5, 15],
            "score_direction": "higher_is_more_anomalous",
        }

        joblib.dump(bundle, model_path)

        result = pd.concat(
            [train, validation, test],
            ignore_index=True,
        )
        all_results.append(result)

        summary["services"][service] = {
            "total_rows": n,
            "training_rows": len(train),
            "validation_rows": len(validation),
            "testing_rows": len(test),
            "threshold": threshold,
            "test_anomalies": int(test["is_anomaly"].sum()),
            "test_anomaly_percentage": round(
                float(test["is_anomaly"].mean() * 100), 2
            ),
            "model_path": str(model_path),
        }

        print(f"\n{service}")
        print(f"  Total rows:      {n}")
        print(f"  Training rows:   {len(train)}")
        print(f"  Validation rows: {len(validation)}")
        print(f"  Testing rows:    {len(test)}")
        print(f"  Threshold:       {threshold:.6f}")
        print(f"  Test anomalies:  {int(test['is_anomaly'].sum())}")
        print(f"  Saved: {model_path}")

    if not all_results:
        raise SystemExit("No models were trained.")

    report = pd.concat(all_results, ignore_index=True)

    report_path = OUTPUT_DIR / "v3_temporal_predictions.csv"
    report.to_csv(report_path, index=False)

    summary["rows_scored"] = len(report)
    summary["report"] = str(report_path)

    summary_path = OUTPUT_DIR / "v3_temporal_training_summary.json"

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n========== V3 TEMPORAL SUMMARY ==========")
    print(json.dumps(summary, indent=2))
    print("\nTraining completed successfully.")


if __name__ == "__main__":
    main()
