# OpenClaw 직접 조회 (`openclaw_direct`, 내부 개발용 초안)

> 상태: 스캐너 내부 초안 `0.1.0-draft` · 작성일 2026-11-13
> 구현은 `asset_scanner/openclaw_direct.py`이고 `plugin_skill_assets`·`node_gateway_identity`가 사용합니다. 공통 ID·공통 스키마는 확정하지 않았습니다.
> **이 기능은 지정한 OpenClaw 실행 파일을 실제로 실행합니다.** 다만 아래 허용 목록의 읽기 조회만 실행하며, 실제 OpenClaw로는 아직 검증하지 못했습니다(5장).

## 1. 근거: 명령별 확인 결과 (OpenClaw 2026.9.6)

확인일 2026-11-13. 이전에 받아 둔 npm 패키지 `openclaw@2026.9.6`의 문서와 번들 코드를 **정적으로 읽었습니다**(OpenClaw를 설치·실행하지 않음, 이 PC에는 OpenClaw가 설치돼 있지 않음). 번들 코드 확인은 구현을 텍스트로 읽은 것이며 실행 결과가 아닙니다.

| 명령 | 확인한 동작 (번들 코드) | 처리 |
|---|---|---|
| `openclaw --version` | commander 버전 옵션 (`-V`, `--version`) | 허용. 설치 버전 기록용 |
| `openclaw plugins list --json` | `runPluginsListCommand` → `buildPluginRegistrySnapshotReport`: 설정과 **지속 레지스트리**를 읽고 없거나 무효이면 매니페스트에서 메모리 안에서 파생. **Gateway에 접속하지 않음**. 출력 `{workspaceDir, workspaceScope, registry, plugins[], diagnostics}` | 허용 |
| `openclaw node identity --json` | `runNodeIdentityShow` → `loadDeviceIdentityIfPresentAsync`: 로컬 상태의 `primary` 장치 신원을 **읽기만** 하고 없으면 **만들지 않고** 오류 종료. 출력 `{deviceId, publicKey}` | 허용 |
| `openclaw gateway call gateway.identity.get --json` | `gateway call`은 **임의 메서드를 호출하는 범용 RPC**입니다. 다만 `callGatewayReadOnlyCli`(`sharedStateMode: "read-only"`)를 쓰므로 호출 측이 로컬 장치 신원·토큰을 **만들지 않습니다**(`loadDeviceIdentityIfPresent`). 메서드 `gateway.identity.get`은 Gateway 쪽에서 `{deviceId, publicKey}`만 돌려주며 요구 범위는 `operator.read`. `--json` 모드의 오류는 JSON으로 stdout에 쓰고 종료 코드 1 | **이 메서드 하나로 고정**해 허용. 다른 메서드·`--params`는 허용하지 않음 |
| `openclaw skills list --json` | `loadSkillsStatusReport`: 먼저 `callGateway`로 Gateway의 `skills.status` RPC를 호출하고, 실패하면 암묵적 로컬 Gateway일 때만 로컬 계산으로 대체. **비읽기 모드**라 `resolveDeviceIdentityForGatewayCall`이 `loadOrCreateDeviceIdentity`를 호출해 **로컬 장치 신원을 새로 만들 수 있음**(loopback Gateway에 공유 비밀 token/password가 있으면 신원을 생략). 신원이 만들어져 Gateway에 연결되면 페어링 요청으로 이어질 수 있음 | **기본 거부.** `--accept-skills-list-gateway-rpc`로 사용자가 명시적으로 동의해야만 실행하고 결과에 `acknowledged_risk`를 기록 |

그 밖의 근거: 루트 옵션 `--profile <name>`(상태·설정을 `~/.openclaw-<name>`으로 분리), `--dev`, `--container <name>`(컨테이너 안에서 실행 → **허용하지 않음**), 범위 환경변수 `OPENCLAW_CONFIG_PATH`·`OPENCLAW_STATE_DIR`·`OPENCLAW_HOME`. `gateway call`의 옵션 `--timeout <ms>`·`--expect-url <url>`("해석된 URL이 다르면 연결 전에 실패"). `--url`·`--token`·`--password`는 명령행에 인증정보나 임의 대상이 드러나므로 **넘기지 않습니다**(인증은 OpenClaw 설정 또는 사용자가 이름으로 지정한 환경변수).

