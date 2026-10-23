# AI-Powered Self-Healing DevOps Platform

A machine-learning-focused observability project that explores how service telemetry can be transformed into anomaly signals and actionable operator guidance. The core ML workflow validates metrics data, applies **scikit-learn Isolation Forest** anomaly detection, produces a structured anomaly report, and passes the results to a recommendation layer.

The example application contains three services—**User**, **Order**, and **Payment**—with Prometheus-oriented observability, a Python data/ML pipeline, an advisory decision engine, guarded recovery components, and a local dashboard. The project is relevant to roles involving **machine learning engineering, applied ML, anomaly detection, data preprocessing, and ML-enabled operations**.

> [!IMPORTANT]
> **Safety boundary:** the documented pipeline is advisory-only and the dashboard is read-only. An anomaly prediction is not a confirmed incident, and a recommendation is not proof that an action is safe. Keep live recovery execution disabled unless a separate authorization, testing, rollback, and operational-review process explicitly approves it.

## Contents

- [Goals](#goals)
- [Features](#features)
- [Architecture](#architecture)
- [Machine learning approach](#machine-learning-approach)
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

1. Build an end-to-end applied ML workflow around service telemetry and operational metrics.
2. Validate and prepare metrics data before model inference.
3. Apply Isolation Forest models to identify observations that differ from learned metric patterns.
4. Convert model output into a structured anomaly report that can be reviewed and consumed downstream.
5. Connect ML outputs to a decision-support layer without confusing predictions with verified incidents.
6. Present model and service context through a dashboard and retain a guarded, auditable recovery boundary.

## Features

- **Microservices:** User, Order, and Payment services built with Python/FastAPI.
- **Metrics and monitoring:** Prometheus-oriented metrics collection and query configuration.
- **ML data pipeline:** metrics dataset validation and preparation before scoring.
- **Unsupervised anomaly detection:** per-service scikit-learn Isolation Forest workflow for identifying unusual metric patterns without requiring incident labels at inference time.
- **Structured model outputs:** anomaly-report CSV and saved model artifacts for downstream inspection.
- **ML-to-decision integration:** transforms anomaly-report records into recommendations for human review.
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

## Machine learning approach

The machine-learning component is the analytical core of the project. It uses operational metrics as input and produces anomaly signals that can be inspected by downstream decision logic and a human operator.

### Problem framing

Service telemetry is time-varying and can exhibit unusual combinations of metric values before or during a service degradation. In a practical monitoring environment, labeled examples of every possible incident may be limited. This project therefore demonstrates an **unsupervised anomaly-detection** approach rather than claiming to be a supervised incident classifier.

### Model: Isolation Forest

The detector uses the Isolation Forest algorithm available in scikit-learn. Isolation Forest identifies observations that are easier to isolate from the rest of the data and can be used to flag unusual metric patterns.

At a high level, the workflow is:

1. Load the selected metrics dataset.
2. Validate the input and prepare the metric records for scoring.
3. Apply the configured feature selection and service grouping used by the detector.
4. Fit or use the Isolation Forest model according to the implementation and run configuration.
5. Generate anomaly predictions/scores and write the resulting report.
6. Pass report records to the advisory decision engine.

The exact feature columns, estimator parameters, contamination setting, and artifact format should be taken from the current implementation and configuration; they are not fixed by this overview. The repository does not claim a particular precision, recall, F1 score, or production detection rate without a labeled evaluation.

### ML pipeline stages

| Stage | Purpose | Result |
|---|---|---|
| Data ingestion | Load the selected metrics CSV or prepared telemetry dataset | Input records |
| Data validation | Check input availability and suitability for processing | Validated/prepared data or an actionable failure |
| Feature preparation | Select and organize the metric fields used by the detector | Model-ready feature data |
| Anomaly detection | Apply the configured Isolation Forest workflow | Anomaly labels/scores as supported by the implementation |
| Report generation | Persist the detector output | Anomaly-report CSV and model artifacts |
| Decision support | Interpret report entries using downstream rules | Advisory recommendations |
| Human review | Check metric context and service behavior | Operator decision; not automatic proof of an incident |

### Data and evaluation considerations

- **Feature quality matters:** metric names, units, missing values, service labels, and sampling intervals affect the usefulness of model output.
- **Service context matters:** different services can have different traffic and latency baselines, so grouping and feature choices should be reviewed rather than assumed interchangeable.
- **Anomaly flags are not labels:** an unusual observation may be benign, and an incident may not always appear as a statistical outlier.
- **Evaluation needs ground truth:** to measure precision, recall, F1, false-positive rate, or detection delay, build or obtain a labeled validation dataset and document the evaluation protocol.
- **Reproducibility matters:** record the dataset version, feature set, model parameters, and output artifact paths for each experiment.
- **No performance claims are implied:** this README does not assert benchmark scores or production readiness without measured evidence.

### Skills demonstrated

This project can be discussed as experience with Python-based data/ML workflows, metrics data validation, unsupervised anomaly detection, scikit-learn, model artifact handling, structured inference outputs, pipeline integration, and communicating model signals to a downstream application. Be prepared to explain the actual implementation choices and their limitations in an interview.

## End-to-end workflow

1. **Collect telemetry or load a dataset.** Obtain metrics from configured services/monitoring or a prepared CSV file.
2. **Validate and prepare data.** Check the input and prepare the metric records for model processing.
3. **Run the ML detector.** Apply the configured Isolation Forest workflow to the selected features and service groupings.
4. **Persist model outputs.** Write an anomaly report and model artifacts to the selected paths.
5. **Generate recommendations.** The decision engine consumes the report and writes advisory recommendations.
6. **Review model signals.** An operator checks the metric context and service behavior before deciding whether a flag is meaningful.
7. **Inspect dashboard and audit information.** Use the dashboard to review available telemetry and recovery-related records.
8. **Keep actions separately authorized.** A model prediction or recommendation is not equivalent to an executed or successful recovery action.

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
