# OpenClaw `mcp.servers` → 스캐너 결과 필드 매핑 (협의용 초안)

> 상태: 스캐너 내부 초안 v0.1.0-draft · 작성일 2026-09-29
> 이 문서의 필드명과 구조는 **팀 공통 스키마가 아닙니다.** `docs/common-data-structure-discussion.md`(협의 전 제안)의
> 결정 사항이 확정되면 이 결과를 공통 형식으로 변환합니다. 전역 자산 ID 규칙도 정하지 않았습니다.

## 1. 근거 자료

| 근거 | 내용 | 확인 방법 |
|---|---|---|
| OpenClaw 문서 [MCP, skills, and plugins](https://docs.openclaw.ai/gateway/config-extensions) | 등록 위치 `mcp.servers`, `command`/`args`, `url`/`transport`, `enabled: false`는 정의를 유지한 채 제외 | 2026-09-29 웹 문서 확인 |
| OpenClaw 문서 [Transports and OAuth](https://docs.openclaw.ai/cli/mcp/transports) | stdio: `command`·`args`·`env`·`cwd`/`workingDirectory`, 원격: `url`·`headers`·`transport`·`auth`·`oauth`·`sslVerify`·`clientCert`/`clientKey` | 2026-09-29 웹 문서 확인 |
| OpenClaw 문서 [environment, secrets, and includes](https://docs.openclaw.ai/gateway/config-secrets-env) | `${VAR}`(대문자 이름만), `${VAR:-기본값}`, `$${VAR}` 이스케이프, SecretRef `{source, provider, id}`, `$include` | 2026-09-29 웹 문서 확인 |
| OpenClaw **2026.9.6** npm 패키지의 `docs/nodes/mcp-and-skills.md` (제목 "Node-hosted MCP servers and skills") | Node 쪽 MCP 서버는 Node 머신의 `openclaw.json`에 `nodeHost.mcp.servers.<이름>`으로 선언. 문서 예제의 필드: `command`·`args`·`toolFilter`(stdio), `url`·`transport`·`headers`(원격). 이 문서에 `enabled`는 나오지 않음. 노드 호스트는 설정 변경을 감시하지 않으며 재시작 후 반영. OAuth MCP 서버는 이 경로에서 미지원 | 2026-10-06 `npm pack openclaw@2026.9.6`(tarball 내려받기만, 설치·실행 없음)로 받은 패키지의 문서 파일을 직접 읽음. 같은 내용을 현행 공개 문서 [docs.openclaw.ai/nodes/mcp-and-skills](https://docs.openclaw.ai/nodes/mcp-and-skills)에서도 확인 (공개 문서는 페이지에 버전 표기가 없음) |
| 공격 표면 정의 v2.0 §7.3, §12.1 | 비밀값 미수집, MCP Server 최소 필드(서버 이름·선언 위치·source path·command/args 또는 endpoint·transport) | `git show origin/docs/mcp-attack-surface-definition:docs/mcp-attack-surface.md` |

**미검증:** 위 필드는 문서 기준입니다. 확인한 것은 문서 내용이며, 다음은 확인하지 않았습니다.
- `openclaw config schema` 출력과 2026.9.6 소스(설정 스키마): `nodeHost.mcp.servers` 항목의 허용 필드와 `enabled` 지원 여부는 문서에 없어 스키마로 확인하지 못했습니다. 스캐너는 설정에 적힌 `enabled`만 그대로 기록합니다.
- 서버가 실제로 등록된 Node 설정 원본: SNAP-1 Node 설정에는 `nodeHost.mcp`가 없습니다. 가상 설정과 테스트로만 확인했습니다.
- 위 표 중 `mcp.servers` 근거(`config-extensions` 등)는 2026-09-29 공개 문서 기준이며, 2026.9.6 패키지 문서와의 일치는 이번에 `nodeHost.mcp.servers`에 대해서만 대조했습니다.

## 1-1. 등록 영역 선택 (`--registry-path`)

한 번의 실행은 등록 영역 **하나**만 수집합니다. 기본값은 `mcp.servers`이며 기존 명령의 동작은 그대로입니다.

| 값 | 의미 | 쓰는 곳 |
|---|---|---|
| `mcp.servers` (기본) | Gateway 설정의 MCP 서버 등록 영역 | Gateway 설정 파일 |
| `nodeHost.mcp.servers` | Node 호스트 설정의 MCP 서버 등록 영역 | Node 설정 파일 |

- 임의의 경로는 받지 않습니다. 키 이름에 점이 들어갈 수 있어 문자열 경로는 모호하기 때문입니다. 영역을 늘리려면 코드의 `SUPPORTED_REGISTRY_PATHS`에 추가합니다.
- 파일 전체를 파싱하되, 선택한 등록 영역만 수집·보고합니다. 같은 파일에 두 영역이 모두 있어도 고르지 않은 영역의 서버, 중복 키, `$include`, 가린 키는 결과·`collection.reasons`·`key_redactions`에 나타나지 않습니다. 파일 전체를 파싱하므로 JSON5 구문 오류나 최상위가 객체가 아닌 경우는 어느 영역을 골라도 `failed`입니다.
- 선택한 경로는 `source.registry_path`, 서버별 `declaration_path`·`declaration_pointer`, `collection.reasons[].field_path`, 서버별 `issues[]`·`unresolved[]`·`redactions[]`의 위치에 그대로 쓰입니다. 수집 실패 결과에도 기록됩니다.
- `registry_absent`의 `field_path`는 **처음 없는 단계**입니다. 예: Node 설정에 `nodeHost`만 있고 `mcp`가 없으면 `nodeHost.mcp`. 이것은 "서버 0개"가 아니라 "그 설정에 해당 영역이 선언되지 않음"입니다. SNAP-1 Node 설정이 이 경우입니다.
- 이 단계의 `$include`·중복 키 판정도 선택한 경로 기준입니다. 예: 선택한 영역의 조상(`nodeHost`)에 있는 `$include`는 `partial`로 만들지만, 반대편 영역(`mcp`)의 `$include`는 영향이 없습니다.
- 실패 코드 `<키>_not_object`는 객체가 아닌 단계의 마지막 키 이름을 씁니다. 기본 경로에서는 기존과 같은 `mcp_not_object`·`servers_not_object`이고, Node 경로에서는 `nodeHost_not_object`·`mcp_not_object`·`servers_not_object`입니다. `field_path`로 어느 단계인지 구분합니다.
- 아래 표들의 `mcp.servers`는 "선택한 등록 영역"으로 읽으면 됩니다.

## 2. 서버 항목 필드

| 결과 필드 | 원천 | 의미 | 없을 때 |
|---|---|---|---|
| `registration_key` | `mcp.servers`의 키 | 등록키(서버 이름). 코드에 고정된 이름 없음. 키가 토큰처럼 보이면 `<redacted-key-N>` | — |
| `registration_key_redacted` | 계산 | 등록키를 자리표시자로 바꿨으면 `true`. 설정에 `<redacted-key-1>`처럼 적힌 일반 키는 `true`가 아니므로 이 값으로 구분 | 생략 |
| `source_path` | CLI `--config` | 읽은 설정 파일의 절대 경로. 토큰처럼 보이는 경로 조각만 `<redacted>` | — |
| `declaration_path` | 키 위치 | 사람이 읽는 선언 위치. 점·공백 등이 있는 키는 `mcp.servers["a.b"]` | — |
| `declaration_pointer` | 키 위치 | 같은 위치의 JSON Pointer(RFC 6901) — 기계 처리용 | — |
| `declared.enabled` | `enabled` (boolean) | 설정에 **명시된** 값만 기록 | 필드 생략. 기본 동작(활성으로 간주 등)을 추측하지 않음 |
| `declared.transport` | `transport` (string) | 명시된 전송 방식 | 생략. 문서상 원격 기본값이 `sse`이지만 채우지 않음 |
| `declared.command` | `command` | stdio 실행 명령 (가림 처리 후) | 생략 |
| `declared.args` | `args` (string 배열) | 명령 인자 (가림 처리 후) | 생략 |
| `declared.cwd` / `declared.workingDirectory` | 같은 이름 | 작업 폴더. 원천 키 이름을 그대로 유지 | 생략 |
| `declared.url` | `url` | 원격 endpoint (가림 처리 후) | 생략 |
| `declared_keys` | 항목의 모든 키 | 선언된 키 이름 목록(값 없음) | — |
| `credentials.env` / `credentials.headers` | `env`, `headers` | 이름 목록과 값의 **종류**(`literal`/`env_ref`/`literal_with_env_ref`/`secret_ref`/`invalid_secret_ref`/`non_string`)만. 값은 저장하지 않음 | 필드 생략 |
| `credentials.auth` / `oauth` / `clientCert` / `clientKey` | 같은 이름 | 존재 여부(`present`), 하위 키 이름, SecretRef이면 `value_kind`만 | 필드 생략 |
| `other_declared_keys` | 위 목록에 없는 키 | 이름만 기록(예: `requestTimeoutMs`, `sslVerify`, `toolFilter`, `codex`). 값은 이번 단계에서 해석하지 않음 | `[]` |
| `unresolved[]` | 항목 하위 | 해석하지 않은 `$include`·`${VAR}`·SecretRef. 이름·위치만 | `[]` |
| `redactions[]` | 가림 처리 | 가린 `field_path`와 `reason` | `[]` |
| `issues[]` | 검증 | 서버별 문제 (아래 표) | `[]` |
| `collection_status` | 계산 | `complete` / `partial`(미해석 참조·타입 오류·잘못된 SecretRef) / `invalid`(항목이 객체가 아니거나 내부 오류) | — |

서버별 문제 코드 (`issues[].code`). 파일 전체 실패와 달리 다른 서버의 수집을 멈추지 않습니다.

| code | 의미 | 항목 상태 |
|---|---|---|
| `entry_not_object` | 등록 항목이 객체가 아님 | `invalid` |
| `field_type_invalid` | `enabled`·`command`·`args`·`env` 등의 자료형이 틀림. 값은 저장하지 않고 자료형만 기록 | `partial` |
| `duplicate_key` | 항목 안에서 같은 키가 반복됨 (마지막 값만 읽음) | `partial` |
| `invalid_secret_ref` | 인증정보 위치(`env`·`headers` 값, `auth`·`oauth`·`clientCert`·`clientKey`)에 SecretRef 모양 객체가 있으나 형식이 틀림. `problems`에 필드·문제 종류·자료형만 기록 (원래 값 없음) | `partial` |
| `no_connection_target_declared` | `command`와 `url`이 모두 없음 (선언 사실에 대한 경고) | 영향 없음 |
| `collector_internal_error` | 이 항목 처리 중 스캐너 내부 오류. 예외 종류만 기록하고 항목은 버리지 않음 | `invalid` |

SecretRef 판정: 키가 `source`·`provider`·`id`로만 이루어지고 `source`가 있는 객체만 SecretRef 후보로 봅니다. `source`가 문자열(env/file/exec/store)이고 `provider`·`id`가 문자열이면 유효한 참조입니다. `{"source": "git", "url": ...}`처럼 다른 키가 섞인 일반 설정 객체는 참조로 보지 않고, 인증정보 위치가 아닌 곳(`codex` 등)의 잘못된 모양 객체도 문제로 보고하지 않습니다.

`declared`는 OpenClaw 원천 키 이름을 바꾸지 않고 보존합니다. 공통 형식의 `endpoint`는 `declared.url`에서 변환하는 것을 전제로 합니다.

## 3. 파일 전체 수집 상태 (`collection`)

| `status` | `outcome` | 의미 | `server_count` |
|---|---|---|---|
| `complete` | `servers_found` | 모든 항목을 완전히 읽음 | 개수 |
| `complete` | `empty_registry` | `mcp.servers`가 `{}` — 정상적인 빈 등록 목록 | `0` |
| `complete` | `registry_absent` | `mcp` 또는 `mcp.servers` 영역 자체가 없음 (`{}`, `{"mcp":{}}`) | `null` |
| `partial` | `registry_absent` | 영역이 없지만 영향을 주는 `$include`나 `mcp`·`servers` 키 중복이 있어 없다고 확정할 수 없음. 예: `{"mcp":{"servers":{…}},"mcp":{}}` | `null` |
| `partial` | `servers_found` / `empty_registry` | 서버별 문제, 중복 등록키, 미해석 include·참조가 있음 | 개수 |
| `failed` | `file_not_found` | 파일 없음 | `null` |
| `failed` | `read_error` | 폴더 경로, 권한 등 읽기 실패, UTF-8 아님 | `null` |
| `failed` | `parse_error` | JSON5 구문 오류 (줄·열 번호만 기록) | `null` |
| `failed` | `invalid_structure` | 최상위·`mcp`·`mcp.servers`가 객체가 아님 | `null` |

`server_count: null`은 "0개"가 아니라 "셀 수 없음"입니다. 실패는 절대 빈 목록 성공으로 보고하지 않습니다.
`registry_absent` 안내 자체는 불완전 사유가 아닙니다. 사유가 있다는 이유만으로 `partial`이 되지 않고, 중복 키·미해석 include처럼 결과를 확정하지 못하게 하는 사유가 있을 때만 `partial`입니다.

`collection.key_redactions`: 비밀값처럼 보여 자리표시자로 바꾼 객체 키의 위치 목록 (`registry_absent`·`failed`에서는 생략). 선택한 등록 영역 안의 키만 기록합니다. (등록 영역 선택 기능 추가 전에는 설정 파일 전체의 가린 키를 기록했습니다. 영역 밖의 키는 수집 대상이 아니므로 이번에 범위를 줄였습니다.)

## 4. `$include`와 참조 처리

- `$include`는 읽지 않습니다. 최상위·`mcp`·`mcp.servers`·서버 항목 하위에 있으면 등록 목록이 달라질 수 있으므로 `unresolved`에 기록하고 `partial`로 보고합니다. `agents` 등 등록 영역과 무관한 위치의 include는 영향이 없어 기록하지 않습니다.
- `$include` 대상 문자열도 결과로 나가므로 다른 문자열과 같은 가림 규칙을 적용하고, 가렸으면 `unresolved[].redactions`에 사유를 남깁니다.
- SecretRef 객체는 `source`·`provider`·`id`(참조 식별자)만 남깁니다. 식별자가 토큰처럼 보이면 `<redacted>`로 바꿉니다.

### 환경변수 참조 문법 (공개 문서 [Default values](https://docs.openclaw.ai/gateway/config-secrets-env#default-values), 2026-09-29 기준)

| 표현 | 참조 이름 | 결과에 남는 문자열 | 비고 |
|---|---|---|---|
| `${VAR}` | `VAR` | `${VAR}` | 펼치지 않음 |
| `${VAR:-fallback}` | `VAR` | `${VAR:-<redacted>}` | fallback은 비밀일 수 있어 가리고 `env_default_value_removed` 기록 |
| `${VAR:-}` | `VAR` | `${VAR:-}` | 빈 fallback은 가릴 것이 없음 |
| `$${VAR}` | 없음 | `$${VAR}` | 이스케이프된 문자 그대로의 값 |
| `$${VAR:-x}` | 없음 | `$${VAR:-x}` | 이스케이프된 문자 그대로의 값 |
| `${A:-${B}}` | `B` | `${A:-${B}}` | fallback에 `$`·`{`가 들어갈 수 없으므로 바깥쪽은 표현식이 아님. 안쪽 `${B}`만 참조 |

- 이름은 대문자 `[A-Z_][A-Z0-9_]*`만 인식합니다 (`${lower}`는 문자 그대로).
- 실제 환경변수 값은 읽거나 펼치지 않습니다. `declared`의 문자열은 가림 처리된 값이며, 바뀐 곳은 `redactions`에 사유와 함께 남습니다.
- **미확인:** 위 규칙은 현행 공개 문서 기준입니다. 팀 테스트베드(OpenClaw 2026.9.5)가 같은 규칙으로 동작하는지는 실제 환경에서 확인해야 합니다.

## 5. 비밀값 가림 규칙

| 대상 | 처리 | `reason` |
|---|---|---|
| `env`·`headers` 값 | 저장하지 않음, 이름과 종류만 | (`values_withheld: true`) |
| `auth`·`oauth`·`clientCert`·`clientKey` | 존재 여부·하위 키 이름만 | (`value_withheld: true`) |
| `--token X`, `--api-key=X` 등 비밀 이름 플래그 뒤 값 | `<redacted>` (값이 기본값 없는 `${VAR}`면 유지) | `value_after_secret_flag`, `secret_flag_value` |
| `PASSWORD=X` 형태 인자 | 값만 `<redacted>` | `secret_assignment_value` |
| 비밀 이름이 아닌 `--옵션=값` | 옵션 이름은 두고 값 부분에 문자열 규칙 전체 적용 (예: `--endpoint=https://<redacted>@host/mcp?token=<redacted>`) | 값 규칙의 사유 |
| 문자열 안 어디든 있는 URL | 사용자정보·쿼리 값·fragment·토큰 모양 경로 조각을 `<redacted>` (쿼리 키 이름·호스트·일반 경로는 유지) | `url_userinfo`, `url_query_values`, `url_fragment`, `url_path_token` |
| `Name: value` 헤더 문자열 (`-H`, `--header`, `--header=` 값 등) | 이름이 인증 관련(`Authorization`, `Cookie`, `X-Api-Key`, token·secret·auth·key 포함)이면 값만 `<redacted>`. `Content-Type` 등은 유지 | `auth_header_value` |
| 셸 명령 문자열 (`-c`, `/c`, `/k`, `-Command`, `--command`, `-EncodedCommand` 다음의 공백 포함 인자) | 해석·실행하지 않고 통째로 `<redacted>` | `shell_command_string_withheld` |
| 공백이 든 복합 인자 (예: `"run --api-key X now"`) | 단어 단위로 검사해 비밀이 보이면 통째로 `<redacted>`, 아니면 유지 (`"hello world"`) | `compound_arg_with_secret_withheld` |
| 알려진 토큰 모양(`sk-…`, `ghp_…`, `xox…`, `AKIA…`, JWT, `Bearer …`) | `<redacted>` | `token_pattern:<종류>` |
| 32자 이상 무작위 문자열 | `<redacted>` (보수적: 커밋 해시 등도 가려질 수 있음) | `high_entropy_value` |
| 토큰처럼 보이는 객체 키 (등록키, env·header 이름 등) | 파싱 단계에서 `<redacted-key-N>`으로 바꿔 선언 위치·필드 경로·표준출력에도 원래 키가 나가지 않음 (자리표시자 규칙은 아래) | `key_looks_like_secret` |
| 토큰처럼 보이는 참조 이름·SecretRef id·경로 조각 | `<redacted>` | `ref_name_looks_like_secret` 등 |
| `$include` 대상 | 문자열 규칙 적용 (fallback 가림 등) | `unresolved[].redactions` |
| 파싱 오류·내부 오류 메시지 | 원문 대신 줄·열 번호, 예외 종류만 | — |

설정 파일 원문 전체와 파일 해시(비밀값을 포함한 내용의 해시)는 저장하지 않습니다. 원래 키나 비밀값의 해시를 식별자로 쓰지 않습니다.

### 키 자리표시자 규칙

- 번호는 **객체 하나 안에서** 등장 순서대로 붙입니다. 원래 키나 그 해시는 쓰지 않습니다. 다른 객체의 `<redacted-key-1>`은 다른 키일 수 있으며, 선언 위치(경로)로 구분합니다.
- 같은 객체에 설정 원문의 일반 키로 이미 있는 이름(예: `<redacted-key-1>`)은 건너뛰고 다음 번호를 씁니다. 따라서 가림 때문에 서로 다른 항목이 같은 이름으로 합쳐지지 않습니다.
- 같은 원래 키가 두 번 선언되면 같은 자리표시자를 받으므로, 기존 규칙대로 중복(`duplicate_registration_key`·`duplicate_key`)과 `partial`로 보고합니다. 가림 때문에 중복이 새로 생기지는 않습니다.

### 가림의 한계 (미지원)

- 비밀 판단은 이름·모양 기반 규칙입니다. 평범한 단어처럼 생긴 비밀값이 이름 없는 위치 인자로 들어 있으면(예: `sample-server mysecretword`) 가려지지 않습니다.
- 셸 명령 문자열은 알려진 셸 플래그 다음 인자와 공백 포함 복합 인자만 다룹니다. 셸 문법(따옴표·변수·파이프)을 해석하지 않습니다.
- 헤더 형태는 `Name: value` 한 줄만 인식합니다.
- `other_declared_keys`의 값(`toolFilter`, `codex` 등)은 저장하지 않으므로 가림 대상이 아닙니다.

## 6. Tool 카탈로그: 저장된 `tools/list` 응답 → 결과 필드 (MCP 2026-07-28)

> 상태: 스캐너 내부 개발용 초안 `0.1.0-draft`. 구현은 `asset_scanner/tools_catalog.py`. 팀 공통 스키마와 공통 ID(Issue #10, PR #11 협의안)는 반영하지 않았다.

### 6-1. 근거 자료와 확인 방법 (2026-10-06 조회)

| 자료 | 용도 |
| --- | --- |
| [MCP 2026-07-28 Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | `tools/list` 요청·응답 형태, Tool 필드, 이름 규칙, 오류 처리 |
| [MCP 2026-07-28 Pagination](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/pagination) | `nextCursor`는 불투명 토큰, 없으면 종료, 빈 문자열도 유효한 커서, 잘못된 커서는 -32602 |
| `modelcontextprotocol/modelcontextprotocol` 저장소 `schema/2026-07-28/schema.ts` | 필드 정의의 기준. 파일 안 `LATEST_PROTOCOL_VERSION = "2026-07-28"` |
| 같은 저장소의 `schema/2026-07-28/examples/` (`ListToolsResult`, `Tool`) | 테스트 응답의 형태 |

**확인한 파일의 고정 위치 (2026-10-06 확인):**

| 파일 | 마지막으로 수정한 커밋 SHA | 비고 |
| --- | --- | --- |
| `schema/2026-07-28/schema.ts` | `271ecc9accafdd9b83a3c869fa67c22953b2af80` (2026-07-28, "fix(schema): apply subscriptions/listen envelope and MetaObject rename to 2026-07-28") | 이 SHA 시점의 파일(raw URL에 SHA 사용)과 이전에 `main`에서 내려받은 파일이 **바이트 단위로 같음**(`cmp` 일치, SHA-256 `742750af0bb8c716e7030c4977c992b55d1adc4407e9e66997db5846baedc2cd`). `schema.json`도 같음 |
| `docs/specification/2026-07-28/server/tools.mdx` | `0cb6c6a31768cbb16129b35e6b569a31fecfe1b6` | 해당 SHA 원문에서 `resultType`, `ttlMs`, `cacheScope`, `nextCursor` 예시를 확인 |
| `docs/specification/2026-07-28/server/utilities/pagination.mdx` | `b488c16623e5202a3961e551886044577ae0f096` | 해당 SHA 원문에서 "empty string is a valid cursor" 규정을 확인 |

위 SHA는 각 파일을 마지막으로 바꾼 커밋이다(GitHub `commits?path=` 조회). 조회 시점의 `main` HEAD는 `8e12bf3c8f01f374146acfa19b8ece0018bfc86c`(2026-10-05)이며, 이 파일들은 그 이후에도 위 커밋 내용 그대로다. 고정 URL 형태: `https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/<SHA>/<경로>`. 규격이 바뀌면 이 SHA를 기준으로 차이를 확인한다. 위의 modelcontextprotocol.io 페이지는 같은 저장소의 문서가 게시된 것이며, 이 SHA의 원문과 위 인용 구절을 대조했다.

**주의:** 규격 사이트의 Schema Reference 페이지를 요약 도구로 읽은 결과는 `title`, `outputSchema`, `ttlMs`, `cacheScope`가 없다고 나와 위 Tools 페이지와 어긋났다. `schema.ts` 원본을 직접 읽어 확인한 결과 이 필드들이 모두 정의돼 있다. 요약 결과는 근거로 쓰지 않았고, 구현은 `schema.ts`와 Tools·Pagination 페이지 원문에 맞췄다. 다른 버전(예: 2025년 규격)의 응답은 이 구조와 같다고 가정하지 않으며, 입력이 `protocol_version`으로 `2026-07-28`을 선언하지 않으면 읽지 않는다.

### 6-2. 응답(`ListToolsResult`) 필드

| 규격 필드 | 필수 | 이 스캐너의 처리 | 결과 위치 |
| --- | --- | --- | --- |
| JSON-RPC `result` / `error` | 둘 중 하나 | `result`면 해석, `error`면 `error_response` 실패. 둘 다 있거나 둘 다 없으면 `invalid_response_structure`. `jsonrpc` 없이 `result` 객체만 있는 형태는 `bare_result`로 받는다. | `servers[].pages[].wrapper` |
| `resultType` | 예 (`complete` \| `input_required` \| 기타 문자열). 스키마 주석: 이 버전의 서버는 **MUST** 포함 | `complete`만 완료된 Tool 목록으로 읽는다. **없거나 문자열이 아니면** 규격 위반(`result_type_missing`/`result_type_invalid`)으로 기록하고 **완료를 추정하지 않는다**: Tool은 보존하되 서버는 `partial`/`completion_unverified`. `input_required`·알 수 없는 문자열은 구조를 추정하지 않고 읽지 않는다(`failed`). | `pages[].result_type`, `pages[].result_type_state`, `issues` |
| `tools` | 예 | 배열이 아니거나 없으면 실패. 빈 배열은 성공한 빈 목록. | `servers[].tools` |
| `nextCursor` | 아니오 | 문자열이면(빈 문자열 포함) 목록이 남은 것으로 본다. 값은 저장하지 않고 존재 여부만 기록한다. | `pages[].has_next_cursor` |
| `ttlMs`, `cacheScope` | 규격상 예 (`CacheableResult`: `ttlMs: number`(0 이상), `cacheScope: "public" \| "private"`) | 없거나 형식이 틀리면 규격 위반(`cache_hint_missing`/`cache_hint_invalid`)으로 **기록만** 한다. Tool은 버리지 않고 수집 상태도 바꾸지 않는다. 틀린 값은 힌트로 기록하지 않는다. | `pages[].ttl_ms`, `cache_scope`, `issues` |
| `_meta` | 아니오 | 가림 후 보존 (`io.modelcontextprotocol/serverInfo`는 서버가 스스로 밝힌 값일 뿐이며 검증하지 않는다). | `pages[].result_meta` |
| 그 밖의 키 | - | 이름만 기록 | `pages[].other_result_fields` |

### 6-3. Tool(`Tool`) 필드

| 규격 필드 | 필수 | 형식 검사 | 비고 |
| --- | --- | --- | --- |
| `name` | 예 | 비어 있지 않은 문자열이 아니면 항목 제외(`tool_item_invalid`, 위치만 기록)하고 규격 위반(`tool_name_missing`)도 기록 | 규격은 1~128자, `A-Z a-z 0-9 _ - .`를 권장(SHOULD). 어긋나면 경고만 남긴다. 서버 안 유일성도 권장이며 중복해도 두 항목을 유지한다. |
| `title` | 아니오 | 문자열 | 표시 우선순위는 `title` → `annotations.title` → `name` (규격). 이 스캐너는 표시 이름을 정하지 않고 원본을 보존한다. |
| `description` | 아니오 | 문자열 | 비신뢰 데이터 |
| `icons[]` (`src`, `mimeType`, `sizes`, `theme`) | 아니오 | 배열, 각 항목에 문자열 `src` | URL은 가림 규칙 적용, 이미지를 내려받지 않는다. |
| `inputSchema` | 예 | 객체이고 루트 `type`이 `"object"`인지만 확인 (**제한된 구조 검사**) | 위반 시 항목은 보존하되 `definition_status: "failed_limited_checks"`와 `definition_issues`를 붙인다. 통과해도 `passed_limited_checks`일 뿐 전체 JSON Schema 검증 완료가 아니다. `$schema` 기본값은 2020-12(규격)이며 스키마 내부 유효성·`$ref` 해석·`x-mcp-header` 검사는 하지 않는다. |
| `outputSchema` | 아니오 | 객체 | 규격상 `type: "object"`가 필수는 아니다(배열 출력 예시가 있음). 루트 type은 검사하지 않는다. |
| `annotations` (`title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) | 아니오 | 객체, `title`은 문자열, 힌트는 불리언 | 규격: 모두 **힌트**이며 신뢰되지 않은 서버의 값으로 판단하지 않는다. 기본값(예: `destructiveHint` 기본 true)을 대신 채우지 않는다. |
| `_meta` | 아니오 | 객체 | |
| 그 밖의 키 | - | - | `other_definition_fields`에 이름만 적고 값은 `definition`에 그대로 둔다. |

`definition`에는 위 객체가 **받은 구조 그대로**(비밀값 가림만 적용) 들어간다. 응답에 없는 필드는 만들지 않는다. 프로젝트 확장 필드(`internal_ref`, `server_index`, `page_index`, `definition_status`, `definition_check_level`, `definition_issues`, `redactions`, `definition_altered`, `trust`)는 `definition` 밖에 둬 공식 필드와 섞이지 않게 한다.

**잘못된 정의의 보존:** 이 결과는 인벤토리 수집용이다. 형식이 틀린 Tool 정의도 `failed_limited_checks`와 오류 근거를 붙여 보존하며(식별할 `name`이 없는 항목만 예외), 어느 상태도 "정상 사용 가능한 Tool"이라는 뜻이 아니다. `passed_limited_checks`는 이 문서의 표에 적힌 제한된 구조 검사를 통과했다는 뜻일 뿐이다. 실제로 하는 검사와 하지 않는 검사는 결과 JSON의 `scope.definition_validation`에도 기록한다.

### 6-4. 서버 소속·출처 필드 (프로젝트 확장, 협의 전)

| 필드 | 의미 | 하지 않는 것 |
| --- | --- | --- |
| `server_index` | 입력 파일 안 서버 순서 | 공통 ID가 아니다. |
| `server_ref` (`server_ref_kind: capture_local_label`) | 입력 파일 안에서 서버를 구분하는 이름 | 팀 공통 `server_id`가 확정됐다고 표현하지 않는다. 가림 후 같은 문자열이 돼도 `server_index`로 구분한다. |
| `config_link.registration_key`, `registry_path` | 설정 수집 결과와 잇기 위한 입력상 참고값 | 설정 수집 결과와 대조하지 않는다(`verified_against_config_scan: false`). |
| `internal_ref` (`capture-server[i]/tools[n]`) | 이 결과 파일 안의 Tool 위치 | 공통 자산 ID가 아니며 안정성을 보장하지 않는다. |
| `source.source_kind`, `evidence_type`, `live_server_query: false` | 저장된 응답을 읽었다는 출처 표시 | 실제 서버 조회 성공으로 표현하지 않는다. |
| `source.capture_path` | `--capture`로 받은 로컬 경로(물리 경로) | ID 입력으로 쓰지 않는다. 물리·논리 경로 기준은 팀 합의 전이다(PR #11 "추가 합의 필요"). |
| `source.origin_declared_by_input` | 입력 파일이 스스로 밝힌 출처(예: `synthetic_test_data`) | 검증하지 않는다. |

### 6-5. 수집 상태 규칙

두 축을 분리한다. 현재 상태 필드(`complete`/`partial`/`failed`)는 **수집 완전성**만 표현하고, 규격 적합성은 이슈의 `category`와 `spec_conformance`로 표현한다. 상태 필드의 값은 늘리지 않았다.

- 서버 상태(수집 완전성): `complete`(모든 페이지를 읽었고 완료 여부도 확인됨, 빠진 항목 없음) / `partial`(일부 Tool을 읽었으나 `nextCursor`가 남았거나, 항목이 제외됐거나, 완료를 확인하지 못함) / `failed`(읽은 페이지 없음 → `tool_count: null`).
- `issues[].category`: `completeness`(`severity: "error"`만 상태를 `partial`/`failed`로 만든다) / `conformance`(규격 적합성. 상태를 바꾸지 않는다. `severity`는 `violation` = 필수·MUST 위반, `recommendation_not_met` = SHOULD 미충족).
- `spec_conformance.status`: `violations_found` / `no_violations_found` / `not_evaluated`(읽은 응답 없음). `checks: "limited"`는 이 모듈이 제한된 검사만 한다는 표시이며 `no_violations_found`는 전체 규격 적합성이 아니다. `collection.spec_conformance`가 서버별 결과를 집계한다.
- 사유 코드는 `field_path`·`page_index`·`tool_index`로 위치를 가리키며 원문 값은 넣지 않는다.
- 성공한 빈 목록(`empty_list`)만 "Tool 0개"다. 오류 응답·잘못된 구조·응답 없음·입력 파일 문제는 0개로 쓰지 않는다.
- 전체 `collection.tool_count`는 읽은 항목 수이며, `tool_count_complete: false`이면 서버의 전체 Tool 수가 아니다.

### 6-6. 이번 단계에서 하지 않은 것

MCP 서버 접속·실행, `tools/call`, 실제 서버가 지금 같은 목록을 반환하는지 확인, Agent 노출·호출 가능 판정, Resource·Prompt·capabilities 수집, `x-mcp-header`·`$ref` 검증, `nextCursor`를 이용한 후속 페이지 요청, 공통 `server_id`·`asset_id` 생성, 백엔드·대시보드 연동.

### 6-7. 가림·정규화 규칙 (V5 검토 반영)

서버가 제공한 모든 값(`definition`, `_meta`, 응답 `_meta`, 서버 이름, 오류 메시지)은 비신뢰 입력이며 결과에 쓰기 전에 아래 규칙을 적용한다. 기록(`tools[].redactions`)에는 위치(`field_path`)와 사유(`reason`)만 남기고 **원문 값과 원래 키 이름은 넣지 않는다.** 가림 위치 표기에서 키가 가려진 곳은 자리표시자(`<redacted-key-N>`)로 적는다.

| 대상 | 처리 | `reason` |
| --- | --- | --- |
| 알려진 토큰 모양, URL의 사용자정보·쿼리·fragment | 모든 문자열에 적용(구조 키 `$id`·`$ref`·`$schema`·`pattern` 아래 포함). 해당 부분만 `<redacted>` | `token_pattern:*`, `url_userinfo`, `url_query_values`, `url_fragment` |
| 토큰 모양·고립된 surrogate가 든 **객체 키·`properties` 이름** | 같은 객체 안의 일반 키와 겹치지 않는 `<redacted-key-N>`(번호는 객체 안 등장 순서, 원래 키·해시 미사용, 이미 있는 같은 이름은 건너뜀). `required`의 같은 이름도 같은 자리표시자로 맞춘다. | `key_looks_like_secret`, `lone_surrogate_in_key`, `reference_to_masked_key` |
| 인증 이름 필드의 문자열 값 | 이름을 단어로 나눠 `token`·`secret`·`password`·`passwd`·`pwd`·`apikey`·`authorization`·`credential(s)`·`cookie`·`bearer`, 또는 `api key`·`access key`·`private key`·`client secret`·`secret key`·`auth token`·`session token` 조합이 들어 있으면 값을 `<redacted>`. 객체·배열이면 하위 문자열 값을 모두 가린다. `author`·`token_budget`(숫자) 같은 일반 이름, 값 없이 이름만 참조하는 `${VAR}`는 보존. | `secret_named_field_value` |
| 비밀 이름 속성의 `default`·`const`·`examples`·`enum` | `properties.<이름>` 아래에서만 `<redacted>`(기존 규칙 유지). 같은 속성의 `type`·`description` 등은 보존 | `secret_named_property_value` |
| 구조 키(`$ref`·`$anchor`·`type`·`format`·`pattern` 등) 아래 문자열 | 토큰·URL 자격증명만 가리고, 긴 식별자처럼 보인다는 이유만으로는 지우지 않는다. | - |
| 고립된 surrogate(값) | 문제 글자만 U+FFFD로 대체, 나머지 문자열 보존 | `lone_surrogate_replaced` |
| 비유한 숫자 | 입력 파싱 시 `NaN`·`Infinity`·`-Infinity`와 float가 무한대가 되는 값(`1e400`)을 숫자가 아닌 표식으로 받는다. 정의 안에서는 `"<non-finite-number>"`로 대체. 캐시 힌트(`ttlMs`)는 정상 값으로 인정하지 않고 `cache_hint_invalid`로만 기록(`ttl_ms` 미기록). `ttlMs` 검사에서는 float로 표현할 수 없을 만큼 큰 정수(예: 400자리)도 유한한 숫자로 인정하지 않는다(정의 안의 큰 정수는 유효한 JSON이므로 그대로 보존). | `non_finite_number_replaced` |

- 가림·정규화가 적용된 Tool은 `definition_altered: true`이며 서버가 보낸 원본과 다를 수 있다. 키 이름이 바뀌면 이름을 가리키는 참조가 어긋날 수 있다(`required`만 맞춘다). 가린 정의를 실행 가능한 원본 스키마로 보증하지 않는다.
- `$ref`·`$id`는 문자열로만 저장한다. 해석·조회·접속하지 않는다(`scope.definition_validation.redaction_note`).
- 전체 문자열·전체 정의를 지워서 문제를 피하지 않는다. 한 값의 문제로 다른 Tool·서버를 버리지 않는다.
- 입력 파일은 읽기만 하며 바꾸지 않는다.

### 6-8. 중복 JSON 키와 수집 완전성 (V5 검토 반영)

JSON 파서는 같은 키가 두 번 나오면 마지막 값만 남긴다. 앞의 값이 서버·페이지·Tool 목록이었다면 누락된 것이므로, 수집 판단에 영향을 주는 객체의 중복을 모두 검사한다. 복원하지는 않고(마지막 값만 읽음) 누락 가능성을 `complete`로 덮지 않는다.

| 위치 | 기록 위치 | 상태에 미치는 영향 |
| --- | --- | --- |
| 입력 최상위 (`servers`, `origin` 등) | `collection.reasons[]`: `duplicate_key_in_capture`, `field_path: "(root)"`, `duplicate_keys` | 모두 `complete`였다면 파일 전체 `partial` / `duplicate_keys_in_capture`, `tool_count_complete: false` |
| 서버 항목 (`pages`, `server_ref`, `protocol_version` 등) | 그 서버의 `issues[]`: `duplicate_key`, `field_path: "servers[i]"`, `duplicate_keys` | 그 서버만 `partial` / `duplicate_keys`. `failed`면 유지. 다른 서버는 영향 없음 |
| 응답 외피 (`result`·`error`·`jsonrpc`·`id`) | `issues[]`: `duplicate_key`, `field_path: "pages[i]"`, `page_index` | 그 서버 `partial` |
| `result` 내부, Tool 내부 (기존) | `issues[]`: `duplicate_key`, `field_path: "pages[i].result…"` 또는 `…tools[n]` | 그 서버 `partial` |

- `duplicate_keys`에는 키 이름만 적으며 토큰 모양 이름은 `<redacted>`로 적는다.
- 서로 다른 서버의 동명 Tool은 중복 JSON 키가 아니다. 별도 항목으로 각각 보존하며 완전 수집 판단에 영향이 없다.

### 6-9. 결과 저장과 종료 코드

- 직렬화·UTF-8 인코딩을 파일을 열기 전에 끝내고(엄격한 JSON: `allow_nan=False`), 같은 폴더의 임시 파일에 쓴 뒤 `os.replace`로 교체한다(`asset_scanner/output.py`, 설정 수집 CLI와 공통). 실패해도 기존 결과는 유지되고 빈 파일·임시 파일이 남지 않는다.
- 저장 전에 값·키의 고립된 surrogate를 U+FFFD로 바꾸고 건수를 `collection.output_text_normalizations`에 남긴다(0이면 키 없음). 유효한 한글·이모지·유럽 문자는 원문 그대로 저장한다.
- 종료 코드: 입력 문제 3(결과 저장됨) / 수집 `partial` 1 / 저장 실패 4(메시지에 예외 종류만, 내용 없음) / 인자 오류 2 / 완전 0.


## 7. 실제 stdio 조회 (`live_tools`, 개발용 서버 1개) — 내부 개발용 초안

> 이 장은 **직접 만든 개발용 MCP 서버 하나**를 대상으로 한 실제 통신 기능의 근거와 규칙이다. 팀 테스트베드 서버를 조회한 것이 아니다. 팀 테스트베드 검증은 이 장의 어떤 항목에도 포함되지 않았다. 팀 공통 스키마와 공통 ID는 구현하지 않았다.

### 7-1. SDK 선택과 근거 (2026-10-07 확인)

| 항목 | 내용 |
| --- | --- |
| 사용 SDK | 공식 MCP Python SDK `mcp` — https://github.com/modelcontextprotocol/python-sdk (문서: https://py.sdk.modelcontextprotocol.io/) |
| 고정한 버전 | **`mcp==2.3.0`** (`requirements.txt`), 하위 의존성 포함 전체 버전은 `requirements-live-lock.txt` |
| 선택 이유 | 2026-07-28 규격을 지원하는 정식(비 프리릴리스) 2.x 중 현재 최신이다. 2.0.0 릴리스 노트가 "supports the 2026-07-28 revision"을 명시한다. 2.0.1~2.3.0은 같은 2.x 정식 릴리스이며 수정·동작 변경이 쌓였다(예: 2.3.0은 빈 `_meta`·`params`를 보내지 않도록 고침). 1.x는 2.0.0 릴리스 노트가 "유지보수 모드(보안 수정만)"라고 밝힌 라인이라 새 기능 대상으로 고르지 않았다. |
| 태그와 커밋 SHA | `v2.3.0` → `2118f14f8a19bc158d8a1cf90af58d85d187f849` (2026-10-02) / `v2.0.0` → `6f69a3758ebf2ee55ce050f58b470ce11af71133` (2026-07-28). GitHub `git/ref/tags` 조회 결과(둘 다 `commit` 객체) |
| PyPI 배포물 | `mcp-2.3.0-py3-none-any.whl` SHA-256 `dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377`, `mcp-2.0.0-py3-none-any.whl` SHA-256 `1cb4c75d2d2c7b8c1d756355e5d82a39f2822cc7f13e22a2051d7ca3592349d6` (PyPI 메타데이터와 직접 내려받은 휠이 일치) |
| 소스 확인 | 두 휠 모두 `mcp/client/caching.py`("SEP-2549, protocol revision 2026-07-28")와 `Client`의 2026-07-28 처리 코드를 포함 |
| Python 호환 | SDK `Requires-Python >=3.10`. 이 프로젝트 환경(Windows 10, **Python 3.14.4**)에서 설치(`pip install mcp==2.3.0`)와 `pip check`(깨진 의존성 없음), 통합 테스트가 통과했다. 하위 의존성(pydantic-core, cryptography, cffi, pywin32 등) 설치가 모두 성공했다. |
| 2.0.0 호환 확인 | **V8(`--max-tools` 누적 한도·시간 제한 검증 수정) 이후 재실행:** 별도 가상환경(`mcp==2.0.0`, `mcp-types==2.0.0`)에서 `test_live_tools.py`와 `test_v7_review_fixes.py` 67개가 통과했다(2.3.0 고정 확인 테스트 1개 제외). 이전(V7) 기록: 별도 가상환경(`mcp==2.0.0`, `mcp-types==2.0.0`, 나머지 하위 의존성은 같은 버전)에서 같은 통합 테스트 26개가 모두 통과했다(2.3.0 고정을 확인하는 테스트 1개는 의도적으로 제외). 스캐너는 `stdio_client(...)`를 Transport로 `Client`에 넘기므로 2.0.0에서도 동작한다. `Client(StdioServerParameters(...))` 직접 전달은 2.1.0부터라(릴리스 노트 #3321) 2.0.0에서는 쓸 수 없다. 2.0.0을 쓰려면 `requirements.txt`의 고정을 바꾸고 `requirements-live-lock.txt`와 고정 확인 테스트도 함께 갱신해야 한다. |

참고 릴리스 노트: https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0, `.../v2.3.0`.

### 7-2. 통신 흐름 — SDK의 흐름을 그대로 사용

- 스캐너는 버전별 초기 통신을 직접 구현하지 않고 모든 버전에 `initialize`를 강제하지도 않는다. `Client(stdio_client(...), mode="auto")`(SDK 기본)가 `server/discover`를 먼저 시도하고 구형 서버면 `initialize` 핸드셰이크로 되돌아간다.
- 실제로 개발용 서버의 요청 기록에서 확인한 순서: 2026-07-28로 협상되면 `server/discover` → `tools/list`(`initialize` 없음). 구형 흐름(`mode="legacy"`)은 `initialize` → `notifications/initialized`로 2025-11-25가 협상된다.
- 협상된 버전이 2026-07-28이 아니면 `tools/list`를 **요청하지 않고** `failed` / `protocol_version_unsupported`로 기록한다. 버전 이름이나 필수 필드를 바꿔 2026-07-28 파서에 맞추지 않는다.
- `tools/call`은 보내지 않는다. 서버 stderr는 버리며 내용·크기를 저장하지 않는다.

### 7-3. 원본 응답과 SDK 변환 결과의 구분

| 단계 | 누가 | 이 수집의 취급 |
| --- | --- | --- |
| JSON 파싱 | SDK | 전송 계층의 원문(중복 키, `NaN` 토큰)은 확인하지 못한다. SDK가 파싱한 값 중 비유한 float은 정적 카탈로그와 같은 표식으로 바꿔 `non_finite_number_replaced`로 처리 |
| 응답 검증 | SDK | `session.send_request`가 협상된 버전의 스키마로 검증한다. **거부되면 pydantic 예외** → `sdk_validation_rejected`(오류 종류·위치만 기록, 서버가 보낸 입력 값은 기록하지 않음). Tool 0개가 아니다 |
| 음수 `ttlMs` | SDK | 검증 전에 0으로 올린다(SDK 동작). 이 수집이 기록하는 `ttl_ms`는 올린 뒤 값일 수 있다 |
| Tool 모델 변환 | SDK `list_tools` | **거치지 않는다.** `send_request(..., TypeAdapter(dict))`로 검증을 통과한 result dict를 그대로 받으므로 SDK 모델의 기본값(`None` 등)이 서버가 선언한 값처럼 보이지 않는다 |
| x-mcp-header 필터 | SDK `list_tools` | 2026-07-28에서 잘못된 `x-mcp-header` Tool을 **조용히 제외**한다. 인벤토리는 제외하지 않고 보존하며, `tools[].sdk_list_tools_would_drop`(true/false/null)으로 SDK라면 제외했을 Tool을 표시한다 |
| 응답 캐시 | SDK `Client` | 끈다(`cache=None`). 매 페이지를 서버에 요청한다 |

`live.server_info_from_wire`·`live.capabilities_from_wire`는 SDK가 서버 응답에서 파싱한 값 중 **서버가 실제로 보낸 필드만**(`exclude_unset`) 가림 후 옮긴다. 서버가 보내지 않은 값은 만들지 않는다.

### 7-4. 제한과 실패 코드

제한: 전체 시간(`--timeout`, 기본 60초, 서버 실행부터 정리까지), 요청 하나(`--request-timeout`, 기본 15초), 최대 페이지(`--max-pages`, 기본 50), 최대 Tool 수(`--max-tools`, 기본 5000). 빈 문자열 커서는 다음 페이지가 있다는 뜻이며, 이미 사용한 커서가 다시 오면 반복으로 보고 멈춘다.

| 상황 | 서버 상태 / outcome | 보존 |
| --- | --- | --- |
| 성공한 빈 목록 | `complete` / `empty_list`, `tool_count: 0` | - |
| 서버가 JSON-RPC 오류로 응답 | 첫 페이지면 `failed` / `error_response`, 뒤 페이지면 `partial` | 앞 페이지 Tool |
| 요청 응답 대기 시간 초과 | `request_timeout` (첫 페이지면 `failed`) | 앞 페이지 Tool |
| 전체 시간 초과 | `total_timeout` | 앞 페이지 Tool |
| 서버가 먼저 종료 | `connection_closed` | 앞 페이지 Tool |
| 서버를 시작하지 못함 / 협상 중 종료·시간 초과 | `connect_failed` / `server_exited_before_ready` / `connect_timeout` (`failed`) | - |
| SDK 응답 검증 거부 | `sdk_validation_rejected` | 앞 페이지 Tool |
| 협상 버전이 2026-07-28이 아님 | `failed` / `protocol_version_unsupported` | - (응답을 읽지 않음) |
| 반복 커서 / 최대 페이지 | `cursor_repeated` / `max_pages_reached` → `partial` (`next_cursor_remaining` 동반) | 읽은 Tool |
| 최대 Tool 수(`--max-tools`) 초과: 받은 페이지가 남은 한도를 넘음 (최종 페이지 포함) | `partial` / `tool_limit_reached`(`excluded_tools`, `page_index`) | 남은 한도까지의 Tool. 초과분은 저장하지 않고 `live.limit_exclusions`에 건수만 기록 |
| 최대 Tool 수에 정확히 도달 + `nextCursor` 남음 | `partial` / `tool_limit_reached` + `next_cursor_remaining`, 다음 페이지 미요청 | 읽은 Tool 전부 |
| 최대 Tool 수와 정확히 같고 마지막 페이지 | `complete` 유지 | 전부 |

모든 경우 서버 프로세스와 연결은 정리하며(시간 초과·조기 종료 포함), 정리 중 오류는 `live.teardown_error_types`에만 남고 결과 상태를 바꾸지 않는다. 실패는 traceback 없이 상태와 종료 코드(0 완전, 1 부분, 3 실패, 4 저장 실패, 2 인자 오류)로 나타난다. 시간 초과 시 SDK가 서버에 표준 취소 알림(`notifications/cancelled`)을 보낸다.

### 7-5. 결과 필드

정적 카탈로그와 같은 형식(`agent-scope.scanner.mcp-tools-catalog`)을 재사용하며 아래만 다르다.

| 필드 | 값 |
| --- | --- |
| `source` | `source_kind: "live_stdio_query"`, `evidence_type: "live_protocol_response"`, `live_server_query: true`, `transport: "stdio"`, `target.kind: "dev_demo_server"`, `target.team_testbed: false`, `target.command_origin`(내장 서버이며 OpenClaw 설정에서 읽은 명령 아님) |
| `scope.not_verified` | `wire_level_raw_json`, `team_testbed`, `tools_call`, `resources_prompts`, `exposure`, `callability`, `authorization`, `common_server_id` |
| `servers[].live` | `transport`, `executed_process`, `demo_scenario`, `sdk`(`package`, `version`), `negotiation`(요청 모드, 협상 버전, 카탈로그 지원 여부), `server_info_from_wire`, `capabilities_from_wire`, `requests`(`tools_list_sent`, `tools_call_sent: 0`), `result_origin`, `sdk_processing`, `limits`, `elapsed_ms` |
| `servers[].server_ref_kind` | `live_session_label` — 이 조회 안에서만 쓰는 이름이며 공통 server_id가 아님 |
| `tools[].internal_ref` | `live-session[0]/tools[n]` — 이 결과 안의 위치이며 공통 자산 ID가 아님 |

조회 성공은 Agent 노출이나 호출 가능을 뜻하지 않는다. 가림·정규화·제한된 정의 검사·안전한 저장은 정적 카탈로그와 같은 코드를 쓰며(7-3의 SDK 단계 제외), 가림 전 응답은 메모리에서만 다룬다.

### 7-6. 개발용 서버와 정답 목록

- `asset_scanner/dev_mcp_server.py`: 공식 SDK 저수준 `Server`로 만든 stdio 서버. `tools/list`에 서로 다른 Tool 2개(`echo_text`, `add_numbers`)를 광고한다. `tools/call`은 처리하지 않고 오류를 돌려준다. 외부 계정·인증정보·네트워크가 필요 없다.
- `examples/dev-server-ground-truth.json`: 위 Tool 2개의 이름·설명·`inputSchema` 정답 목록. 서버 코드와 별개로 손으로 작성했고 스캐너 출력과 대조한다. **팀 테스트베드의 정답 목록이 아니다.**
- 서버 요청 기록(`DEV_MCP_SERVER_LOG`, 검증용): 시작(pid·시나리오), 요청 메서드 이름, `tools/list` 커서 상태(없음/빈 문자열/있음)만 기록한다. 응답 원문·커서 값·인증정보는 기록하지 않는다.
- 시나리오(`--scenario`): `two-tools`(기본), `empty`, `error`, `paginated`, `empty-cursor`, `big-first-page`, `uneven-pages`, `fail-second`, `slow`, `exit-early`, `cursor-loop`, `endless`, `secrets`, `unicode`, `sparse`, `bad-header`, `invalid-schema`. 스캐너의 경계·실패 처리를 실제 통신으로 검증하기 위한 동작이며 정상 서버의 기능이 아니다.

### 7-7. 검증 범위의 구분

| 구분 | 내용 | 수행 |
| --- | --- | --- |
| 가상 응답 단위 테스트 | 저장된 `tools/list` 응답 JSON을 읽는 테스트(`test_tools_catalog.py`, `test_v5_review_fixes.py` 등). 서버 통신 없음 | 수행 |
| 실제 stdio 통합 테스트 (**개발용 서버**) | 별도 프로세스로 실행한 개발용 서버와 SDK 클라이언트의 실제 stdio 통신(`test_live_tools.py`) | 수행 |
| 팀 테스트베드 검증 | 팀 테스트베드의 실제 등록 서버·정답 목록과의 대조 | **미수행** (자료 대기) |

### 7-8. 한계

- 실행 대상은 내장 개발용 서버 하나뿐이다. OpenClaw 설정에 적힌 서버 명령의 자동 실행, 원격(HTTP) 서버, 인증이 필요한 서버는 다음 단계다.
- JSON 파싱을 SDK가 하므로 전송 계층의 중복 키·`NaN` 토큰은 검출하지 못한다. SDK 응답 검증이 거부하는 응답은 Tool 정의를 보존하지 못하고 실패로만 기록한다(정적 응답 읽기처럼 필드 누락을 위반으로 기록하며 읽는 경로는 없음).
- 2026-07-28로 협상된 연결만 읽는다. 다른 버전 지원은 별도 구현이 필요하다.
- SDK 서버 미들웨어(`Server.middleware`)는 SDK가 "provisional"로 표시한 API이며 개발용 서버의 요청 기록에만 쓴다.
- 서버 시작 시간(약 3~5초, 환경에 따라 다름)이 첫 요청 시간 제한에 포함될 수 있어 기본 요청 제한을 15초로 두었다.

### 7-9. 제한값 처리 방침 (V7 검토 반영)

**Tool 수 한도(`--max-tools`)**
- 한도는 서버 하나에서 **보존하는 Tool 수**이며 최종 페이지를 포함한 전체 페이지 누적에 적용한다. 보존한 Tool은 응답 순서의 앞에서부터이며 `page_index`·`index_in_page`·`internal_ref`(`live-session[0]/tools[n]`)·가림 기록(`redactions`)·소속 서버(`server_index`·`server_ref`)가 그대로다.
- 받은 페이지가 남은 한도보다 크면 초과분을 **결과에 저장하지 않는다**(정의도 가림 전 원문도 기록하지 않음). 제외 사실은 `servers[].live.limit_exclusions[]`(`page_index`, `tools_in_response`, `tools_kept`, `tools_excluded`), 해당 페이지 기록의 `tools_in_response`, 서버 이슈 `tool_limit_reached`(`excluded_tools`)로 남는다. 서버 상태는 `partial`, `collection.tool_count_complete`는 `false`다.
- 한도에 도달했지만 `nextCursor`가 남았으면 다음 페이지를 요청하지 않고 `partial`(`tool_limit_reached` + `next_cursor_remaining`)이다. 한도와 정확히 같은 수를 모았고 마지막 페이지(`nextCursor` 없음)면 `complete`를 유지한다.
- **정적 카탈로그의 고정 한도와의 관계:** 정적 카탈로그(`tools_catalog`)는 서버당 5000개(`MAX_TOOLS_PER_SERVER`) 고정 한도를 갖는다. 실제 조회의 사용자 한도는 1~5000으로 제한해 이 고정 한도를 넘을 수 없다(넘는 값은 인자 오류). 따라서 실제 조회의 유효 한도는 항상 사용자 한도이고, 정적 카탈로그 CLI의 동작과 한도는 바뀌지 않았다.
- **이 한도가 제한하지 않는 것:** 응답 페이지 자체는 서버가 이미 보냈고 SDK가 파싱했다. 수신 바이트와 SDK 파싱 메모리는 이 한도로 제한되지 않는다. 한도는 결과에 보존하는 Tool 수와 다음 요청 여부만 정한다.

**시간·페이지 제한값 검증**
- 전체 시간(`--timeout`)과 요청 시간(`--request-timeout`)은 **유한한 수이며 0 초과 86400초(24시간) 이하**여야 한다. `nan`·`inf`·`-inf`·0·음수·86400 초과·불리언·숫자가 아닌 값은 거부한다. 상한은 이벤트 루프의 대기 시간 변환 오류(`timeout too big`)를 막기 위한 것이다. `--max-pages`는 1 이상 정수, `--max-tools`는 1~5000 정수다.
- **검증은 서버를 실행하기 전에 한다.** CLI의 잘못된 값은 argparse 인자 오류(종료 코드 2)이며 서버 프로세스·결과 파일·요청 로그·임시 파일이 생기지 않고 기존 결과 파일(내용·수정 시각)은 그대로다. 이전에는 `inf`·`nan` 제한이 결과 JSON의 `live.limits`로 들어가 저장 단계에서 거부돼 입력 오류가 저장 실패(종료 코드 4)로 잘못 분류됐고, Windows에서 `--timeout=nan`은 이벤트 루프의 `ValueError`로 traceback과 종료 코드 1이 났다.
- **공개 함수 `collect_live_demo`도 같은 검사(`validate_limits`)를 실행 전에 한다.** 잘못된 `LiveLimits`는 `ValueError`(필드 이름 포함)로 거부하며 서버를 실행하지 않는다. CLI와 함수가 같은 검사를 쓰므로 숨은 동작 차이가 없다. 이는 이전 동작(검증 없이 실행)에서 의도적으로 바꾼 것이며, 이유는 잘못된 시간 값이 결과 JSON을 깨뜨리거나 이벤트 루프 오류로 이어지는 것을 서버 실행 전에 막기 위해서다.
