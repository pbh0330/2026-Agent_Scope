# SNAP-0 / SNAP-1 구축 기록

> 작업일: 2026.10.04 (일)
> 작업자: 박병하
> 결과: 두 VM(`tb-gw`, `tb-node`)에 `SNAP-0`, `SNAP-1` 생성 완료
> 민감정보: IP·사용자명·토큰은 자리표시자(`<TB_GW_IP>`, `<TB_NODE_IP>`, `<TB_USER>`, `<DUMMY_TOKEN>`)로 표기

---

## 1. 결과 요약

| 항목 | tb-gw | tb-node |
|---|---|---|
| 생성 방식 | 기존 VM(Ubuntu 24.04.5 Desktop ISO 설치본) | `tb-gw`를 SNAP-0 직전 상태에서 **전체 복제(full clone)** 후 식별자 재생성 |
| vCPU / RAM / 디스크 | 2 / 6 GB / 150 GB | 2 / 4 GB / 150 GB (복제로 디스크 크기 상속) |
| IP (VMnet8, 고정) | `<TB_GW_IP>` | `<TB_NODE_IP>` |
| OS / 커널 | Ubuntu 24.04.5 LTS / 7.0.0-38-generic | 동일 |
| 설치 패키지 목록 해시 (`dpkg-query` sha256 앞 16자) | `7d16c29a4b9aea75` | `7d16c29a4b9aea75` (동일) |
| open-vm-tools | 13.0.10.0 (build-25056151) | 동일 |
| Node.js / npm | v24.21.0 (apt hold) / 11.19.0 | 동일 |
| OpenClaw | 2026.9.6 (eb377ac), 게이트웨이 systemd 사용자 서비스 | 2026.9.6 (eb377ac), 노드 호스트 systemd 사용자 서비스 |
| 스냅샷 | SNAP-0, SNAP-1 (전원 끈 상태) | SNAP-0, SNAP-1 (전원 끈 상태) |

노드를 복제로 만든 이유: Desktop ISO는 무인 설치가 번거롭고, 복제는 패키지 구성까지 바이트 단위로 같아 "같은 ISO로 OS 차이 제거"라는 사양 의도를 더 엄격하게 충족한다. 복제 후 machine-id, SSH 호스트 키, MAC 주소, BIOS UUID, 호스트명, IP를 모두 새로 만들었다.

---

## 2. SNAP-0 절차

### 2.1 공통 (tb-gw에서 수행 후 복제)

```bash
# 원격 관리: openssh-server + 키 인증, 테스트베드 VM 한정 비밀번호 없는 sudo
sudo apt install -y openssh-server open-vm-tools
echo '<TB_USER> ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-agentscope-testbed

# 자동 업데이트 비활성화 (R2 재현성)
sudo systemctl disable --now unattended-upgrades apt-daily.timer apt-daily-upgrade.timer
# /etc/apt/apt.conf.d/20auto-upgrades : APT::Periodic::* "0";
sudo snap refresh --hold

# 기본 패키지 + Node.js 24 (NodeSource), 버전 고정
sudo apt-get install -y curl ca-certificates gnupg git jq build-essential python3 python3-venv unzip net-tools
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt-get install -y nodejs && sudo apt-mark hold nodejs

# 고정 IP (VMnet8 DHCP 범위 .128~.254 밖, 게이트웨이·DNS .2)
sudo nmcli con mod netplan-ens33 ipv4.method manual ipv4.addresses <TB_GW_IP>/24 \
  ipv4.gateway <VMNET8_GW> ipv4.dns <VMNET8_GW> ipv6.method disabled
```

`/etc/hosts`에 `tb-gw`, `tb-node`를 등록했다.

### 2.2 tb-node 복제

1. `tb-gw` 종료 후 `vmrun clone <tb-gw.vmx> <tb-node.vmx> full -cloneName=tb-node`
2. vmx에서 `ethernet0.generatedAddress` 삭제(MAC 재생성), `memsize = "4096"`
3. 부팅 후 호스트명 `tb-node`, `/etc/machine-id` 재생성, `ssh-keygen -A`로 호스트 키 재생성, IP `<TB_NODE_IP>`로 변경 후 재부팅

### 2.3 스냅샷

두 VM을 모두 종료한 뒤 `vmrun snapshot <vmx> SNAP-0`.

---

## 3. SNAP-1 절차

### 3.1 OpenClaw 설치 (양쪽)

```bash
sudo npm install -g openclaw@2026.9.6
openclaw --version   # OpenClaw 2026.9.6 (eb377ac)
```

패키지에 해당 버전의 `docs/`가 함께 들어 있다(`$(npm root -g)/openclaw/docs`). 이후 절차는 이 문서를 기준으로 했다.

### 3.2 게이트웨이 (tb-gw)

```bash
openclaw onboard --non-interactive --accept-risk --mode local --auth-choice skip \
  --gateway-bind lan --gateway-port 18789 --gateway-auth token --gateway-token <DUMMY_TOKEN> \
  --install-daemon --skip-skills --skip-channels --skip-hooks --skip-search --skip-ui \
  --suppress-gateway-token-output --workspace /home/<TB_USER>/workspace
openclaw config set update.checkOnStart false
# systemd drop-in: Environment=OPENCLAW_NO_AUTO_UPDATE=1
```

