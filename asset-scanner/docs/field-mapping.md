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
| 공격 표면 정의 v2.0 §7.3, §12.1 | 비밀값 미수집, MCP Server 최소 필드(서버 이름·선언 위치·source path·command/args 또는 endpoint·transport) | `git show origin/docs/mcp-attack-surface-definition:docs/mcp-attack-surface.md` |

**미검증:** 위 필드는 공개 문서 기준입니다. 팀 테스트베드(OpenClaw 2026.9.5)의 실제 설정 원본과 `openclaw config schema` 출력으로는
아직 확인하지 않았습니다.

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

`collection.key_redactions`: 비밀값처럼 보여 자리표시자로 바꾼 객체 키의 위치 목록 (`registry_absent`·`failed`에서는 생략).

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
