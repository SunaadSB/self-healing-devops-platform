"""Run metrics -> anomaly detection -> recommendations -> optional recovery.

Recovery remains advisory-only unless explicitly enabled by the operator.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ML_PYTHON = ROOT / ".venv-ml" / "Scripts" / "python.exe"

COLLECTOR = ROOT / "ml" / "collect_dataset.py"
DETECTOR = ROOT / "ml" / "detect_anomalies_v2.py"
DECISION_ENGINE = ROOT / "recovery" / "decision_engine.py"
CONTROLLER = ROOT / "recovery" / "recovery_controller.py"

DATASET = ROOT / "data" / "metrics_dataset_v2.csv"
ANOMALY_REPORT = ROOT / "data" / "anomaly_report_v2.csv"
RECOMMENDATIONS = ROOT / "data" / "recovery_recommendations_v2.csv"
RUN_LOG = ROOT / "data" / "pipeline_runs.jsonl"

ALLOWED_SERVICES = {"user-service", "order-service", "payment-service"}


def _run_stage(name: str, command: Sequence[str], env: dict[str, str]) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    print(f"\n========== {name.upper()} ==========", flush=True)
    print("Command:", " ".join(str(part) for part in command), flush=True)
    try:
        completed = subprocess.run(
            list(command), cwd=ROOT, env=env, text=True,
            capture_output=True, check=False,
        )
        if completed.stdout:
            print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr,
                  end="" if completed.stderr.endswith("\n") else "\n")
        result = {
            "stage": name,
            "status": "success" if completed.returncode == 0 else "failed",
            "return_code": completed.returncode,
            "_stdout": completed.stdout or "",
            "_stderr": completed.stderr or "",
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if completed.returncode != 0:
            result["error"] = f"Process exited with code {completed.returncode}"
        return result
    except OSError as exc:
        return {
            "stage": name, "status": "failed", "return_code": None,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }


def _run_recovery(execute: bool, authorized: bool) -> list[dict]:
    """Send generated recommendations through the existing guarded controller."""
    if not execute:
        return []

    results = []
    try:
        with RECOMMENDATIONS.open("r", newline="", encoding="utf-8-sig") as stream:
            recommendations = list(csv.DictReader(stream))
    except (OSError, csv.Error) as exc:
        return [{
            "status": "failed",
            "reason": "recommendations_unreadable",
            "detail": str(exc),
        }]

    seen = set()
    for item in recommendations:
        service = (item.get("service") or "").strip()
        if service not in ALLOWED_SERVICES:
            continue
        if item.get("recommendation") != "review_recovery":
            continue

        # Never execute twice for the same service in one pipeline run.
        if service in seen:
            continue
        seen.add(service)

        command = [
            str(VENV_PYTHON), str(CONTROLLER),
            "--service", service,
            "--execute",
        ]
        if authorized:
            command.append("--authorize")

        result = _run_stage(f"recovery:{service}", command, os.environ.copy())
        record = {"service": service, **result}
        if result["status"] == "success":
            try:
                record["controller_result"] = json.loads(
                    # Controller CLI emits its result as JSON on stdout.
                    _last_json_line(result.get("_stdout", ""))
                )
            except (ValueError, json.JSONDecodeError):
                pass
        results.append(record)

    return results


def _last_json_line(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            return line
    raise ValueError("No JSON object in controller output")


def run_pipeline(
    *,
    collect: bool = True,
    env_overrides: dict[str, str] | None = None,
    execute_recovery: bool = False,
    authorized: bool = False,
) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    started_at = datetime.now(timezone.utc).isoformat()
    stages: list[dict] = []

    env = os.environ.copy()
    pythonpath_parts = [str(ROOT)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env.update({
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": os.pathsep.join(pythonpath_parts),
        "DATASET_PATH": str(DATASET),
        "MODEL_DIR_PATH": str(ROOT / "ml" / "models"),
        "REPORT_PATH": str(ANOMALY_REPORT),
    })
    if env_overrides:
        env.update(env_overrides)

    if collect:
        stages.append(_run_stage("collect", [str(VENV_PYTHON), str(COLLECTOR), "--once"], env))
        if stages[-1]["status"] != "success":
            return _finish(run_id, started_at, stages)

    stages.append(_run_stage("detect", [str(ML_PYTHON), str(DETECTOR)], env))
    if stages[-1]["status"] != "success":
        return _finish(run_id, started_at, stages)

    stages.append(_run_stage(
        "recommend",
        [str(VENV_PYTHON), str(DECISION_ENGINE),
         "--input", str(ANOMALY_REPORT), "--output", str(RECOMMENDATIONS)],
        env,
    ))
    if stages[-1]["status"] != "success":
        return _finish(run_id, started_at, stages)

    recovery_results = _run_recovery(execute_recovery, authorized)
    stages.append({
        "stage": "_recovery_metadata",
        "status": "success",
        "recovery_results": recovery_results,
        "execute_recovery": execute_recovery,
    })
    return _finish(run_id, started_at, stages)


def _finish(
    run_id: str,
    started_at: str,
    stages: list[dict],
    execute_recovery: bool = False,
    recovery_results: list[dict] | None = None,
) -> dict:
    metadata = next(
        (s for s in stages if s.get("stage") == "_recovery_metadata"),
        {},
    )
    stages = [s for s in stages if s.get("stage") != "_recovery_metadata"]
    results = recovery_results if recovery_results is not None else metadata.get("recovery_results", [])
    execute_recovery = execute_recovery or bool(metadata.get("execute_recovery", False))
    result = {
        "run_id": run_id,
        "status": "success" if all(s["status"] == "success" for s in stages) else "failed",
        "mode": "automatic" if execute_recovery else "advisory_only",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "stages": stages,
        "artifacts": {
            "dataset": str(DATASET),
            "anomaly_report": str(ANOMALY_REPORT),
            "recommendations": str(RECOMMENDATIONS),
        },
        "recovery_actions_executed": sum(
            1 for item in results
            if item.get("controller_result", {}).get("status") == "recovered"
        ),
        "recovery_results": results,
    }
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result) + "\n")
    print("\n========== PIPELINE SUMMARY ==========")
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-collection", action="store_true")
    parser.add_argument(
        "--execute-recovery", action="store_true",
        help="Request recovery execution; controller authorization is still required.",
    )
    parser.add_argument(
        "--authorize-recovery", action="store_true",
        help="Explicitly authorize controller actions for this run.",
    )
    args = parser.parse_args()

    if args.authorize_recovery and not args.execute_recovery:
        parser.error("--authorize-recovery requires --execute-recovery")

    for interpreter in (VENV_PYTHON, ML_PYTHON):
        if not interpreter.is_file():
            print(f"Required Python interpreter not found: {interpreter}", file=sys.stderr)
            return 2

    result = run_pipeline(
        collect=not args.skip_collection,
        execute_recovery=args.execute_recovery,
        authorized=args.authorize_recovery,
    )
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())




