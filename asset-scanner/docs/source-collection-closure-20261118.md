# 원천 수집 누락 보완 — 809775e 이후

기준 커밋: `809775e9987da9d21ca021d5bf01542cf8a4b7f0` (`feature/scanner-config`). 이 문서는 해당 커밋 이후 추가한 수집 원천과 검증 범위를 기록하며 소스·테스트와 함께 반영한다. 공통 ID·공통 스키마·정책 판정 규칙은 바꾸지 않는다.

## 왜 이전 테스트에서 빠졌는가

기존 대응표 12절에도 기록한 것처럼, 초기 조사는 패키지 문서 일부(8개)를 검색한 결과로 원천의 존재 여부를 판단했다. 특정 예제나 설명서에 값이 없다는 사실을 전체 원천에 값이 없다는 뜻으로 확대했다. 그 뒤 누락을 찾아도 기능별 보완 목록과 테스트 통과 기록으로 관리했고, 요구 항목별로 원천 → 파서 → 출력 → 검증을 다시 연결하지 않았다. 그래서 “구현한 코드의 테스트 통과”가 “요구 항목 모두 구현”으로 잘못 안내됐다.

이는 실제 미구현을 합의 대기·실환경 검증 대기와 섞어 설명한 오류다. `809775e`와 Linux 935개 통과는 그 커밋의 동작에 관한 증거이며 전체 요구사항 충족 증거가 아니다. 이미 구현·검증된 기능은 유효하지만 누락 항목은 별도 보완해야 한다.

## 이번 보완의 연결표

모든 새 검증 입력은 테스트가 임시 폴더에 만든 가상 자료다. 실제 OpenClaw·VM·팀 서버 직접 조회 결과가 아니다.

| 원천 | 수집 코드·입력 | 실제 출력 | 검증 파일 |
|---|---|---|---|
| `devices list --json`의 `paired`·`pending` | `device_inventory.py`, `--devices-json` 또는 `--query-devices` | `devices[].identity.device_id`, `client.clientId/clientMode`, `reported_pairing_state`, `source_pointer`, `declared`, `node_surface` | `test_device_inventory.py`, `test_openclaw_direct.py` |
| 사용자 지정 systemd unit의 `[Service]` | `service_identity.py`, `--systemd-unit` 반복 지정 | `units[].declarations[].field/value/value_status/source_line` (`User`, `Group`, `DynamicUser`, `SupplementaryGroups`) | `test_service_identity.py` |
| `agents.entries.*.sandbox` 및 Agent exec 선언 | `permission_auth.py`의 공통 스키마 기반 경로 | `items[].config_path/config_pointer/applies_to/value` — defaults와 Agent 값을 별도 기록 | `test_policy_source_gaps.py`, 기존 Permission 테스트 |
| `tools.exec.applyPatch.workspaceOnly` (전역·Agent) | 같은 모듈, boolean 자료형 검사 | `file_policy`, 원래 경로와 선언된 값 | `test_policy_source_gaps.py` |
| Tlon `network.dangerouslyAllowPrivateNetwork`, `models.providers.*.request.allowPrivateNetwork` | 같은 모듈, 채널·모델 제공자별 적용 범위 | `network_policy`, `applies_to.scope: channel/model_provider` | `test_policy_source_gaps.py` |
| 추가 include 경계 | 공통 `config_includes.py`, `OPENCLAW_INCLUDE_ROOTS` 또는 API `allowed_roots` | 기존 `include_origin`, 외부 경계 파일은 `include-root[n]/...`; `includes.notes`에 추가 경계 개수·선택 원천 | `test_config_include_roots.py`, 기존 include·live 거부 테스트 |
| 저장된 Plugin inspect 설치 원천 | `plugin_skill_assets --plugin-inspect-json` 반복 지정 | `plugin_inspect_outputs[].install.declared`, `digest_metadata`, `accepted_surface`; 로컬 manifest와 일치하면 `plugins[].installation_observations` | `test_plugin_inspect_sources.py`, 기존 Plugin 테스트 |

`clientId: node-host`는 관측된 클라이언트 종류 라벨이다. 장치 ID·MCP Client 인스턴스 ID·팀 공통 ID로 대체하지 않는다. 같은 라벨의 여러 기록을 합치지 않는다. 이 새 보고서의 `devices[].declared`는 명령 출력에서 옮긴 속성 묶음의 내부 필드명이며 OpenClaw 설정 선언이라는 뜻이 아니다. `paired`에 들어 있었다는 증거와 현재 `connected` 값도 별도 보존한다.

