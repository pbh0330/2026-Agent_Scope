# OVA 수령 후 OpenClaw 원천 검증 절차 (준비본)

> 상태: **준비본 · 아직 실행하지 않음** · 작성일 2026-11-17 · 스캐너 `feature/scanner-config` (미커밋 수정 포함)
> OVA는 아직 수령 전입니다. 이 문서의 `⟦…⟧`는 **실제 환경을 확인한 뒤 채울 값**이며, 지금은 어떤 값도 확인된 것이 아닙니다.
> "저장 자료 기대값"은 테스트베드가 2026-10-04에 저장한 파일의 값으로, **비교용 참고**일 뿐 OVA에서 관측한 값이 아닙니다.
> 공통 자산 ID 규칙·공통 스키마는 구현·확정하지 않습니다. 결과의 `internal_ref`·순번·라벨은 영속 ID가 아닙니다.

## 0. 이 PC의 준비 상태 (읽기 전용 점검, 2026-11-17 20:46)

원본 기록: `asset-scanner/output/host-check-20261117/host-check.txt`. 프로그램 설치·설정 변경은 하지 않았습니다.

| 항목 | 이 PC | 팀 사양서 요구(`testbed-spec-20260929.md`, `ova-packaging.md`) | 판단 |
|---|---|---|---|
| VMware / VirtualBox | **설치 흔적 없음**(`Program Files\VMware`, `Oracle\VirtualBox`, `ovftool` 모두 없음) | VMware Workstation(가상 하드웨어 v22), OVA 임포트에 `ovftool` | 미설치 |
| 메모리 | 총 7.9GB, 점검 시 여유 1.1GB | tb-gw 6GB + tb-node 4GB = **10GB** | **부족** |
| 디스크 | C: 총 238GB, **여유 8GB**(다른 드라이브 없음) | tb-gw 150GB·tb-node 80GB(실제 OVA는 압축·씬 디스크라 더 작을 수 있으나 **수령 전에는 알 수 없음**) | **부족 가능성 높음** |
| CPU·가상화 | i7-7700HQ 4코어/8스레드, 펌웨어 가상화 **활성**, SLAT 지원 | vCPU 2 + 2 | 가상화는 가능 |
| Hyper-V 상태 | `HypervisorPresent=False`(실행 중 아님), Windows 기능 상태는 권한 때문에 조회 불가 | VMware와 Hyper-V 충돌 가능 | 설치 시 확인 필요 |

**결론**: 이 PC는 가상화 하드웨어는 지원하지만 메모리·디스크가 사양에 못 미쳐 두 VM 동시 구동은 현실적이지 않습니다. 선택지: (a) 사양서의 작업자 PC(Xeon W-2123, RAM 64GB)에서 VM을 구동하고 이 PC에서는 저장된 출력만 분석, (b) 여유 공간·메모리가 충분한 다른 호스트 사용, (c) 외장 디스크 + 한 번에 VM 1대씩(페어링·`devices list`는 두 VM이 필요). **어느 쪽으로 할지는 정해 주세요**(아래 §6).

## 1. 원칙 (모든 단계 공통)

1. **읽기 전용 조회만.** `openclaw`의 초기화·설치·업데이트·페어링·설정 변경 명령, `mcp set/remove`, `tools/call`·`resources/read`·`prompts/get`은 하지 않습니다. 스캐너 직접 조회의 허용 목록은 `version`·`plugins`·`node-identity`·`gateway-identity`와, 동의한 경우의 `skills`뿐입니다([openclaw-direct.md](openclaw-direct.md)).
2. **임포트 직후 스냅샷**을 만들고 그 상태를 보존합니다(원본 보존, 되돌릴 기준). 부팅 순서는 OVA 문서대로 tb-node → tb-gw.
3. **인증값 원문·해시는 출력·로그·식별 입력에 남기지 않습니다.** OVA의 토큰은 더미(`ova-packaging.md` 4절)여도 결과에 쓰지 않습니다. 저장 전 `<DUMMY_TOKEN>`·`Bearer ` 문자열 검색으로 확인합니다.
4. **값의 출처를 구분해 기록합니다**: 사용자 입력 / VM에서 관측 / 저장 자료(기대값) / 미확인.
5. 각 단계의 명령·종료 코드·시각을 `asset-scanner/output/ova-verify-⟦YYYYMMDD⟧/`에 기록합니다(`output/`은 Git 제외).
6. 환경 변경을 일으킬 수 있는 항목(복제·재설치·재페어링·`skills list`)은 **별도 승인 뒤에만** 합니다.

