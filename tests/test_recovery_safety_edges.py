import csv
import json
import subprocess

from recovery.recovery_controller import recover
from recovery.decision_engine import generate_recommendations


def test_rollout_verification_failure_is_audited(tmp_path):
    calls = []

    class Result:
        stdout = ""
        stderr = "rollout exceeded progress deadline"

        def __init__(self, returncode):
            self.returncode = returncode

    def fake_runner(command, **kwargs):
        calls.append(command)
        return Result(0 if len(calls) == 1 else 1)

    audit = tmp_path / "audit.jsonl"
    result = recover(
        "order-service", execute=True, authorized=True,
        audit_path=audit, runner=fake_runner,
    )

    assert result["status"] == "verification_failed"
    assert result["reason"] == "rollout_status_failed"
    assert len(calls) == 2
    assert json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])["status"] == "verification_failed"


def test_kubectl_timeout_is_audited(tmp_path):
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_runner(command, **kwargs):
        calls.append(command)
        if len(calls) == 2:
            raise subprocess.TimeoutExpired(command, timeout=130)
        return Result()

    audit = tmp_path / "audit.jsonl"
    result = recover(
        "payment-service", execute=True, authorized=True,
        audit_path=audit, runner=fake_runner,
    )

    assert result["status"] == "failed"
    assert result["reason"] == "kubectl_error"
    assert json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])["status"] == "failed"


def test_missing_kubectl_executable_is_audited(tmp_path):
    def fake_runner(command, **kwargs):
        raise FileNotFoundError("kubectl not found")

    audit = tmp_path / "audit.jsonl"
    result = recover(
        "user-service", execute=True, authorized=True,
        audit_path=audit, runner=fake_runner,
    )

    assert result["status"] == "failed"
    assert result["reason"] == "kubectl_error"
    assert json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])["reason"] == "kubectl_error"


def test_cooldown_is_checked_after_a_new_anomaly_streak(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    fields = [
        "timestamp", "service", "request_rate", "error_ratio",
        "p95_latency_seconds", "anomaly_score", "is_anomaly",
    ]
    rows = [
        ("10:00:00", True),
        ("10:01:00", True),
        ("10:02:00", True),  # first recommendation
        ("10:03:00", False), # reset streak
        ("10:04:00", True),
        ("10:05:00", True),
        ("10:06:00", True),  # suppressed by cooldown
        ("10:07:00", False), # reset again
        ("10:08:00", True),
        ("10:09:00", True),
        ("10:10:00", True),  # still within cooldown
        ("10:11:00", False),
        ("10:12:00", True),
        ("10:13:00", True),
        ("10:14:00", True),  # cooldown has elapsed: second recommendation
    ]

    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for clock, flagged in rows:
            writer.writerow({
                "timestamp": f"2026-10-18T{clock}+00:00",
                "service": "order-service",
                "request_rate": "1.0",
                "error_ratio": "0.0",
                "p95_latency_seconds": "0.01",
                "anomaly_score": "-0.2" if flagged else "0.2",
                "is_anomaly": str(flagged),
            })

    _, recommendations, _ = generate_recommendations(source, output)

    assert len(recommendations) == 2
    assert recommendations[0]["timestamp"].endswith("10:02:00+00:00")
    assert recommendations[1]["timestamp"].endswith("10:14:00+00:00")

