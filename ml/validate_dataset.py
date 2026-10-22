
"""Validate the collected Prometheus metrics dataset."""

import csv
import os
import sys
from collections import Counter
from pathlib import Path

DATASET = Path(os.getenv("DATASET_PATH", "data/metrics_dataset.csv"))

EXPECTED_SERVICES = {
    "user-service",
    "order-service",
    "payment-service",
}

NUMERIC_FIELDS = (
    "request_rate",
    "error_ratio",
    "p95_latency_seconds",
)

REQUIRED_FIELDS = (
    "timestamp",
    "service",
    *NUMERIC_FIELDS,
)


def validate_dataset(path=DATASET):
    """Return a validation report without modifying the dataset."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("Dataset is empty or has no header")

        missing_columns = set(REQUIRED_FIELDS) - set(reader.fieldnames)
        if missing_columns:
            raise ValueError(
                f"Missing columns: {sorted(missing_columns)}"
            )

        rows = list(reader)

    if not rows:
        raise ValueError("Dataset contains no data rows")

    issues = []
    snapshots = Counter()
    services = Counter()
    seen_pairs = set()
    numeric_values = {field: [] for field in NUMERIC_FIELDS}

    for line_number, row in enumerate(rows, start=2):
        timestamp = (row.get("timestamp") or "").strip()
        service = (row.get("service") or "").strip()

        if not timestamp:
            issues.append(f"Row {line_number}: missing timestamp")
        else:
            snapshots[timestamp] += 1

        if service not in EXPECTED_SERVICES:
            issues.append(
                f"Row {line_number}: unexpected service {service!r}"
            )
        else:
            services[service] += 1

        pair = (timestamp, service)
        if pair in seen_pairs:
            issues.append(
                f"Row {line_number}: duplicate timestamp/service pair"
            )
        seen_pairs.add(pair)

        for field in NUMERIC_FIELDS:
            raw = (row.get(field) or "").strip()

            if not raw:
                issues.append(
                    f"Row {line_number}: missing {field}"
                )
                continue

            try:
                value = float(raw)
            except ValueError:
                issues.append(
                    f"Row {line_number}: invalid {field}={raw!r}"
                )
                continue

            if value < 0:
                issues.append(
                    f"Row {line_number}: negative {field}={value}"
                )
                continue

            if field == "error_ratio" and value > 1:
                issues.append(
                    f"Row {line_number}: error_ratio exceeds 1"
                )
                continue

            numeric_values[field].append(value)

    incomplete_snapshots = {
        timestamp: count
        for timestamp, count in snapshots.items()
        if count != len(EXPECTED_SERVICES)
    }

    print(f"Dataset: {path.resolve()}")
    print(f"Rows: {len(rows)}")
    print(f"Snapshots: {len(snapshots)}")
    print("\nRows by service:")

    for service in sorted(EXPECTED_SERVICES):
        print(f"  {service}: {services[service]}")

    print("\nMetric ranges:")
    for field, values in numeric_values.items():
        if values:
            print(
                f"  {field}: min={min(values):.8g}, "
                f"max={max(values):.8g}, "
                f"valid_values={len(values)}"
            )
        else:
            print(f"  {field}: no valid values")

    print(f"\nIncomplete snapshots: {len(incomplete_snapshots)}")

    # A constant zero error ratio is mathematically valid, but it can also
    # mean that no error responses were observed during collection. Surface
    # this as a diagnostic warning without falsely failing a clean dataset.
    error_values = numeric_values["error_ratio"]
    if error_values and all(value == 0 for value in error_values):
        print(
            "WARNING: error_ratio is zero in every row. This may be a "
            "genuine zero-error period; validate error telemetry with a "
            "known 4xx/5xx test before relying on this feature."
        )

    print(f"Validation issues: {len(issues)}")

    for timestamp, count in list(incomplete_snapshots.items())[:10]:
        print(f"  Snapshot {timestamp}: {count} rows")

    for issue in issues[:20]:
        print(f"  ISSUE: {issue}")

    if len(issues) > 20:
        print(f"  ... {len(issues) - 20} additional issues")

    return not issues and not incomplete_snapshots


if __name__ == "__main__":
    try:
        valid = validate_dataset()
    except (OSError, ValueError) as exc:
        print(f"Validation failed: {exc}")
        sys.exit(1)

    sys.exit(0 if valid else 1)