## 2. 실행 방식 (먼저 정할 것)

스캐너의 직접 조회(`openclaw_direct`)는 **스캐너가 실행되는 머신의 `openclaw` 실행 파일**을 `Popen`으로 실행합니다. 원격(SSH) 실행 기능은 없습니다. 그래서 두 방식이 있습니다.

| 방식 | 내용 | 장단점 |
|---|---|---|
| **B. 수동 저장 후 분석(권장)** | VM 안에서 아래 명령을 사람이 실행해 출력을 파일로 저장 → 호스트로 복사 → 스캐너가 **저장된 출력**으로 분석 | 스캐너를 VM에 설치할 필요 없음. 출처는 `observed_from_stored_command_output`이며 관측 시각은 `--observed-at`로 직접 선언 |
| A. VM 안에서 스캐너 실행 | 스캐너를 VM으로 복사해 `--openclaw-bin $(which openclaw)`로 직접 조회 | `observed_from_direct_query`·스캐너 시계 시각이 기록됨. **Ubuntu의 Python(3.12 예상)에서 현재 버전 테스트는 하지 않았음**(과거 별도 Linux 3.12 기록 301개는 현재 결과 아님). 원본 VM에 파일을 더하므로 임포트 사본에서만 |

⟦선택한 방식: B / A⟧ · ⟦스캐너가 실행될 머신과 Python 버전⟧

## 3. 단계별 절차

### 단계 1 — 버전·프로필 확인

| # | 확인 | 명령(읽기 전용) | 기록할 값 | 저장 자료 기대값(참고) |
|---|---|---|---|---|
| 1-1 | OpenClaw 버전 | `openclaw --version` | ⟦버전·커밋⟧ | 2026.9.6 (eb377ac) |
| 1-2 | OS·Node | `cat /etc/os-release`, `node -v` | ⟦OS⟧ ⟦Node⟧ | Ubuntu 24.04.5 LTS, Node v24.21.0 |
| 1-3 | 호스트명·역할 | `hostname` (tb-gw / tb-node) | ⟦호스트명⟧ | tb-gw, tb-node |
| 1-4 | OpenClaw 프로필 | `ls -d ~/.openclaw*`, `env \| grep -c '^OPENCLAW_'`(값은 기록하지 않고 **이름만**), 서비스 유닛에 `--profile`/`--dev` 사용 여부 | ⟦프로필 사용 여부·이름⟧ | 기본 위치 `~/.openclaw`(프로필 없음) |
| 1-5 | 설정·상태 위치 | `ls -l ~/.openclaw/openclaw.json ~/.openclaw/state/` | ⟦설정 파일 경로⟧ ⟦상태 DB 경로⟧ | `~/.openclaw/openclaw.json`, `~/.openclaw/state/openclaw.sqlite` |
| 1-6 | 테스트베드 구성 세트 | OVA 문서상 SNAP-2-P2 상태 확인: `openclaw.json`의 `mcp.servers` 키 | ⟦P0/P1/P2 중 무엇⟧ | P2 (`fs-workspace`, `inventory-remote`) |

판정: 1-1이 2026.9.6과 다르면 이후 결과는 `version_matches_researched_basis: false`로 표시하고 근거 문서와의 일치를 가정하지 않습니다. `--require-openclaw-version 2026.9.6`을 쓰면 불일치 시 조회를 실행하지 않습니다(방식 A).

### 단계 2 — Gateway / Node identity

