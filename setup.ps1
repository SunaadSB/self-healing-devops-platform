Write-Host "============================================"
Write-Host " AI Self-Healing DevOps Platform"
Write-Host " Portable Setup"
Write-Host "============================================"

# 1. Check required tools
Write-Host "`n[1] Checking tools..."

python --version
kubectl version --client
docker --version

# 2. Install Python dependencies
Write-Host "`n[2] Installing Python dependencies..."

python -m pip install --upgrade pip

if (Test-Path "ai-anomaly-detector\requirements.txt") {
    pip install -r ai-anomaly-detector\requirements.txt
}

pip install streamlit prometheus-api-client streamlit-autorefresh pandas scikit-learn requests kubernetes

# 3. Check Kubernetes
Write-Host "`n[3] Checking Kubernetes cluster..."

kubectl get nodes

# 4. Deploy microservices
Write-Host "`n[4] Deploying microservices..."

kubectl apply -f k8s\

# 5. Deploy Prometheus
Write-Host "`n[5] Deploying Prometheus..."

kubectl apply -f monitoring\prometheus-config.yaml
kubectl apply -f monitoring\prometheus-deployment.yaml

# 6. Deploy Grafana
Write-Host "`n[6] Deploying Grafana..."

kubectl apply -f monitoring\grafana-deploymet.yaml

# 7. Wait for deployments
Write-Host "`n[7] Waiting for deployments..."

kubectl rollout status deployment/user-service
kubectl rollout status deployment/order-service
kubectl rollout status deployment/payment-service
kubectl rollout status deployment/prometheus

# 8. Show final status
Write-Host "`n============================================"
Write-Host " DEPLOYMENT STATUS"
Write-Host "============================================"

kubectl get pods
kubectl get svc
kubectl get deployments

Write-Host "`n============================================"
Write-Host " SETUP COMPLETE"
Write-Host "============================================"

Write-Host "`nStart AI detector:"
Write-Host "cd ai-anomaly-detector"
Write-Host "python app.py"

Write-Host "`nStart dashboard in another PowerShell:"
Write-Host "cd ai-anomaly-detector"
Write-Host "streamlit run dashboard.py"