$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python environment not found: $python"
}
& $python -c "import fastapi, uvicorn; print('FastAPI and Uvicorn available')" 
if ($LASTEXITCODE -ne 0) {
    throw "FastAPI/Uvicorn are not available in .venv. No packages were installed."
}
Set-Location $projectRoot
Write-Host ""
Write-Host "Starting read-only Self-Healing Dashboard at http://127.0.0.1:8088"
Write-Host "Press Ctrl+C to stop. No Kubernetes changes will be made."
& $python -m uvicorn dashboard.dashboard_app:app --host 127.0.0.1 --port 8088
