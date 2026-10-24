@echo off
chcp 65001 >nul
rem ============================================================
rem  DOF demo launcher - one command per judge request.
rem  Usage:  scripts\demo\demo.cmd <topic>
rem  Topics: fullstack grafana prometheus kafka excel live
rem          frontend-code backend-code cicd tests health stop help
rem ============================================================
cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "TOPIC=%~1"
if "%TOPIC%"=="" set "TOPIC=help"
if /i "%TOPIC%"=="fullstack"     goto fullstack
if /i "%TOPIC%"=="grafana"       goto grafana
if /i "%TOPIC%"=="prometheus"    goto prometheus
if /i "%TOPIC%"=="kafka"         goto kafka
if /i "%TOPIC%"=="excel"         goto excel
if /i "%TOPIC%"=="live"          goto live
if /i "%TOPIC%"=="frontend-code" goto fcode
if /i "%TOPIC%"=="backend-code"  goto bcode
if /i "%TOPIC%"=="cicd"          goto cicd
if /i "%TOPIC%"=="tests"         goto tests
if /i "%TOPIC%"=="health"        goto health
if /i "%TOPIC%"=="stop"          goto stop
goto help

:help
echo.
echo   demo fullstack      - start the whole stack (Docker) and show every container
echo   demo grafana        - start ONLY Grafana (+Prometheus) and open it   http://localhost:3001
echo   demo prometheus     - start ONLY Prometheus and open Targets page    http://localhost:9090
echo   demo kafka          - start ONLY Kafka and list/read topics          localhost:9092
echo   demo excel          - open the variables list in Excel and generate sample well data
echo   demo live           - run backend services + live dashboard in console windows
echo   demo frontend-code  - open the frontend source in VS Code
echo   demo backend-code   - open the backend source in VS Code
echo   demo cicd           - show CI/CD workflows and the latest GitHub Actions runs
echo   demo tests          - run backend tests + frontend type-check/build
echo   demo health         - ping every service /health
echo   demo stop           - stop everything
echo.
goto :eof

:fullstack
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml ps
call :health
start "" http://localhost:8000/docs
goto :eof

:grafana
docker compose -f docker-compose.dev.yml up -d prometheus grafana
timeout /t 8 >nul
start "" http://localhost:3001
echo Grafana login: admin / admin  (anonymous viewing is enabled)
goto :eof

:prometheus
docker compose -f docker-compose.dev.yml up -d prometheus
timeout /t 5 >nul
start "" http://localhost:9090/targets
goto :eof

:kafka
docker compose -f docker-compose.dev.yml up -d zookeeper kafka
timeout /t 25 >nul
docker exec ogim-kafka kafka-topics --bootstrap-server kafka:29092 --list
echo.
echo --- Reading topic raw-sensor-data (Ctrl+C to stop). Ingest data first with: demo live
docker exec ogim-kafka kafka-console-consumer --bootstrap-server kafka:29092 --topic raw-sensor-data --from-beginning --max-messages 5 --timeout-ms 15000
goto :eof

:excel
if not exist data\variables_list.csv (echo data\variables_list.csv not found & goto :eof)
start "" excel "%ROOT%\data\variables_list.csv"
echo Generating 1 week of simulated data per well (SIMULATED - say so to the judges)...
python scripts\generate_sample_data.py
dir data\*.csv
for %%F in (data\PROD-001_sample_1week.csv) do if exist %%F start "" excel "%ROOT%\%%F"
goto :eof

:live
start "gateway"  cmd /k "cd /d %ROOT%\backend\api-gateway && python -m uvicorn main:app --port 8000"
start "auth"     cmd /k "cd /d %ROOT%\backend\auth-service && python -m uvicorn main:app --port 8001"
start "ingest"   cmd /k "cd /d %ROOT%\backend\data-ingestion-service && python -m uvicorn main:app --port 8002"
start "alert"    cmd /k "cd /d %ROOT%\backend\alert-service && python -m uvicorn main:app --port 8004"
start "tags"     cmd /k "cd /d %ROOT%\backend\tag-catalog-service && python -m uvicorn main:app --port 8007"
start "frontend" cmd /k "cd /d %ROOT%\frontend\web && npm install && npm run dev"
timeout /t 20 >nul
start "" http://localhost:3000
goto :eof

:fcode
code "%ROOT%\frontend\web\src"
code -g "%ROOT%\frontend\web\src\pages\Dashboard.tsx"
goto :eof

:bcode
code "%ROOT%\backend"
code -g "%ROOT%\backend\api-gateway\main.py"
goto :eof

:cicd
type .github\workflows\ci-cd.yml | more
start "" https://github.com/parsasohrab1/DOF-Digital-Oil-Field/actions
goto :eof

:tests
cd backend && python -m pytest -q --no-header -p no:cacheprovider
cd "%ROOT%\frontend\web" && call npx tsc --noEmit && call npm run build
cd "%ROOT%"
goto :eof

:health
for %%P in (8000 8001 8002 8003 8004 8005 8006 8007 8008 8011 8012 8013 8014) do (
  curl -s -o nul -w "port %%P -> HTTP %%{http_code}\n" http://localhost:%%P/health
)
goto :eof

:stop
docker compose -f docker-compose.dev.yml down
goto :eof