| # | 확인 | 명령 | 기록할 값 | 저장 자료 기대값(참고) |
|---|---|---|---|---|
| 2-1 | Node identity (tb-node) | `openclaw node identity --json > node-identity.json` | ⟦deviceId⟧ ⟦publicKey⟧ | deviceId `b8cd252a…48da921` |
| 2-2 | Gateway identity (tb-gw) | `openclaw gateway call gateway.identity.get --json --expect-url ⟦ws://127.0.0.1:18789⟧ > gateway-identity.json` | ⟦deviceId⟧ ⟦publicKey⟧ | deviceId `e3e14de2…eddaa4` |
| 2-3 | 접속 대상 | 설정의 `gateway.port`·`bind` | ⟦Gateway URL⟧(방식 A는 `--expect-gateway-url`로 고정 필수) | port 18789, bind lan(설정 사본) |
| 2-4 | 페어링 근거(스캐너 미지원, 수동 저장만) | tb-gw: `openclaw devices list --json > devices-list.json` | ⟦`paired[].deviceId`⟧ | Node deviceId와 일치(저장 자료) |
| 2-5 | 반복 조회 | 2-1·2-2를 **같은 세션에서 2회**, 재부팅 후 1회 | ⟦3회 값 동일 여부⟧ | 시점 간 동일(저장 자료) |
| 2-6 | 복제 후 유지 | OVA 임포트는 곧 VM 복제입니다. 2-1·2-2 값을 **저장 자료와 비교** | ⟦저장 자료와 일치 여부⟧ | OVA 문서는 "장치 신원 유지"로 계획했으나 **확인된 사실이 아님** |

스캐너 실행(방식 B):
```powershell
.\.venv\Scripts\python.exe -m asset_scanner.node_gateway_identity `
  --gateway-identity gw1=⟦gateway-identity.json⟧ --node-identity nd1=⟦node-identity.json⟧ `
  --observed-at gw1=⟦VM에서 명령을 실행한 시각 ISO8601+시간대⟧ --observed-at nd1=⟦…⟧ `
  --output output\ova-verify-⟦날짜⟧\identity.json
```
라벨은 Gateway·Node를 통틀어 유일해야 합니다. 사용자 입력(`--subject id=`)을 쓰면 관측값과 별도 필드로 보존되고 다르면 충돌로 표시됩니다. 같은 `deviceId`가 여러 입력에 있으면 합치지 않고 표시합니다.

### 단계 3 — Plugin / Skill

| # | 확인 | 명령 | 기록할 값 | 저장 자료 기대값(참고) |
|---|---|---|---|---|
| 3-1 | Plugin 목록 | tb-gw: `openclaw plugins list --json > plugins-list.json`(Gateway에 접속하지 않음, [코드]). **현재 저장 자료는 텍스트 표라 이 단계에서 처음 JSON을 확보** | ⟦plugins[].id·rootDir·origin·enabled·status⟧ | `agentscope-asset-catalog`, origin global |
| 3-2a | 진입점·의존성 | 3-2에서 복사한 `package.json`: `openclaw.extensions`·`runtimeExtensions`·`dependencies` | ⟦진입점 경로·의존성 이름·버전 범위⟧(스캐너 결과 `package.entry_points`·`package.dependencies`와 대조). 진입점 파일 자체는 읽거나 실행하지 않음 | GitHub 사본: `./index.js`, peer `openclaw 2026.9.6` |
| 3-2 | 설치된 manifest 원본 | `⟦~/.openclaw/extensions/agentscope-asset-catalog/⟧`의 `openclaw.plugin.json`·`package.json`을 호스트로 복사, `sha256sum` | ⟦해시⟧ ⟦GitHub 고정 사본과의 차이⟧ | 아래 §4의 GitHub 사본과 `description`이 다름(저장된 `plugin inspect` 기준) |
| 3-3 | 같은 id·이름의 복수 설치본 | `ls ~/.openclaw/extensions/ ~/.openclaw/plugins 2>/dev/null` 등 설치 위치별로 같은 `id` 존재 여부 | ⟦복수 설치본 유무와 각 `rootDir`⟧ | 없음(저장 자료에는 1개) |
| 3-4 | Skill 디렉터리 | tb-gw `⟦~/workspace/skills⟧`, tb-node `⟦~/.openclaw/skills⟧`의 `SKILL.md` 복사(본문 포함이 부담이면 frontmatter만) | ⟦Skill 이름·설치 경로⟧ | gw `inventory-owner-report`, node `node-disk-report`·`node-notes-summary` |
| 3-5 | Skill 목록(**기본 거부**) | `openclaw skills list --json`은 Gateway RPC를 호출하고 **로컬 장치 신원을 새로 만들어 페어링 요청으로 이어질 수 있음**([코드]). 승인 없이는 실행하지 않음 | ⟦실행 여부와 승인자⟧ | 저장 자료는 텍스트 표 |

스캐너 실행(방식 B):
```powershell
.\.venv\Scripts\python.exe -m asset_scanner.plugin_skill_assets `
  --plugin-dir ⟦복사한 플러그인 폴더⟧ --skills-dir ⟦복사한 skills 폴더⟧ `
  --plugins-list-json ⟦plugins-list.json⟧ --config ⟦복사한 openclaw.json⟧ `
  --output output\ova-verify-⟦날짜⟧\plugin-skill.json
```
`plugins list`의 `id`+`rootDir`이 디렉터리 입력과 모두 맞을 때만 런타임 관측과 연결하고, 같은 `id`·다른 경로는 `runtime_candidates_not_linked`로 남습니다. 경로는 **복사본의 경로**이며 VM 설치 경로가 아닙니다(`runtime_observation`의 `rootDir`가 VM 경로).

