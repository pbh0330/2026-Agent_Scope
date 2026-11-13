#!/usr/bin/env bash
# 개발 PC(Go 1.24 이상)에서 테스트베드용 실행 파일을 만든다: dist/agentscope-usage-api(+ .sha256)
# Windows PowerShell에서는:
#   cd token-collector\backend\usageapi
#   $env:GOOS="linux"; $env:GOARCH="amd64"; $env:CGO_ENABLED="0"
#   go build -trimpath -ldflags="-s -w" -o ..\..\dist\agentscope-usage-api .\cmd\agentscope-usage-api
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$ROOT/dist"
cd "$ROOT/backend/usageapi"
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" \
  -o "$ROOT/dist/agentscope-usage-api" ./cmd/agentscope-usage-api
cd "$ROOT/dist" && sha256sum agentscope-usage-api > agentscope-usage-api.sha256
cat agentscope-usage-api.sha256
