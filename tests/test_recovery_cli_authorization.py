import json
import sys

import recovery.recovery_controller as controller


def test_cli_defaults_to_dry_run(monkeypatch, capsys):
    captured = {}

    def fake_recover(service, execute=False, authorized=False):
        captured.update(
            service=service,
            execute=execute,
            authorized=authorized,
        )
        return {"status": "dry_run"}

    monkeypatch.setattr(controller, "recover", fake_recover)
    monkeypatch.setattr(
        sys, "argv",
        ["recovery_controller", "--service", "order-service"],
    )
    monkeypatch.delenv("RECOVERY_AUTH_TOKEN", raising=False)

    controller.main()

    assert captured == {
        "service": "order-service",
        "execute": False,
        "authorized": False,
    }
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"


def test_cli_execute_without_authorization_is_not_authorized(
    monkeypatch, capsys
):
    captured = {}

    def fake_recover(service, execute=False, authorized=False):
        captured.update(
            service=service,
            execute=execute,
            authorized=authorized,
        )
        return {
            "status": "rejected",
            "reason": "explicit_authorization_required",
        }

    monkeypatch.setattr(controller, "recover", fake_recover)
    monkeypatch.setattr(
        sys, "argv",
        ["recovery_controller", "--service", "order-service", "--execute"],
    )
    monkeypatch.delenv("RECOVERY_AUTH_TOKEN", raising=False)

    try:
        controller.main()
    except SystemExit as exc:
        assert exc.code == 1

    assert captured == {
        "service": "order-service",
        "execute": True,
        "authorized": False,
    }
    assert json.loads(capsys.readouterr().out)["status"] == "rejected"


def test_cli_authorize_flag_without_token_is_not_authorized(
    monkeypatch, capsys
):
    captured = {}

    def fake_recover(service, execute=False, authorized=False):
        captured.update(
            service=service,
            execute=execute,
            authorized=authorized,
        )
        return {
            "status": "rejected",
            "reason": "explicit_authorization_required",
        }

    monkeypatch.setattr(controller, "recover", fake_recover)
    monkeypatch.setattr(
        sys, "argv",
        [
            "recovery_controller",
            "--service", "order-service",
            "--execute", "--authorize",
        ],
    )
    monkeypatch.delenv("RECOVERY_AUTH_TOKEN", raising=False)

    try:
        controller.main()
    except SystemExit as exc:
        assert exc.code == 1

    assert captured["execute"] is True
    assert captured["authorized"] is False
    assert json.loads(capsys.readouterr().out)["status"] == "rejected"
import json
import sys

import recovery.recovery_controller as controller


def test_cli_execution_kill_switch_overrides_flags_and_token(
    monkeypatch, capsys
):
    captured = {}

    def fake_recover(service, execute=False, authorized=False):
        captured.update(
            service=service,
            execute=execute,
            authorized=authorized,
        )
        return {
            "status": "rejected",
            "reason": "explicit_authorization_required",
        }

    monkeypatch.setattr(controller, "recover", fake_recover)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "recovery_controller",
            "--service", "order-service",
            "--execute", "--authorize",
        ],
    )
    monkeypatch.setenv("RECOVERY_AUTH_TOKEN", "test-only-placeholder")
    monkeypatch.delenv("RECOVERY_EXECUTION_ENABLED", raising=False)

    try:
        controller.main()
    except SystemExit as exc:
        assert exc.code == 1

    assert captured["execute"] is True
    assert captured["authorized"] is False
    assert json.loads(capsys.readouterr().out)["status"] == "rejected"
