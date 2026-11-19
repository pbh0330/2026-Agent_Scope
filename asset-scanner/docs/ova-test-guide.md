# OpenClaw OVA 환경 자산 수집 검증 절차서

작성일: 2026-11-19 · 코드 기준: **`55db6a39a275ae5b10eaf2ad3c77d699acce24c7`** · PR #5

**목적:** OVA에 구성된 실제 OpenClaw 환경에서 설정·설치 정보 수집, OpenClaw 실행 파일 직접 조회, MCP 서버의 네 종류 목록 조회를 검증합니다. 실행 조건·수집 결과·오류·제약을 기록하여 팀 검토와 후속 보완의 근거로 활용합니다.

| 역할 | 수행 내용 |
|---|---|
| 검증 수행자 | 실제 환경 확인, 검증 명령 실행, 종료 코드·결과·미수행 사유 기록 및 공유 |
| 테스트베드 관리 담당자 | VM 접속 정보, 실행 경로·프로필·대상 서버·테스트 인증정보 확인 지원 |
| 스캐너 개발 담당자 | 검증 결과와 원천 대조, 수집 오류·응답 차이 분석 및 보완 |

- 스캐너는 `feature/scanner-config`에 함께 올라가 있습니다. PR #5는 `develop` 대상 **Draft이며 미병합**입니다. `main`이나 `develop`을 내려받으면 이 코드가 없습니다.
- 이 코드의 Linux 자동 테스트는 51개 파일·1,136개 통과, pytest 종료 코드 0입니다. 가상 설정·DB·가짜 OpenClaw CLI·개발용 MCP 서버 등을 이용한 자동 테스트입니다. **실제 OVA 결과는 코드 `82c7579`의 부분 검증이며, 이후 `dist/extensions` 탐색 수정은 VM 재검증 대기**입니다. 결과와 제약은 10절에 구분하여 기록합니다.
- 명령은 **Windows PowerShell이 아니라 각 VM 안의 Linux Bash 터미널**에서 실행합니다. Gateway와 Node가 별도 VM이면 각각 진행합니다. stdio 서버는 스캐너와 같은 VM에서 실행되므로 호스트 PC에서 대신 실행하지 않습니다.
- 설정 수집 → OpenClaw 직접 조회 → 선택 MCP 서버 조회 순서입니다. 전체 자동 테스트 1,136개를 VM에서 다시 실행할 필요는 없습니다.

## 1. 검증 전 준비 사항

| 필요한 정보 | 확인 방법·주의점 |
|---|---|
| VM 실행·로그인 | 테스트베드 관리 담당자가 안내한 OVA 가져오기·부팅 절차를 따릅니다. OpenClaw를 운영하는 기존 사용자로 로그인합니다. |
| 원본 상태 보존 | 테스트용 VM 사본이나 시작 전 스냅샷을 사용합니다. 스캐너·가상환경·결과 파일은 추가됩니다. 조회 대상 설정을 수정하거나 OpenClaw를 업데이트·초기화·재페어링하지 않습니다. |
| 실행 파일·설정·상태·프로필 | 실제 경로와 적용 중인 프로필을 테스트베드 관리 담당자에게 확인합니다. 예전 문서의 경로나 버전을 현재 관측값으로 쓰지 않습니다. |
| Gateway 주소 | Gateway identity·장치 조회에 사용할 실제 `ws://` 또는 `wss://` 주소입니다. MCP 서버의 HTTP 주소와 다릅니다. |
| 인증·사설 CA | 필요한 경우 테스트용 값을 비공개로 전달받습니다. 토큰·비밀번호를 명령 인자, GitHub 댓글, 스크린샷에 넣지 않습니다. |
| 실행 환경 | Git, Python 3, venv, 패키지 다운로드가 필요합니다. 코드 검증 환경은 Python 3.12.14입니다. 설치·네트워크가 막히면 해당 단계의 차단 사유를 전달합니다. |

`skills list`는 OpenClaw 버전에 따라 Gateway RPC와 장치 신원 생성을 일으킬 수 있어 **기본 절차에서 실행하지 않습니다.** Skill은 우선 설치 파일에서 수집합니다. MCP에서는 목록만 요청하며 `tools/call`, `resources/read`, `prompts/get`은 실행하지 않습니다. stdio 조회는 선택한 서버 프로그램을 실제로 시작하므로 기존에 실행을 허용한 테스트 서버만 고릅니다.

## 2. 코드 및 실행 환경 준비

새 폴더를 만들어 정확한 코드 버전을 받습니다. 기존 같은 이름 폴더가 있으면 중단하므로 다른 작업을 덮어쓰지 않습니다.

```bash
(
  set -e
  SCANNER_SETUP_DIR="$HOME/agentscope-ova-check-20261119"
  if [ -e "$SCANNER_SETUP_DIR" ]; then
    printf '기존 폴더가 있습니다. 새 폴더 이름을 정한 뒤 다시 진행하세요.\n' >&2
    exit 1
  fi
  git clone --single-branch --branch feature/scanner-config \
    https://github.com/pbh0330/2026-Agent_Scope.git "$SCANNER_SETUP_DIR"
  cd "$SCANNER_SETUP_DIR"
  git switch --detach 55db6a39a275ae5b10eaf2ad3c77d699acce24c7
  cd asset-scanner
  python3 -m venv .venv-ova
  .venv-ova/bin/python -m pip install -r requirements.txt
  .venv-ova/bin/python -m pip check
  printf 'SETUP_OK\n'
)
```

