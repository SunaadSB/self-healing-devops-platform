
"""Run anomaly detection and advisory recommendations safely."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", required=True,
        help="Input metrics CSV path",
    )
    parser.add_argument(
        "--model-dir", required=True,
        help="Model directory path",
    )
    parser.add_argument(
        "--report", required=True,
        help="Anomaly report CSV path",
    )
    parser.add_argument(
        "--recommendations", required=True,
        help="Advisory recommendations CSV path",
    )
    args = parser.parse_args()

    dataset = Path(args.dataset).resolve()
    model_dir = Path(args.model_dir).resolve()
    report = Path(args.report).resolve()
    recommendations = Path(args.recommendations).resolve()

    # Prevent destructive path aliasing before creating directories or files.
    if len({dataset, report, recommendations}) != 3:
        print(
            "Dataset, anomaly report, and recommendations paths must be different.",
            file=sys.stderr,
        )
        return 2
    if model_dir in {dataset, report, recommendations}:
        print(
            "Model directory must be different from dataset and output paths.",
            file=sys.stderr,
        )
        return 2

    # Refuse to overwrite existing artifacts.
    for path in (report, recommendations):
        if path.exists():
            print(f"Refusing to overwrite existing file: {path}", file=sys.stderr)
            return 2

    if not dataset.is_file():
        print(f"Dataset not found: {dataset}", file=sys.stderr)
        return 2

    if model_dir.exists() and any(model_dir.iterdir()):
        print(f"Refusing to use non-empty model directory: {model_dir}", file=sys.stderr)
        return 2

    model_dir.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    recommendations.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["DATASET_PATH"] = str(dataset)
    env["MODEL_DIR_PATH"] = str(model_dir)
    env["REPORT_PATH"] = str(report)

    steps = [
        [
            PYTHON,
            str(ROOT / "ml" / "detect_anomalies_v2.py"),
        ],
        [
            PYTHON,
            str(ROOT / "recovery" / "decision_engine.py"),
            "--input", str(report),
            "--output", str(recommendations),
        ],
    ]

    for step in steps:
        print(f"\nRunning: {' '.join(step)}", flush=True)
        result = subprocess.run(step, cwd=ROOT, env=env, check=False)
        if result.returncode != 0:
            print(
                f"Pipeline stopped with exit code {result.returncode}.",
                file=sys.stderr,
            )
            return result.returncode

    print(f"\nAnomaly report: {report}")
    print(f"Advisory recommendations: {recommendations}")
    print("Pipeline completed. No recovery actions were executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
