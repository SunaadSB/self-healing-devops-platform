"""Calculate recovery effectiveness from the recovery audit log."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_LOG = ROOT / "logs" / "recovery_audit.jsonl"

SUCCESS_STATUSES = {"recovered"}
FAILURE_STATUSES = {
    "failed",
    "verification_failed",
    "audit_failed_after_action",
}


def calculate_recovery_metrics(audit_path=DEFAULT_AUDIT_LOG):
    """Calculate outcomes without counting dry runs or double-counting attempts."""
    path = Path(audit_path)
    records = []

    if path.exists():
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid audit JSON on line {line_number}"
                    ) from exc

                if not isinstance(record, dict):
                    raise ValueError(
                        f"Audit entry on line {line_number} is not an object"
                    )
                records.append(record)

    dry_runs = sum(
        1 for record in records
        if str(record.get("mode", "")).lower() in {"dry-run", "dry_run"}
        or record.get("status") == "dry_run"
    )

    # Correlate modern records by attempt_id, retaining the latest state.
    correlated = {}
    legacy = []

    for index, record in enumerate(records):
        if str(record.get("mode", "")).lower() != "execute":
            continue

        attempt_id = record.get("attempt_id")
        if isinstance(attempt_id, str) and attempt_id.strip():
            correlated[attempt_id] = record
        else:
            legacy.append((index, record))

    # Legacy records have no attempt ID. Pair a start only with a later
    # terminal record for the same service/action/namespace within 10 minutes.
    consumed = set()
    legacy_outcomes = []

    for start_pos, (start_index, start) in enumerate(legacy):
        if start.get("status") != "in_progress":
            continue

        start_time = start.get("timestamp") or start.get("started_at")
        try:
            from datetime import datetime
            start_dt = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            start_dt = None

        if start_dt is None:
            continue

        identity = (
            start.get("service"),
            start.get("action"),
            start.get("namespace"),
        )

        for end_index, end in legacy:
            if end_index <= start_index or end_index in consumed:
                continue
            if end.get("status") not in SUCCESS_STATUSES | FAILURE_STATUSES:
                continue
            if (
                end.get("service"),
                end.get("action"),
                end.get("namespace"),
            ) != identity:
                continue

            end_time = end.get("timestamp") or end.get("completed_at")
            try:
                end_dt = datetime.fromisoformat(str(end_time).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue

            # Normalize naive timestamps to UTC only for comparison.
            from datetime import timezone
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)

            elapsed = (end_dt - start_dt).total_seconds()
            if 0 <= elapsed <= 600:
                consumed.add(start_index)
                consumed.add(end_index)
                legacy_outcomes.append(end)
                break

    for index, record in legacy:
        if index in consumed:
            continue
        if record.get("status") != "in_progress":
            legacy_outcomes.append(record)
        else:
            legacy_outcomes.append(record)

    outcomes = list(correlated.values()) + legacy_outcomes

    successes = sum(
        1 for record in outcomes
        if record.get("status") in SUCCESS_STATUSES
    )
    failures = sum(
        1 for record in outcomes
        if record.get("status") in FAILURE_STATUSES
    )
    unresolved = sum(
        1 for record in outcomes
        if record.get("status") == "in_progress"
    )

    eligible = successes + failures
    rate = round(100.0 * successes / eligible, 2) if eligible else None

    return {
        "audit_entries": len(records),
        "dry_run_operations": dry_runs,
        "live_attempts": len(outcomes),
        "eligible_attempts": eligible,
        "verified_successes": successes,
        "failed_attempts": failures,
        "unresolved_attempts": unresolved,
        "recovery_rate_percent": rate,
        "status": "measured" if eligible else "not_yet_measured",
    }
