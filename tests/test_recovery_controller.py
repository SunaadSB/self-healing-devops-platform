import json
import subprocess

from recovery.recovery_controller import recover


def test_default_is_dry_run_and_does_not_call_kubectl(tmp_path):
    def forbidden_runner(*args, **kwargs):
        raise AssertionError("kubectl must not run in dry-run mode")

    audit = tmp_path / "audit.jsonl"
    result = recover("order-service", audit_path=audit, runner=forbidden_runner)

    assert result["status"] == "dry_run"
    assert json.loads(audit.read_text(encoding="utf-8"))["status"] == "dry_run"


def test_unknown_service_is_rejected(tmp_path):
    def forbidden_runner(*args, **kwargs):
        raise AssertionError("kubectl must not run for an unknown service")

    result = recover("kube-system", execute=True, authorized=True,
                     audit_path=tmp_path / "audit.jsonl", runner=forbidden_runner)

    assert result["status"] == "rejected"
    assert result["reason"] == "service_not_allowlisted"


def test_execute_without_authorization_is_rejected(tmp_path):
    def forbidden_runner(*args, **kwargs):
        raise AssertionError("kubectl must not run without authorization")

    result = recover("order-service", execute=True, authorized=False,
                     audit_path=tmp_path / "audit.jsonl", runner=forbidden_runner)

    assert result["status"] == "rejected"
    assert result["reason"] == "explicit_authorization_required"



def test_authorized_restart_and_verification(tmp_path):
    import json

    calls = []

    class Result:
        def __init__(self, stdout=""):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    deployment = {
        "metadata": {"generation": 2},
        "spec": {"replicas": 1},
        "status": {
            "observedGeneration": 2,
            "updatedReplicas": 1,
            "readyReplicas": 1,
            "availableReplicas": 1,
        },
    }

    def fake_runner(command, **kwargs):
        calls.append(command)

        if command[1] == "get":
            return Result(json.dumps(deployment))

        return Result("deployment successfully rolled out")

    result = recover(
        "order-service",
        execute=True,
        authorized=True,
        audit_path=tmp_path / "audit.jsonl",
        runner=fake_runner,
    )

    assert result["status"] == "recovered"
    assert result["reason"] == "rollout_and_deployment_verified"
    assert len(calls) == 3
    assert calls[0][1:3] == ["rollout", "restart"]
    assert calls[1][1:3] == ["rollout", "status"]
    assert calls[2][1] == "get"
    assert result["verification"] == (
        "Deployment generation and replica counts verified"
    )


def test_failed_restart_is_recorded(tmp_path):
    class Result:
        returncode = 1
        stdout = ""
        stderr = "permission denied"

    result = recover(
        "payment-service", execute=True, authorized=True,
        audit_path=tmp_path / "audit.jsonl",
        runner=lambda *args, **kwargs: Result(),
    )

    assert result["status"] == "failed"
    assert "permission denied" in result["detail"]