Plugin 설치 원천은 `id`와 `rootDir`이 모두 맞을 때만 해당 설치본에 연결한다. 이름이나 ID만 같은 다른 디렉터리에 연결하지 않는다. `installedAt`과 `acceptedSurfaceAt`은 원래 의미로 저장하며 `last_updated`·`modified`로 바꾸지 않는다. 무결성 문자열은 원문·해시를 복사하지 않고 선언 여부와 자료형만 기록한다. 검증 결과는 계속 `not_performed`다.

서비스 파일은 선언 증거다. 서비스가 실행 중이라는 사실, 최종 UID/GID, systemd 기본값·drop-in 우선순위, 실제 프로세스 소유자는 계산하지 않는다. `Environment`, `EnvironmentFile`, `ExecStart`를 저장하거나 실행하지 않는다. `%` 지정자·인용·escape가 있으면 해석하지 않았다는 문제를 기록한다.

## 조회·경계의 제한

- `devices` 직접 조회는 허용 목록의 `devices list --json`만 실행한다. `approve`, `remove`, `rotate` 등은 추가하지 않았다. Gateway 대상 확인이 필요하며, 지정 URL은 이 명령이 지원하는 `--url`로 전달한다. 명시 URL이 없으면 OpenClaw가 로컬 pairing 저장소로 fallback할 수 있어 관측 기록에 이를 남긴다.
- 추가 include 경계는 설정 수집을 `--resolve-includes`로 켠 경우에만 사용한다. POSIX `:`, Windows `;`로 구분한다. `~` 확장을 포함한 절대 디렉터리를 받으며, 상대·누락·파일 경계는 오류로 표시한다. 이는 상대 경로를 cwd로 해석할 수 있는 OpenClaw 코드보다 엄격한 제한이다.
- include 경로는 실제 경로와 해석 전 경로가 각각 허용 경계 안인지 검사한다. 허용 경계 사이의 심볼릭 링크는 읽을 수 있지만 어느 허용 경계도 아닌 곳으로 나가는 링크·하드링크는 거부한다. 파일·깊이·개수 한도는 유지한다. 새 필드는 대시보드 어댑터에 자동 전달되지 않는다.
- Plugin inspect는 명시적으로 지정한 저장 JSON을 읽는다. 설치 SQLite를 자동 탐색하지 않는다. 직접 조회한 `plugins list`와 별도 원천이며 설치 기록을 확인했다고 실제 설치 파일의 무결성을 확인한 것은 아니다.

## 실행 예

