# 자산 스캐너 — OpenClaw MCP 서버 등록 정보 수집기 (1단계)

OpenClaw 설정 파일(JSON/JSON5)을 **읽기만 해서** 선택한 등록 영역(기본 `mcp.servers`, 선택 `nodeHost.mcp.servers`)에 등록된 MCP 서버 목록과 출처를 JSON으로 저장합니다.

- 출력은 **스캐너 내부 협의용 초안**입니다. 팀 공통 스키마가 아닙니다. → [필드 매핑과 근거](docs/field-mapping.md)
- 설정 속 명령 실행, 서버 접속, 도구 조회, 환경변수 값 해석, `$include` 파일 읽기, 설정 수정을 **하지 않습니다.**
- 실제 연결 여부·도구 목록·capabilities·protocol_version·노출/호출 가능 상태는 채우지 않습니다.
- 이 설정 수집기는 Tool 정의를 읽지 않습니다. 저장된 `tools/list` 응답을 읽는 별도 모듈은 아래 [Tool 카탈로그 1단계](#tool-카탈로그-1단계-저장된-toolslist-응답-읽기)를 보세요.
- 위 약속은 **이 정적 설정 수집기와 저장된 응답 읽기 모듈**에 해당합니다. 개발용 MCP 서버를 실제로 실행해 조회하는 별도 모듈은 [실제 stdio 조회](#실제-stdio-조회-개발용-mcp-서버-1개--서버-프로세스를-실행합니다)에 있으며, **그 명령만 서버 프로세스를 실행**하고 팀 테스트베드 검증이 아닙니다.
- **실제 테스트베드 연동은 미검증입니다.** `examples/`의 설정은 모두 테스트용 가상 설정이며 실제 팀 설정이 아닙니다.

## 구성

```text
asset-scanner/
├── asset_scanner/
│   ├── cli.py         # --config / --output / --registry-path 명령행
│   ├── collector.py   # 파일 읽기·JSON5 파싱·선택한 등록 영역(mcp.servers 또는 nodeHost.mcp.servers) 수집
│   ├── redaction.py   # 비밀값 가림, 환경변수·SecretRef 참조 감지
│   ├── report.py      # 결과 JSON(협의용 초안) 조립
│   ├── output.py         # 결과 JSON 저장 (엄격한 JSON, 임시 파일 후 교체)
│   ├── tools_catalog.py  # 저장된 tools/list 응답 → Tool 정의 목록 (별도 CLI, 서버 접속 없음)
│   ├── live_tools.py     # 개발용 MCP 서버를 stdio로 실행해 tools/list 실제 조회 (SDK 사용, 서버 프로세스 실행)
│   └── dev_mcp_server.py # 검증용 개발 MCP 서버 (공식 SDK, Tool 2개)
├── examples/          # 테스트용 가상 설정 (실제 팀 설정 아님)
├── tests/             # pytest
└── docs/field-mapping.md
```

## 설치 (Windows PowerShell)

Python 3.14.4에서 검증했습니다.

```powershell
cd asset-scanner
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

실행만 할 때는 `requirements.txt`(json5 0.15.0)만 설치해도 됩니다.

## 실행

```powershell
.\.venv\Scripts\python.exe -m asset_scanner --config examples\two-servers.json5 --output output\two-servers.result.json
```

실제 설정을 읽을 때도 경로를 명시합니다. 스캐너는 기본 경로(`~/.openclaw/openclaw.json`)를 스스로 찾지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m asset_scanner --config "$env:USERPROFILE\.openclaw\openclaw.json" --output output\openclaw.result.json
```

### 수집할 등록 영역 선택 (`--registry-path`)

한 번에 등록 영역 하나만 읽습니다. 옵션을 생략하면 기존과 같이 `mcp.servers`(Gateway 설정)를 읽습니다. Node 설정 파일의 `nodeHost.mcp.servers`를 읽으려면 명시적으로 선택합니다.

```powershell
.\.venv\Scripts\python.exe -m asset_scanner --config examples\node-and-gateway.json5 --output output\node.result.json --registry-path nodeHost.mcp.servers
```

- 선택할 수 있는 값은 `mcp.servers`, `nodeHost.mcp.servers` 두 가지뿐입니다. 그 밖의 값은 인자 오류(종료 코드 2)입니다.
- 파일 전체를 파싱하되, 선택한 등록 영역만 수집·보고합니다. 같은 파일에 두 영역이 있어도 고르지 않은 영역의 서버·중복 키·가린 키는 결과에 나타나지 않습니다. (파일 전체를 파싱하므로 구문 오류는 어느 영역을 골라도 수집 실패입니다.)
- 선택한 경로는 결과의 `source.registry_path`, 서버별 `declaration_path`, 오류·참조의 위치에 기록됩니다. 표준출력 첫 줄에도 `등록 영역: …`이 표시됩니다.
- 근거: OpenClaw 2026.9.6 패키지 문서(`docs/nodes/mcp-and-skills.md`). 설정 스키마·소스, 서버가 실제로 등록된 Node 설정으로는 아직 확인하지 않았습니다. → [필드 매핑 1-1](docs/field-mapping.md#1-1-등록-영역-선택---registry-path)
- `nodeHost.mcp`가 없는 설정(예: SNAP-1 Node 설정)은 `registry_absent`입니다. 서버 0개가 아닙니다.

| 종료 코드 | 의미 (결과 파일은 1·3에서도 저장됨) |
|---|---|
| 0 | 완전 수집 (`complete`) |
| 1 | 부분 수집 (`partial`) — 미해석 include·환경변수 참조, 서버별 문제 등 |
| 2 | 인자 오류 |
| 3 | 수집 실패 (`failed`) — 파일 없음·읽기 실패·JSON5 오류·잘못된 구조 |
| 4 | 결과 파일 저장 실패(직렬화·인코딩·교체 실패 포함) 또는 `--output`이 `--config`와 같은 파일. 이 경우 기존 결과 파일은 바뀌지 않음 |

### 결과 파일 저장 방식 (설정 수집 CLI와 Tool 카탈로그 CLI 공통, `asset_scanner/output.py`)

- 결과는 **엄격한 JSON(UTF-8, `NaN`·`Infinity` 없음)** 입니다. 직렬화·UTF-8 인코딩은 파일을 열기 **전에** 끝내고, 같은 폴더의 임시 파일에 완전히 쓴 뒤 `os.replace`로 교체합니다. 어느 단계에서 실패해도 기존 결과 파일은 그대로이고 빈 파일·임시 파일이 남지 않습니다. 실패하면 종료 코드 4와 한 줄 메시지(예외 종류만, 문자열 내용 없음)를 냅니다. 이전에는 쓰기 전에 파일을 먼저 비웠기 때문에 저장 중 예외가 나면 기존 결과가 0바이트로 지워졌습니다.
- **고립된 surrogate**(예: JSON 이스케이프 `\ud800`)는 UTF-8로 저장할 수 없습니다. 방침: 해당 문자만 U+FFFD(대체 문자)로 바꾸고 나머지 문자열은 보존합니다. 근거: 결과가 항상 유효한 UTF-8이어야 하고, 한 문자열의 문제 때문에 다른 정상 항목·서버를 버리지 않기 위해서입니다. 객체 키가 바뀌어 다른 키와 겹치면 `<redacted-key-N>` 자리표시자를 씁니다. 바뀐 문자열 수는 `collection.output_text_normalizations`에 남깁니다(없으면 키 자체가 없음). 유효한 한글·이모지·유럽 문자는 이스케이프하지 않고 원문 그대로 저장합니다(짝을 이룬 surrogate 이스케이프 `😀`는 평범한 이모지로 읽습니다).
- 입력 문제(없음·잘못된 JSON 등) → 종료 코드 3(결과 저장됨), 수집 상태 `partial` → 1, 저장 실패 → 4로 구분합니다. 입력 파일은 읽기만 하며 바꾸지 않습니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

전체 테스트에는 개발용 MCP 서버를 실제로 실행하는 stdio 통합 테스트(`tests\test_live_tools.py`, 약 3분)가 포함됩니다. 서버를 실행하지 않는 테스트만 돌리려면 `--ignore=tests\test_live_tools.py`를 붙이세요 ([실제 stdio 조회](#실제-stdio-조회-개발용-mcp-서버-1개--서버-프로세스를-실행합니다) 절 참조).

## 콘솔 출력 인코딩

Windows 콘솔 코드페이지(예: cp949)로 표현할 수 없는 문자(이모지, 일부 서버 이름·경로 등)는 표준출력·오류출력에서 `\uXXXX` 또는 `\UXXXXXXXX` 형태로 표시합니다. 표현할 수 있는 문자는 그대로 출력합니다. `PYTHONUTF8=1` 같은 설정은 필요하지 않습니다. 결과 JSON 파일은 항상 UTF-8이며 원문 이름을 그대로 보존하므로, 정확한 값은 결과 파일에서 확인하세요. 출력 때문에 종료 코드가 바뀌지 않습니다(위 종료 코드 표 그대로).

## 예제 결과 (`examples\two-servers.json5`, 일부 생략)

표준출력:

```text
등록 영역: mcp.servers
수집 상태: complete (servers_found)
등록 항목: 2개
  - mcp.servers.sample-files  [항목 상태: complete, enabled: 미선언]
  - mcp.servers.sample-remote  [항목 상태: complete, enabled: false]
결과 저장: output\two-servers.result.json
```

결과 파일:

```json
{
  "format": "agent-scope.scanner.openclaw-mcp-config",
  "format_version": "0.1.0-draft",
  "source": { "source_path": "<저장소 경로>\\asset-scanner\\examples\\two-servers.json5", "registry_path": "mcp.servers" },
  "scope": { "values_resolved": false, "not_verified": ["connection", "tools", "resources_prompts", "capabilities", "protocol_version", "exposure", "callability"] },
  "collection": { "status": "complete", "outcome": "servers_found", "server_count": 2, "reasons": [], "unresolved": [] },
  "servers": [
    {
      "registration_key": "sample-files",
      "declaration_path": "mcp.servers.sample-files",
      "collection_status": "complete",
      "declared": { "command": "npx", "args": ["-y", "@example/sample-files-mcp", "./workspace"], "cwd": "./sandbox" }
    },
    {
      "registration_key": "sample-remote",
      "declaration_path": "mcp.servers.sample-remote",
      "collection_status": "complete",
      "declared": { "url": "https://mcp.example.test/mcp", "transport": "streamable-http", "enabled": false },
      "other_declared_keys": ["requestTimeoutMs"]
    }
  ]
}
```

`sample-files`에 `enabled`와 `transport`가 없는 것은 설정에 적혀 있지 않기 때문입니다. 기본값을 추측해 채우지 않습니다.

## 예제 파일

| 파일 | 확인 내용 | 기대 상태 |
|---|---|---|
| `examples/two-servers.json5` | 서로 다른 서버 2개(stdio, 원격), 비활성 서버 보존 | `complete`, 종료 코드 0 |
| `examples/fake-secrets.json5` | 가짜 비밀값(`FAKE` 표식)이 결과·출력에 남지 않음 | `partial`(참조 포함), 종료 코드 1 |
| `examples/include-and-refs.json5` | 미해석 `$include`·`${VAR}` 기록 | `partial`, 종료 코드 1 |
| `examples/review-r1-secrets.json5` | 1차 검토 R1: `--옵션=URL`, `-H`/`--header`, 셸 명령 문자열, `$include` fallback, 토큰 모양 등록키의 가림 | `partial`(미해석 include), 종료 코드 1 |

## 비밀값 가림 요약

결과 파일·표준출력·오류출력에는 다음을 남기지 않습니다. 상세 규칙과 한계는 [필드 매핑 문서 5장](docs/field-mapping.md#5-비밀값-가림-규칙)에 있습니다.

- `env`·`headers`·`auth`·`oauth`·`clientCert`·`clientKey`의 값 (이름·존재 여부·참조 종류만 기록)
- 인자·URL·헤더 문자열·`$include` 대상 속 비밀값: 비밀 이름 플래그 값, URL 사용자정보·쿼리 값·fragment, 인증 헤더 값, 알려진 토큰 모양
- 셸 명령 문자열(`sh -c "..."` 등): 해석·실행하지 않고 통째로 가림
- 토큰처럼 보이는 등록키: `<redacted-key-N>`으로 바꾸며, 서로 다른 서버는 합쳐지지 않음
- `${VAR:-fallback}`의 fallback: `${VAR:-<redacted>}`로 표시하고 사유를 남김

가림은 유용한 정보(포트, 패키지명, 파일 경로, 비밀 없는 URL, `Content-Type` 같은 일반 헤더)를 보존합니다.
이름·모양 기반 규칙이므로 평범한 단어처럼 생긴 비밀값이 이름 없는 인자로 들어 있으면 가리지 못합니다.

## 오류·부분 수집 상태 요약

| 상황 | `collection.status` / `outcome` |
|---|---|
| 파일 없음 · 읽기 실패 · JSON5 오류 · 잘못된 구조 | `failed` / `file_not_found` · `read_error` · `parse_error` · `invalid_structure` |
| 등록 영역 없음 | `complete` / `registry_absent` (`server_count: null`) |
| 등록 영역 없음 + 상위 키 중복 또는 미해석 include | `partial` / `registry_absent` |
| 빈 등록 목록 `{}` | `complete` / `empty_registry` (`server_count: 0`) |
| 일부 서버에 타입 오류·잘못된 SecretRef·미해석 참조 | `partial` / `servers_found` — 정상 서버는 그대로 수집, 문제는 `servers[].issues`에 기록 |

## Tool 카탈로그 1단계: 저장된 `tools/list` 응답 읽기

위 설정 수집기와 **별도 모듈**입니다. 이미 저장해 둔 MCP `tools/list` 응답 JSON을 읽어 Tool 정의를 정리할 뿐이며, 기존 `--config` CLI의 동작은 바꾸지 않았습니다. 결과는 **내부 개발용 초안**입니다.

- MCP 서버에 접속·실행하지 않고 `tools/call`도 하지 않습니다. 따라서 결과는 "실제 서버 조회 성공", "Agent에 노출됨", "호출 가능"을 뜻하지 않습니다.
- 근거 규격은 **MCP 2026-07-28**(`server/tools`, `utilities/pagination`, `schema.ts`)입니다. 입력이 `protocol_version: "2026-07-28"`을 선언하지 않으면 Tool을 읽지 않고 실패로 기록합니다. 다른 버전의 응답을 같은 구조로 가정하지 않습니다.
- Resource·Prompt 수집, 공통 server_id·asset_id 생성, 백엔드·대시보드 연동은 하지 않았습니다.

```powershell
.\.venv\Scripts\python.exe -m asset_scanner.tools_catalog --capture examples\tools-list-capture.json --output output\tools-catalog.result.json
```

종료 코드는 설정 수집 CLI와 같습니다: 0 완전, 1 부분, 2 인자 오류, 3 실패(읽은 Tool 없음), 4 저장 실패 또는 `--output`이 `--capture`와 같은 파일.

### 입력: capture 파일

`examples/tools-list-capture.json`은 **가상 자료**입니다(`origin: "synthetic_test_data"`). 서버별로 `tools/list` 응답을 받은 순서대로 `pages`에 넣습니다. 각 응답은 JSON-RPC 응답 전체(`result` 또는 `error`)이거나, `result` 객체만 있는 형태입니다.

```json
{
  "format": "tools-list-capture",
  "origin": "synthetic_test_data",
  "servers": [
    {
      "server_ref": "sample-files",
      "registration_key": "sample-files",
      "registry_path": "mcp.servers",
      "protocol_version": "2026-07-28",
      "pages": [
        {"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "tools": [ ... ], "nextCursor": "page-2", "ttlMs": 300000, "cacheScope": "public"}},
        {"jsonrpc": "2.0", "id": 2, "result": {"resultType": "complete", "tools": [ ... ], "ttlMs": 300000, "cacheScope": "public"}}
      ]
    }
  ]
}
```

`server_ref`는 이 파일 안에서 서버를 구분하는 이름일 뿐 **공통 server_id가 아닙니다.** `registration_key`·`registry_path`는 설정 수집 결과와 연결하기 위한 참고값이며 대조하지 않습니다(`verified_against_config_scan: false`).

### 출력 (일부 생략)

```json
{
  "format": "agent-scope.scanner.mcp-tools-catalog",
  "format_version": "0.1.0-draft",
  "source": {"capture_path": "examples\tools-list-capture.json", "source_kind": "stored_tools_list_response", "live_server_query": false, "origin_declared_by_input": "synthetic_test_data"},
  "collection": {"status": "complete", "outcome": "all_servers_listed", "server_count": 3, "tool_count": 3, "tool_count_complete": true, "reasons": [],
                 "spec_conformance": {"checks": "limited", "servers_with_violations": 0, "servers_no_violations_found": 3, "servers_not_evaluated": 0, "violation_count": 0}},
  "servers": [
    {
      "server_index": 0, "server_ref": "sample-files", "server_ref_kind": "capture_local_label",
      "collection_status": "complete", "outcome": "tools_listed", "tool_count": 2,
      "spec_conformance": {"status": "no_violations_found", "checks": "limited", "violation_count": 0, "violations": [], "recommendations_not_met": []},
      "pages": [{"page_index": 0, "result_type": "complete", "tool_count": 1, "has_next_cursor": true, "ttl_ms": 300000, "cache_scope": "public"}],
      "tools": [
        {
          "internal_ref": "capture-server[0]/tools[0]", "server_index": 0, "server_ref": "sample-files",
          "page_index": 0, "index_in_page": 0,
          "definition": {"name": "read_file", "title": "Read File", "description": "...", "inputSchema": {"type": "object", "...": "..."}, "outputSchema": {"...": "..."}, "annotations": {"readOnlyHint": true}, "icons": ["..."]},
          "definition_status": "passed_limited_checks", "definition_check_level": "limited_structure", "definition_issues": [], "redactions": [],
          "trust": "untrusted_server_provided"
        }
      ]
    }
  ]
}
```

- `definition`은 서버가 보낸 Tool 객체를 **원래 구조 그대로**(비밀값 가림만 적용) 담습니다. 응답에 없는 선택 필드(`title`, `outputSchema`, `annotations`, `icons`, `_meta`)는 만들지 않습니다. 공식 필드가 아닌 키는 `other_definition_fields`에 이름만 적습니다(값은 `definition`에 그대로 있습니다).
- **잘못된 Tool 정의도 보존합니다.** 인벤토리 수집 대상이므로 `inputSchema` 누락·형식 오류 같은 문제가 있어도 항목을 버리지 않고 `definition_status: "failed_limited_checks"`와 오류 근거(`definition_issues[]`: `code`, `field_path`)를 붙입니다. 이 상태는 **정상 사용 가능한 Tool이라는 뜻이 아니며**, `passed_limited_checks`도 마찬가지입니다. 식별할 `name`이 없는 항목만 제외하고 위치(`page_index`, `tool_index`)와 사유를 `issues`에 남깁니다.
- `internal_ref`는 이 결과 파일 안의 위치로 만든 내부 참조입니다. 공통 자산 ID가 아니며 실행 사이의 안정성을 보장하지 않습니다.
- 서로 다른 서버의 동명 Tool은 `server_index`·`internal_ref`가 다른 별도 항목입니다. 같은 서버 안의 이름 중복도 두 항목을 모두 유지하고 경고만 남깁니다.

### 수집 상태와 규격 적합성은 별개입니다

- **수집 완전성** (`collection_status`: `complete` / `partial` / `failed`): 응답을 끝까지 읽어 Tool을 빠짐없이 모았는가.
- **규격 적합성** (`spec_conformance`): 읽은 응답이 MCP 2026-07-28 규격의 필수·권장 사항을 지키는가. 상태 필드를 바꾸지 않고 `issues[]`에 `category: "conformance"`로 기록하며, 서버별·전체 요약을 제공합니다. `violation`은 필수 필드·MUST 위반, `recommendation_not_met`은 SHOULD 미충족입니다. 이 검사는 아래 "제한된 구조 검사"가 전부이므로 `no_violations_found`는 전체 규격 적합성 인증이 아닙니다. 읽은 응답이 없으면 `not_evaluated`입니다.
- `protocol_version`이 2026-07-28인데 `resultType`·`ttlMs`·`cacheScope`가 없거나 형식이 틀리면 규격 위반으로 기록하고, 읽을 수 있는 Tool은 그대로 보존합니다. 캐시 필드 누락·오류만으로는 Tool을 버리지도, 상태를 `partial`로 바꾸지도 않습니다.
- `resultType`이 없거나 문자열이 아니면 응답이 완료됐는지 알 수 없으므로 **완료를 추정하지 않습니다.** Tool은 보존하되 서버는 `partial` / `completion_unverified`이며 읽은 Tool 수는 하한입니다. 알 수 없는 문자열 값(예: `streaming`)은 응답 구조를 추정하지 않고 읽지 않습니다(`failed`).

### 수집 상태

| 상황 | 서버 상태 / outcome | 비고 |
| --- | --- | --- |
| 성공한 빈 목록 | `complete` / `empty_list`, `tool_count: 0` | 유일하게 "Tool 0개"로 말할 수 있는 경우 |
| 정상 목록(여러 페이지 포함) | `complete` / `tools_listed` | |
| 오류 응답(`error`) | `failed` / `error_response`, `tool_count: null` | 0개가 아님. 오류 `code`만 저장하고 `data`는 저장하지 않음 |
| 잘못된 구조(`tools` 없음 등), `input_required`, 알 수 없는 `resultType` | `failed` / 해당 사유 | |
| `protocol_version` 미선언·다른 버전 | `failed` / `protocol_version_not_declared`·`protocol_version_unsupported` | Tool을 읽지 않음 |
| 응답 없음 | `failed` / `no_response` | |
| `name`이 없는 항목, 객체가 아닌 항목 | `partial` / `incomplete_list` | `name` 없는 항목은 제외하고 위치만 기록 |
| 응답 외피(`result`·`error`·`jsonrpc`·`id`)·`result`·Tool의 중복 키 | `partial` | 마지막 값만 남고 앞의 값은 읽지 못했으므로 완전 수집으로 보지 않음. `issues[]`의 `duplicate_key`에 위치(`field_path`)와 키 이름(`duplicate_keys`)을 기록하고, 읽을 수 있는 Tool은 보존 |
| 서버 항목(`pages`·`server_ref` 등)의 중복 키 | 그 서버만 `partial` / `duplicate_keys` | 다른 정상 서버는 그대로 `complete`. 이미 `failed`인 서버는 `failed`를 유지하고 중복 사실만 추가 |
| 입력 최상위(`servers`·`origin` 등)의 중복 키 | 파일 전체 `partial` / `duplicate_keys_in_capture` | `collection.reasons`의 `duplicate_key_in_capture`(`field_path: "(root)"`). `servers`가 중복되면 마지막 배열만 읽으므로 앞 배열의 서버가 빠졌을 수 있고 `tool_count_complete: false`. 마지막 값으로 읽은 서버는 각자의 상태를 유지 |
| `inputSchema` 누락·형식 오류 등 Tool 정의 문제 | 상태 유지 (`complete`일 수 있음) | 항목은 `failed_limited_checks`와 `definition_issues`를 붙여 **보존**. `spec_conformance`에 위반으로 집계 |
| `resultType` 없음·문자열 아님 | `partial` / `completion_unverified` | 위반 기록 + 완료 미확인. Tool은 보존 |
| 마지막 페이지에 `nextCursor`가 남음(빈 문자열 포함) | `partial` / `incomplete_list`, 사유 `next_cursor_remaining` | 읽은 Tool 수는 서버 전체 수가 아님. 커서 값은 저장하지 않음 |
| 뒤쪽 페이지 오류 | `partial` | 앞 페이지 Tool 유지 |
| `ttlMs`·`cacheScope` 누락·오류, `jsonrpc` 값 이상 | 상태 유지 | 규격 위반으로만 기록(`category: "conformance"`). 틀린 값은 힌트로 기록하지 않음 |
| 이름 형식 권장 위반, 같은 서버의 이름 중복 | 상태 유지 | `recommendation_not_met`으로 기록. 두 항목 모두 유지 |

전체 상태는 모든 서버가 `complete`면 `complete`, 모두 `failed`면 `failed`, 그 외 `partial`입니다. 입력 파일 문제(없음·비UTF-8·잘못된 JSON·`servers` 비어 있음)는 `failed`이며 서버·Tool 수를 0으로 쓰지 않고 `null`로 둡니다.

### 서버 제공 데이터 취급

`description`, `annotations`, `inputSchema` 안의 문장 등은 **비신뢰 데이터**로만 저장합니다(`trust: "untrusted_server_provided"`). 해석·실행하지 않고 지시문으로 취급하지 않으며, 콘솔에는 설명문·오류 메시지를 출력하지 않습니다(서버 이름은 JSON 이스케이프한 짧은 형태로만 출력). 가림 대상과 방식은 다음과 같고, 위치(`field_path`)와 사유(`reason`)만 `tools[].redactions`에 남기며 **원문 값·원래 키 이름은 기록하지 않습니다.** 일반 문장·정상 스키마·일반 메타데이터는 통째로 지우지 않습니다.

| 대상 | 처리 | `reason` |
| --- | --- | --- |
| 알려진 토큰 모양, URL의 사용자정보·쿼리·fragment (설명·`$id`·`$ref`·`$schema`·`pattern`·`_meta` 등 **모든 문자열**, 구조 키 포함) | 해당 부분만 `<redacted>` | `token_pattern:*`, `url_userinfo`, `url_query_values`, `url_fragment` |
| 토큰 모양인 **객체 키·`properties` 이름** | 같은 객체 안에서 일반 키와 겹치지 않는 `<redacted-key-N>`로 바꿈. `required`의 같은 이름도 같은 자리표시자로 맞춤 | `key_looks_like_secret`, `reference_to_masked_key` |
| 인증 이름 필드(`api_key`, `accessToken`, `password`, `credentials` 등)의 문자열 값(하위 값 포함) | `<redacted>`. `author`·`token_budget` 같은 일반 이름이나 `${VAR}`처럼 이름만 가리키는 참조는 보존 | `secret_named_field_value` |
| 비밀 이름 속성(`properties.api_key` 등)의 `default`·`const`·`examples`·`enum` 값 | `<redacted>` (같은 속성의 `description` 등은 보존) | `secret_named_property_value` |
| 구조 키(`$ref`·`$anchor`·`type`·`format`·`pattern` 등) 아래 긴 식별자 | 토큰 모양·URL 자격증명만 가리고, 긴 식별자처럼 보인다는 이유로는 지우지 않음 | - |
| 고립된 surrogate(값·키) | U+FFFD로 대체 / 키는 자리표시자 | `lone_surrogate_replaced`, `lone_surrogate_in_key` |
| `NaN`·`Infinity`·`-Infinity`·`1e400`처럼 float로 바꾸면 무한대가 되는 숫자 | 정의 안에서는 `"<non-finite-number>"`로 대체. 캐시 힌트(`ttlMs`)면 정상 값으로 인정하지 않고 `cache_hint_invalid`(규격 위반)로만 기록하며 `ttl_ms`를 기록하지 않음 | `non_finite_number_replaced` |

가림·정규화가 적용된 Tool은 `definition_altered: true`이며 **서버가 보낸 원본과 다를 수 있습니다.** 키 이름이 바뀌면 이름을 가리키는 참조(`required` 외)가 어긋날 수 있고, 가린 정의를 실행 가능한 원본 스키마로 보증하지 않습니다. `$ref`는 문자열로만 저장하며 실행·조회·접속하지 않습니다(`scope.definition_validation.redaction_note`).

### 제한된 구조 검사 (전체 JSON Schema 검증이 아님)

Tool 정의에 대해 실제로 하는 검사는 다음뿐입니다(결과 JSON의 `scope.definition_validation`에도 같은 내용이 있습니다).

- `name`이 비어 있지 않은 문자열인가
- `inputSchema`가 객체이고 **루트 `type`이 `"object"`인가**
- `title`·`description`·`outputSchema`·`annotations`(힌트 자료형)·`icons[].src`·`_meta`의 기본 JSON 자료형

**하지 않는 검사:** `inputSchema`·`outputSchema` 전체의 JSON Schema 유효성(2020-12·draft-07 키워드), `$ref`·`$defs` 해석, `x-mcp-header` 제약, `outputSchema` 내부 구조, `annotations` 의미, 아이콘 접근 가능 여부. 루트 `type`만 통과한 `inputSchema`가 JSON Schema로 유효하다는 뜻은 아닙니다. 그래서 상태 값도 `valid`가 아니라 `passed_limited_checks`입니다.

### 가림의 한계 (미지원)

- 이름·모양 기반 규칙입니다. 평범한 문장처럼 생긴 비밀값은 가려지지 않습니다. 인증 이름 필드는 이름을 단어로 나눠 비교하는 보수적 규칙이라(예: `token_type`의 문자열 값도 가려짐) 일반 메타데이터가 일부 가려질 수 있습니다.
- 키를 가리면 `required` 밖의 이름 참조(`dependentRequired`, `$ref`의 JSON 포인터 등)는 맞추지 않습니다.
- 설정 수집 CLI의 고립된 surrogate는 건수(`collection.output_text_normalizations`)만 남기며 Tool 카탈로그처럼 위치별 기록은 없습니다. 설정 수집 CLI는 `NaN`·`Infinity`·`1e400`을 `args`·`cwd`·`enabled`·`env` 값에 넣은 가상 설정으로 시험했을 때 결과에 나타나지 않았습니다(수정 전에도 동일). 그 밖의 위치는 확인하지 않았고 별도 변환은 하지 않습니다. 만약 비유한 숫자가 결과에 들어가면 저장 단계가 엄격한 JSON만 허용하므로 종료 코드 4로 실패하고 기존 결과는 유지됩니다.
- 현재는 `2026-07-28`로 선언된 저장 응답만 읽습니다. 실제 서버 조회를 추가할 때는 협상한 `protocol_version`에 맞춰 처리해야 합니다.
- `capture_path`는 `--capture`로 받은 로컬 경로 그대로입니다. 사용자 이름이 들어 있을 수 있으니 결과를 공유하기 전에 확인하세요.

## 실제 stdio 조회 (개발용 MCP 서버 1개) — 서버 프로세스를 실행합니다

> **이 절의 명령은 서버 프로세스를 실행합니다.** 실행 대상은 프로젝트에 포함된 개발용 서버(`asset_scanner.dev_mcp_server`) 하나뿐이며 외부 계정·인증정보·네트워크가 필요 없습니다. 이 검증은 **개발용 서버에 대한 것이고 팀 테스트베드 검증이 아닙니다.** OpenClaw 설정에 적힌 서버 명령을 자동으로 실행하는 기능은 아직 없습니다. 위 정적 수집 CLI(`python -m asset_scanner`, `python -m asset_scanner.tools_catalog`)는 서버를 실행하거나 접속하지 않으며 이 모듈과 분리돼 있습니다(SDK도 import하지 않음).

### 준비 (Windows PowerShell)

```powershell
cd asset-scanner
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt      # 공식 MCP Python SDK mcp==2.3.0 포함
```

SDK `mcp`는 2026-07-28 규격을 지원하는 정식 2.x 중 **2.3.0**으로 고정했습니다(근거·태그 SHA·호환 확인: [필드 매핑 7장](docs/field-mapping.md)). 실제 설치 전체 버전은 `requirements-live-lock.txt`에 있습니다.

### 실행

```powershell
# 개발용 서버를 별도 프로세스로 실행해 tools/list를 조회하고 결과를 저장합니다
.\.venv\Scripts\python.exe -m asset_scanner.live_tools --demo --output output\live-demo.result.json
```

- `--demo`가 없으면 인자 오류(종료 코드 2)이며 서버를 실행하지 않습니다.
- 선택 옵션: `--scenario`(개발용 서버의 검증용 동작, 기본 `two-tools`), `--timeout`(전체, 기본 60초), `--request-timeout`(요청 하나, 기본 15초), `--max-pages`(기본 50), `--max-tools`(보존할 최대 Tool 수, 기본·최대 5000), `--demo-request-log <파일>`(서버가 받은 요청의 메서드 이름·횟수만 기록하는 검증용 로그).
- **제한값은 서버를 실행하기 전에 검사합니다.** 두 시간 값은 `0`보다 크고 `86400`(24시간) 이하인 **유한한 수**여야 합니다(`nan`·`inf`·`-inf`·`0`·음수·너무 큰 값은 거부). `--max-pages`는 1 이상, `--max-tools`는 1~5000(정적 카탈로그의 고정 한도 5000을 넘을 수 없음)이어야 합니다. 잘못된 값은 **인자 오류(종료 코드 2)** 이며 서버를 실행하지 않고 결과 파일·요청 로그를 만들지 않으며 기존 결과 파일은 그대로입니다. 공개 함수 `collect_live_demo`도 같은 검사(`validate_limits`)를 실행 전에 하고 잘못된 `LiveLimits`는 `ValueError`로 거부하므로 CLI와 함수의 동작이 다르지 않습니다.
- 종료 코드: 0 완전 / 1 부분 / 2 인자 오류 / 3 실패 / 4 저장 실패. 결과 파일은 정적 카탈로그와 같은 방식으로(임시 파일 후 교체) 저장하며 실패해도 기존 결과는 유지됩니다.
- 서버를 시작하는 데 몇 초가 걸립니다(첫 실행은 더 오래 걸릴 수 있음). 시간 초과·서버 조기 종료·오류에서도 서버 프로세스와 연결을 정리하고 traceback 없이 상태로 기록합니다.

콘솔 출력 예 (설명문·응답 원문은 출력하지 않습니다):

```text
서버 프로세스를 실행합니다: 개발용 MCP 서버 (stdio, tools/list만 요청, tools/call 없음)
실제 stdio 조회 결과 (개발용 서버, 팀 테스트베드 아님)
협상된 protocol_version: 2026-07-28
수집 상태: complete (all_servers_listed)
읽은 Tool: 2개
  - "echo_text"
  - "add_numbers"
결과 저장: output\live-demo.result.json
```

### 무엇이 일어나고 무엇을 기록하는가

- 공식 SDK 클라이언트가 개발용 서버를 stdio 프로세스로 실행합니다. 버전 협상은 SDK의 기본 흐름(`server/discover` 우선, 구형 서버는 `initialize`)에 맡기며 이 프로젝트가 초기 통신을 구현하거나 `initialize`를 강제하지 않습니다.
- 서버에 보내는 요청은 `tools/list`(와 협상 요청)뿐입니다. **`tools/call`은 보내지 않습니다.** 시간 초과가 나면 SDK가 표준 취소 알림(`notifications/cancelled`)을 보냅니다.
- 협상된 `protocol_version`, `serverInfo`, `capabilities`는 서버가 실제로 보낸 값만 `servers[].live`에 기록합니다. 협상된 버전이 2026-07-28이 아니면 응답을 읽지 않고 `protocol_version_unsupported`로 기록합니다.
- `nextCursor`가 있으면 다음 페이지를 요청합니다(빈 문자열 커서도 이어짐). 전체·요청별 시간 제한, 최대 페이지 수, 반복 커서 감지가 무한 대기를 막습니다.
- **`--max-tools`는 최종 페이지를 포함한 전체 누적 Tool 수에 적용합니다.** 한 페이지가 남은 한도를 넘으면 남은 한도까지만 보존하고 초과분은 **결과에 정의를 저장하지 않으며**(`servers[].live.limit_exclusions`에 페이지별 응답 건수·보존 건수·제외 건수만 기록, 이슈 `tool_limit_reached`에 `excluded_tools`) 서버를 `partial`, `tool_count_complete: false`로 표시하고 다음 페이지는 요청하지 않습니다. 한도와 **정확히 같은 수**를 모았고 마지막 페이지임이 확인되면 `complete`를 유지하고, 한도에 도달했지만 `nextCursor`가 남아 있으면 `partial`입니다(`tool_limit_reached` + `next_cursor_remaining`). 보존한 Tool의 `page_index`·`index_in_page`·`internal_ref`·가림 기록·소속 서버는 그대로입니다. **한도는 서버가 이미 보낸 페이지의 수신 바이트나 SDK 파싱 메모리를 제한하지 않습니다.** 최초 응답 페이지 자체는 서버가 전송하며 이 한도는 결과에 보존하는 Tool 수와 다음 요청 여부를 정합니다.
- 응답은 SDK가 협상된 버전의 스키마로 검증한 **result dict 그대로** 받습니다. SDK의 `Tool` 모델 변환(기본값 보충, 잘못된 `x-mcp-header` Tool 조용히 제외)을 거치지 않으며, SDK의 응답 캐시는 끕니다. SDK가 거부한 응답은 `sdk_validation_rejected`로 근거(오류 종류·위치)와 함께 실패 기록하며 빈 목록으로 취급하지 않습니다. 자세한 구분은 [필드 매핑 7-3](docs/field-mapping.md).
- 결과의 `source`는 `live_stdio_query` / `live_server_query: true` / `target.team_testbed: false`입니다(저장된 응답의 `live_server_query: false`와 다름). **조회 성공은 Agent 노출이나 호출 가능을 뜻하지 않습니다.** 공통 ID와 팀 공통 스키마는 구현하지 않았고 `server_ref`·`internal_ref`는 이 결과 안에서만 쓰는 이름입니다.
- 가림·정규화·제한된 정의 검사·안전한 저장은 정적 카탈로그와 같은 코드를 씁니다. 가림 전 응답은 파일·로그에 쓰지 않고 메모리에서만 다룹니다. 서버 stderr는 버리며 내용·크기를 저장하지 않습니다.

### 개발용 서버, 정답 목록, 검증용 시나리오

| 파일 | 내용 |
| --- | --- |
| `asset_scanner/dev_mcp_server.py` | 공식 SDK로 만든 개발용 stdio 서버. 서로 다른 Tool 2개(`echo_text`, `add_numbers`)를 광고하고 `tools/call`은 처리하지 않습니다. 단독 실행: `python -m asset_scanner.dev_mcp_server` (stdio로 JSON-RPC를 기다립니다) |
| `examples/dev-server-ground-truth.json` | 위 Tool 2개의 이름·설명·`inputSchema` 정답 목록(서버 코드와 별개로 작성). 팀 테스트베드의 정답 목록이 아님 |

`--scenario` 값: `two-tools`(기본), `empty`(성공한 빈 목록), `error`(서버 오류), `paginated`, `empty-cursor`(빈 문자열 커서), `big-first-page`(첫 페이지 Tool 2개+커서, `--max-tools` 검증), `uneven-pages`(1개+커서, 2개, `--max-tools` 누적 검증), `fail-second`(뒤 페이지 실패), `slow`(응답 없음), `exit-early`(조회 중 서버 종료), `cursor-loop`, `endless`, `secrets`(가짜 인증정보), `unicode`, `sparse`(선택 필드 없음), `bad-header`(SDK가 제외할 Tool), `invalid-schema`(SDK 검증 거부). 이 값들은 스캐너의 경계·실패 처리를 실제 통신으로 검증하기 위한 것입니다.

### 테스트 구분

```powershell
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests\test_live_tools.py   # 서버를 실행하지 않는 테스트 (가상 응답 단위 테스트 포함)
.\.venv\Scripts\python.exe -m pytest tests\test_live_tools.py -v             # 개발용 서버를 실제로 실행하는 stdio 통합 테스트 (약 3분)
.\.venv\Scripts\python.exe -m pytest -v                                      # 전체 (서버 실행 포함)
```

- **가상 응답 단위 테스트**: 저장된 응답 JSON을 읽습니다. 서버를 실행하지 않습니다.
- **실제 stdio 통합 테스트**: 개발용 서버를 별도 프로세스로 실행해 SDK 클라이언트로 통신합니다. 서버가 받은 메서드 기록으로 `tools/call`이 없음을 확인하고, 종료 후 서버 pid가 남지 않았는지 확인합니다.
- **팀 테스트베드 검증**: 아직 하지 않았습니다(자료 대기).

### 한계

- 실행 대상은 내장 개발용 서버 하나입니다. 원격(HTTP)·인증이 필요한 서버, OpenClaw 설정에서 읽은 서버 명령 실행은 다음 단계입니다.
- JSON 파싱을 SDK가 하므로 전송 계층의 중복 키·`NaN` 토큰 원문은 확인하지 못합니다. SDK가 검증에서 거부한 응답은 Tool 정의를 보존하지 못합니다. 음수 `ttlMs`는 SDK가 0으로 올린 값이 기록될 수 있습니다.
- 2026-07-28로 협상된 연결만 읽습니다.

## 이번 단계에서 하지 않은 것 / 후속 확인

- 실제 팀 OpenClaw 2026.9.5 설정 원본으로 수집 확인 (`openclaw config schema`와 필드 대조 포함)
- 테스트베드 2026.9.5의 환경변수 기본값 문법이 현행 공개 문서(`${A:-${B}}` → 안쪽 `B`만 참조)와 같은지 확인
- `$include` 파일 읽기와 병합, 환경변수·SecretRef 해석(값은 계속 저장하지 않음)
- Node-hosted MCP 서버, Gateway/Node 자산, `DECLARES` 관계, 공통 스키마(`InventorySnapshot`) 변환
- 팀 테스트베드·OpenClaw 설정에서 읽은 서버 명령의 실제 조회 (개발용 서버 1개의 stdio 조회만 지원), 원격(HTTP)·인증 서버, `tools/call`, Resource·Prompt 수집, 공통 ID 생성
