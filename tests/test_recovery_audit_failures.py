from recovery import recovery_controller as controller


def test_audit_intent_failure_prevents_kubectl(monkeypatch, tmp_path):
    def fail_audit(*args, **kwargs):
        raise OSError("simulated disk error")

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("kubectl must not run if intent audit fails")

    monkeypatch.setattr(controller, "write_audit", fail_audit)

    result = controller.recover(
        "order-service", execute=True, authorized=True,
        audit_path=tmp_path / "audit.jsonl", runner=forbidden_runner,
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "audit_unavailable_before_action"



def test_final_audit_failure_is_reported_without_claiming_success(
    monkeypatch, tmp_path
):
    import json

    writes = []

    def fail_final_audit(path, record):
        writes.append(record.copy())
        if len(writes) == 2:
            raise OSError("simulated disk full")

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

    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)

        if command[1] == "get":
            return Result(json.dumps(deployment))

        return Result("deployment successfully rolled out")

    monkeypatch.setattr(controller, "write_audit", fail_final_audit)

    result = controller.recover(
        "order-service",
        execute=True,
        authorized=True,
        audit_path=tmp_path / "audit.jsonl",
        runner=fake_runner,
    )

    assert writes[0]["status"] == "in_progress"
    assert len(calls) == 3
    assert result["status"] == "audit_failed_after_action"
    assert result["reason"] == "final_audit_write_failed"
    assert result["operation_status"] == "recovered"
