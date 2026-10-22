import csv

from recovery.decision_engine import generate_recommendations


def write_report(path, services):
    fields = [
        "timestamp", "service", "request_rate", "error_ratio",
        "p95_latency_seconds", "anomaly_score", "is_anomaly", "model_service",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for service, timestamps_and_flags in services.items():
            for timestamp, flagged in timestamps_and_flags:
                writer.writerow({
                    "timestamp": timestamp,
                    "service": service,
                    "request_rate": "1.0",
                    "error_ratio": "0.0",
                    "p95_latency_seconds": "0.01",
                    "anomaly_score": "-0.2" if flagged else "0.2",
                    "is_anomaly": str(flagged),
                    "model_service": service,
                })


def test_three_consecutive_anomalies_generate_advisory(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    write_report(source, {
        "order-service": [
            ("2026-10-18T10:00:00+00:00", True),
            ("2026-10-18T10:01:00+00:00", True),
            ("2026-10-18T10:02:00+00:00", True),
        ]
    })

    _, recommendations, _ = generate_recommendations(source, output)

    assert len(recommendations) == 1
    assert recommendations[0]["service"] == "order-service"
    assert recommendations[0]["status"] == "advisory_only"
    assert recommendations[0]["recommendation"] == "review_recovery"


def test_isolated_anomalies_do_not_generate_advisory(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    write_report(source, {
        "order-service": [
            ("2026-10-18T10:00:00+00:00", True),
            ("2026-10-18T10:01:00+00:00", False),
            ("2026-10-18T10:02:00+00:00", True),
            ("2026-10-18T10:03:00+00:00", False),
        ]
    })

    _, recommendations, _ = generate_recommendations(source, output)

    assert recommendations == []


def test_cooldown_suppresses_repeat_advisory(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    write_report(source, {
        "order-service": [
            ("2026-10-18T10:00:00+00:00", True),
            ("2026-10-18T10:01:00+00:00", True),
            ("2026-10-18T10:02:00+00:00", True),
            ("2026-10-18T10:03:00+00:00", True),
            ("2026-10-18T10:04:00+00:00", True),
            ("2026-10-18T10:05:00+00:00", True),
            ("2026-10-18T10:06:00+00:00", True),
            ("2026-10-18T10:07:00+00:00", True),
            ("2026-10-18T10:08:00+00:00", True),
            ("2026-10-18T10:09:00+00:00", True),
            ("2026-10-18T10:10:00+00:00", True),
            ("2026-10-18T10:11:00+00:00", True),
            ("2026-10-18T10:12:00+00:00", True),
        ]
    })

    _, recommendations, _ = generate_recommendations(source, output)

    assert len(recommendations) == 1


def test_anomaly_streak_resets_after_excessive_timestamp_gap(tmp_path):
    source = tmp_path / "input_gap.csv"
    output = tmp_path / "output_gap.csv"
    write_report(source, {
        "order-service": [
            ("2026-10-18T10:00:00+00:00", True),
            ("2026-10-18T10:01:00+00:00", True),
            ("2026-10-18T10:04:00+00:00", True),
            ("2026-10-18T10:05:00+00:00", True),
            ("2026-10-18T10:06:00+00:00", True),
        ]
    })

    _, recommendations, _ = generate_recommendations(source, output)

    assert len(recommendations) == 1
    assert recommendations[0]["timestamp"].endswith("10:06:00+00:00")


def test_anomaly_streak_allows_gap_within_90_seconds(tmp_path):
    source = tmp_path / "input_jitter.csv"
    output = tmp_path / "output_jitter.csv"
    write_report(source, {
        "order-service": [
            ("2026-10-18T10:00:00+00:00", True),
            ("2026-10-18T10:01:30+00:00", True),
            ("2026-10-18T10:03:00+00:00", True),
        ]
    })

    _, recommendations, _ = generate_recommendations(source, output)

    assert len(recommendations) == 1
    assert recommendations[0]["status"] == "advisory_only"
