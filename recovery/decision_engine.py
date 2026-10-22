"""Recommendation-only anomaly decision engine. Never invokes kubectl."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "anomaly_report_v2.csv"
DEFAULT_OUTPUT = ROOT / "data" / "recovery_recommendations_v2.csv"

ALLOWED_SERVICES = {"user-service", "order-service", "payment-service"}
MIN_CONSECUTIVE_ANOMALIES = 3
MAX_ANOMALY_GAP = timedelta(seconds=90)
COOLDOWN = timedelta(minutes=10)

REQUIRED_FIELDS = {
    "timestamp",
    "service",
    "is_anomaly",
    "anomaly_score",
    "request_rate",
    "error_ratio",
    "p95_latency_seconds",
}

OUTPUT_FIELDS = [
    "timestamp",
    "service",
    "recommendation",
    "status",
    "reason",
    "consecutive_anomalies",
    "anomaly_score",
    "request_rate",
    "error_ratio",
    "p95_latency_seconds",
    "cooldown_minutes",
]


def parse_bool(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def parse_timestamp(value):
    """Parse an ISO timestamp and normalize it to UTC."""
    text = str(value).strip()
    if not text:
        raise ValueError("Empty timestamp in anomaly report")

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp in anomaly report: {text!r}") from exc

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


def generate_recommendations(input_path=DEFAULT_INPUT, output_path=DEFAULT_OUTPUT):
    with Path(input_path).open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "Missing required columns: " + ", ".join(sorted(missing))
            )
        rows = list(reader)

    rows = [
        row for row in rows
        if row.get("service") in ALLOWED_SERVICES
    ]

    # Parse timestamps before sorting; ISO strings with different offsets
    # cannot safely be sorted as if their text were chronological.
    for row in rows:
        row["_parsed_timestamp"] = parse_timestamp(row["timestamp"])


    rows.sort(
        key=lambda row: (
            row["service"],
            row["_parsed_timestamp"],
        )
    )

    recommendations = []
    streaks = {service: 0 for service in ALLOWED_SERVICES}
    last_anomaly_time = {}
    last_recommendation = {}

    for row in rows:
        service = row["service"]
        timestamp = row["_parsed_timestamp"]
        anomalous = parse_bool(row.get("is_anomaly", ""))

        if not anomalous:
            streaks[service] = 0
            last_anomaly_time.pop(service, None)
            continue

        previous_anomaly = last_anomaly_time.get(service)

        # A gap greater than the collection tolerance breaks the streak.
        if (
            previous_anomaly is None
            or timestamp - previous_anomaly > MAX_ANOMALY_GAP
            or timestamp < previous_anomaly
        ):
            streaks[service] = 1
        else:
            streaks[service] += 1

        last_anomaly_time[service] = timestamp

        if streaks[service] != MIN_CONSECUTIVE_ANOMALIES:
            continue

        previous_recommendation = last_recommendation.get(service)
        if (
            previous_recommendation is not None
            and timestamp - previous_recommendation < COOLDOWN
        ):
            continue

        last_recommendation[service] = timestamp

        recommendations.append({
            "timestamp": timestamp.isoformat(),
            "service": service,
            "recommendation": "review_recovery",
            "status": "advisory_only",
            "reason": (
                f"{MIN_CONSECUTIVE_ANOMALIES}_consecutive_anomaly_records"
                f"_within_{int(MAX_ANOMALY_GAP.total_seconds())}_seconds"
            ),
            "consecutive_anomalies": streaks[service],
            "anomaly_score": row.get("anomaly_score", ""),
            "request_rate": row.get("request_rate", ""),
            "error_ratio": row.get("error_ratio", ""),
            "p95_latency_seconds": row.get("p95_latency_seconds", ""),
            "cooldown_minutes": int(COOLDOWN.total_seconds() / 60),
        })

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(recommendations)

    return len(rows), recommendations, output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    count, recommendations, output = generate_recommendations(
        args.input,
        args.output,
    )

    print(f"Rows evaluated: {count}")
    print(f"Recommendations generated: {len(recommendations)}")
    print(f"Output: {output}")
    print(f"Maximum anomaly gap: {MAX_ANOMALY_GAP.total_seconds():.0f} seconds")
    print("Mode: advisory only; no recovery actions executed")


if __name__ == "__main__":
    main()
