# اجرای زنده داشبورد میدان دهلران بدون اینترنت و بدون بک‌اند
# پیش‌نیاز: یک‌بار (با اینترنت) npm install در frontend/web انجام شده باشد

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Web = Join-Path $Root "frontend\web"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host " داشبورد زنده آفلاین — میدان دهلران" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Host "خطا: Node.js نصب نیست یا در PATH نیست." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $Web "node_modules"))) {
    Write-Host "پوشه node_modules یافت نشد." -ForegroundColor Yellow
    Write-Host "برای اولین بار به اینترنت نیاز است:" -ForegroundColor Yellow
    Write-Host "  cd frontend\web" -ForegroundColor White
    Write-Host "  npm install" -ForegroundColor White
    Write-Host ""
    $choice = Read-Host "الان با اینترنت نصب شود؟ (y/N)"
    if ($choice -match '^[yY]') {
        Set-Location $Web
        npm install
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } else {
        exit 1
    }
}

Set-Location $Web

# اجبار حالت آفلاین حتی اگر env لود نشود
$env:VITE_OFFLINE_LIVE = "true"

Write-Host "شروع Vite در حالت offline..." -ForegroundColor Green
Write-Host ""
Write-Host "آدرس داشبورد: http://127.0.0.1:3000/" -ForegroundColor Cyan
Write-Host "داده زنده: شبیه‌سازی محلی میدان دهلران (هر ۴ ثانیه)" -ForegroundColor Cyan
Write-Host "اینترنت / بک‌اند لازم نیست." -ForegroundColor Cyan
Write-Host ""

# باز کردن مرورگر بعد از کمی تأخیر
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:3000/"
} | Out-Null

npm run dev:offline
