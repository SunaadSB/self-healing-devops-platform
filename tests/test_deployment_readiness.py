import json
import subprocess

from recovery.recovery_controller import verify_deployment_readiness


def make_deployment(
    generation=2,
    observed_generation=2,
    desired=1,
    updated=1,
    ready=1,
    available=1,
):
    return {
        "metadata": {"generation": generation},
        "spec": {"replicas": desired},
        "status": {
            "observedGeneration": observed_generation,
            "updatedReplicas": updated,
            "readyReplicas": ready,
            "availableReplicas": available,
        },
    }


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_runner_for(result):
    def runner(command, **kwargs):
        assert command[1] == "get"
        assert command[2] == "deployment/order-service"
        assert "-n" in command
        assert "ai-self-healing" in command
        assert "-o" in command
        assert "json" in command
        return result

    return runner


def test_healthy_deployment_is_ready():
    deployment = make_deployment()
    result = FakeResult(stdout=json.dumps(deployment))

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=fake_runner_for(result),
    )

    assert ready is True
    assert reason == "deployment_ready"
    assert "verified" in detail


def test_stale_observed_generation_is_rejected():
    deployment = make_deployment(
        generation=3,
        observed_generation=2,
    )
    result = FakeResult(stdout=json.dumps(deployment))

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=fake_runner_for(result),
    )

    assert ready is False
    assert reason == "generation_not_observed"
    assert "behind" in detail


def test_replicas_not_all_ready_are_rejected():
    deployment = make_deployment(
        desired=3,
        updated=3,
        ready=2,
        available=2,
    )
    result = FakeResult(stdout=json.dumps(deployment))

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=fake_runner_for(result),
    )

    assert ready is False
    assert reason == "replicas_not_ready"
    assert "desired=3" in detail
    assert "ready=2" in detail


def test_malformed_json_is_rejected():
    result = FakeResult(stdout="{not valid json")

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=fake_runner_for(result),
    )

    assert ready is False
    assert reason == "invalid_deployment_response"
    assert detail


def test_missing_deployment_fields_are_rejected():
    result = FakeResult(
        stdout=json.dumps({"metadata": {}, "spec": {}, "status": {}})
    )

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=fake_runner_for(result),
    )

    assert ready is False
    assert reason == "invalid_deployment_response"
    assert detail


def test_zero_desired_replicas_are_rejected():
    deployment = make_deployment(
        desired=0,
        updated=0,
        ready=0,
        available=0,
    )
    result = FakeResult(stdout=json.dumps(deployment))

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=fake_runner_for(result),
    )

    assert ready is False
    assert reason == "zero_desired_replicas"
    assert "zero" in detail.lower()


def test_kubectl_nonzero_exit_is_rejected():
    result = FakeResult(
        returncode=1,
        stderr="simulated kubectl failure",
    )

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=fake_runner_for(result),
    )

    assert ready is False
    assert reason == "deployment_query_failed"
    assert "simulated kubectl failure" in detail


def test_kubectl_timeout_is_handled():
    def timeout_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 15)

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=timeout_runner,
    )

    assert ready is False
    assert reason == "deployment_query_failed"
    assert detail


def test_negative_replica_count_is_rejected():
    deployment = make_deployment(
        desired=1,
        updated=1,
        ready=-1,
        available=1,
    )
    result = FakeResult(stdout=json.dumps(deployment))

    ready, reason, detail = verify_deployment_readiness(
        "order-service",
        runner=fake_runner_for(result),
    )

    assert ready is False
    assert reason == "invalid_deployment_response"
    assert detail
