from pipeline import run_pipeline as pipeline


def test_pipeline_stops_when_collection_fails(monkeypatch, tmp_path):
    calls = []

    def fake_stage(name, command, env):
        calls.append(name)
        return {"stage": name, "status": "failed", "return_code": 1}

    monkeypatch.setattr(pipeline, "_run_stage", fake_stage)
    monkeypatch.setattr(pipeline, "_finish", lambda run_id, started_at, stages: {
        "status": "failed", "stages": stages
    })

    result = pipeline.run_pipeline(collect=True)

    assert result["status"] == "failed"
    assert calls == ["collect"]


def test_pipeline_runs_all_stages_in_order_when_successful(monkeypatch):
    calls = []

    def fake_stage(name, command, env):
        calls.append(name)
        return {"stage": name, "status": "success", "return_code": 0}

    monkeypatch.setattr(pipeline, "_run_stage", fake_stage)
    monkeypatch.setattr(pipeline, "_finish", lambda run_id, started_at, stages: {
        "status": "success", "stages": stages
    })

    result = pipeline.run_pipeline(collect=True)

    assert result["status"] == "success"
    assert calls == ["collect", "detect", "recommend"]


def test_pipeline_can_skip_collection(monkeypatch):
    calls = []

    def fake_stage(name, command, env):
        calls.append(name)
        return {"stage": name, "status": "success", "return_code": 0}

    monkeypatch.setattr(pipeline, "_run_stage", fake_stage)
    monkeypatch.setattr(pipeline, "_finish", lambda run_id, started_at, stages: {
        "status": "success", "stages": stages
    })

    pipeline.run_pipeline(collect=False)

    assert calls == ["detect", "recommend"]


def test_authorized_recovery_uses_controller_authorize_flag(monkeypatch, tmp_path):
    import csv

    recommendations = tmp_path / "recommendations.csv"
    with recommendations.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["service", "recommendation"]
        )
        writer.writeheader()
        writer.writerow({
            "service": "user-service",
            "recommendation": "review_recovery",
        })

    monkeypatch.setattr(pipeline, "RECOMMENDATIONS", recommendations)

    captured = []

    def fake_stage(name, command, env):
        captured.append((name, command))
        return {
            "stage": name,
            "status": "success",
            "return_code": 0,
            "_stdout": '{"status": "dry_run"}',
        }

    monkeypatch.setattr(pipeline, "_run_stage", fake_stage)

    results = pipeline._run_recovery(execute=True, authorized=True)

    assert len(results) == 1
    assert captured[0][0] == "recovery:user-service"
    command = captured[0][1]
    assert "--authorize" in command
    assert "--authorized" not in command

def test_detector_uses_canonical_paths_despite_inherited_overrides(monkeypatch):
    captured = []

    monkeypatch.setenv(
        "REPORT_PATH",
        str(pipeline.ROOT / "data" / "anomaly_report_smoke_test.csv"),
    )
    monkeypatch.setenv(
        "MODEL_DIR_PATH",
        str(pipeline.ROOT / "ml" / "models_smoke_test"),
    )

    def fake_stage(name, command, env):
        captured.append((name, command, env.copy()))
        return {"stage": name, "status": "success", "return_code": 0}

    monkeypatch.setattr(pipeline, "_run_stage", fake_stage)
    monkeypatch.setattr(pipeline, "_run_recovery", lambda *args, **kwargs: [])

    result = pipeline.run_pipeline(collect=False)

    assert result["status"] == "success"

    detect = next(item for item in captured if item[0] == "detect")
    env = detect[2]

    assert env["REPORT_PATH"] == str(pipeline.ANOMALY_REPORT)
    assert env["MODEL_DIR_PATH"] == str(pipeline.ROOT / "ml" / "models")
    assert env["REPORT_PATH"] != str(
        pipeline.ROOT / "data" / "anomaly_report_smoke_test.csv"
    )
    assert env["MODEL_DIR_PATH"] != str(
        pipeline.ROOT / "ml" / "models_smoke_test"
    )

    recommend = next(item for item in captured if item[0] == "recommend")
    command = recommend[1]
    assert str(pipeline.ANOMALY_REPORT) in command
    assert str(pipeline.RECOMMENDATIONS) in command