**확인하지 못한 것**: 실제 출력 JSON과 위 필드 정의의 일치(번들 타입으로만 확인), npm이 만드는 실제 실행 파일 래퍼(Windows `.cmd` 등)의 인자 처리, `plugins list`가 실행 중 레지스트리·캐시·진단 파일을 쓰는지의 전부(레지스트리 쓰기는 코드에서 찾지 못했지만 OpenClaw 자체 로그 파일 기록은 막지 못함), Gateway 쪽 `gateway.identity.get`이 신원이 없을 때 만든다는 구현(`loadOrCreateProcessDeviceIdentityAsync`, 실행 중인 Gateway에는 이미 있다는 전제).

## 2. 사용법

```powershell
# 설치 버전 확인과 조회 요약 (출력 원문은 저장하지 않음)
.\.venv\Scripts\python.exe -m asset_scanner.openclaw_direct --openclaw-bin C:\path\openclaw.cmd --query plugins --query node-identity --output output\direct.result.json

# 기존 수집 CLI의 직접 조회 옵션
.\.venv\Scripts\python.exe -m asset_scanner.plugin_skill_assets --plugin-dir C:\path\plugin --openclaw-query plugins --openclaw-bin C:\path\openclaw.cmd --output output\plugin-skill.result.json
.\.venv\Scripts\python.exe -m asset_scanner.node_gateway_identity --query-node-identity --query-gateway-identity gw --expect-gateway-url ws://127.0.0.1:18789 --openclaw-bin C:\path\openclaw.cmd --output output\identity.result.json
```

공통 옵션: `--openclaw-bin`(필수, 지정한 파일만 실행. PATH 검색 없음), `--profile`/`--dev`, `--config-path`·`--state-dir`·`--openclaw-home`(**이미 존재해야 함**: 스캐너가 새로 만들지 않고 OpenClaw가 초기화하지 않도록), `--pass-env 이름`(이름만 기록), `--openclaw-timeout`, `--max-output-bytes`, `--require-openclaw-version 접두어`, `--openclaw-agent`(skills). 같은 종류를 저장된 출력 파일과 직접 조회로 동시에 주면 출처가 섞이므로 오류입니다.

- **gateway-identity**: 접속 대상은 OpenClaw 설정이 정합니다. `--expect-gateway-url ws(s)://…`로 대상을 고정하거나(OpenClaw의 `--expect-url`로 연결 전에 검사) `--accept-configured-gateway`로 설정이 가리키는 Gateway에 접속함을 확인해야 하며 둘 다 없으면 실행하지 않습니다. 고정하지 않은 경우 `gateway_target.basis`가 `configured_by_openclaw_unverified`입니다.
- **skills**: 기본 거부(1장). 저장된 `skills list --json` 출력을 쓰는 방법도 그대로 있습니다.
- 설치 버전이 근거 문서 버전(2026.9.6)과 다르면 실행하되 `version_matches_researched_basis: false`로 표시하고, `--require-openclaw-version`을 주면 불일치 시 조회를 실행하지 않습니다.

## 3. 안전 장치

| 항목 | 내용 |
|---|---|
| 셸 | 사용하지 않음. 인자 배열로 실행(`shell=False`), 인자는 고정 목록과 엄격한 정규식을 통과한 값뿐 |
| 허용 목록 | 5개 조회(`version`, `plugins`, `node-identity`, `gateway-identity`, `skills`)만. 그 밖의 하위 명령은 실행 전에 거부. 초기화·설치·업데이트·페어링·설정 변경 명령은 목록에 없음 |
| 환경 | 자식에게는 최소 기본 변수와 명시한 범위(프로필·설정·상태 폴더)와 이름을 지정한 변수만 전달. 부모의 `OPENCLAW_*`, 인증 변수는 넘기지 않음. 지정한 변수의 **값은 어디에도 기록하지 않음** |
| 시간·크기 | 조회당 시간 제한(기본 30초), stdout 8MiB·stderr 64KiB 제한. 넘으면 프로세스 **트리**를 종료(Windows `taskkill /T`, POSIX 프로세스 그룹). 손자 프로세스가 파이프를 붙잡아도 정리 |
| 입력·작업 위치 | stdin은 닫힘(DEVNULL), 작업 폴더는 임시 폴더 |
| 출력 원문 | 파일·로그에 쓰지 않음(`raw_output_stored: false`). JSON은 메모리에서 파싱해 기존 파서의 가림을 거친 값만 남김. 실패 시 stderr는 가린 한 줄(200자)과 크기, stdout 오류 JSON은 키 이름만 기록 |

## 4. 출처 구분

