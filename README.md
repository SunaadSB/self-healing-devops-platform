# Self-Healing DevOps Platform

A demo platform with three FastAPI services, an API gateway, Prometheus metrics, Kubernetes manifests, and an AI anomaly detector.

## Local service ports

The service containers listen on their internal ports; Docker Compose publishes them on the host ports below so they match the API gateway and the standalone Prometheus configuration.

| Component | Host port | Container port |
|---|---:|---:|
| API gateway (run separately) | 8000 | — |
| User service | 8001 | 8000 |
| Order service | 8002 | 8001 |
| Payment service | 8003 | 8002 |

## Run the services locally with Docker Compose

From the repository root:

```bash
docker compose up --build
```

The Compose file starts the user, order, and payment services. To run the gateway separately, install its Python dependencies and start it from the repository root:

```bash
python -m pip install fastapi uvicorn requests
python -m uvicorn main:app --app-dir api-gateway --host 0.0.0.0 --port 8000
```

The gateway's default upstream URLs target the published host ports: user `127.0.0.1:8001`, order `127.0.0.1:8002`, and payment `127.0.0.1:8003`. This default is for running the gateway on the host; if you containerize the gateway, change the upstream URLs to the Compose service names and container ports.

## Prometheus configuration

- `monitoring/prometheus.yml` is for a Prometheus process running on the same host as the Compose-published service ports. It scrapes `localhost:8001`, `localhost:8002`, and `localhost:8003`.
- `monitoring/prometheus-config.yaml` is for Kubernetes and scrapes the Kubernetes service DNS names on their service ports.

For the AI detector, `PROMETHEUS_URL` currently defaults to `http://localhost:9090`, appropriate when Prometheus is available on the same host. For the dashboard, the default is `http://localhost:30090`, the NodePort exposed by the Kubernetes Prometheus manifest.

## Kubernetes

Apply the manifests in `k8s/` and the Prometheus manifests in `monitoring/` to a configured Kubernetes cluster. Ensure the service images have been built and loaded into the cluster or pushed to a registry before applying deployments that use `imagePullPolicy: Never`.

## Important note

This repository is a demonstration, not a production-ready payment or self-healing system. Validate deployment settings, monitoring connectivity, and recovery behavior in a test environment before using autonomous recovery.
