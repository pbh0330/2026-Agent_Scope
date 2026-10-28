@echo off
setlocal
rem ---------------------------------------------------------------------------
rem  AgentScope token monitoring without Docker (Windows): Prometheus + Grafana
rem  - Expects otelcol-agentscope.exe to be running already (/metrics on :9464)
rem  - Tools folder (default %USERPROFILE%\agentscope-tools) must contain the
rem    extracted zips:  prometheus-*.windows-amd64\   and   grafana*\
rem  - Override the folder:  set AGENTSCOPE_TOOLS=D:\tools  before running
rem  Details: README.md in this folder
rem ---------------------------------------------------------------------------

set "HERE=%~dp0"
if not defined AGENTSCOPE_TOOLS set "AGENTSCOPE_TOOLS=%USERPROFILE%\agentscope-tools"

set "PROM_DIR="
for /d %%D in ("%AGENTSCOPE_TOOLS%\prometheus-*") do set "PROM_DIR=%%~fD"
set "GRAFANA_DIR="
for /d %%D in ("%AGENTSCOPE_TOOLS%\grafana*") do set "GRAFANA_DIR=%%~fD"

if not defined PROM_DIR goto no_prom
if not exist "%PROM_DIR%\prometheus.exe" goto no_prom
if not defined GRAFANA_DIR goto no_grafana

set "DATA=%AGENTSCOPE_TOOLS%\data"
if not exist "%DATA%\prometheus" mkdir "%DATA%\prometheus"
if not exist "%DATA%\grafana" mkdir "%DATA%\grafana"

echo [1/2] Prometheus: %PROM_DIR%
start "Prometheus - AgentScope" "%PROM_DIR%\prometheus.exe" --config.file="%HERE%prometheus.yml" --enable-feature=exemplar-storage --storage.tsdb.path="%DATA%\prometheus" --web.listen-address=127.0.0.1:9090

for %%I in ("%HERE%..\grafana\provisioning\dashboards") do set "AGENTSCOPE_DASHBOARDS=%%~fI"
for %%I in ("%HERE%grafana\provisioning") do set "GF_PATHS_PROVISIONING=%%~fI"
set "GF_PATHS_DATA=%DATA%\grafana"
set "GF_SERVER_HTTP_ADDR=127.0.0.1"

echo [2/2] Grafana: %GRAFANA_DIR%
if exist "%GRAFANA_DIR%\bin\grafana.exe" goto grafana_new
start "Grafana - AgentScope" /D "%GRAFANA_DIR%" "%GRAFANA_DIR%\bin\grafana-server.exe" --homepath "%GRAFANA_DIR%"
goto started
:grafana_new
start "Grafana - AgentScope" /D "%GRAFANA_DIR%" "%GRAFANA_DIR%\bin\grafana.exe" server --homepath "%GRAFANA_DIR%"

:started
echo.
echo Started. Open:
echo   Grafana     http://localhost:3000   (admin / admin)
echo   Prometheus  http://localhost:9090
echo Close the two new windows to stop them.
exit /b 0

:no_prom
echo [ERROR] prometheus.exe not found under %AGENTSCOPE_TOOLS%\prometheus-*
echo         Extract prometheus-*.windows-amd64.zip into %AGENTSCOPE_TOOLS%
exit /b 1

:no_grafana
echo [ERROR] Grafana folder not found under %AGENTSCOPE_TOOLS%\grafana*
echo         Extract the Grafana Windows zip into %AGENTSCOPE_TOOLS%
exit /b 1
