
"""Train per-service Isolation Forest models and score metrics.

Detection only: this script does not trigger recovery actions.
"""

from pathlib import Path
import json
import os

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(os.getenv("DATASET_PATH", str(ROOT / "data" / "metrics_dataset.csv"))).resolve()
MODEL_DIR = Path(os.getenv("MODEL_DIR_PATH", str(ROOT / "ml" / "models"))).resolve()
REPORT = Path(os.getenv("REPORT_PATH", str(ROOT / "data" / "anomaly_report.csv"))).resolve()

FEATURES = [
    "request_rate",
    "error_ratio",
    "p95_latency_seconds",
]
REQUIRED = ["timestamp", "service", *FEATURES]

CONTAMINATION = 0.02
RANDOM_STATE = 42
MIN_ROWS_PER_SERVICE = 30


def main():
    if not DATASET.is_file():
        raise SystemExit(f"Dataset not found: {DATASET}")

    df = pd.read_csv(DATASET)

    missing = sorted(set(REQUIRED) - set(df.columns))
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")

    df = df[REQUIRED].copy()
    df[FEATURES] = df[FEATURES].apply(
        pd.to_numeric, errors="coerce"
    )
    rows_before_filter = len(df)
    missing_by_column = df[REQUIRED].isna().sum()
    missing_required_rows = int(df[REQUIRED].isna().any(axis=1).sum())
    if missing_required_rows:
        print(
            f"WARNING: dropping {missing_required_rows} of {rows_before_filter} "
            "rows with missing required values. "
            f"Missing by column: {missing_by_column[missing_by_column > 0].to_dict()}"
        )
    df = df.dropna(subset=REQUIRED)
    print(f"Valid rows after required-field filtering: {len(df)} / {rows_before_filter}")

    if df.empty:
        raise SystemExit("No valid metric rows found.")

    if (df[FEATURES] < 0).any().any():
        raise SystemExit("Negative metric values found.")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for service, group in df.groupby("service", sort=True):
        group = group.sort_values("timestamp").copy()

        if len(group) < MIN_ROWS_PER_SERVICE:
            print(
                f"Skipping {service}: only {len(group)} valid rows."
            )
            continue

        X = group[FEATURES]

        model = make_pipeline(
            StandardScaler(),
            IsolationForest(
                n_estimators=200,
                contamination=CONTAMINATION,
                random_state=RANDOM_STATE,
            ),
        )
        model.fit(X)

        # Lower scores are more anomalous.
        group["anomaly_score"] = model.decision_function(X)
        group["is_anomaly"] = model.predict(X) == -1
        group["model_service"] = service

        model_path = MODEL_DIR / f"{service}-isolation-forest.joblib"
        joblib.dump(
            {
                "model": model,
                "features": FEATURES,
                "service": service,
                "contamination": CONTAMINATION,
                "random_state": RANDOM_STATE,
            },
            model_path,
        )

        results.append(group)

        print(
            f"{service}: rows={len(group)}, "
            f"flagged={int(group['is_anomaly'].sum())}, "
            f"model={model_path}"
        )

    if not results:
        raise SystemExit("No models trained; check the dataset.")

    report = pd.concat(results, ignore_index=True)
    report.to_csv(REPORT, index=False)

    summary = {
        "dataset": str(DATASET),
        "report": str(REPORT),
        "rows_scored": len(report),
        "anomalies_flagged": int(report["is_anomaly"].sum()),
        "contamination": CONTAMINATION,
        "mode": "detection-only",
    }

    print("\nSummary:")
    print(json.dumps(summary, indent=2))
    print("\nNote: flagged rows are model predictions, not confirmed incidents.")


if __name__ == "__main__":
    main()