- 모델 백엔드는 미정이므로 `--auth-choice skip`으로 설정하지 않았다.
- 노드가 다른 VM에서 접속하므로 `bind: "lan"`(0.0.0.0:18789) + 토큰 인증을 사용한다.
- 게이트웨이 시작부터 포트 대기까지 약 15초 걸렸다(120초 제한 대비 여유 있음, 기본 플러그인 상태).

### 3.3 노드 (tb-node)

```bash
openclaw config set nodeHost.autoUpdate.enabled false   # 헤드리스 노드는 기본값이 매시간 자동 업데이트
openclaw config set update.checkOnStart false
export OPENCLAW_GATEWAY_TOKEN=<DUMMY_TOKEN> OPENCLAW_NO_AUTO_UPDATE=1
openclaw node install --host <TB_GW_IP> --port 18789 --display-name tb-node
sudo loginctl enable-linger <TB_USER>
# systemd drop-in: Environment=OPENCLAW_NO_AUTO_UPDATE=1
```

### 3.4 페어링 (2단계 승인, tb-gw에서)

```bash
openclaw devices list                    # 1단계: 장치 승인 (role: node)
openclaw devices approve <deviceRequestId>
# tb-node: systemctl --user restart openclaw-node
openclaw nodes pending                   # 2단계: 명령 표면 승인
openclaw nodes approve <nodeRequestId>
openclaw nodes describe --node tb-node   # Status: paired · connected
```

승인된 노드 명령: `browser.proxy`, `browser.proxy.upload.v1`, `desktop.stream`, `fs.listDir`, `mcp.tools.call.v1`, `ollama.chat`, `ollama.models`, `system.execApprovals.get/set`, `system.notify`, `system.run`, `system.run.prepare`, `system.which`, `terminal.upload`
Caps: `browser, file, local-inference, mcp, system`

### 3.5 기준선 수집 후 스냅샷

`openclaw security audit --json`, `plugins list`, `skills list`, `mcp list`를 수집한 뒤([../baseline/SNAP-1/](../baseline/SNAP-1/)), 두 VM을 종료하고 `SNAP-1`을 생성했다.

---

## 4. SNAP-1 기준선

| 항목 | 결과 | 파일 |
|---|---|---|
| MCP 서버 (`mcp.servers`) | 0건 | `tb-gw.mcp-list.txt` |
| 노드 측 MCP 서버 (`nodeHost.mcp.servers`) | 0건 | `tb-node.openclaw.json` |
| 플러그인 | 내장(stock) 63종 중 40종 활성, 사용자 설치 0건 | `tb-gw.plugins-list.txt` |
| 스킬 | 내장 57종(21종 ready), 사용자 설치 0건, 노드 `~/.openclaw/skills/` 없음 | `tb-gw.skills-list.txt`, `tb-node.openclaw-tree.txt` |
| 내장 보안 감사 | critical 1, warn 1, info 1 | `tb-gw.security-audit.json` |

보안 감사 결과:

| 심각도 | checkId | 내용 |
|---|---|---|
| critical | `gateway.control_ui.allowed_origins_required` | LAN 바인딩인데 `gateway.controlUi.allowedOrigins`가 설정 파일에 없음 |
| warn | `gateway.auth_no_rate_limit` | 비루프백 바인딩인데 `gateway.auth.rateLimit` 미설정 |
| info | `summary.attack_surface` | `tools.elevated: enabled`, `browser control: enabled` 등 |

SNAP-1은 "설치 직후 기본 상태" 기준선이므로 위 항목은 보완하지 않고 그대로 두었다. 보완 여부는 정상군(SNAP-2)에서 결정한다.

---

## 5. 공식 문서(09.15 조사) 대비 실측 차이

| 항목 | 09.15 조사 / 사양서 | 2026.9.6 실측 |
|---|---|---|
| 노드 식별 정보 | `~/.openclaw/node.json` | **폐지**. `~/.openclaw/state/openclaw.sqlite`의 `config_machine_state`(`nodeHost.config`), `device_identities`(`primary`), `device_auth_tokens`. 수집은 `openclaw node identity --json`으로 하며, 출력 `deviceId`가 게이트웨이 페어링 기록(`openclaw devices list --json`)의 노드 ID와 일치함을 확인 |
| 게이트웨이 식별 정보 | 미조사 | `openclaw gateway call gateway.identity.get --json` → `deviceId`, 반복 조회 시 동일 값 확인 |
| 노드의 MCP 도구 호출 명령 | `mcp.tools.cll.v1` | `mcp.tools.call.v1` |
| 노드 자동 업데이트 | 언급 없음 | 헤드리스 노드는 기본값이 매시간 자동 업데이트 → `nodeHost.autoUpdate.enabled: false`로 비활성화 |
| 노드의 게이트웨이 토큰 | 언급 없음 | `~/.openclaw/node.systemd.env`에 평문 저장(서비스 환경 파일). S4 관측 지점 후보 |
| "자산 0건" 기준선 | 플러그인·스킬 없음 | 내장 플러그인·스킬이 기본 로드됨. "사용자 추가 자산 0건"으로 정의 필요 |
| 노드 페어링 | 페어링 1회 | 장치 승인(`devices approve`)과 명령 표면 승인(`nodes approve`)의 2단계 |
