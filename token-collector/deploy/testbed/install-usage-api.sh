#!/usr/bin/env bash
# tb-gw에서 게이트웨이 사용자로 실행(sudo 없이):
#   ./install-usage-api.sh <agentscope-usage-api 실행 파일 경로>
# 실행 파일은 개발 PC에서 deploy/build.sh(또는 README의 go build 명령)로 만든 linux/amd64 파일.
# 같은 폴더에 <파일>.sha256이 있으면 확인한다. 다시 실행해도 같은 결과(덮어쓰고 재시작).
set -euo pipefail

BIN=${1:?"사용법: $0 <agentscope-usage-api 실행 파일>"}
[ -f "$BIN" ] || { echo "파일 없음: $BIN" >&2; exit 1; }
if [ -f "$BIN.sha256" ]; then
  (cd "$(dirname "$BIN")" && sha256sum -c "$(basename "$BIN").sha256")
fi

HERE=$(cd "$(dirname "$0")" && pwd)
BASE="$HOME/agentscope"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$BASE/bin" "$BASE/data" "$UNIT_DIR"

install -m 0755 "$BIN" "$BASE/bin/agentscope-usage-api"
HELP=$("$BASE/bin/agentscope-usage-api" -h 2>&1 || true)
grep -q -- "-live" <<<"$HELP" || { echo "실행 파일이 맞지 않음(--live 옵션 없음)" >&2; exit 1; }

install -m 0644 "$HERE/agentscope-usage-api.service" "$UNIT_DIR/agentscope-usage-api.service"
systemctl --user daemon-reload
systemctl --user enable --now agentscope-usage-api
systemctl --user restart agentscope-usage-api
sleep 2
systemctl --user is-active agentscope-usage-api
curl -fsS http://127.0.0.1:8088/api/v1/usage/health && echo
