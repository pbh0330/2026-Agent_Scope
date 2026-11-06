#!/usr/bin/env bash
# tb-gw에서 게이트웨이 사용자로 실행(sudo 없이):
#   Collector(OpenTelemetry 공식 otelcol(core 배포판), 버전 고정)를 내려받아 ~/agentscope에 설치하고
#   systemd 사용자 서비스 agentscope-collector로 등록한다. 다시 실행해도 같은 결과(덮어쓰기).
set -euo pipefail

VERSION=0.161.0
# 공식 릴리스 파일의 SHA-256(2026-11-03 내려받아 계산). 버전을 바꾸면 같이 바꾼다.
SHA256=6c2af0731a53691e3771d82a4b71e2941a46de27af191e40c697b6ed8643e50e

[ "$(uname -m)" = "x86_64" ] || { echo "x86_64만 지원(현재 $(uname -m))" >&2; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
BASE="$HOME/agentscope"
UNIT_DIR="$HOME/.config/systemd/user"
TGZ="otelcol_${VERSION}_linux_amd64.tar.gz"
URL="https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${VERSION}/${TGZ}"

mkdir -p "$BASE/bin" "$BASE/data" "$UNIT_DIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "내려받기: $TGZ"
curl -fsSL -o "$TMP/$TGZ" "$URL"
echo "${SHA256}  $TMP/$TGZ" | sha256sum -c -
tar -xzf "$TMP/$TGZ" -C "$TMP" otelcol
install -m 0755 "$TMP/otelcol" "$BASE/bin/otelcol"
install -m 0644 "$HERE/otelcol-testbed.yaml" "$BASE/otelcol-testbed.yaml"
"$BASE/bin/otelcol" validate --config "$BASE/otelcol-testbed.yaml"
echo "설정 검사 통과"

install -m 0644 "$HERE/agentscope-collector.service" "$UNIT_DIR/agentscope-collector.service"
systemctl --user daemon-reload
systemctl --user enable --now agentscope-collector
systemctl --user restart agentscope-collector   # 다시 실행한 경우 새 설정 적용
sleep 2
systemctl --user is-active agentscope-collector
echo "스팬 파일: $BASE/data/agentscope-traces.jsonl (첫 요청 후 생김)"