### 단계 4 — MCP 서버 목록 조회

| # | 확인 | 명령·방법 | 기록할 값 | 저장 자료 기대값(참고) |
|---|---|---|---|---|
| 4-1 | 설정 선언 수집 | VM의 `openclaw.json`을 **복사해** `python -m asset_scanner --config <복사본> --output …`; tb-node는 `--registry-path nodeHost.mcp.servers`. 복사 전 파일은 변경하지 않음. **`$include`를 쓰는지 먼저 확인**(`grep -c '\$include'`)하고 쓰면 포함 파일도 **같은 상대 구조로** 함께 복사해 `--resolve-includes`를 추가(최상위 설정 폴더 밖 파일은 읽지 않음). 쓰지 않으면 옵션 불필요 | ⟦등록 키·`declaration_pointer`⟧ | gw: fs-workspace·inventory-remote, node: kg-memory·demo-everything |
| 4-2 | 환경변수 참조 | 설정의 `${…}`는 **해석하지 않고** `unresolved`로 남아 `partial`(종료 코드 1)이 되는 것이 정상. 단 4-5의 실제 조회에서는 같은 헤더의 값을 환경변수 옵션으로 제공하면 선언 참조를 대체함(아래) | ⟦`unresolved` 이름 목록⟧ | `INVENTORY_MCP_TOKEN`, `EVERYTHING_DEMO_KEY` |
| 4-3 | Plugin 선언 서버 | 3-2의 manifest로 `--plugin-manifest <복사본>` | ⟦`mcpServers` 키⟧ | asset-catalog (stdio, `node ./mcp-server.mjs`) |
| 4-4 | CLI 대조(수동 저장만) | `openclaw mcp list`(OpenClaw 관리 서버만 표시), `openclaw mcp probe --json`(투영 이름 포함). **`mcp show`는 환경변수를 풀어 출력한다는 보고가 있어 실행하지 않음** | ⟦서버 수·투영 Tool 이름⟧ | `fs-workspace__list_directory` 등 |
| 4-5 | 실제 목록 조회 | **tools/list·resources/list·resources/templates/list·prompts/list만.** 아래 제약 참고 | ⟦서버별 `collection_status`·개수⟧ | Tool 40·Resource 11(템플릿 2)·Prompt 5(정답 목록 P2) |
| 4-6 | 연결 | `linking`으로 등록 키 ↔ 목록 결과 | ⟦linked/unlinked 수⟧ | 5/5(manifest 포함, 저장 자료) |

