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

    # New records are correlated by attempt_id. For each ID, the latest
    # record is the current state; in_progress remains unresolved.
    correlated = {}
    legacy = []

    for index, record in enumerate(records):
        if str(record.get("mode", "")).lower() != "execute":
            continue

        attempt_id = record.get("attempt_id")
        if isinstance(attempt_id, str) and attempt_id.strip():
            correlated[attempt_id] = record
        elif record.get("status") != "in_progress":
            # Legacy records have no stable correlation key. Retain their
            # previous per-record behavior rather than guessing a pairing.
            legacy.append(record)
        else:
            # An uncorrelated intent is unresolved; do not discard it.
            legacy.append(record)

    outcomes = list(correlated.values()) + legacy

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
