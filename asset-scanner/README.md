# 자산 스캐너 — OpenClaw MCP 서버 등록 정보 수집기 (1단계)

OpenClaw 설정 파일(JSON/JSON5)을 **읽기만 해서** `mcp.servers`에 등록된 MCP 서버 목록과 출처를 JSON으로 저장합니다.

- 출력은 **스캐너 내부 협의용 초안**입니다. 팀 공통 스키마가 아닙니다. → [필드 매핑과 근거](docs/field-mapping.md)
- 설정 속 명령 실행, 서버 접속, 도구 조회, 환경변수 값 해석, `$include` 파일 읽기, 설정 수정을 **하지 않습니다.**
- 실제 연결 여부·도구 목록·capabilities·protocol_version·노출/호출 가능 상태는 채우지 않습니다.
- **실제 테스트베드 연동은 미검증입니다.** `examples/`의 설정은 모두 테스트용 가상 설정이며 실제 팀 설정이 아닙니다.

## 구성

```text
asset-scanner/
├── asset_scanner/
│   ├── cli.py         # --config / --output 명령행
│   ├── collector.py   # 파일 읽기·JSON5 파싱·mcp.servers 수집
│   ├── redaction.py   # 비밀값 가림, 환경변수·SecretRef 참조 감지
│   └── report.py      # 결과 JSON(협의용 초안) 조립
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

| 종료 코드 | 의미 (결과 파일은 1·3에서도 저장됨) |
|---|---|
| 0 | 완전 수집 (`complete`) |
| 1 | 부분 수집 (`partial`) — 미해석 include·환경변수 참조, 서버별 문제 등 |
| 2 | 인자 오류 |
| 3 | 수집 실패 (`failed`) — 파일 없음·읽기 실패·JSON5 오류·잘못된 구조 |
| 4 | 결과 파일 저장 실패 또는 `--output`이 `--config`와 같은 파일 |

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## 예제 결과 (`examples\two-servers.json5`, 일부 생략)

표준출력:

```text
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

## 이번 단계에서 하지 않은 것 / 후속 확인

- 실제 팀 OpenClaw 2026.9.5 설정 원본으로 수집 확인 (`openclaw config schema`와 필드 대조 포함)
- 테스트베드 2026.9.5의 환경변수 기본값 문법이 현행 공개 문서(`${A:-${B}}` → 안쪽 `B`만 참조)와 같은지 확인
- `$include` 파일 읽기와 병합, 환경변수·SecretRef 해석(값은 계속 저장하지 않음)
- Node-hosted MCP 서버, Gateway/Node 자산, `DECLARES` 관계, 공통 스키마(`InventorySnapshot`) 변환
- MCP 서버 접속과 도구 목록 조회 (다음 단계)