asset-scanner 폴더에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m asset_scanner.device_inventory --devices-json devices.json --output devices.result.json
.\.venv\Scripts\python.exe -m asset_scanner.service_identity --systemd-unit openclaw-gateway.service --output service-identity.result.json
.\.venv\Scripts\python.exe -m asset_scanner.plugin_skill_assets --plugin-inspect-json plugin-inspect.json --output plugin-install.result.json
```

실제 입력 경로·가상환경은 사용자 환경에 맞춰 지정한다.

## 여전히 분리해서 확인할 항목

| 항목 | 현재 판단 |
|---|---|
| 실제 OpenClaw/OVA 설치본·프로필·권한·출력과 일치 | 실환경 검증 대기. 이번 테스트로 대체하지 않음 |
| 공통 ID, host_id의 의미, 환경·프로필의 공통 ID 입력, provider 정의 | 팀 합의 대기. 기존 사용자 입력·직접 조회 scope는 보존 |
| catalog/capability hash의 대상·직렬화, 신뢰 기준, 실효 권한·노출 판정 | 합의 대기. 임의 알고리즘을 추가하지 않음 |
| OAuth issuer/audience/expiry 자동 수집 | 여전히 미구현. 네트워크 메타데이터와 비밀이 섞인 인증 저장소 중 어떤 원천·접근 범위를 지원할지 확인 필요. 원천이 없다고 표현하지 않음 |
| Plugin/Skill `last_updated`·`modified`, 실행 파일의 실제 script/binary 유형 | 정확한 원천·의미 확인 대기. 설치 시각·설치 방식으로 대신 채우지 않음 |
| 전체 설치 자동 탐색·보호 저장소, 모든 OS의 서비스·프로세스 자동 식별 | 이번 새 입력으로 구현했다고 주장하지 않음 |
| YAML 전체 문법 | 기존의 제한된 부분집합. 미해석 문법·한도를 결과에 명시 |

따라서 이번 보완을 전체 요구사항 100% 충족으로 표현하지 않는다. 새 원천 경로의 구현과 전체 요구사항 승인, 실제 환경 검증은 각각 증거가 필요하다.

## 고정 원천

- OpenClaw [`eb377ac59e6c9fd6c7705028034812becf00271b`](https://github.com/openclaw/openclaw/tree/eb377ac59e6c9fd6c7705028034812becf00271b): `src/cli/devices-cli.ts`, `devices-cli.runtime.ts`, `src/config/zod-schema.agent-runtime.ts`, `zod-schema.sandbox.ts`, `types.models.ts`, `types.provider-request.ts`, `zod-schema.installs.ts`, `includes.ts`, `paths.ts`, `docs/channels/tlon.md`, `docs/gateway/index.md`.
- 팀 저장 출력 [`444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb`](https://github.com/pbh0330/2026-Agent_Scope/tree/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/raw/P2): `tb-gw.devices-list.json`, `tb-gw.plugin-inspect.agentscope-asset-catalog.json`. 구조 확인 원천이며 이번 새 테스트의 입력은 이 파일을 실제 환경으로 재실행한 것이 아닌 가상 자료다.

## 검증

**최종 검증: Linux·Python 3.12.14, 994 passed / 0 failed / 0 skipped, pytest 종료 코드 0, 220.38초.** 한 번에 끝난 전체 실행이며 영향 테스트나 이전 결과와 합산하지 않았다. 의존성 변경은 없다.

최종 전체 실행 결과는 검토 묶음의 `review/logs/source-closure-release-full.*`와 별도 검증 기록에 둔다. 별도 CLI 예시 4회(devices, Plugin inspect, 정책, 서비스 선언)는 모두 종료 코드 0이며 입력 4개 파일의 전후 SHA-256이 같고 결과에 가짜 비밀 표식이 남지 않았다. 입력·출력·조건은 `review/synthetic-examples/`에 함께 둔다. 영향 테스트 265개 통과(종료 코드 0)는 전체 실행과 합산하지 않는다. 공통 ID 확정·실제 OpenClaw 검증·PR/Issue 답글 등록·병합은 이 수집 보완에 포함하지 않는다.


## 새 CLI의 실제 가상 출력 발췌

사람이 작성한 가상 JSON·systemd 파일을 새 CLI에 입력해 얻은 출력에서 관련 필드만 발췌했다. 실제 VM 출력이 아니며, 아래에서는 파일 경로·관측 시각 등 다른 필드를 생략했다.

### devices list 입력의 장치·클라이언트

```json
{
  "identity": {
    "device_id": {
      "original_value": "lab-node-01",
      "status": "as_reported"
    }
  },
  "client": {
    "clientId": {
      "original_value": "node-host",
      "status": "as_reported"
    },
    "clientMode": {
      "original_value": "node",
      "status": "as_reported"
    }
  },
  "reported_pairing_state": "paired",
  "source_pointer": "/paired/0",
  "connected": false
}
```

### Plugin inspect 입력의 설치 기록

```json
{
  "declared": {
    "source": "npm",
    "spec": "@sample/plugin@1.2.3",
    "installPath": "/synthetic/plugin",
    "installedAt": "2026-11-01T00:00:00Z"
  },
  "digest_metadata": {
    "integrity": {
      "declared": true,
      "value_state": "nonempty_string",
      "verification": "not_performed"
    }
  }
}
```

### 서비스 파일의 실행 계정 선언

```json
{
  "declarations": [
    {
      "field": "User",
      "source_line": 2,
      "section": "Service",
      "origin": "declared_in_selected_unit",
      "value": "sample-user",
      "value_status": "as_declared"
    },
    {
      "field": "Group",
      "source_line": 3,
      "section": "Service",
      "origin": "declared_in_selected_unit",
      "value": "sample-group",
      "value_status": "as_declared"
    },
    {
      "field": "DynamicUser",
      "source_line": 4,
      "section": "Service",
      "origin": "declared_in_selected_unit",
      "value": false,
      "value_status": "as_declared"
    }
  ]
}
```
