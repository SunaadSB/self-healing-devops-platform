# Self-Healing DevOps Dashboard (local, read-only)

This dashboard is an add-on for the existing project. It does not change Kubernetes, execute `kubectl`, or trigger recovery actions.

## Install into the project

Extract the `dashboard` folder into:
`E:\Projects\ai-powered-self-healing\dashboard`

The archive includes:
- `dashboard_app.py`
- `static\index.html`
- `START-DASHBOARD.ps1`

The existing `dashboard` folder may be empty; back it up first if it contains anything important.

## Run

From PowerShell in the project root:

```powershell
Set-Location "E:\Projects\ai-powered-self-healing"
.\dashboard\START-DASHBOARD.ps1
```

Then open http://127.0.0.1:8088

If your `.venv` is missing FastAPI/Uvicorn, use an environment where they are already installed; the script checks before starting and does not install packages.

## Data sources

- Prometheus: `http://localhost:30090`
- User service: `http://localhost:31478`
- Order service: `http://localhost:32040`
- Payment service: `http://localhost:30441`
- Audit log: `logs\recovery_audit.jsonl`
- Recommendations: `data\recovery_recommendations_v2.csv`

Override endpoints with environment variables if necessary:
`PROMETHEUS_URL`, `USER_SERVICE_URL`, `ORDER_SERVICE_URL`, `PAYMENT_SERVICE_URL`, `RECOVERY_AUDIT_PATH`, `RECOMMENDATIONS_PATH`.

## Important limitations

- Generic PromQL expressions are used for request rate, error rate, and p95 latency. If metric names differ, the UI shows `No data`; inspect `/metrics` and adapt the expressions before relying on them.
- Recovery rate is a preliminary calculation from recognizable non-dry-run audit statuses. It is intentionally marked as an estimate and must not be presented as an official rate until the audit schema and actual recovery verification are confirmed.
- This is a local, read-only dashboard. It does not execute recovery or expose recovery controls.
