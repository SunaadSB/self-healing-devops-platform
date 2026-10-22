"""Guarded Kubernetes recovery controller. Dry-run is the default."""

import argparse
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

NAMESPACE = "ai-self-healing"
ALLOWED_SERVICES = {
    "user-service",
    "order-service",
    "payment-service",
    "recovery-test",
}

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_LOG = ROOT / "logs" / "recovery_audit.jsonl"


def utc_now():
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def write_audit(path, record):
    """Append an audit record and flush it to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def verify_deployment_readiness(
    service,
    kubectl="kubectl",
    runner=subprocess.run,
):
    """Verify deployment generation and desired replica readiness."""
    command = [
        kubectl,
        "get",
        "deployment/" + service,
        "-n",
        NAMESPACE,
        "-o",
        "json",
    ]

    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "deployment_query_failed", str(exc)[:1000]

    if result.returncode != 0:
        detail = result.stderr or result.stdout or "kubectl get failed"
        return False, "deployment_query_failed", detail[:1000]

    try:
        deployment = json.loads(result.stdout)

        metadata = deployment["metadata"]
        spec = deployment["spec"]
        status = deployment["status"]

        generation = metadata["generation"]
        desired = spec["replicas"]
        observed = status["observedGeneration"]
        updated = status["updatedReplicas"]
        ready = status["readyReplicas"]
        available = status["availableReplicas"]

        values = (
            generation,
            desired,
            observed,
            updated,
            ready,
            available,
        )

        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError(
                "Generations and replica counts must be "
                "non-negative integers"
            )

    except (ValueError, TypeError, KeyError) as exc:
        return (
            False,
            "invalid_deployment_response",
            str(exc)[:1000],
        )

    if desired == 0:
        return (
            False,
            "zero_desired_replicas",
            "Deployment has zero desired replicas",
        )

    if observed < generation:
        return (
            False,
            "generation_not_observed",
            (
                f"Observed generation {observed} is behind "
                f"metadata generation {generation}"
            ),
        )

    if updated != desired or ready != desired or available != desired:
        return (
            False,
            "replicas_not_ready",
            (
                f"desired={desired}, updated={updated}, "
                f"ready={ready}, available={available}"
            ),
        )

    return (
        True,
        "deployment_ready",
        "Deployment generation and replica counts verified",
    )


def recover(
    service,
    execute=False,
    authorized=False,
    audit_path=DEFAULT_AUDIT_LOG,
    kubectl="kubectl",
    runner=subprocess.run,
):
    """Perform a dry-run or an explicitly authorized recovery."""
    started_at = utc_now()
    record = {
        "timestamp": started_at,
        "started_at": started_at,
        "service": service,
        "namespace": NAMESPACE,
        "action": "rollout_restart",
        "mode": "execute" if execute else "dry-run",
        "status": "rejected",
    }

    if service not in ALLOWED_SERVICES:
        record["reason"] = "service_not_allowlisted"

    elif execute and not authorized:
        record["reason"] = "explicit_authorization_required"

    elif not execute:
        record.update(
            status="dry_run",
            reason="no_cluster_changes_made",
        )

    else:
        # Each authorized live operation has one stable correlation ID.
        record["attempt_id"] = str(uuid.uuid4())

        # Persist intent before any potentially disruptive cluster command.
        intent = dict(record)
        intent.update(
            status="in_progress",
            reason="recovery_attempt_started",
        )

        try:
            write_audit(audit_path, intent)
        except OSError as exc:
            record.update(
                status="rejected",
                reason="audit_unavailable_before_action",
                detail=str(exc)[:1000],
            )
            return record

        try:
            restart = runner(
                [
                    kubectl,
                    "rollout",
                    "restart",
                    "deployment/" + service,
                    "-n",
                    NAMESPACE,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            if restart.returncode != 0:
                record.update(
                    status="failed",
                    reason="rollout_restart_failed",
                    detail=(restart.stderr or restart.stdout or "")[:1000],
                )

            else:
                verify = runner(
                    [
                        kubectl,
                        "rollout",
                        "status",
                        "deployment/" + service,
                        "-n",
                        NAMESPACE,
                        "--timeout=120s",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=130,
                    check=False,
                )

                if verify.returncode != 0:
                    record.update(
                        status="verification_failed",
                        reason="rollout_status_failed",
                        detail=(verify.stderr or verify.stdout or "")[:1000],
                    )

                else:
                    ready, reason, detail = verify_deployment_readiness(
                        service,
                        kubectl=kubectl,
                        runner=runner,
                    )

                    if ready:
                        record.update(
                            status="recovered",
                            reason="rollout_and_deployment_verified",
                            verification=detail,
                        )
                    else:
                        record.update(
                            status="verification_failed",
                            reason=reason,
                            detail=detail[:1000],
                        )

        except (OSError, subprocess.TimeoutExpired) as exc:
            record.update(
                status="failed",
                reason="kubectl_error",
                detail=str(exc)[:1000],
            )

        record["completed_at"] = utc_now()
        record["timestamp"] = record["completed_at"]

        try:
            write_audit(audit_path, record)
        except OSError as exc:
            # The action may already have changed the cluster.
            return {
                **record,
                "operation_status": record["status"],
                "status": "audit_failed_after_action",
                "reason": "final_audit_write_failed",
                "detail": str(exc)[:1000],
            }

        return record

    record["completed_at"] = utc_now()
    record["timestamp"] = record["completed_at"]

    try:
        write_audit(audit_path, record)
    except OSError as exc:
        record.update(
            status="audit_write_failed",
            reason="audit_record_could_not_be_written",
            detail=str(exc)[:1000],
        )

    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--service",
        required=True,
        choices=sorted(ALLOWED_SERVICES),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Permit a real deployment restart.",
    )
    parser.add_argument(
        "--authorize",
        action="store_true",
        help="Confirm operator authorization for this action.",
    )

    args = parser.parse_args()

    # Defense-in-depth prototype gate, not strong authentication.
    execution_enabled = (
        os.environ.get("RECOVERY_EXECUTION_ENABLED", "").strip().lower()
        == "true"
    )

    authorized = (
        execution_enabled
        and args.authorize
        and os.environ.get("RECOVERY_AUTH_TOKEN", "").strip() != ""
    )

    result = recover(
        args.service,
        execute=args.execute,
        authorized=authorized,
    )

    print(json.dumps(result, indent=2))

    if result["status"] in {
        "rejected",
        "failed",
        "verification_failed",
        "audit_write_failed",
        "audit_failed_after_action",
    }:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