**`SETUP_OK`가 나왔을 때만** 다음 단계로 갑니다. 문서는 나중에 추가됐지만 실행 코드는 위 SHA로 고정하므로 테스트 도중 브랜치가 바뀌어도 기준은 같습니다. Windows용 `requirements-live-lock.txt`는 사용하지 않습니다.

## 3. 검증 환경 설정 및 실행 기록 준비

이후 명령은 **같은 Bash 터미널**에서 실행합니다. 아래 예시 경로를 그대로 사용하지 말고 VM에서 확인한 실제 값으로 설정합니다. 프로필이 없으면 빈 문자열을 유지합니다.

```bash
cd "$HOME/agentscope-ova-check-20261119/asset-scanner"
SCANNER_PY="$PWD/.venv-ova/bin/python"
SCANNER_ROLE='gateway'                        # Node VM에서는 node
SCANNER_CONFIG='/실제/설정/openclaw.json'
SCANNER_STATE_DIR='/실제/OpenClaw/상태폴더'
SCANNER_PROFILE=''                            # 실제 --profile 이름, 미사용 시 비움
SCANNER_WORKSPACE=''                          # 실제 workspace를 알 때만 입력
SCANNER_INSTALL_ROOT=''                       # 실제 OpenClaw 패키지 루트를 알 때만 입력
SCANNER_GATEWAY_URL=''                        # Gateway VM에서는 실제 ws(s) 주소 입력
SCANNER_OPENCLAW_BIN="$(type -P openclaw)"

prepare_scan() {
  case "$SCANNER_ROLE" in gateway|node) ;; *) printf '역할을 확인하세요.\n'; return 1;; esac
  [ -x "$SCANNER_PY" ] && [ -x "$SCANNER_OPENCLAW_BIN" ] || {
    printf 'Python 또는 OpenClaw 실행 파일을 찾지 못했습니다.\n'; return 1;
  }
  [ -f "$SCANNER_CONFIG" ] && [ -d "$SCANNER_STATE_DIR" ] || {
    printf '실제 설정 파일과 상태 폴더를 입력하세요.\n'; return 1;
  }
  [ "$(git rev-parse HEAD)" = '55db6a39a275ae5b10eaf2ad3c77d699acce24c7' ] || {
    printf '2절의 코드 기준 SHA와 다릅니다. 기준을 확인하세요.\n'; return 1;
  }
  case "$SCANNER_CONFIG:$SCANNER_STATE_DIR" in /*:/*) ;; *) printf '절대 경로가 필요합니다.\n'; return 1;; esac
  SCANNER_REGISTRY='mcp.servers'
  [ "$SCANNER_ROLE" != node ] || SCANNER_REGISTRY='nodeHost.mcp.servers'
  umask 077
  SCANNER_OUT="$(mktemp -d "/tmp/agentscope-ova-${SCANNER_ROLE}-XXXXXXXX")" || return 1
  SCANNER_DIRECT=(--openclaw-bin "$SCANNER_OPENCLAW_BIN"
    --config-path "$SCANNER_CONFIG" --state-dir "$SCANNER_STATE_DIR"
    --openclaw-timeout 60)
  [ -z "$SCANNER_PROFILE" ] || SCANNER_DIRECT+=(--profile "$SCANNER_PROFILE")
  printf 'step\texit_code\tfinished_utc\n' > "$SCANNER_OUT/exits.tsv"
  git rev-parse HEAD > "$SCANNER_OUT/code-sha.txt"
  "$SCANNER_PY" --version > "$SCANNER_OUT/python-version.txt" 2>&1
  "$SCANNER_PY" -m pip freeze > "$SCANNER_OUT/dependencies.txt"
  printf '%s\n' "$SCANNER_ROLE" > "$SCANNER_OUT/vm-role.txt"
  printf 'READY — 결과 폴더: %s\n' "$SCANNER_OUT"
}
prepare_scan
```

`READY`가 나와야 진행합니다. 실제 실행 파일이 PATH에 없으면 `SCANNER_OPENCLAW_BIN`에 기존 실행 파일의 절대 경로를 넣고 준비를 다시 합니다. `SCANNER_INSTALL_ROOT`는 실행 파일 경로가 아니라 manifest·skills 등이 있는 패키지 폴더입니다. 모르면 비워 둡니다.

