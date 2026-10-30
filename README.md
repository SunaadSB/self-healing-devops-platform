# AI-Powered Self-Healing DevOps Platform

An AI-assisted DevOps monitoring and recovery prototype that combines microservices, Prometheus metrics, Isolation Forest anomaly detection, advisory decision-making, guarded recovery workflows, and a FastAPI dashboard.

The platform demonstrates an end-to-end workflow: collect service telemetry, prepare and validate metric data, detect unusual behavior, generate recommendations, and present operational context for human review.

> [!IMPORTANT]
> **Safety boundary:** anomaly predictions and recovery recommendations are decision-support signals, not confirmed incidents. The dashboard is read-only, and a recommendation must not be treated as proof that a recovery action was executed or succeeded. Live remediation must remain separately authorized, tested, and protected by health verification and rollback controls.

## Contents

- [Project overview](#project-overview)
- [Key features](#key-features)
- [Architecture](#architecture)
- [Machine learning and evaluation](#machine-learning-and-evaluation)
- [End-to-end workflow](#end-to-end-workflow)
- [Technology stack](#technology-stack)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Run the advisory pipeline](#run-the-advisory-pipeline)
- [Run the dashboard](#run-the-dashboard)
- [Monitoring and deployment](#monitoring-and-deployment)
- [Testing](#testing)
- [Safety and limitations](#safety-and-limitations)
- [Future enhancements](#future-enhancements)

## Project overview

The demonstration environment contains three Python/FastAPI microservices:

- **User Service**
- **Order Service**
- **Payment Service**

Prometheus-oriented instrumentation and configuration provide service telemetry. The ML pipeline validates metrics data and applies service-specific Isolation Forest models to identify unusual observations. Its outputs are consumed by an advisory decision layer and displayed through a local dashboard alongside pipeline and recovery-related information.

The goal is to demonstrate how machine learning can support operational awareness and recovery decision-making—not to claim a fully autonomous, production-ready remediation system.

## Key features

- **Microservice-based application:** separate User, Order, and Payment services.
- **Metrics collection and monitoring:** Prometheus-compatible metrics and Grafana provisioning/configuration.
- **Data validation and preparation:** checks and prepares metrics datasets for model processing.
- **Isolation Forest anomaly detection:** service-specific model artifacts and detector workflows, including V2 and V3 experiments.
- **Model evaluation:** scripts and reports for detector comparison, tuning, service-level results, and anomaly-type analysis.
- **Advisory decision engine:** converts anomaly-report records into recovery recommendations for review.
- **Guarded recovery components:** recovery controller, recovery metrics, and audit-oriented logic.
- **Operational dashboard:** FastAPI backend and static UI for service health, metrics, anomaly summaries, pipeline state, and recovery information.
- **Container and Kubernetes configuration:** Dockerfiles and Kubernetes manifests for a demonstration environment.
- **Automated tests:** regression coverage for services, data validation, pipeline, dashboard, deployment readiness, and recovery safety behavior.

## Architecture

```text
 User Service       Order Service       Payment Service
      |                  |                    |
      +------------------+--------------------+
                         |
                  Metrics / Telemetry
                         |
                    Prometheus
                         |
              Dataset Collection/Validation
                         |
                Feature Preparation
                         |
             Isolation Forest Detectors
                  (V2 / V3 experiments)
                         |
                 Anomaly Report
                         |
                Advisory Decision Engine
                         |
              Recovery Recommendations
                         |
              Guarded Recovery Controller
                         |
             Recovery State / Audit Metrics
                         |
                 FastAPI Dashboard
                  (Read-only view)
```

The exact runtime topology depends on which local services and optional infrastructure components have been started. The diagram describes the logical project workflow; it does not imply that every component is always running or that a recovery action is automatically executed.

## Machine learning and evaluation

### Detection approach

The project uses **scikit-learn Isolation Forest**, an unsupervised anomaly-detection algorithm. Metrics are validated and prepared before being passed to the configured detector. The detector produces anomaly labels and/or scores that are written to structured outputs and consumed by the advisory layer.

The repository includes multiple model experiments:

- **V2:** updated service-specific Isolation Forest models and tuning/evaluation utilities.
- **V3:** a separate detector/model experiment with evaluation scripts and result summaries.
- **V3 temporal:** training code and service-specific temporal model artifacts for further experimentation.

These are model versions and experiments, not evidence that every model directory is selected by every runtime component. The active model path and detector configuration must be checked in the relevant code and environment.

### Recorded evaluation results

The repository contains evaluation scripts and reports under `data/evaluation/`. The recorded fair V2/V3 comparison reports the following aggregate metrics:

| Metric | Recorded result |
|---|---:|
| Accuracy | 77.06% |
| Precision | 79.49% |
| Recall | 72.94% |
| F1 score | 76.07% |
| False-positive rate | 18.82% |

A separate V2 tuning report records a tuned result of **81.41% accuracy, 93.80% precision, 67.28% recall, and 78.39% F1**. These figures come from distinct evaluation reports/protocols and should not be compared as if they were one identical test run.

Evaluation datasets include synthetic anomaly scenarios. Results are dataset- and protocol-specific; they are not a guarantee of performance on live production traffic. Review the methodology, sample counts, confusion matrices, service-level results, and anomaly-type breakdowns before drawing conclusions.

Detailed evaluation documentation: [Model Evaluation](docs/MODEL_EVALUATION.md).

Useful evaluation assets:

- `data/evaluation/compare_v2_v3_fair.py`
- `data/evaluation/evaluate_detectors.py`
- `data/evaluation/evaluate_v3.py`
- `data/evaluation/tune_v2.py`
- `data/evaluation/fair_v2_v3_summary.json`
- `data/evaluation/evaluation_summary.json`
- `data/evaluation/v3_evaluation_summary.json`

## End-to-end workflow

1. **Collect or load metrics:** use service telemetry or a prepared metrics dataset.
2. **Validate the dataset:** check the input data and prepare supported metric fields.
3. **Run anomaly detection:** apply the configured Isolation Forest detector and model artifacts.
4. **Generate an anomaly report:** persist predictions/scores in a structured report.
5. **Generate recommendations:** pass anomaly records to the advisory decision engine.
6. **Review recovery context:** inspect the recommendation, service state, and available audit information.
7. **View the dashboard:** review metrics, anomaly summaries, pipeline state, and recovery records.
8. **Make an authorized operational decision:** any real remediation requires separate approval and verification.

## Technology stack

| Area | Technologies |
|---|---|
| Language | Python |
| Microservices and dashboard API | FastAPI |
| ASGI server | Uvicorn |
| Data processing | pandas |
| Machine learning | scikit-learn, Isolation Forest |
| Model artifacts | joblib |
| Testing | pytest |
| Monitoring | Prometheus, Grafana |
| Containers and orchestration | Docker, Kubernetes |
| Dashboard UI | HTML, CSS, JavaScript |

## Repository structure

| Path | Purpose |
|---|---|
| `services/` | User, Order, and Payment microservices and Dockerfiles |
| `ml/` | Metrics collection, validation, anomaly detectors, training code, and model artifacts |
| `pipeline/` | Advisory pipeline orchestration |
| `recovery/` | Decision engine, guarded recovery controller, and recovery metrics |
| `dashboard/` | FastAPI dashboard, static interface, and PowerShell launcher |
| `monitoring/` | Prometheus and Grafana configuration |
| `k8s/`, `kubernetes/` | Kubernetes service, workload, and recovery-test manifests |
| `data/` | Example metrics, reports, recommendations, and evaluation outputs |
| `scripts/` | Pipeline, load-test, and supporting utilities |
| `tests/` | Automated regression tests |
| `docs/` | Project documentation and model evaluation notes |

## Getting started

The commands below use **PowerShell on Windows**. Replace the example repository path with the location where you cloned this repository.

### 1. Create a virtual environment

```powershell
Set-Location "E:\Projects\github-sync"

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2. Install dependencies

Install dependencies from the requirements files available for the component you intend to run. For example, the dashboard and each service have their own dependency files:

```powershell
python -m pip install -r .\services\user-service\requirements.txt
python -m pip install -r .\services\order-service\requirements.txt
python -m pip install -r .\services\payment-service\requirements.txt
```

Install the ML and dashboard dependencies required by the corresponding code in your environment. The project may use separate development and ML environments; do not assume that one virtual environment contains every optional dependency.

## Run the advisory pipeline

From the repository root, the project includes an advisory pipeline launcher:

```powershell
python .\scripts\run_advisory_pipeline.py --help
```

Review the available arguments before running it. Use a dataset and fresh output paths appropriate to the current run. Do not overwrite existing reports, recommendations, model artifacts, or audit evidence unintentionally.

The pipeline workflow is:

1. Load and validate the selected metrics dataset.
2. Run the configured anomaly detector.
3. Write an anomaly report and model artifacts to the selected locations.
4. Pass report records to the advisory decision engine.
5. Produce recommendations for human review.

The exact command-line options and default paths are defined by the current script; use its `--help` output as the source of truth.

## Run the dashboard

The repository includes a PowerShell dashboard launcher:

```powershell
.\dashboard\START-DASHBOARD.ps1
```

When the dashboard starts successfully, open:

- Dashboard: [http://127.0.0.1:8088](http://127.0.0.1:8088)

Keep the launcher terminal open while using the dashboard. Stop the local process with `Ctrl+C`.

The dashboard is intended as an operational overview and read-only interface. Its displayed information depends on the availability and configuration of its data sources.

## Monitoring and deployment

### Prometheus and Grafana

The repository includes Prometheus and Grafana configuration under `monitoring/`. Verify that:

1. The relevant services are running and exposing their metrics endpoints.
2. Prometheus can reach the configured scrape targets.
3. The target labels and metric names match the queries used by the dashboard.
4. Grafana is connected to the intended Prometheus data source.

A running dashboard does not by itself prove that Prometheus targets are healthy or that metrics are current.

### Docker and Kubernetes

Dockerfiles and Kubernetes manifests are included in the repository. Before deploying, review image names, ports, namespaces, probes, resource settings, and configuration against your environment. Apply cluster-changing commands only to a Kubernetes environment you are authorized to administer.

The manifests demonstrate deployment configuration; their presence does not prove that a cluster deployment is currently active or production-ready.

## Testing

Run the test suite from the project root in an environment with pytest and the required project dependencies installed:

```powershell
python -m pytest -q
```

The latest recorded development run completed with:

```text
92 passed, 1 warning
```

The warning was a deprecation warning; all 92 tests passed in that run. Rerun the suite after changing code or dependencies. A passing test suite does not independently prove production model accuracy, live monitoring coverage, successful Kubernetes deployment, or safe real-world remediation.

## Safety and limitations

- An anomaly prediction is not a confirmed incident.
- A recommendation is not an executed recovery action.
- A recovery attempt is not a verified recovery outcome.
- Keep live remediation disabled unless authorization, policy checks, health verification, rollback, and audit requirements have been separately implemented and approved.
- Do not commit credentials, API keys, kubeconfig files, private keys, or other secrets.
- Protect the dashboard and monitoring endpoints before exposing them beyond a trusted local environment.
- Model evaluation results depend on the dataset, labels, features, service grouping, and evaluation protocol.
- Synthetic anomaly results should not be represented as production performance.

This repository is a **demonstration prototype for AI-assisted observability and guarded self-healing workflows**, not a production-ready autonomous remediation platform.

## Future enhancements

- Improve anomaly detection accuracy, recall, and F1 through documented, reproducible evaluation.
- Expand labeled and realistic validation scenarios.
- Improve model version selection and deployment configuration.
- Add data freshness and metric-availability indicators.
- Improve anomaly explanations and recommendation traceability.
- Expand integration testing in a disposable Kubernetes environment.
- Strengthen authorization, rollback, post-action health verification, and audit retention.
- Add authentication and security hardening for dashboard and monitoring access.

These are improvement directions, not claims that every item is already implemented.