4-5 제약:
- `live_discovery`는 한 번에 **서버 하나**를 `--server <키>`로 고르고 `--allow-launch`/`--allow-connect`를 명시해야 합니다. 설정을 자동으로 전부 실행하지 않습니다.
- **stdio 서버(fs-workspace·kg-memory·demo-everything·asset-catalog)는 스캐너가 실행되는 머신에서 명령을 띄웁니다.** 호스트에서 돌리면 VM이 아니라 호스트에서 `mcp-server-filesystem` 등을 실행하려 하므로 맞지 않습니다. VM 안에서 실행(방식 A)하거나, 서버가 이미 광고하는 목록을 사람이 저장해 `tools_catalog`·`resources_prompts`로 분석(방식 B)하세요. 저장 형식은 `testbed/tools/mcp-advertised.mjs`의 `*.advertised.json`을 `mcp-lists-capture`로 감싸면 됩니다(변환 스크립트: `output/testbed-stored-20261117/convert_advertised.py`).
- **`inventory-remote`(HTTPS, `https://tb-node:8443/mcp`)만 호스트에서 접속할 수 있습니다.** 필요한 값: ⟦호스트에서 `tb-node`가 해석되는 IP·hosts 항목⟧, ⟦실습용 CA 인증서 파일(`--ca-bundle`)⟧, ⟦`--allow-host tb-node`⟧, ⟦Bearer 토큰을 담은 환경변수 이름(`--bearer-env`; 값은 기록하지 않음)⟧. TLS 검증은 끌 수 없습니다. 이 서버는 **실제 원격 서버에 대한 첫 HTTPS 조회**가 됩니다(지금까지는 로컬 시험 서버만).
- **인증 전달(수정됨)**: P2 설정의 `headers.Authorization: Bearer ${INVENTORY_MCP_TOKEN}`처럼 선언된 헤더는 `--bearer-env ⟦환경변수 이름⟧`(또는 `--auth-header-env Authorization=⟦이름⟧`)을 주면 **그 값으로 대체**되어 조회됩니다. 선언 참조 이름과 옵션 환경변수 이름이 다르면 `ref_name_matches_provided_env: false`로 기록됩니다(허용). 옵션 없이 실행하면 `unresolved_reference`로 거부됩니다. 이 서버의 `url`·`command`·다른 헤더에 참조가 있으면 거부됩니다.
- 설정이 `$include`로 나뉜 서버를 조회할 때는 `--resolve-includes`를 붙입니다(해석하지 못하면 거부).
- 서버 안내문·설명은 비신뢰 데이터입니다. 결과는 `definition_altered`·`alteration`으로 가림·변경 여부와 사유를 확인합니다.

```powershell
# 예: 원격 HTTPS 서버 하나 (실행 전 §1 원칙 확인, 값은 확인 후 채움)
$env:⟦TOKEN_ENV_NAME⟧ = "⟦OVA 문서의 더미 토큰 — 결과·로그에 쓰지 않음⟧"
.\.venv\Scripts\python.exe -m asset_scanner.live_discovery --config ⟦복사한 tb-gw openclaw.json⟧ `
  --server inventory-remote --allow-connect --allow-host ⟦tb-node⟧ --ca-bundle ⟦ca.crt⟧ `
  --bearer-env ⟦TOKEN_ENV_NAME⟧ --output output\ova-verify-⟦날짜⟧\live-inventory-remote.json
```

## 4. 선행 자료: manifest 사본 검증 결과 (OVA 수령 전, 완료)

GitHub 고정 커밋의 **사본**을 검증한 것이며 **VM에 설치된 파일을 검증한 것이 아닙니다.** 상세는 [qa-fix-and-source-validation-20261117.md 3.6절](qa-fix-and-source-validation-20261117.md). 단계 3-2·4-3에서 설치본으로 같은 검증을 되풀이해 차이를 기록합니다.

### 단계 5 — 정책·업데이트·승인 문서 (선택)

