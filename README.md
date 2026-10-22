# AI-Powered Self-Healing DevOps Platform

A guarded DevOps prototype that collects service metrics, detects anomalous behavior, and produces **advisory-only** recovery recommendations. The recommendation pipeline does not execute recovery actions.

## Services

- User Service
- Order Service
- Payment Service

## Architecture

- Python and FastAPI service components
- Docker and Kubernetes deployment environment
- Prometheus metrics and Grafana dashboards
- Per-service scikit-learn Isolation Forest anomaly detection
- Recommendation engine and guarded recovery controller

## Current workflow

1. Collect or prepare a metrics CSV dataset.
2. Validate the dataset before model training or scoring.
3. Run anomaly detection to produce an anomaly-report CSV and model artifacts.
4. Feed the anomaly report to the decision engine.
5. Review the recommendation CSV; no automated recovery is performed by this pipeline.

### Run the advisory pipeline

Use an isolated model directory and new output filenames. The runner refuses to overwrite existing report/recommendation files, refuses to use a non-empty model directory, and rejects path collisions.

```powershell
.\.venv-ml\Scripts\python.exe .\scripts\run_advisory_pipeline.py `
  --dataset .\data\metrics_dataset_v2.csv `
  --model-dir .\ml\models_stage6_run `
  --report .\data\anomaly_report_stage6_run.csv `
  --recommendations .\data\recommendations_stage6_run.csv
```

Use paths that do not already exist for the report and recommendations. The model directory must be empty or absent. The ML environment needs the project's installed dependencies, including pandas, scikit-learn, and joblib.

### Decision-engine behavior

- Only `user-service`, `order-service`, and `payment-service` are considered.
- A recommendation requires three consecutive anomaly records for a service, with no gap greater than 90 seconds.
- A ten-minute cooldown limits repeat recommendations per service.
- Output status is `advisory_only`; the engine does not call `kubectl` or restart services.

## Safety

- The end-to-end pipeline is advisory-only.
- Do not enable live recovery without a separate, reviewed authorization and safety procedure.
- Use fresh output paths and retain existing datasets, models, and reports as evidence.
- Test against synthetic or copied data before using newly collected production-like telemetry.

## Tests

Run the regression suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests -q
```

The suite includes service, metrics-collection, dataset-validation, decision-engine, and recovery-safety tests. The advisory-pipeline regression test verifies that an anomaly report is passed to the decision engine and produces an advisory recommendation without invoking recovery.

## Known telemetry limitation

The current checked-in `metrics_dataset_v2.csv` snapshot was previously observed with `error_ratio` equal to zero in every row. This does not by itself establish whether the cause is instrumentation, Prometheus query configuration, or the absence of error responses. Verify the metrics query and telemetry source before using error ratio as a meaningful anomaly feature. No deliberate error traffic should be generated without explicit approval.

## Validation status

Record test results and telemetry findings with the date and environment in which they were verified. A successful test suite does not establish that live Prometheus instrumentation or Kubernetes recovery behavior has been validated.
