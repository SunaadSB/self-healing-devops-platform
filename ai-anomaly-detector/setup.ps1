Write-Host "============================================"
Write-Host " AI Self-Healing DevOps Platform Setup"
Write-Host "============================================"

Write-Host "`n[1/4] Installing Python dependencies..."

python -m pip install --upgrade pip

pip install -r requirements.txt

pip install streamlit prometheus-api-client streamlit-autorefresh pandas scikit-learn requests kubernetes

Write-Host "`n[2/4] Checking Python..."

python --version

Write-Host "`n[3/4] Checking Kubernetes..."

kubectl version --client

kubectl get nodes

Write-Host "`n[4/4] Checking project files..."

$files = @(
    "app.py",
    "dashboard.py",
    "model.py",
    "isolation_forest_model.pkl",
    "requirements.txt"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "OK: $file" -ForegroundColor Green
    }
    else {
        Write-Host "MISSING: $file" -ForegroundColor Red
    }
}

Write-Host "`n============================================"
Write-Host "Setup check completed."
Write-Host "============================================"

Write-Host "`nTo start the dashboard:"
Write-Host "streamlit run dashboard.py"

Write-Host "`nTo start the AI detector:"
Write-Host "python app.py"