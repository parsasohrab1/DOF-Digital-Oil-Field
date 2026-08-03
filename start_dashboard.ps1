# PowerShell script to start SOGF Dashboard
# This script starts backend services manually (without Docker)

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Starting SOGF Dashboard" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

# Check if Node.js is available
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Host "Error: Node.js is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

Write-Host "Starting Backend Services..." -ForegroundColor Yellow
Write-Host ""

# Start API Gateway
Write-Host "Starting API Gateway on port 18000..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "18000", "--reload" -WorkingDirectory "backend/api-gateway" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Auth Service
Write-Host "Starting Auth Service on port 8001..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload" -WorkingDirectory "backend/auth-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Data Ingestion Service
Write-Host "Starting Data Ingestion Service on port 8002..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--reload" -WorkingDirectory "backend/data-ingestion-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start ML Inference Service
Write-Host "Starting ML Inference Service on port 8003..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--reload" -WorkingDirectory "backend/ml-inference-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Alert Service
Write-Host "Starting Alert Service on port 8004..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004", "--reload" -WorkingDirectory "backend/alert-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Reporting Service
Write-Host "Starting Reporting Service on port 8005..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005", "--reload" -WorkingDirectory "backend/reporting-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Command Control Service
Write-Host "Starting Command Control Service on port 8006..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006", "--reload" -WorkingDirectory "backend/command-control-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Tag Catalog Service
Write-Host "Starting Tag Catalog Service on port 8007..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007", "--reload" -WorkingDirectory "backend/tag-catalog-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Digital Twin Service
Write-Host "Starting Digital Twin Service on port 8008..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008", "--reload" -WorkingDirectory "backend/digital-twin-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Edge Computing Service
Write-Host "Starting Edge Computing Service on port 8009..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8009", "--reload" -WorkingDirectory "backend/edge-computing-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start ERP Integration Service
Write-Host "Starting ERP Integration Service on port 8010..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--reload" -WorkingDirectory "backend/erp-integration-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start DVR Service
Write-Host "Starting DVR Service on port 8011..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8011", "--reload" -WorkingDirectory "backend/dvr-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Remote Operations Service
Write-Host "Starting Remote Operations Service on port 8012..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8012", "--reload" -WorkingDirectory "backend/remote-operations-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Data Variables Service
Write-Host "Starting Data Variables Service on port 8013..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8013", "--reload" -WorkingDirectory "backend/data-variables-service" -WindowStyle Minimized

Start-Sleep -Seconds 2

# Start Storage Optimization Service
Write-Host "Starting Storage Optimization Service on port 8014..." -ForegroundColor Green
Start-Process python -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8014", "--reload" -WorkingDirectory "backend/storage-optimization-service" -WindowStyle Minimized

Write-Host ""
Write-Host "Waiting for services to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "Starting Frontend..." -ForegroundColor Yellow
Write-Host ""

# Start Frontend
Set-Location "frontend/web"
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing Frontend dependencies..." -ForegroundColor Yellow
    npm install
}

Write-Host "Starting Frontend Development Server..." -ForegroundColor Green
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Dashboard URLs:" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:3000" -ForegroundColor Green
Write-Host "API Gateway: http://localhost:18000" -ForegroundColor Green
Write-Host "API Docs: http://localhost:18000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "برای اجرای زنده بدون اینترنت (فقط فرانت‌اند):" -ForegroundColor Yellow
Write-Host "  .\start_offline_dashboard.ps1" -ForegroundColor White
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan

npm run dev