| # | 확인 | 방법 | 기록할 값 | 저장 자료 기대값(참고) |
|---|---|---|---|---|
| 5-1 | 정책·인증·업데이트 선언 | 복사한 `openclaw.json`으로 `python -m asset_scanner.permission_auth --config <복사본> [--resolve-includes] --output …` | ⟦`items[]` 카테고리·경로⟧ | Gateway: `tools.profile`, `gateway.auth.mode/token`(값 비저장), `update.checkOnStart`; Node: `update.checkOnStart`, `nodeHost.autoUpdate.enabled` |
| 5-2 | 허용·차단(allow/deny) 선언 | 위 결과에 `tool_policy` allow/deny 항목이 있는지 | ⟦있음/없음⟧ | 저장 자료에는 없음. **최종 실효 권한은 계산하지 않음** |

## 5. 채워야 할 값 모음

| 값 | 용도 | 확인 단계 | 현재 |
|---|---|---|---|
| ⟦OpenClaw 버전·커밋⟧ | 근거 문서와 일치 | 1-1 | 미확인 |
| ⟦프로필 사용 여부·이름⟧ | `--profile` 전달 여부 | 1-4 | 미확인 |
| ⟦`openclaw.json`·상태 DB 경로⟧ | 설정 복사·`--config-path` | 1-5 | 미확인 |
| ⟦Gateway URL⟧ | `--expect-gateway-url` | 2-3 | 미확인(설정 사본상 18789) |
| ⟦Gateway·Node deviceId·publicKey⟧ | identity 비교 | 2-1·2-2 | 미확인 |
| ⟦Plugin 설치 경로·manifest 해시⟧ | 설치본 대조 | 3-1·3-2 | 미확인 |
| ⟦Skill 설치 경로⟧ | 복사 위치 | 3-4 | 미확인 |
| ⟦tb-node 해석 IP·CA 인증서·토큰 환경변수 이름⟧ | HTTPS 조회 | 4-5 | 미확인 |
| ⟦`$include` 사용 여부와 포함 파일 목록⟧ | `--resolve-includes` | 4-1 | 미확인 |
| ⟦실행 방식 A/B, 스캐너 실행 머신⟧ | 전체 | §2 | 미정 |
| ⟦OVA 파일명·크기·SHA256⟧ | 무결성 | 0 | 미수령 |

## 6. 결정이 필요한 것

1. VM을 구동할 호스트(이 PC는 부족 — §0).
2. 실행 방식 A(VM 안에서 직접 조회) / B(저장 후 분석).
3. `skills list --json` 실행 허용 여부(장치 신원·페어링 위험).
4. 복제·재설치·재페어링 후 identity 유지 검증을 이번 범위에 넣을지(임포트 사본에서만, 원본 OVA·스냅샷 보존).

## 7. 결과 기록 규칙

각 단계 결과를 [qa-fix-and-source-validation-20261117.md](qa-fix-and-source-validation-20261117.md)와 [확인표 응답 초안](asset-collection-checklist-scanner-reply-draft.md)의 `[직접]` 칸에 추가합니다. 저장 자료 분석 `[저장]`과 섞지 않고, OVA에서 관측한 값만 `[직접: OVA]`로 표시합니다. 관측하지 못한 항목은 미확인으로 남깁니다.

## 8. 최종 구분 (2026-11-17)

| 구분 | 항목 |
|---|---|
| **완료**(코드·테스트·가상 또는 저장 자료로 확인) | URL 원문 보존·`alteration` 기록 / 인증 헤더 `${VAR}` 대체 / `$include` 읽기 전용 해석(문서화된 규칙)과 실패 시 실행 거부 / Plugin 진입점·의존성·설치 힌트 / MCP `declared_extra` / `update_policy` / 요구사항 대응표 |
| **부분 지원** | Node 페어링(`devices list`)·SQLite 설정 / Skill·Plugin 설치 경로·출처 / Permission/Auth(선언만, 실효 권한 계산 없음) / `$include`(공식 구현 기준 병합·빈 배열·배열 원소별 출처 지원, `collector`·`permission_auth`·`plugin_skill_assets --config`·`live_discovery` 모두 연동. 추가 경계 `OPENCLAW_INCLUDE_ROOTS`만 미지원) / 환경·프로필(사용자 입력과 관측값은 분리 보존하나 `environment_id`·`profile_id` 출력 필드 없음) |
| **합의 대기**(구현하지 않음) | 공통 자산 ID / 서명·무결성 **검증**(신뢰 기준) / 실효 권한·exposed·potentially_callable 판정 / Permission/Auth 집계 단위 / `host_id`·`client_id`·`environment_id`·`profile_id` / 실행 위치 증적 / catalog·capability hash / 어댑터의 신규 필드 매핑(대응표 6절) |
| **OVA 검증 대기** | 실제 버전·프로필·설정 위치 / identity 유지(복제·재시작) / 설치본 Plugin manifest와 GitHub 사본의 `description` 차이 / `plugins list --json`·`devices list --json` 실제 출력 / 실제 `$include` 사용 여부와 병합 결과 / `inventory-remote` 실제 HTTPS 조회와 `--bearer-env` 인증 대체 / 심볼릭 링크 경계 이탈(권한 있는 환경) |

