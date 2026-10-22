# AI-Powered Self-Healing DevOps Platform

A Python-based DevOps monitoring and anomaly-detection prototype designed to demonstrate how service telemetry can be used to identify unusual behavior, generate recovery recommendations, and give operators a single place to inspect service and recovery status.

The example application contains three services—**User**, **Order**, and **Payment**—with Prometheus-oriented observability, an ML-based anomaly detector, a recommendation engine, a guarded recovery layer, and a local dashboard.

> [!IMPORTANT]
> **Safety boundary:** the documented pipeline is advisory-only and the dashboard is read-only. An anomaly prediction is not a confirmed incident, and a recommendation is not proof that an action is safe. Keep live recovery execution disabled unless a separate authorization, testing, rollback, and operational-review process explicitly approves it.

## Contents

- [Goals](#goals)
- [Features](#features)
- [Architecture](#architecture)
- [End-to-end workflow](#end-to-end-workflow)
- [Repository structure](#repository-structure)
- [Requirements](#requirements)
- [Setup](#setup)
- [Run the advisory pipeline](#run-the-advisory-pipeline)
- [Run the dashboard](#run-the-dashboard)
- [Services and observability](#services-and-observability)
- [Testing](#testing)
- [Generated outputs](#generated-outputs)
- [Troubleshooting](#troubleshooting)
- [Security and safe operation](#security-and-safe-operation)
- [Limitations and future improvements](#limitations-and-future-improvements)
- [Project status](#project-status)

## Goals

1. Demonstrate a practical monitoring-to-diagnosis workflow for a small microservice application.
2. Validate service-metric data before using it for anomaly detection.
3. Use Isolation Forest models to flag observations that differ from learned metric patterns.
4. Convert anomaly reports into operator-facing recommendations.
5. expose service health, telemetry summaries, pipeline information, and recovery audit data through a local dashboard.
6. Establish a guarded recovery architecture where actions can be evaluated and audited without assuming that every recommendation should be executed automatically.

## Features

- **Microservices:** User, Order, and Payment services built with Python/FastAPI.
- **Metrics and monitoring:** Prometheus-oriented metrics collection and query configuration.
- **Input validation:** checks and preparation for metrics datasets before model scoring.
- **Anomaly detection:** per-service scikit-learn Isolation Forest workflow.
- **Advisory decision engine:** transforms anomaly-report records into recommendations for human review.
- **Guarded recovery components:** controller and recovery-metrics code for representing recovery-related state and audit information.
- **Read-only dashboard:** a local FastAPI application and static interface for inspecting health, metrics, anomaly summaries, pipeline state, and recovery records.
- **Deployment configuration:** Kubernetes manifests and monitoring configuration for a demonstration environment.
- **Regression tests:** tests for key service, pipeline, dashboard, decision, and recovery-safety behavior.

## Architecture

The main logical components are:

| Component | Responsibility | Output / boundary |
|---|---|---|
| User service | Example user-facing microservice | Service responses and available telemetry |
| Order service | Example order-processing microservice | Service responses and available telemetry |
| Payment service | Example payment-processing microservice | Service responses and available telemetry |
| Prometheus / monitoring configuration | Scrapes and queries configured metrics | Time-series telemetry, subject to correct instrumentation and configuration |
| Dataset validation and ML pipeline | Validates prepared metric records and scores observations | Anomaly report and model artifacts |
| Decision engine | Interprets anomaly report entries | Advisory recommendations for operator review |
| Recovery controller / metrics | Represents guarded recovery-related state and audit data | Auditable status; live action is not implied by a recommendation |
| Dashboard | Presents available service and pipeline information | Read-only operator view |

### Technology stack

- **Language:** Python
- **API / dashboard framework:** FastAPI
- **ASGI server:** Uvicorn
- **Data and ML:** pandas, scikit-learn, joblib
- **Testing:** pytest and the project’s API test utilities
- **Observability / deployment integrations:** Prometheus, Grafana, Docker, Kubernetes (where configured)

The exact components available at runtime depend on the environment and which optional infrastructure has been started.

## End-to-end workflow

1. **Collect or prepare telemetry.** Obtain metrics from the configured services/monitoring stack or use a prepared CSV dataset.
2. **Validate input data.** Check that the dataset is present and suitable for the pipeline before scoring it.
3. **Detect anomalies.** Run the anomaly detector against the configured metric features and service groupings.
4. **Write an anomaly report.** Store the detector output at the selected report path for inspection and downstream processing.
5. **Generate recommendations.** The decision engine reads the report and writes advisory recommendations.
6. **Review the evidence.** An operator checks the metrics, report rows, and service context rather than treating a model flag as a confirmed incident.
7. **Inspect dashboard and audit information.** Use the local dashboard to view the data available from configured integrations and recovery-related records.
8. **Authorize any real action separately.** This repository’s advisory example does not make recommendations equivalent to executed or successful recovery actions.

## Repository structure

| Path | Purpose |
|---|---|
| `services/` | User, Order, and Payment service code and container definitions |
| `ml/` | Metrics collection, dataset validation, anomaly detection, and model-related code |
| `pipeline/` | Pipeline orchestration components |
| `recovery/` | Decision engine, guarded controller, and recovery metrics |
| `dashboard/` | Read-only dashboard application, static UI, and launcher |
| `k8s/`, `kubernetes/` | Kubernetes workload/service and recovery-test manifests |
| `monitoring/` | Prometheus and Grafana configuration |
| `data/` | Example datasets and generated reports/recommendations |
| `logs/` | Local logs and recovery audit records, where generated |
| `tests/` | Automated regression tests |
| `scripts/` | Advisory pipeline and supporting utilities |

Generated files and local runtime state may differ between development machines. Check the actual contents of a directory before assuming every optional component or artifact is present.

## Requirements

### Core development requirements

- Python 3
- Project dependencies appropriate to the component being run, including FastAPI/Uvicorn for the dashboard and pandas, scikit-learn, and joblib for the ML pipeline
- pytest and the project test dependencies to run the test suite

### Optional infrastructure

- Docker, for container builds
- Kubernetes, for cluster deployment
- Prometheus, for scraping/querying telemetry
- Grafana, for metrics visualization

You can run the local pipeline and dashboard without treating every optional infrastructure integration as mandatory. Infrastructure-specific steps depend on the configuration in this repository and your local/cluster environment.

## Setup

Commands below use **PowerShell on Windows** and assume the terminal is at the repository root.

### 1. Open the repository

```powershell
Set-Location "E:\Projects\self-healing-devops-platform"
```

If you cloned the repository to another location, replace the path with your local checkout.

### 2. Create and activate a virtual environment

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation due to local execution policy, follow your organization’s approved policy for activating a local virtual environment; do not weaken machine-wide security settings just to run the project.

### 3. Install dependencies

Install the dependency set maintained by the repository, if a requirements file is present:

```powershell
if (Test-Path .\requirements.txt) {
    python -m pip install -r .\requirements.txt
} else {
    Write-Host "No root requirements.txt found; install the dependencies documented for the component you plan to run."
}
```

The dashboard needs FastAPI and Uvicorn. The ML pipeline needs the data/ML dependencies listed above. Install only the dependencies needed for the selected workflow if the repository does not provide one consolidated requirements file.

### 4. Verify Python and paths

```powershell
python --version
python -m pip --version
Test-Path .\scripts\run_advisory_pipeline.py
Test-Path .\dashboard\START-DASHBOARD.ps1
```

A missing script or launcher usually means the command is being run from the wrong checkout or the local branch has not been updated.

## Run the advisory pipeline

Run this from the repository root in a Python environment with the ML dependencies installed. Use **fresh output paths for each run**. The runner is designed to refuse unsafe path collisions, overwriting existing report/recommendation files, or writing into a non-empty model directory.

Example:

```powershell
python .\scripts\run_advisory_pipeline.py `
  --dataset .\data\metrics_dataset_v2.csv `
  --model-dir .\ml\models_local_run `
  --report .\data\anomaly_report_local_run.csv `
  --recommendations .\data\recommendations_local_run.csv
```

### What this command does

1. Uses the specified metrics dataset as input.
2. Runs the anomaly-detection stage in `ml/detect_anomalies_v2.py`.
3. Passes the anomaly report to `recovery/decision_engine.py`.
4. Writes the report, recommendations, and model artifacts to the selected output paths.

**This workflow generates recommendations; it does not execute recovery actions.**

### Output paths

- Dataset: `data/metrics_dataset_v2.csv`
- Model output directory: `ml/models_local_run/`
- Anomaly report: `data/anomaly_report_local_run.csv`
- Recommendations: `data/recommendations_local_run.csv`

These are example paths. If you run the pipeline again, choose new output paths or deliberately archive/remove prior outputs only after confirming they are not needed. Do not delete audit evidence merely to make a command pass.

### Interpreting results

- A flagged row is a model-generated anomaly signal, not a verified outage.
- A recommendation is a suggestion based on the input report and configured decision logic.
- Model quality depends on the training data, feature definitions, service grouping, data quality, and detector configuration.
- Missing or mismatched metric values can make results incomplete or misleading; validate the dataset and feature semantics before drawing conclusions.

## Run the dashboard

The dashboard is intended for local, read-only use. It presents available service, metric, anomaly, pipeline, and recovery-audit information. It is not a Kubernetes control plane and should not be treated as proof that a service has recovered.

### Start

With the dashboard dependencies installed, run:

```powershell
.\dashboard\START-DASHBOARD.ps1
```

Open [http://127.0.0.1:8088](http://127.0.0.1:8088). Keep the terminal open while using the dashboard. Press `Ctrl+C` in that terminal to stop the process.

### Default integration endpoints

The launcher/project configuration documents these local endpoints:

| Integration | Default URL |
|---|---|
| Dashboard | `http://127.0.0.1:8088` |
| Prometheus | `http://localhost:30090` |
| User service | `http://localhost:31478` |
| Order service | `http://localhost:32040` |
| Payment service | `http://localhost:30441` |

These are environment-specific defaults, not guarantees that the services are currently running or reachable. Check the local port-forwarding/deployment configuration if they do not respond.

### Configure endpoints

The dashboard supports these environment variables for endpoint configuration:

- `PROMETHEUS_URL`
- `USER_SERVICE_URL`
- `ORDER_SERVICE_URL`
- `PAYMENT_SERVICE_URL`

Set them to the actual reachable endpoints for your environment before launching the dashboard. Avoid embedding credentials or tokens in source files or committed configuration.

### Dashboard shows no data

The dashboard may display empty metrics if the configured PromQL queries do not match the metric names exported by the running services. Verify the actual service `/metrics` output and Prometheus target status before interpreting an empty chart as a service failure.

## Services and observability

### Microservices

The sample system separates responsibilities into User, Order, and Payment services. This structure is intended to demonstrate how a monitoring and diagnosis workflow can consider multiple services instead of relying on a single application process.

### Prometheus and Grafana

Prometheus and Grafana are optional infrastructure integrations for collecting and visualizing telemetry. To validate an environment:

1. Confirm that the services are running and reachable.
2. Confirm that Prometheus can reach each configured scrape target.
3. Inspect the metrics exposed by each service.
4. Compare the real metric names and labels with the PromQL queries used by dashboards and application code.
5. Check time ranges and query results before concluding that a service has no traffic or is unhealthy.

Do not infer that all targets are healthy merely because the dashboard process itself starts successfully.

### Kubernetes

The repository includes Kubernetes-related manifests under `k8s/` and `kubernetes/`. Review the selected manifests and namespace, image names, ports, probes, resource settings, and configuration before applying them to a cluster. Commands that modify a cluster should be run only against an environment you are authorized to administer.

## Testing

Run the regression suite from the repository root in an environment with pytest and the project dependencies installed:

```powershell
python -m pytest .\tests -q
```

The latest reported run in the active development folder completed with **92 passed and 1 Starlette/httpx deprecation warning**. That is a recorded development result, not a guarantee for every machine or future commit. Rerun the tests after changing code or dependencies.

A passing test suite does not by itself prove that:
- Prometheus is scraping the intended targets in a live environment;
- all Kubernetes manifests deploy successfully;
- anomaly detection is accurate for production traffic;
- the recovery controller can safely execute actions in a real cluster; or
- recovery success metrics reflect independently verified outcomes.

## Generated outputs

The pipeline can produce:

- **Anomaly report CSV:** detector output for downstream review.
- **Recommendation CSV:** advisory decision-engine output.
- **Model artifacts:** files written to the model output directory.
- **Logs/audit records:** local diagnostic or recovery-related state, depending on which components have been run.

Keep input datasets, model artifacts, reports, and audit logs distinguishable by run. Preserve relevant artifacts when investigating a result, and avoid committing large generated outputs, local logs, credentials, or machine-specific state unless they are intentionally part of a reviewed sample dataset.

## Troubleshooting

| Symptom | Checks |
|---|---|
| Python cannot find a script | Confirm the terminal is at the repository root and the path exists with `Test-Path`. |
| Dependency import error | Activate the intended virtual environment and install the dependencies for that component. |
| Pipeline refuses to run | Check that the dataset exists, output paths do not collide, report files do not already exist, and the model directory is absent or empty. Select fresh output paths rather than overwriting prior evidence. |
| Dashboard does not start | Check the Python environment, FastAPI/Uvicorn installation, launcher path, and whether port `8088` is already in use. |
| Dashboard opens but metrics are empty | Check endpoint variables, service reachability, Prometheus targets, metric names, labels, and PromQL queries. |
| Prometheus target is down | Check service availability, target address/port, cluster networking or port-forwarding, and scrape configuration. |
| Anomaly report looks unexpected | Inspect dataset quality, selected features, service labels, model configuration, and the rows flagged by the detector. A prediction alone is not proof of an incident. |
| Recovery audit is not all successful | Separate dry-run, in-progress, failed, unresolved, and independently verified outcomes before computing success rates. Do not count a recommendation as a completed recovery. |

## Security and safe operation

- Keep the recovery execution path disabled by default. Use advisory or dry-run behavior unless live actions have been separately approved.
- Do not commit API keys, recovery tokens, passwords, kubeconfig files, private keys, or other secrets.
- Do not expose the local dashboard publicly without authentication, authorization, network controls, and a security review.
- Verify Prometheus query semantics and metric units before using latency, request rate, or error ratio as decision features.
- Validate recovery audit schemas and distinguish recommendation, attempt, verification, and final outcome.
- Test rollback and failure handling in a non-production environment before considering any automated remediation.
- Use synthetic or copied data for experiments where possible. Do not generate deliberate error traffic or trigger live recovery without explicit authorization.
- Treat ML output as decision support for an operator, not as a substitute for incident investigation.

## Limitations and future improvements

This project is a demonstration prototype. Possible next steps include:

- improving dataset quality checks and feature documentation;
- evaluating anomaly detector precision/recall against labeled scenarios;
- adding model versioning and reproducible experiment metadata;
- adding explicit data freshness and metric-availability indicators to the dashboard;
- strengthening alert deduplication and recommendation explanations;
- expanding integration tests against a disposable Kubernetes environment;
- adding authenticated dashboard access and hardened secrets/configuration handling;
- formalizing recovery authorization, policy checks, health verification, rollback, and audit retention.

These are potential enhancements, not claims that every item is already implemented.

## Project status

The repository demonstrates a monitoring-to-anomaly-report-to-advisory-recommendation workflow, a read-only dashboard, and guarded recovery-related components. It should **not** be described as a production-ready autonomous remediation system.

Before production use, complete environment-specific deployment validation, security review, observability verification, model evaluation, and a formally approved and tested recovery authorization/rollback process.

## License and contributions

No license or contribution policy is asserted here. Add the appropriate license, contribution guidelines, and support/contact information if this repository is to be distributed or maintained collaboratively.