- `--dev`로 운영 중이면 `SCANNER_DIRECT`의 `--profile` 대신 `--dev`를 사용합니다. `OPENCLAW_HOME`을 별도로 쓰면 `SCANNER_DIRECT+=(--openclaw-home '/실제/홈')`을 추가합니다.
- 직접 조회는 터미널의 OpenClaw 범위·인증 환경변수를 전부 넘기지 않습니다. 실제 운영에 필요한 변수만 `SCANNER_DIRECT+=(--pass-env OPENCLAW_GATEWAY_TOKEN)`처럼 **이름으로** 추가합니다. 값은 기존 환경이나 비공개 입력을 사용합니다. 다른 필수 변수도 같은 방식입니다.
- `$include`가 설정 폴더 밖에 있으면 실제 `OPENCLAW_INCLUDE_ROOTS`를 확인합니다. 임의로 `/` 전체를 허용하지 않습니다. 직접 조회에 필요한 경우 이 변수도 `--pass-env OPENCLAW_INCLUDE_ROOTS`로 추가합니다.
- 결과 폴더는 선택한 상태·workspace·설치·추가 허용 경계 **밖**이어야 합니다. 아래 설치 수집이 출력 경계 오류로 거부되면 별도 경계 밖 폴더로 바꿔 준비합니다. `/tmp` 전체를 탐색 대상으로 고르지 않습니다.

실행 기록 함수를 한 번 등록합니다. 명령 인자에 인증값을 넣지 않는 전제이며, 실제 Python 종료 코드를 `exits.tsv`에 기록합니다. 부분 수집이 있어도 다음 검증을 진행하기 위해 함수 자체는 계속 실행됩니다.

```bash
run_scan() {
  local scan_step="$1" scan_rc
  shift
  [[ "$scan_step" =~ ^[a-z0-9][a-z0-9-]{0,63}$ ]] || return 2
  [ ! -e "$SCANNER_OUT/$scan_step.command.txt" ] || {
    printf '이미 실행한 이름입니다. 새 단계 이름을 사용하세요: %s\n' "$scan_step"; return 2;
  }
  printf '%q ' "$SCANNER_PY" "$@" > "$SCANNER_OUT/$scan_step.command.txt"
  printf '\n' >> "$SCANNER_OUT/$scan_step.command.txt"
  if "$SCANNER_PY" "$@" > "$SCANNER_OUT/$scan_step.stdout.log" 2> "$SCANNER_OUT/$scan_step.stderr.log"; then
    scan_rc=0
  else
    scan_rc=$?
  fi
  printf '%s\t%s\t%s\n' "$scan_step" "$scan_rc" "$(date -u +%FT%TZ)" >> "$SCANNER_OUT/exits.tsv"
  printf '%s: exit=%s\n' "$scan_step" "$scan_rc"
  return 0
}
```

## 4. 기본 자산 수집 — VM별 실행

```bash
run_scan 01-version -m asset_scanner.openclaw_direct \
  "${SCANNER_DIRECT[@]}" --query version --output "$SCANNER_OUT/01-version.json"

run_scan 02-config -m asset_scanner \
  --config "$SCANNER_CONFIG" --registry-path "$SCANNER_REGISTRY" \
  --resolve-includes --output "$SCANNER_OUT/02-config.json"

run_scan 03-permission -m asset_scanner.permission_auth \
  --config "$SCANNER_CONFIG" --resolve-includes --output "$SCANNER_OUT/03-permission.json"

SCANNER_INVENTORY=(--state-dir "$SCANNER_STATE_DIR" --config "$SCANNER_CONFIG" --resolve-includes)
[ -z "$SCANNER_WORKSPACE" ] || SCANNER_INVENTORY+=(--workspace-dir "$SCANNER_WORKSPACE")
[ -z "$SCANNER_INSTALL_ROOT" ] || SCANNER_INVENTORY+=(--installation-root "$SCANNER_INSTALL_ROOT")
run_scan 04-installation -m asset_scanner.installation_inventory \
  "${SCANNER_INVENTORY[@]}" --output "$SCANNER_OUT/04-installation.json"

run_scan 05-plugins-direct -m asset_scanner.plugin_skill_assets \
  --config "$SCANNER_CONFIG" --resolve-includes --openclaw-query plugins \
  "${SCANNER_DIRECT[@]}" --output "$SCANNER_OUT/05-plugins-direct.json"
```

| 결과 | 확인할 것 |
|---|---|
| `01-version.json` | 실제 버전·프로필·조회 범위. 근거 문서의 2026.9.6과 달라도 관측 버전을 그대로 보고합니다. |
| `02-config.json` | `servers[]`의 등록키·선언 값·위치·include 출처. `registry_absent`·`server_count: null`은 등록 영역을 찾지 못했다는 뜻이며 서버 0개와 다릅니다. |
| `03-permission.json` | 허용·차단·인증 선언의 원천 항목. 인증 성공이나 최종 실효 권한을 판정한 결과가 아닙니다. |
| `04-installation.json` | `assets.plugins`·`assets.skills`, 설치 경로·출처. 입력한 경계 밖 설치본은 탐색하지 않으므로 0개만 보고 전체 미설치라고 판단하지 않습니다. |
| `05-plugins-direct.json` | 실제 OpenClaw Plugin 목록과 관측 출처. 이 명령은 04번 보고서와 자동 연결하지 않으므로 `runtime_only` 개수를 누락 개수로 해석하지 않습니다. |