**OVA에서 추가로 확인할 `$include` 항목**: ⟦실제 설정의 `$include` 사용 여부·포함 파일 구조⟧ / 배열이 여러 파일에 걸쳐 있을 때 스캐너의 연결 순서·원소별 출처가 실제 OpenClaw가 해석한 결과(예: `openclaw config` 계열의 출력, 확인 명령은 OVA에서 정함)와 같은지 / 심볼릭 링크·하드링크 경계 이탈 거부(이 PC에서는 권한·OS 때문에 미확인) / `OPENCLAW_INCLUDE_ROOTS` 설정 여부(설정돼 있으면 스캐너는 해당 파일을 읽지 못함).

**OVA에서 추가로 확인할 항목(2026-11-18 후속 보완 반영)**

| # | 확인 | 방법 | 기록할 값 |
|---|---|---|---|
| 5-3 | 호스트 승인 문서 확보 | 승인은 호스트 SQLite(`~/.openclaw/state/openclaw.sqlite#exec_approvals_config`)에 있다. 이전 버전 파일 `~/.openclaw/exec-approvals.json`이 남아 있으면 복사하고, 없으면 **문서를 내보내는 방법**을 OVA에서 확인(`openclaw approvals get`은 병합된 유효 정책 출력이라 이 입력이 아님). 확인 전에는 DB를 직접 읽거나 수정하지 않는다 | ⟦승인 문서 확보 방법·경로⟧ |
| 5-4 | 승인 문서 수집 | `permission_auth --config <복사본> --exec-approvals-file <승인 문서 사본> --output …` | ⟦`exec_approvals*` 항목, 소켓 토큰은 `literal_withheld`⟧ |
| 5-5 | sandbox·`tools.exec`·`tools.fs`·`browser.ssrfPolicy` 선언 | 같은 `permission_auth` 결과의 `sandbox_policy`·`exec_policy`·`file_policy`·`network_policy` | ⟦실제 선언 유무⟧(저장 자료 P0~P2·S1~S4 설정에는 없음) |
| 3-5 | Skill 설치 기록 | 각 Skill 폴더의 `.clawhub/origin.json`(ClawHub 설치만 존재, 로컬·Git 설치는 없음) | ⟦`install_origin` 유무·`registry`·`installed_version`⟧ |
| 3-6 | Skill 설치 명세 | `metadata.openclaw.install`의 `sha256`이 숫자로 읽히지 않는지(`sha256_state`) | ⟦`install_specs`·`sha256_state`⟧ |
| 2-7 | 스캐너 직접 조회의 client capabilities | 방식 A에서 `live_discovery` 결과의 `client_capabilities_sent`(스캐너 SDK가 보낸 값, OpenClaw 값 아님) | ⟦`mode`·`capabilities`⟧ |
| 2-8 | OpenClaw 클라이언트의 client capabilities | 스캐너로는 관측할 수 없음. OpenClaw가 서버에 보낸 값을 확인하려면 서버 측 로그·캡처가 필요(`client_sender` 출처와 함께 저장 캡처에 넣을 수 있음) | ⟦확보 가능 여부⟧ |
