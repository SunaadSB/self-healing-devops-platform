import json

import pytest

from recovery.recovery_metrics import calculate_recovery_metrics


def write_records(path, records):
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_correlated_success_counts_once_and_excludes_dry_runs(tmp_path):
    audit = tmp_path / "audit.jsonl"
    write_records(
        audit,
        [
            {
                "attempt_id": "attempt-1",
                "mode": "execute",
                "status": "in_progress",
            },
            {
                "attempt_id": "attempt-1",
                "mode": "execute",
                "status": "recovered",
            },
            {"mode": "dry-run", "status": "dry_run"},
        ],
    )

    metrics = calculate_recovery_metrics(audit)

    assert metrics["audit_entries"] == 3
    assert metrics["dry_run_operations"] == 1
    assert metrics["live_attempts"] == 1
    assert metrics["eligible_attempts"] == 1
    assert metrics["verified_successes"] == 1
    assert metrics["failed_attempts"] == 0
    assert metrics["unresolved_attempts"] == 0
    assert metrics["recovery_rate_percent"] == 100.0


def test_unresolved_attempt_is_not_counted_as_success_or_failure(tmp_path):
    audit = tmp_path / "audit.jsonl"
    write_records(
        audit,
        [
            {
                "attempt_id": "attempt-open",
                "mode": "execute",
                "status": "in_progress",
            }
        ],
    )

    metrics = calculate_recovery_metrics(audit)

    assert metrics["live_attempts"] == 1
    assert metrics["eligible_attempts"] == 0
    assert metrics["unresolved_attempts"] == 1
    assert metrics["recovery_rate_percent"] is None


def test_completed_failure_counts_in_denominator(tmp_path):
    audit = tmp_path / "audit.jsonl"
    write_records(
        audit,
        [
            {
                "attempt_id": "attempt-fail",
                "mode": "execute",
                "status": "in_progress",
            },
            {
                "attempt_id": "attempt-fail",
                "mode": "execute",
                "status": "verification_failed",
            },
        ],
    )

    metrics = calculate_recovery_metrics(audit)

    assert metrics["live_attempts"] == 1
    assert metrics["eligible_attempts"] == 1
    assert metrics["failed_attempts"] == 1
    assert metrics["recovery_rate_percent"] == 0.0


def test_legacy_records_without_attempt_id_remain_supported(tmp_path):
    audit = tmp_path / "audit.jsonl"
    write_records(
        audit,
        [
            {"mode": "execute", "status": "recovered"},
            {"mode": "execute", "status": "failed"},
        ],
    )

    metrics = calculate_recovery_metrics(audit)

    assert metrics["live_attempts"] == 2
    assert metrics["eligible_attempts"] == 2
    assert metrics["verified_successes"] == 1
    assert metrics["failed_attempts"] == 1
    assert metrics["recovery_rate_percent"] == 50.0


def test_malformed_json_raises_clear_error(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text('{"mode":"execute"}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        calculate_recovery_metrics(audit)


def test_non_object_json_raises_clear_error(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text('[]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="not an object"):
        calculate_recovery_metrics(audit)


def test_missing_audit_file_returns_unmeasured_metrics(tmp_path):
    metrics = calculate_recovery_metrics(tmp_path / "missing.jsonl")

    assert metrics["audit_entries"] == 0
    assert metrics["eligible_attempts"] == 0
    assert metrics["unresolved_attempts"] == 0
    assert metrics["recovery_rate_percent"] is None
    assert metrics["status"] == "not_yet_measured"
