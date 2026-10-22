# AI-Powered Self-Healing DevOps Platform

A monitoring and anomaly-detection prototype for a three-service application. It collects or consumes service telemetry, validates metrics data, identifies unusual behavior with per-service Isolation Forest models, and generates recovery recommendations for operator review.

> **Safety boundary:** the documented anomaly/recommendation pipeline is advisory-only. The local dashboard is read-only. Do not treat a model flag as a confirmed incident, and do not enable automated recovery without a separately reviewed authorization and safety procedure.

## Project components

- **Microservices:** User, Order, and Payment services implemented with Python/FastAPI.
- **Telemetry:** Prometheus metrics collection and query configuration.
- **Anomaly detection:** dataset validation and per-service scikit-learn Isolation Forest models.
- **Decision engine:** evaluates anomaly reports and writes advisory recommendations.
- **Recovery controller and audit metrics:** guarded components for recording/evaluating recovery-related state; live execution must remain disabled unless explicitly authorized and reviewed.
- **Dashboard:** local, read-only FastAPI dashboard for service health, metrics, anomaly summaries, pipeline information, and recovery audit data.
- **Deployment and observability:** Kubernetes manifests plus Grafana/Prometheus configuration.
- **Tests:** regression coverage for services, data collection/validation, dashboard/pipeline behavior, decision logic, and recovery safety.

## Architecture and workflow

1. Collect service metrics from Prometheus or prepare a metrics CSV dataset.
2. Validate the dataset before scoring.
3. Run anomaly detection to produce an anomaly-report CSV and model artifacts.
4. Pass the anomaly report to the decision engine.
5. Review the generated recommendations and supporting telemetry.
6. Use the dashboard and audit log to inspect current service status and prior recovery-related events.

An anomaly prediction is a signal for investigation, not proof of an outage. Recommendation quality depends on the input data, metric definitions, model, and configured thresholds.

## Repository layout

| Path | Purpose |
|---|---|
| `services/` | User, Order, and Payment service code and container definitions |
| `ml/` | Metrics collection, dataset validation, anomaly detection, and model artifacts |
| `pipeline/` | Pipeline orchestration |
| `recovery/` | Decision engine, guarded controller, and recovery metrics |
| `dashboard/` | Read-only dashboard application, static UI, and launcher |
| `k8s/`, `kubernetes/` | Kubernetes service/workload and recovery-test manifests |
| `monitoring/` | Prometheus and Grafana configuration |
| `data/` | Example metrics datasets and generated reports/recommendations |
| `logs/` | Local logs and recovery audit records |
| `tests/` | Automated regression tests |
| `scripts/` | Advisory pipeline and supporting utilities |

## Requirements

- Python 3
- Python dependencies used by the project components, including FastAPI/Uvicorn for the dashboard and pandas, scikit-learn, and joblib for the ML pipeline
- Optional infrastructure for deployment/observability: Docker, Kubernetes, Prometheus, and Grafana

Use a project-specific virtual environment and install the dependencies appropriate to the components you intend to run. Do not commit virtual environments, credentials, or machine-specific configuration.

## Run the advisory anomaly pipeline

Run from the repository root in a Python environment with the ML dependencies installed. Choose **new output paths** for each run; the runner refuses to overwrite existing report/recommendation files or use a non-empty model directory.

Example for PowerShell:

```powershell
python .\scripts\run_advisory_pipeline.py `
  --dataset .\data\metrics_dataset_v2.csv `
  --model-dir .\ml\models_local_run `
  --report .\data\anomaly_report_local_run.csv `
  --recommendations .\data\recommendations_local_run.csv
```

The pipeline runs `ml/detect_anomalies_v2.py` and then `recovery/decision_engine.py`. It writes the anomaly report and advisory recommendations to the specified paths. **It does not execute recovery actions.**

The runner checks that input/output paths do not collide, the input dataset exists, output files do not already exist, and the model directory is absent or empty. Preserve previous reports and model artifacts rather than overwriting them.

## Run the local dashboard

The dashboard is intended for local, read-only use. It does not change Kubernetes resources, run `kubectl`, or expose recovery controls.

From PowerShell at the repository root, with `.venv` containing FastAPI and Uvicorn:

```powershell
.\dashboard\START-DASHBOARD.ps1
```

Open [http://127.0.0.1:8088](http://127.0.0.1:8088). Press `Ctrl+C` in the terminal to stop it.

Default integrations in the launcher documentation:

- Prometheus: `http://localhost:30090`
- User service: `http://localhost:31478`
- Order service: `http://localhost:32040`
- Payment service: `http://localhost:30441`

Configure alternate endpoints with `PROMETHEUS_URL`, `USER_SERVICE_URL`, `ORDER_SERVICE_URL`, and `PAYMENT_SERVICE_URL` as needed. The dashboard may show “No data” if the configured PromQL metric names do not match the deployed instrumentation; verify the actual `/metrics` output before interpreting charts.

## Tests

Run the regression suite from the repository root in an environment with pytest and project dependencies installed:

```powershell
python -m pytest .\tests -q
```

The latest reported run in the active development folder completed with **92 passed and 1 Starlette/httpx deprecation warning**. Results can vary by environment; rerun the tests after changes. A passing test suite does not prove that live telemetry, Kubernetes deployment, or production recovery behavior has been validated.

## Safety and operational notes

- Keep recovery execution disabled by default; use dry-run/advisory behavior unless a separate authorization and safety review explicitly approves otherwise.
- Never commit recovery tokens, credentials, kubeconfig files, or other secrets.
- Validate Prometheus queries and metric semantics before using request rate, error ratio, or latency as decision features.
- Check audit schemas and recovery verification before reporting a recovery success rate. Historical audit entries may include dry runs, in-progress attempts, and unresolved attempts.
- Use synthetic or copied data for experiments where possible. Do not generate deliberate error traffic or trigger live recovery without approval.
- Treat model predictions and recommendations as decision support for a human operator, not as a substitute for incident investigation.

## Project status

This repository is a prototype for demonstrating telemetry collection, anomaly detection, advisory decision-making, and a guarded recovery architecture. Production readiness requires environment-specific deployment validation, security review, reliable metric instrumentation, and an explicitly tested recovery authorization/rollback process.