`04-installation`과 `05-plugins-direct`는 독립 실행입니다. 설치본과 직접 목록을 연결하려면 실제 manifest 디렉터리를 확인하고 05번 명령에 `--plugin-dir /실제/Plugin/디렉터리`를 반복 지정하여 새 단계 이름으로 실행합니다. 원본 경로가 가려진 출력에서 경로를 추측하지 않습니다. 연결은 ID와 설치 루트가 모두 일치해야 하며, `loaded`·`disabled`는 OpenClaw가 보고한 상태로 구분합니다.

## 5. 실제 Gateway·Node identity와 장치

Gateway VM에서는 실제 Gateway 주소와 선택한 설정·상태·프로필을 확인한 뒤 실행합니다. 주소에는 사용자명·비밀번호·토큰을 넣지 않습니다. 주소나 인증이 미확인이라면 이 단계는 미수행으로 기록합니다.

**OpenClaw 2026.9.6의 devices 인증 제약:** `devices list --url`은 설정·환경변수 인증으로 대체하지 않으므로 `--pass-env OPENCLAW_GATEWAY_TOKEN`만 추가해도 해결되지 않습니다([공식 문서, 고정 버전](https://github.com/openclaw/openclaw/blob/eb377ac59e6c9fd6c7705028034812becf00271b/docs/cli/devices.md)). 기본 절차는 identity에만 `--expect-gateway-url`을 적용하고, devices에는 **선택한 설정의 Gateway로 접속함을 확인한 경우** `--accept-configured-gateway`를 사용합니다. 명시적 URL을 자동 제거하거나 다른 Gateway로 재시도하는 동작은 추가하지 않습니다.

이 방식의 devices 대상은 설정에 위임되며 명시적 URL로 고정한 조회와 다릅니다. 로컬 페어링 상태로 대체될 가능성도 결과의 `observation.gateway_target`에 기록됩니다. 특정 URL과 인증정보를 동시에 전달하는 devices 조회는 현재 인터페이스의 지원 한계이며, 토큰을 명령행에 노출해 우회하지 않습니다.

```bash
if [ "$SCANNER_ROLE" = gateway ] && [ -n "$SCANNER_GATEWAY_URL" ]; then
  run_scan 06-identity-a -m asset_scanner.node_gateway_identity \
    "${SCANNER_DIRECT[@]}" --expect-gateway-url "$SCANNER_GATEWAY_URL" \
    --query-gateway-identity gateway --output "$SCANNER_OUT/06-identity-a.json"
  run_scan 06-identity-b -m asset_scanner.node_gateway_identity \
    "${SCANNER_DIRECT[@]}" --expect-gateway-url "$SCANNER_GATEWAY_URL" \
    --query-gateway-identity gateway --output "$SCANNER_OUT/06-identity-b.json"
  run_scan 07-devices -m asset_scanner.device_inventory \
    "${SCANNER_DIRECT[@]}" --accept-configured-gateway \
    --query-devices --output "$SCANNER_OUT/07-devices.json"
elif [ "$SCANNER_ROLE" = node ]; then
  run_scan 06-identity-a -m asset_scanner.node_gateway_identity \
    "${SCANNER_DIRECT[@]}" --query-node-identity node --output "$SCANNER_OUT/06-identity-a.json"
  run_scan 06-identity-b -m asset_scanner.node_gateway_identity \
    "${SCANNER_DIRECT[@]}" --query-node-identity node --output "$SCANNER_OUT/06-identity-b.json"
else
  printf 'Gateway 주소 미확인으로 identity·devices 미수행\n' >> "$SCANNER_OUT/not-performed.txt"
fi
```

두 identity 결과에서 같은 출처의 식별값이 유지되는지 비교합니다. 단순 재조회 확인이며 재시작·복제·재설치 후의 영속성 검증은 아닙니다. 장치의 `paired`·`pending`, `clientId`·`clientMode`를 구분합니다. 페어링 기록만으로 현재 연결 상태나 공통 자산 ID를 확정하지 않습니다.

## 6. 실제 MCP 서버의 네 목록 조회

`02-config.json`과 VM의 실제 설정을 대조해 **등록키 하나**를 고릅니다. 조회 가능한 원천은 선택한 설정 영역의 서버 선언입니다. Plugin manifest에만 있는 서버를 임의로 설정에 옮겨 원래 환경의 성공으로 보고하지 않습니다.

아래 두 방식 중 대상에 맞는 **하나**를 실행합니다. 다른 서버도 검사하려면 등록키와 `SCANNER_TAG`를 바꿉니다. 태그는 파일 이름용이므로 `stdio01`, `https01` 같은 짧은 일반 문자열을 쓰고, 등록키 자체를 파일 이름으로 쓰지 않습니다.

### A. stdio 서버 — 같은 VM에서 프로그램 실행

설정의 `command`·`args`와 작업 폴더를 먼저 확인합니다. `--allow-launch`는 그 프로그램의 실제 실행을 허용하는 옵션입니다.

```bash
SCANNER_SERVER='실제-등록키'
SCANNER_TAG='stdio01'
run_scan "08-$SCANNER_TAG" -m asset_scanner.live_discovery \
  --config "$SCANNER_CONFIG" --registry-path "$SCANNER_REGISTRY" --resolve-includes \
  --server "$SCANNER_SERVER" --allow-launch --config-scan-ref "$SCANNER_ROLE" \
  --output "$SCANNER_OUT/08-$SCANNER_TAG.json" \
  --catalog-output "$SCANNER_OUT/08-$SCANNER_TAG-tools.json"
```

### B. HTTP·HTTPS 서버 — 설정 주소로 연결

원격 서버는 HTTPS와 정확한 호스트 허용이 필요합니다. 로컬 루프백 HTTP도 지원합니다. 인증 방식은 실제 서버에 맞춰 고릅니다.

```bash
SCANNER_SERVER='실제-등록키'
SCANNER_TAG='https01'
SCANNER_HTTP=(--allow-connect)
# 원격일 때만: 실제 URL의 호스트 이름 또는 IP, 스킴·포트·경로는 제외
SCANNER_HTTP+=(--allow-host '실제.mcp.example')
# 사설 CA를 쓸 때만 주석을 풀고 실제 PEM 파일을 지정
# SCANNER_HTTP+=(--ca-bundle '/실제/ca.pem')
# Bearer 인증을 쓸 때만 아래 세 줄을 실행. 입력은 화면·명령 이력에 남기지 않음
# read -r -s -p '테스트용 Bearer 토큰: ' SCANNER_MCP_TOKEN
# printf '\n'
# export SCANNER_MCP_TOKEN
# SCANNER_HTTP+=(--bearer-env SCANNER_MCP_TOKEN)

run_scan "08-$SCANNER_TAG" -m asset_scanner.live_discovery \
  --config "$SCANNER_CONFIG" --registry-path "$SCANNER_REGISTRY" --resolve-includes \
  --server "$SCANNER_SERVER" "${SCANNER_HTTP[@]}" --config-scan-ref "$SCANNER_ROLE" \
  --output "$SCANNER_OUT/08-$SCANNER_TAG.json" \
  --catalog-output "$SCANNER_OUT/08-$SCANNER_TAG-tools.json"
unset SCANNER_MCP_TOKEN
```

`X-Api-Key` 같은 인증이면 같은 비공개 입력 방식으로 환경변수를 만들고 `--auth-header-env X-Api-Key=SCANNER_MCP_TOKEN`을 씁니다. Bearer와 중복 지정하지 않습니다. 인증 헤더의 `${VAR}` 대체는 지원하지만 **모든 환경변수·SecretRef를 일반적으로 해석하지는 않습니다.** `unresolved_reference`이면 원천을 바꿔 성공시키지 말고 거부 사유를 남깁니다.

기본 연결 방식은 `auto`입니다. `protocol.negotiated_protocol_version`을 기록하고 서버가 선택한 버전을 확인합니다. 지원 파서는 2025-11-25·2026-07-28이며, 맞추기 위해 OpenClaw나 SDK를 임의 교체하지 않습니다. OAuth 로그인 흐름·구형 SSE는 지원 범위 밖입니다. TLS 검증 해제나 리다이렉트 우회는 하지 않습니다.

| 확인 위치 | 기록할 내용 |
|---|---|
| `protocol` | 실제 협상 버전, 연결 방식 |
| `lists.tools`, `lists.resources`, `lists.resource_templates`, `lists.prompts` | 각 목록의 상태·개수·문제. 서버가 해당 능력을 제공하지 않을 수도 있음 |
| `complete` + 0개 | 끝까지 읽은 빈 목록 |
| `unsupported` | 첫 목록 응답이 메서드 미지원 오류였음 |
| `not_performed` | 요청하지 않았거나 응답을 얻지 못함. 빈 목록·미지원으로 바꾸지 않음 |
| `partial`·`failed` | 일부만 읽었거나 읽지 못함. 저장된 개수를 전체 개수로 사용하지 않음 |

Tool 카탈로그 파일이 만들어졌으면 선언과 연결도 확인합니다. `SCANNER_TAG`는 방금 조회한 값을 유지합니다.

```bash
if [ -f "$SCANNER_OUT/08-$SCANNER_TAG-tools.json" ]; then
  run_scan "09-link-$SCANNER_TAG" -m asset_scanner.linking \
    --config-scan "$SCANNER_ROLE=$SCANNER_OUT/02-config.json" \
    --catalog "$SCANNER_TAG=$SCANNER_OUT/08-$SCANNER_TAG-tools.json" \
    --subject "$SCANNER_ROLE=$SCANNER_ROLE" --output "$SCANNER_OUT/09-link-$SCANNER_TAG.json"
fi
```

설정 수집이 `${VAR}` 등 미해석 참조로 `partial`이면 전체 연결 보고서도 `config_scan_not_complete`로 `partial`일 수 있습니다. 이때 `collection.counts.linked`와 개별 연결 결과는 별도로 확인합니다. 전체 `partial`을 연결 실패로 해석하거나 경고를 없애기 위해 설정 파일에 인증값을 직접 쓰지 않습니다.

`--subject`는 검증 수행자가 입력한 역할입니다. 같은 이름만으로 서버를 합치지 않고 `config_scan_ref`·등록 영역·등록키로 연결되는지 확인합니다. 여기의 라벨은 공통 ID가 아닙니다. 이 연결 모듈은 Tool 카탈로그 연결이며 Resource·Prompt까지 통합했다고 보고하지 않습니다.

## 7. 선택 원천 추가 검증

경로를 실제로 확인한 항목만 실행합니다. 없거나 위치·형식을 모르면 미수행과 사유를 기록합니다. DB·인증 원문을 공유할 필요는 없습니다. 아래 명령은 읽기 전용 스냅샷으로 지정 원천을 읽습니다.

| 대상 | 선택 기준 |
|---|---|
| 설치 인덱스·상태 DB | 실제 버전과 원천 확인 후 지정. 지원 테이블·형식 밖 자료는 미지원으로 기록 |
| 인증 메타데이터 | issuer·resource·scope·만료 등만 수집. 계정 소유자·인증값·인증값 해시는 공유하지 않음 |
| Linux PID | 테스트베드 관리 담당자가 실제 OpenClaw 프로세스라고 확인한 PID. 이름 검색 결과만으로 소속을 확정하지 않음 |
| systemd 유닛 | 선택 파일의 `User`·`Group` 등 선언. drop-in을 포함한 최종 적용값이나 실제 실행 계정과 구분 |

각 블록의 예시 경로·PID를 바꿔 해당하는 것만 실행합니다.

```bash
# 실제 Plugin 인덱스 JSON이 있을 때. DB를 읽는다면 --plugin-index-json 대신 --state-db 사용 가능
run_scan 10-install-index -m asset_scanner.installation_inventory \
  "${SCANNER_INVENTORY[@]}" --plugin-index-json '/실제/plugin-index.json' \
  --output "$SCANNER_OUT/10-install-index.json"

# 실제 상태 DB가 있을 때: MCP OAuth 원천. 읽은 범위만으로 인증 전체 유무를 판정하지 않음
run_scan 11-auth-db -m asset_scanner.auth_metadata \
  --state-db '/실제/openclaw.sqlite' --output "$SCANNER_OUT/11-auth-db.json"

# 모델 계정 namespace는 별도 선택. 실제 테스트용 계정 자료가 있을 때만 실행
run_scan 12-model-account -m asset_scanner.auth_metadata \
  --model-account-db '/실제/openclaw.sqlite' --output "$SCANNER_OUT/12-model-account.json"

# 실제 PID 확인 후 숫자 변경. OpenClaw 실행 파일은 파일 형식 근거만 관측
run_scan 13-process -m asset_scanner.process_identity \
  --pid 12345 --entry-file "$SCANNER_OPENCLAW_BIN" --output "$SCANNER_OUT/13-process.json"

run_scan 14-service -m asset_scanner.service_identity \
  --systemd-unit '/실제/openclaw.service' --output "$SCANNER_OUT/14-service.json"
```

DB 인증 항목이 0개이면 선택한 테이블·namespace의 0개입니다. 다른 저장소의 인증정보가 없다는 뜻이 아닙니다. 다른 인증 원천을 확인한 경우 `auth_metadata --auth-profiles-json FILE` 또는 `--mcp-oauth-json FILE`을 사용합니다. 토큰 claim 해석은 이번 기본 절차에서 켜지 않습니다.

## 8. 결과 판정 및 오류 기록

- **필수 확인:** 버전·실행 범위, 설정 선언과 출처, Plugin/Skill 설치 경계, Permission/Auth 선언, 역할별 identity, 선택 MCP 서버의 네 목록, Tool 선언 연결입니다. 실행하지 못한 항목은 사유를 남깁니다.
- **성공 기준:** 실제 원천의 값·위치와 출력이 일치하고, 조회 대상·협상 버전·목록 완전성·실패 이유가 구분됩니다. `complete`가 실제 인증 성공·Agent 노출·도구 호출 가능을 뜻하지 않습니다.
- 일반 수집 CLI의 종료 코드: `0` 완전 수집, `1` 부분 수집, `2` 인자 문제, `3` 수집 실패, `4` 저장 문제. **`openclaw_direct`의 `1`은 조회 실패가 있다는 뜻**이므로 JSON의 실패 코드를 확인합니다. `exits.tsv`에 기록된 실제 종료 코드를 결과에 포함합니다.
- 실패하면 해당 단계의 `.stderr.log`, `.stdout.log`, `.json`과 실행 기록을 보존합니다. 인증 거부·TLS·접속 실패·지원하지 않는 명령/응답·include 경계를 구분하고, 원문에 비밀값이 있으면 공유 전 가립니다.
- 오래된 문서의 고정 자산 개수와 맞추기 위해 설정·서버를 추가하지 않습니다. 정정된 정답 목록이 확인되기 전에는 **수집률·누락률을 계산하지 않습니다.**
- 재시작·복제·재페어링 후 identity 유지, 설치본 변조·서명 신뢰 판정, 공통 ID·실효 권한 확정은 이번 기본 테스트 범위가 아닙니다.

## 9. 검증 결과 정리 및 공유

`$SCANNER_OUT` 안의 **생성된 결과만** 공유 대상으로 정리합니다. 원본 설정·SKILL 본문·DB/WAL/SHM·토큰·개인키·가상환경은 포함하지 않습니다. 결과는 가림 기능을 거치지만 출처 경로·일반 문자열에 개인정보가 남을 수 있으므로 공개 PR에는 검증 요약을 기록하고, 전체 결과는 팀의 비공개 공유 경로를 사용합니다. 검증 수행자는 결과와 미수행 사유를 정리하고, 스캐너 개발 담당자는 해당 기록을 원천 대조와 오류 분석에 사용합니다.

같은 터미널에서 종료 코드 표를 확인하고 결과 ZIP을 만듭니다. 기존 동명 ZIP은 덮어쓰지 않습니다.

```bash
cat "$SCANNER_OUT/exits.tsv"
"$SCANNER_PY" - "$SCANNER_OUT" <<'PY'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import sys
root = Path(sys.argv[1])
target = root.with_suffix('.zip')
with ZipFile(target, 'x', ZIP_DEFLATED) as archive:
    for item in sorted(root.iterdir()):
        if item.is_file() and not item.is_symlink():
            archive.write(item, item.name)
print(target)
PY
```

검증 결과는 다음 양식에 따라 VM별로 작성합니다. 미수행 항목은 통과 수에 포함하지 않습니다.

```text
- 코드: 82c7579
- VM 역할 / OS / Python / OpenClaw 실제 버전:
- 프로필·설정·상태 경로 확인 여부:
- 설정 수집: 상태 / 서버 수 또는 registry_absent / include 문제:
- Plugin·Skill: 지정 탐색 경계 / 각 개수 / 직접 목록과 차이:
- Permission/Auth: 수집 원천 / 상태 / 미지원 원천:
- identity: 첫 조회·재조회 성공 여부 / 같은 출처 값 유지 여부:
- devices: 조회 성공 여부 / paired·pending / clientId·clientMode 확인 여부:
- MCP 서버별: 등록키 / stdio·HTTP·HTTPS / 협상 버전:
  - Tool: 상태·개수
  - Resource: 상태·개수
  - ResourceTemplate: 상태·개수
  - Prompt: 상태·개수
- Tool 선언 연결: 성공 / 불가 사유:
- 추가 원천: 설치 인덱스·DB·실행 계정·유닛 중 확인한 것:
- 미수행·실패: 단계 이름 / 실제 종료 코드 / 오류 코드 / 사유:
- 결과 ZIP: 팀 비공개 공유 위치
```

검증이 중단된 경우 마지막 실행 단계·미수행 범위·중단 사유를 기록하여 공유합니다. 실제 환경의 경로·버전·응답 차이에 대한 보완 후, 정정된 정답 목록과 수집률 대조는 별도 단계로 진행합니다.


## 10. 2026-11-19 OVA 실행 결과 및 후속 보완

### 근거와 검증 범위

- 제공된 `scan-1119.zip` 안의 최초 Gateway·Node 실행 ZIP과 Gateway 재실행 ZIP 2개를 분석했습니다. 네 실행 묶음의 `code-sha.txt`는 모두 `82c7579`이고, 단계별 판정은 `exits.tsv` 및 결과 JSON과 대조했습니다.
- 실행 환경: Ubuntu 24.04, Python 3.12.3, OpenClaw 2026.9.6 (eb377ac), MCP SDK 2.3.0. 원격 VM 접속·재실행은 문서 작성 환경에서 수행하지 않았습니다.
- OVA SNAP-2-P2를 VirtualBox로 가져온 **파생 환경**입니다. IP·hosts·Node 접속 대상 변경과 Gateway의 추가 Plugin 설치가 실행 메모에 기록되어 있습니다. 원본 OVA 그대로의 검증으로 취급하지 않습니다.
- Node VM 응답 중단 후 재시작했다는 실행 메모와 담당자 보고가 있습니다. 초기 `network_error`는 ZIP에 남아 있지만, `No route to host` 및 메모리 원인에 대한 진단 원문은 포함되어 있지 않습니다. VM 메모리 부족을 확정 원인으로 쓰지 않습니다.

### 실제 목록 조회 결과

| VM·서버 | 전송·협상 버전 | Tool | Resource | ResourceTemplate | Prompt |
|---|---|---|---|---|---|
| Gateway · fs-workspace | stdio · 2025-11-25 | complete 14 | not_performed | not_performed | not_performed |
| Node · kg-memory | stdio · 2025-11-25 | complete 9 | complete 1 | complete 0 (빈 목록) | not_performed |
| Gateway · inventory-remote (재실행) | HTTPS·사설 CA·Bearer · 2025-11-25 | complete 2 | complete 1 | complete 0 (빈 목록) | complete 1 |
| Node · demo-everything | 실행 전 거부 · 협상 없음 | not_performed | not_performed | not_performed | not_performed |

- 앞의 두 서버에서 미수행한 목록은 `capability_not_declared`입니다. 개별 Tool 카탈로그는 complete이나 전체 네 목록 보고서는 미수행 목록 때문에 partial입니다. 미수행을 빈 목록이나 실제 메서드 미지원 응답으로 바꾸지 않습니다.
- inventory-remote의 이전 두 실행은 연결 실패였고 세 번째는 종료 코드 0입니다. TLS 인증서 체인·호스트 이름 검증이 켜진 상태에서 네 목록이 완전 수집됐습니다. HTTPS 수집 기능 자체의 실패로 분류하지 않습니다.
- demo-everything은 `env.EVERYTHING_DEMO_KEY`의 미해석 참조 때문에 거부됐으며, 보낸 목록 요청은 0개입니다. 해당 서버의 수집은 아직 미완료입니다.
- 성공한 세 조회의 결과는 금지된 자산 실행 요청 카운터 0을 기록합니다. 목록 수집 성공은 Tool 실행·Resource 본문 읽기·Prompt 실행 검증이 아닙니다.

### 기타 수집 결과와 판정

| 항목 | 실제 기록 | 해석·후속 작업 |
|---|---|---|
| devices | 명시 URL: 실패, URL+환경변수 전달: 실패, 설정 위임: complete·1개·종료 코드 0 | 5절의 devices 명령을 설정 위임 방식으로 정정. 명시 URL 인증 지원이 완료된 것은 아님 |
| 장치 원천 | paired, clientId node-host, clientMode node, reported connected true | 원천이 보고한 상태. 관측 시점 이후의 연결·공통 ID·복제 후 동일성은 확정하지 않음 |
| Gateway·Node identity | 두 VM 모두 두 차례 complete, device_id·public_key 각각 동일 | 재조회 일치 확인. 재시작 후 두 값 유지 검증은 별도 대기 |
| 설정 수집 | 각 VM 2개 선언, 각각 partial | inventory-remote Authorization 참조와 demo-everything env 참조를 보존. 인증값 해석은 하지 않음 |
| Tool 선언 연결 | fs-workspace·kg-memory·inventory-remote 각 linked 1 | 세 보고서 모두 설정 수집 partial을 이어받음. 개별 연결은 성공 |
| Permission/Auth | Gateway 4개, Node 2개 원천 항목 complete | 지원 설정의 선언 수집. 최종 실효 권한·모든 인증 저장소의 완전성 판정은 아님 |
| 설치 원천 | Gateway Plugin 2·Skill 52 (partial), Node Plugin 0·Skill 53 (complete) | 지정 경계 내 결과. 아래의 번들 탐색 경로 누락을 발견하여 후속 수정 |
| 직접 Plugin 목록 | Gateway 66개 (bundled 63·config 1·global 2), Node bundled 63개 | manifest를 05번 실행에 전달하지 않아 전부 runtime_only. 누락 수로 그대로 사용하지 않음 |
| 프로세스 UID/GID | 두 VM 모두 선택 PID 관측 complete | 함께 지정한 openclaw.mjs 파일은 entry_not_regular_or_linked여서 보고서 전체 partial |
| systemd 유닛 | 두 VM 모두 complete, declaration_count 0 | 선택 파일을 읽었으나 지원하는 실행 계정 선언은 없었음. 계정 관측은 PID 결과와 구분 |
| 인증 DB | 두 VM 모두 complete, item_count 0 | 선택한 MCP 인증 원천에서 읽힌 항목 0개. 모델 계정·전체 인증 유무를 판정하지 않음 |

### 확인된 누락과 남은 제약

1. **번들 Plugin 탐색 경로:** 직접 목록의 bundled 63개는 `/usr/lib/node_modules/openclaw/dist/extensions` 아래 경로를 보고합니다. 기존 스캐너는 설치 루트의 `extensions`만 후보로 만들었으므로 `dist/extensions`를 추가했습니다. 경계·링크·출력 덮어쓰기 거부와 동명 복수 설치 보존은 유지합니다. 수정 후 실제 VM의 설치 개수·연결 결과는 재검증해야 합니다.
2. **외부 설치와 진입 파일:** Gateway의 선택 경계 밖·링크 경로 이슈는 기록됐으나 이슈에 경로가 없어 token-guard와 일대일로 확정할 수 없습니다. diagnostics-otel은 `index.ts` 관측이 실패하고 `dist/index.js`는 성공했습니다. 개발용·실행용 진입점의 선택 규칙과 실제 파일 상태를 추가 확인합니다.
3. **미해석 참조:** HTTP 인증 헤더 대체로 inventory-remote 조회는 성공했습니다. stdio env의 일반 참조 해석·대체는 현재 미지원이므로 demo-everything은 별도 보완과 재검증 대상입니다. 경고를 없애기 위한 complete 강제 표시는 하지 않습니다.
4. **이번에 미수행:** skills 직접 조회, 설치 인덱스, 모델 계정 namespace, 서명·무결성 신뢰 판정, 재시작·복제·재페어링 후 identity 유지, 정답 대조·수집률 계산입니다.

후속 경로 수정은 자동 테스트에서 기존 배치·빌드 배치·복수 설치·링크 거부·CLI 출력 경계를 검증했습니다. 이 결과와 실제 OVA 재검증 결과는 구분합니다.
