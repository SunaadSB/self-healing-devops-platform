"""Collect timestamped Prometheus metrics into an append-only CSV."""

import argparse
import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from ml.prometheus_collector import collect_features


OUTPUT_FILE = Path(
    os.getenv("DATASET_PATH", "data/metrics_dataset.csv")
)
INTERVAL_SECONDS = max(
    10, int(os.getenv("COLLECTION_INTERVAL_SECONDS", "60"))
)

FIELDS = [
    "timestamp",
    "service",
    "request_rate",
    "error_ratio",
    "p95_latency_seconds",
]


def write_snapshot():
    """Append one snapshot for each service and return row count."""
    snapshot = collect_features()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    needs_header = (
        not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0
    )

    rows_written = 0

    with OUTPUT_FILE.open(
        "a", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)

        if needs_header:
            writer.writeheader()

        timestamp = datetime.now(timezone.utc).isoformat()

        for service, metrics in snapshot.items():
            writer.writerow({
                "timestamp": timestamp,
                "service": service,
                "request_rate": metrics.get("request_rate"),
                "error_ratio": metrics.get("error_ratio"),
                "p95_latency_seconds": metrics.get(
                    "p95_latency_seconds"
                ),
            })
            rows_written += 1

    return rows_written


def main():
    parser = argparse.ArgumentParser(
        description="Collect Prometheus metrics into an append-only CSV."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect one snapshot and exit.",
    )
    args = parser.parse_args()

    print(f"Writing metrics to: {OUTPUT_FILE.resolve()}")

    if args.once:
        rows = write_snapshot()
        print(
            f"{datetime.now(timezone.utc).isoformat()}: "
            f"appended {rows} service rows"
        )
        return 0

    print(f"Collection interval: {INTERVAL_SECONDS} seconds")
    print("Press Ctrl+C to stop.")

    while True:
        try:
            rows = write_snapshot()
            print(
                f"{datetime.now(timezone.utc).isoformat()}: "
                f"appended {rows} service rows"
            )
        except Exception as exc:
            print(f"Collection failed: {exc}")

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