| 출처 | 표시 | 시각 | 의미 |
|---|---|---|---|
| 사용자 제공 | `user_provided` (`--subject` 등) | — | 사용자가 입력한 값. 스캐너가 확인하지 않음 |
| 저장된 출력 | `source_kind: stored_command_output`, `origin: observed_from_stored_command_output` | 관측 시각 미상(`--observed-at`으로 선언한 경우만 `operator_declared`) | 사용자가 미리 저장한 출력의 값 |
| 직접 조회 | `source_kind: direct_query`, `origin: observed_from_direct_query` | `observed_at` = 스캐너 시계, `observed_at_origin: scanner_clock_at_query` | 지정한 OpenClaw가 돌려준 값. 스캐너가 독립적으로 확인한 것은 아님(`verified_by_scanner: false`) |

직접 조회 관측에는 `command`, `executable`(가린 경로), `installed_version`(`--version` 출력의 버전·커밋과 근거 버전 일치 여부), `scope`(프로필·설정/상태 지정 여부·전달한 환경변수 **이름**), `exit_code`, `duration_ms`, `stdout_bytes`, `limits`, `read_only_basis`, `uses_gateway`가 들어갑니다. `linking --observed-identity`는 입력 파일에 적힌 `origin`을 그대로 옮기고(알 수 없는 출처는 `identity_origin_invalid`로 무시), `--subject` 값과 별도 필드에 둡니다.

## 5. 검증 수준 구분

| 구분 | 내용 |
|---|---|
| **가짜 CLI 검증** | 테스트가 만든 가짜 실행 파일(`tests/fake_openclaw.py`를 감싼 `.cmd`)로 확인: 5개 조회의 실행 인자(허용하지 않은 인자 없음), 프로필·범위 전달, 존재하지 않는 경로 거부, 환경변수 격리, 거부 시 프로세스 미생성, 정상 응답→기존 파서 연동, 실패(종료 코드·잘못된 JSON·빈 출력·UTF-8 아님)와 원문 비저장, 시간 초과·초과 출력 시 프로세스 트리(손자 포함) 정리, 버전 불일치·요구 버전, 출처 구분과 `linking` 연동, CLI 종료 코드 |
| **저장된 자료 검증** | 기존 방식(저장된 출력 파일)의 테스트는 그대로이며 이번에 수정한 모듈의 기존 테스트 146개를 다시 실행해 통과를 확인했습니다. |
| **실제 OpenClaw 실행 검증** | **없음 (미확인).** 이 PC에는 OpenClaw가 설치돼 있지 않고 임의로 설치하지 않았습니다. 실제 출력 형식, 실제 `.cmd` 래퍼, 실제 Gateway 접속·신원 동작, 팀 테스트베드는 확인하지 못했습니다. |

## 6. 검증 실행 기록 (2026-11-13)

로그는 `asset-scanner/output/review-resources-prompts/split/direct-*.log`(`.exit.txt`)에 있고 `output/`은 Git에서 제외됩니다. 순차 실행했고 실행기가 시스템 여유 메모리 120MB 미만이면 해당 실행만 중단하도록 감시했습니다.

| 실행 | 대상 | 결과 | pytest 종료 코드 | python 최대 메모리 |
|---|---|---|---|---|
| `direct-a-core` | 인자·거부·환경 | **감시 중단(ABORTED)** — 시스템 여유 메모리 72MB로 하락(python 82MB) | 기록 없음 | 82MB |
| `direct-a2-core` | 같은 묶음 재실행 | 27 passed, 1 failed | 1 | 74MB |
| `direct-b-failures` | 실패 유형·정리·크기 제한 | 6 passed | **0** | 103MB |
| `direct-c-integration` | 파서 연동·`linking`·CLI | 12 passed | **0** | 104MB |
| `direct-d-regression` | 수정한 기존 모듈의 테스트(`plugin_skill_assets`·`node_gateway_identity`·`linking`) | 146 passed | **0** | 83MB |
| **`direct-e-final`** | **`tests/test_openclaw_direct.py` 전체** | **45 passed (37초)** | **0** | 105MB |

- 첫 묶음 중단은 테스트 결함이 아니라 시스템 메모리 압박이며 같은 묶음을 재실행했습니다. 재실행의 실패 1건은 테스트 가정 오류였습니다: Windows에서 `NUL` 장치는 `isatty()`가 `True`라 "tty가 아니다"가 닫힌 stdin의 증거가 못 됩니다 → 가짜 CLI가 stdin을 읽어 즉시 EOF인지 확인하도록 고쳤고 이후 통과했습니다.
- 개발 중 고친 것: 문서로 확인하지 못한 환경변수(`OPENCLAW_NO_PROMPT`)를 제가 임의로 넣었던 부분을 제거했습니다.
- 실행 뒤 남은 가짜 CLI 프로세스는 0개였습니다. 이 기록은 파일 단위 실행이며 전체 실행 기록이 아닙니다.
