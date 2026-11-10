#!/usr/bin/env bash
# OVA 내보내기용 민감정보·흔적 정리 (각 VM의 '내보내기 복제본' 안에서 실행)
#
# 용법:  ./ova-sanitize.sh gw     # tb-gw 복제본에서
#        ./ova-sanitize.sh node   # tb-node 복제본에서
#
# 원본 VM이 아니라 SNAP-2-P2에서 전체 복제한 '일회용 복제본'에서만 실행한다.
# 자세한 배경·점검표는 testbed/docs/ova-packaging.md 참조.
#
# 유지(일부러 지우지 않음):
#   - OpenClaw 장치 신원 ~/.openclaw/state/openclaw.sqlite  (정답 목록 deviceId와 일치해야 함)
#   - 노드 페어링 토큰 ~/.openclaw/node.systemd.env          (페어링 동작 필요)
#   - 실습용 CA·서버 개인키 ~/ca.key, ~/*.key               (inventory-remote HTTPS 즉시 동작)
#   위 셋은 '테스트베드 전용·공개 전제'임을 배포 README에 명시한다.
set -euo pipefail

ROLE="${1:-}"
if [[ "$ROLE" != "gw" && "$ROLE" != "node" ]]; then
  echo "용법: $0 gw|node" >&2
  exit 2
fi

# 배포 README에 적는 '공개 더미' 값. 두 VM의 INVENTORY_MCP_TOKEN은 같아야 inventory-remote가 뜬다.
INVENTORY_DUMMY="testbed-dummy-inventory-token"
EVERYTHING_DUMMY="testbed-dummy-everything-key"

say() { printf '  [sanitize] %s\n' "$1"; }

reset_env_var() {  # reset_env_var <file> <KEY> <value>
  local file="$1" key="$2" val="$3"
  [[ -f "$file" ]] || { say "건너뜀(없음): $file"; return 0; }
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$file"
    say "더미로 교체: ${file}#${key}"
  else
    say "건너뜀(키 없음): ${file}#${key}"
  fi
}

echo "== OVA sanitize ($ROLE) =="

# 1) 더미 자격증명 고정 -----------------------------------------------------
reset_env_var "$HOME/.openclaw/.env" INVENTORY_MCP_TOKEN "$INVENTORY_DUMMY"
if [[ "$ROLE" == "node" ]]; then
  reset_env_var "$HOME/.openclaw/.env" EVERYTHING_DEMO_KEY "$EVERYTHING_DUMMY"
  reset_env_var "$HOME/inventory-remote/.env" INVENTORY_MCP_TOKEN "$INVENTORY_DUMMY"
fi
say "게이트웨이 auth 토큰(openclaw.json#gateway.auth.token)은 형식 훼손을 피해 수동 처리한다:"
say "  openclaw config set gateway.auth.token '<DUMMY_TOKEN>'  (gw에서, 점검표 4절)"

# 2) 셸 히스토리 -----------------------------------------------------------
for h in "$HOME"/.bash_history "$HOME"/.zsh_history "$HOME"/.python_history "$HOME"/.node_repl_history; do
  [[ -e "$h" ]] && { : > "$h"; say "비움: $h"; }
done
sudo sh -c ': > /root/.bash_history' 2>/dev/null || true

# 3) 시스템 로그 -----------------------------------------------------------
sudo find /var/log -type f -exec sh -c ': > "$1"' _ {} \; 2>/dev/null || true
sudo journalctl --rotate 2>/dev/null || true
sudo journalctl --vacuum-time=1s 2>/dev/null || true
say "로그·journald 비움"

# 4) SSH 호스트키 (첫 부팅 때 재생성) --------------------------------------
sudo rm -f /etc/ssh/ssh_host_* && say "SSH 호스트키 삭제(첫 부팅 재생성)" || true
# 첫 부팅 시 재생성 보장(Ubuntu): 서비스가 없으면 수동 재생성 안내
if ! systemctl list-unit-files 2>/dev/null | grep -q ssh-host-keys; then
  say "참고: 임포트 후 키가 없으면 'sudo ssh-keygen -A'로 재생성"
fi

# 5) machine-id (첫 부팅 재생성) ------------------------------------------
sudo truncate -s 0 /etc/machine-id 2>/dev/null && say "/etc/machine-id 비움" || true
sudo rm -f /var/lib/dbus/machine-id 2>/dev/null || true

# 6) 캐시·임시 ------------------------------------------------------------
sudo apt-get clean 2>/dev/null || true
rm -rf "$HOME"/.cache/* 2>/dev/null || true
sudo find /tmp /var/tmp -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
say "apt 캐시·~/.cache·/tmp 정리"

# 7) 잔여 비밀값 흔적 점검(참고 출력, 자동 삭제 아님) ----------------------
echo "== 잔여 토큰 흔적 점검(아래가 비어야 안전) =="
sudo grep -RIl --exclude-dir=/proc --exclude-dir=/sys \
  -e 'INVENTORY_MCP_TOKEN=' -e 'EVERYTHING_DEMO_KEY=' /root /home 2>/dev/null \
  | grep -vE '\.env$|/openclaw\.json$' || echo "  (추가 흔적 없음)"

echo "== 완료. 전원을 끄고 ovftool로 내보낸다(docs/ova-packaging.md 3절). =="
