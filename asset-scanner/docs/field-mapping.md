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
| OpenClaw **2026.9.6** npm 패키지의 `docs/gateway/config-extensions.md` ("MCP, skills, and plugins") 와 같은 패키지의 번들 코드(설정 스키마·필터 매칭 함수) | `sslVerify`·`toolFilter`의 의미와 자료형 (아래 2-1장) | 2026-10-06에 받아 둔 `output/openclaw-9.6/openclaw-2026.9.6.tgz`의 문서와 번들 JS 텍스트를 **정적으로 읽음**(2026-11-11). 설치·실행·접속 없음. 공개 문서·테스트베드는 이번에 확인하지 않음 |
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
| `declared.sslVerify` | `sslVerify` (boolean) | 설정에 **명시된** `true`/`false`만 기록 (2-1장) | 필드 생략. `true`/`false`를 채우지 않음 |
| `declared.toolFilter` | `toolFilter` (object) | `include`·`exclude` 문자열 배열을 원형 그대로(순서·중복·`*` 패턴 유지, 가림 규칙만 적용) 기록. 선언된 목록만 포함 (2-1장) | 필드 생략 |
| `declared_keys` | 항목의 모든 키 | 선언된 키 이름 목록(값 없음) | — |
| `credentials.env` / `credentials.headers` | `env`, `headers` | 이름 목록과 값의 **종류**(`literal`/`env_ref`/`literal_with_env_ref`/`secret_ref`/`invalid_secret_ref`/`non_string`)만. 값은 저장하지 않음 | 필드 생략 |
| `credentials.auth` / `oauth` / `clientCert` / `clientKey` | 같은 이름 | 존재 여부(`present`), 하위 키 이름, SecretRef이면 `value_kind`만 | 필드 생략 |
| `other_declared_keys` | 위 목록에 없는 키 | 이름만 기록(예: `requestTimeoutMs`, `connectionTimeoutMs`, `codex`). 값은 이번 단계에서 해석하지 않음. `sslVerify`·`toolFilter`는 `declared`로 수집하므로 더 이상 여기에 나오지 않음(선언 사실은 `declared_keys`에 있음) | `[]` |
| `unresolved[]` | 항목 하위 | 해석하지 않은 `$include`·`${VAR}`·SecretRef. 이름·위치만 | `[]` |
| `redactions[]` | 가림 처리 | 가린 `field_path`와 `reason` | `[]` |
| `issues[]` | 검증 | 서버별 문제 (아래 표) | `[]` |
| `collection_status` | 계산 | `complete` / `partial`(미해석 참조·타입 오류·잘못된 SecretRef) / `invalid`(항목이 객체가 아니거나 내부 오류) | — |

서버별 문제 코드 (`issues[].code`). 파일 전체 실패와 달리 다른 서버의 수집을 멈추지 않습니다.

| code | 의미 | 항목 상태 |
|---|---|---|
| `entry_not_object` | 등록 항목이 객체가 아님 | `invalid` |
| `field_type_invalid` | `enabled`·`command`·`args`·`env`·`sslVerify`·`toolFilter`(및 `toolFilter.include`/`exclude`) 등의 자료형이 틀림. 값은 저장하지 않고 기대·실제 자료형만 기록. 배열 안에 다른 자료형이 섞이면 `element_types`(자료형 이름만) 추가 | `partial` |
| `field_key_unexpected` | `toolFilter` 안에 `include`/`exclude` 외의 키가 있음. 키 이름(토큰 모양이면 자리표시자)만 기록하고 값은 읽지 않음 | 영향 없음(읽은 값이 손실되지 않음) |
| `duplicate_key` | 항목 안에서, 또는 `env`·`headers`·`auth` 등 항목의 모든 하위 객체 안에서 같은 키가 반복됨 (마지막 값만 읽음). `field_path`는 중복된 키의 위치이며 토큰 모양 키는 자리표시자로 적음. 플러그인 manifest의 `mcpServers`도 같은 경로로 처리 | 그 서버 `partial` → 전체 `partial` (`server_entries_incomplete`). 정상 서버·같은 서버의 나머지 필드는 보존 |
| `invalid_secret_ref` | 인증정보 위치(`env`·`headers` 값, `auth`·`oauth`·`clientCert`·`clientKey`)에 SecretRef 모양 객체가 있으나 형식이 틀림. `problems`에 필드·문제 종류·자료형만 기록 (원래 값 없음) | `partial` |
| `no_connection_target_declared` | `command`와 `url`이 모두 없음 (선언 사실에 대한 경고) | 영향 없음 |
| `collector_internal_error` | 이 항목 처리 중 스캐너 내부 오류. 예외 종류만 기록하고 항목은 버리지 않음 | `invalid` |

SecretRef 판정: 키가 `source`·`provider`·`id`로만 이루어지고 `source`가 있는 객체만 SecretRef 후보로 봅니다. `source`가 문자열(env/file/exec/store)이고 `provider`·`id`가 문자열이면 유효한 참조입니다. `{"source": "git", "url": ...}`처럼 다른 키가 섞인 일반 설정 객체는 참조로 보지 않고, 인증정보 위치가 아닌 곳(`codex` 등)의 잘못된 모양 객체도 문제로 보고하지 않습니다.

`declared`는 OpenClaw 원천 키 이름을 바꾸지 않고 보존합니다. 공통 형식의 `endpoint`는 `declared.url`에서 변환하는 것을 전제로 합니다.

## 버전 표기 정리 (테스트베드 OpenClaw)

| 구분 | 내용 | 확인 수준 |
|---|---|---|
| 팀 자료 기록 | `develop` 브랜치 `testbed/docs/testbed-spec-20260929.md`(2026.9.6 고정, 기준 문서 태그 `v2026.9.6`), `testbed/docs/build-log-snap0-snap1.md`(`openclaw --version` 출력 `OpenClaw 2026.9.6 (eb377ac)` 기록) | 팀 문서를 읽음. 실제 VM은 확인하지 않음 |
| 스캐너 근거 | 2026.9.6 npm 패키지(`output/openclaw-9.6/`)와 태그 `v2026.9.6` = 커밋 `eb377ac59e6c9fd6c7705028034812becf00271b`(8장) | 패키지 문서·코드를 정적으로 읽음 |
| 정정한 표기 | 이전 판 이 문서·README의 "테스트베드 2026.9.5" | 팀 자료에 없는 표기. 팀 스키마 검토 문서(`develop:docs/schema-design-draft.md`)도 불일치로 기록. 9.5가 실제 버전이라는 근거는 없음 |
| 대기 중 | 테스트베드 사양 정정본(담당자 수정본) | 미수령. 버전 값 포함 내용을 모름. 수령 전까지 테스트베드 대조·수집률은 보류 |

이 저장소는 테스트베드 VM에 접속하거나 OpenClaw를 설치·실행하지 않았습니다. 위 "팀 자료 기록"을 실제 환경에서 확인한 값으로 쓰지 않습니다.

## 2-1. `sslVerify`와 `toolFilter`

> 수집 범위: **설정에 적힌 값의 기록**. 정책 적용 여부·연결 안전성·Tool 노출 여부는 판단하지 않습니다. 보안 경고 판정과 정책 실행도 없습니다.

### 근거 (OpenClaw 2026.9.6 패키지)

| 항목 | 문서 (`config-extensions.md`) | 설정 스키마 (번들 코드) |
|---|---|---|
| `sslVerify` | "HTTP TLS controls for private endpoints and mutual TLS" — 원격(HTTP) 서버용 TLS 설정. 예제는 `sslVerify: true` | `boolean().optional()` |
| `toolFilter` | "optional per-server tool selection". `include`는 발견된 MCP Tool을 맞는 이름으로 제한하고, `exclude`는 맞는 이름을 숨김. 항목은 정확한 MCP Tool 이름 또는 단순 `*` glob. 리소스·프롬프트가 있는 서버의 유틸리티 Tool 이름(`resources_list`, `resources_read`, `prompts_list`, `prompts_get`)에도 같은 필터를 씀 | `strictObject({ include?: array(string.trim.min(1)).min(1), exclude?: (같음) })` — `include`/`exclude` 외 키는 스키마 위반 |

- `nodeHost.mcp.servers`의 문서 예제도 `toolFilter: { include: [...] }`를 씁니다(`docs/nodes/mcp-and-skills.md`). 플러그인 manifest의 `mcpServers`는 같은 수집 경로를 쓰지만 이 두 필드를 manifest가 허용하는지는 확인하지 않았습니다. 적힌 값만 기록합니다.
- 런타임 코드는 UI 상태 표시에서 `sslVerify === false`일 때만 "TLS 검증 끔"으로 취급하는 것으로 보입니다. 이것은 코드 구조에서 읽은 것이며 동작을 실행해 확인하지 않았습니다. 스캐너는 이 해석을 결과에 쓰지 않습니다.

### 수집 규칙

| 상황 | 결과 |
|---|---|
| `sslVerify`가 boolean | `declared.sslVerify`에 그대로 (`true`/`false`) |
| `sslVerify`가 없음 | 필드 생략. 문서에 기본값이 명시되어 있지 않으며 채우지 않음 |
| `sslVerify`가 boolean이 아님 (`"false"`, `0`, `null` 등) | 변환하지 않음. `field_type_invalid`(`expected: boolean`, 실제 자료형). 값은 없음. SecretRef 모양 객체이면 `unresolved[]`에 참조 이름만 기록 |
| `toolFilter`가 객체 | `declared.toolFilter`에 선언된 `include`·`exclude`만 담음. 없는 목록은 채우지 않음 (`{}`이면 `{}`) |
| `include`/`exclude`가 문자열 배열 | 순서·중복·빈 문자열·`*` 패턴·앞뒤 공백을 그대로 보존. 각 항목에 문자열 가림 규칙 적용 (`redactions[].field_path`는 `...toolFilter.include[1]`처럼 인덱스까지) |
| `include`/`exclude`가 문자열 배열이 아님 | 그 목록만 보류하고 `field_type_invalid`(`expected: array of string`). 배열에 문자열이 아닌 항목이 섞이면 목록 전체를 보류(일부만 남기지 않음). 다른 목록·다른 필드·다른 서버는 계속 수집 |
| `toolFilter`가 객체가 아님 | `field_type_invalid`(`expected: object`). `declared.toolFilter` 없음 |
| `toolFilter`에 `include`/`exclude` 외 키 | `field_key_unexpected`(키 이름만). 값은 읽지 않음 |
| 중복 키 | 기존 `duplicate_key` 규칙 그대로(마지막 값만 읽음, 해당 서버 `partial`). 예: `sslVerify` 중복, `toolFilter` 중복, `toolFilter.include` 중복 |
| 항목에 `${VAR}` | 기존 규칙대로 `unresolved[]`에 이름만 기록(해석 안 함), 해당 서버 `partial` |

### 한계

- **선언과 적용은 다릅니다.** 이 필드들은 설정 파일에 적힌 값입니다. 서버가 실제로 그 설정으로 연결·필터링되는지, 설정이 로드 시점에 거부되는지(예: 빈 배열은 스키마상 `min(1)` 위반일 수 있음. 스캐너는 `[]`를 그대로 기록하고 위반으로 판정하지 않음)는 확인하지 않았습니다.
- `sslVerify`: `true`/`false`가 실제 연결의 안전성을 확정하지 않습니다. 명시되지 않은 경우의 런타임 기본 동작도 확인하지 않았습니다(필드가 없다는 것은 "적혀 있지 않음"이라는 뜻).
- `toolFilter`: 패턴이 어떤 Tool 이름에 맞는지, 어떤 Tool이 실제로 노출되거나 호출 가능한지는 알 수 없습니다. 문서상 규칙(정확한 이름 또는 `*`)을 이 단계에서 구현·평가하지 않습니다. 런타임이 설정을 정규화하는 방식(예: 문자열이 아닌 항목 제외)에 따라 실제 적용 목록은 기록된 값과 다를 수 있습니다.
- `ssl_verify` 같은 snake_case 이름은 이 설정 스키마의 키로 확인하지 못했습니다. 해당 이름은 이전처럼 `other_declared_keys`에 이름만 남습니다.
- 가림은 이름·모양 기반입니다. 필터 항목이 일반 단어처럼 생긴 비밀값이면 가려지지 않으며, 긴 무작위 문자열 모양의 Tool 이름은 `<redacted>`로 가려질 수 있습니다(5장).
- 2026.9.6 이외 버전, 팀 테스트베드의 실제 설치 환경과의 일치는 확인하지 않았습니다(팀 문서 기록은 2026.9.6 (eb377ac), 아래 "버전 표기 정리").

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
- **미확인:** 위 규칙은 현행 공개 문서 기준입니다. 팀 테스트베드가 같은 규칙으로 동작하는지는 실제 환경에서 확인해야 합니다. (팀 문서는 테스트베드를 OpenClaw 2026.9.6 (eb377ac)로 기록합니다. 이 문서의 이전 판이 쓴 "2026.9.5"는 근거 없는 표기라 정정했습니다. 설치 버전을 스캐너가 확인한 것은 아닙니다. 아래 "버전 표기 정리" 참조)

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
- `other_declared_keys`의 값(`codex` 등)은 저장하지 않으므로 가림 대상이 아닙니다. `toolFilter` 항목은 `declared`에 저장되므로 위 문자열 규칙으로 가립니다.

## 6. Tool 카탈로그: 저장된 `tools/list` 응답 → 결과 필드

> 상태: 스캐너 내부 개발용 초안 `0.1.0-draft`. 구현은 `asset_scanner/tools_catalog.py`. 팀 공통 스키마와 공통 ID(Issue #10, PR #11 협의안)는 반영하지 않았다.

이 장의 필수 완료·캐시 필드 설명은 2026-07-28 기준이다. 2025-11-25 지원과 버전별 차이는 [8장](#8-독립적인-버전-호환성과-manifest-수집-보완)에 정리했다.

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

**주의:** 규격 사이트의 Schema Reference 페이지를 요약 도구로 읽은 결과는 `title`, `outputSchema`, `ttlMs`, `cacheScope`가 없다고 나와 위 Tools 페이지와 어긋났다. `schema.ts` 원본을 직접 읽어 확인한 결과 이 필드들이 모두 정의돼 있다. 요약 결과는 근거로 쓰지 않았고, 구현은 `schema.ts`와 Tools·Pagination 페이지 원문에 맞췄다. 다른 버전의 응답을 같은 구조로 가정하지 않는다. 2026-10-31 변경부터 입력이 선언한 `2025-11-25`·`2026-07-28` 각각의 규칙으로 읽고, 그 밖의 버전은 읽지 않는다.

### 6-2. 응답(`ListToolsResult`) 필드

| 규격 필드 | 필수 | 이 스캐너의 처리 | 결과 위치 |
| --- | --- | --- | --- |
| JSON-RPC `result` / `error` | 둘 중 하나 | `result`면 해석, `error`면 `error_response` 실패. 둘 다 있거나 둘 다 없으면 `invalid_response_structure`. `jsonrpc` 없이 `result` 객체만 있는 형태는 `bare_result`로 받는다. | `servers[].pages[].wrapper` |
| `resultType` | 예 (`complete` \| `input_required` \| 기타 문자열). 스키마 주석: 이 버전의 서버는 **MUST** 포함 | `complete`만 완료된 Tool 목록으로 읽는다. **없거나 문자열이 아니면** 규격 위반(`result_type_missing`/`result_type_invalid`)으로 기록하고 **완료를 추정하지 않는다**: Tool은 보존하되 서버는 `partial`/`completion_unverified`. `input_required`·알 수 없는 문자열은 구조를 추정하지 않고 읽지 않는다(`failed`). | `pages[].result_type`, `pages[].result_type_state`, `issues` |
| `tools` | 예 | 배열이 아니거나 없으면 실패. 빈 배열은 성공한 빈 목록. | `servers[].tools` |
| `nextCursor` | 아니오 | 문자열이면(빈 문자열 포함) 목록이 남은 것으로 본다. `null` 등 문자열 아닌 값은 `next_cursor_invalid`로 기록하고 마지막 페이지로 추정하지 않는다. 값은 저장하지 않고 존재 여부만 기록한다. | `pages[].has_next_cursor` |
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
| `config_link.registration_key`, `registry_path`, `config_scan_ref` | 설정 수집 결과와 잇기 위한 입력상 참조값. `config_scan_ref`는 연결 단계에서 `--config-scan 라벨=경로`로 붙인 라벨 중 어느 설정 수집 결과인지 가리킨다. 문자열이 아니면 값을 옮기지 않고 `config_scan_ref_invalid_type`(JSON 자료형 이름)만 남긴다. | 이 모듈은 설정 수집 결과와 대조하지 않는다(`verified_against_config_scan: false`). 대조·연결은 9장의 `linking` 모듈이 한다. |
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
| 비밀 이름 속성의 `default`·`const`·`examples`·`enum` | `properties.<이름>` 아래에서만 `<redacted>`. 값이 객체·배열이면 구조는 유지하고 중첩된 비어 있지 않은 문자열을 모두 가린다(`anyOf` 가지 안의 값 영역, 값 영역 안의 `properties` 키 포함). 숫자·불리언은 건드리지 않는다. 같은 속성의 `type`·`description` 등은 보존 | `secret_named_property_value` |
| 서버가 보낸 긴 문자열(오류 메시지, `resultType`, `protocol_version`, `origin`) | 전체 원문을 먼저 가린 뒤 200자로 제한한다(`_safe_short`). 자른 뒤 가리면 경계에 걸친 토큰(JWT 세 조각, URL 자격증명)이 패턴에서 벗어나 앞부분이 남기 때문이다 | 가림 사유별 |
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
- 협상된 버전이 2025-11-25·2026-07-28이면 해당 규격으로 `tools/list`를 읽는다. 그 밖의 버전은 요청하지 않고 `failed` / `protocol_version_unsupported`로 기록한다. 버전 이름이나 필수 필드를 바꿔 다른 버전 파서에 맞추지 않는다.
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
| 협상 버전이 2025-11-25·2026-07-28 어느 쪽도 아님 | `failed` / `protocol_version_unsupported` | - (응답을 읽지 않음) |
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
| 팀 테스트베드 검증 | 팀 테스트베드의 실제 등록 서버·정답 목록과의 대조 | **보류** (담당자 사양 수정본 대기). 기존 자료의 수집률·누락을 이번 검증 성과로 쓰지 않음 |

### 7-8. 한계

- 실행 대상은 내장 개발용 서버 하나뿐이다. OpenClaw 설정에 적힌 서버 명령의 자동 실행, 원격(HTTP) 서버, 인증이 필요한 서버는 다음 단계다.
- JSON 파싱을 SDK가 하므로 전송 계층의 중복 키·`NaN` 토큰은 검출하지 못한다. SDK 응답 검증이 거부하는 응답은 Tool 정의를 보존하지 못하고 실패로만 기록한다(정적 응답 읽기처럼 필드 누락을 위반으로 기록하며 읽는 경로는 없음).
- 2025-11-25·2026-07-28을 읽는다. 개발용 서버 외 환경의 실제 호환성은 별도 검증이 필요하다.
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

## 8. 독립적인 버전 호환성과 manifest 수집 보완

확인일: 2026-10-31. 팀 테스트베드의 사양 수정본과 무관하게 공식 문서·직접 작성한 설정·프로젝트 개발용 서버로 검증한다. 기존 테스트베드 자료의 결과 대조, 수집률, 누락 계산은 보류하며 이 변경의 성과로 사용하지 않는다.

### 8-1. 버전별 근거와 응답 처리

| 공식 원문 | 고정 커밋 | 확인한 내용 |
| --- | --- | --- |
| [MCP 2025-11-25 schema.ts](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/c4c367f9f58296a7053f5c78a52fd02bfbb56a49/schema/2025-11-25/schema.ts) | `c4c367f9f58296a7053f5c78a52fd02bfbb56a49`, blob `850a083fa228bf40af6feca42e23fd26342d3c59` | `ListToolsResult extends PaginatedResult`에 `tools: Tool[]`, `nextCursor?: Cursor`와 `Cursor = string`이 정의됨. `Result`에 필수 `resultType`·캐시 필드 없음. Tool의 `execution` 정의 확인 |
| [MCP 2025-11-25 Tools 문서](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/c4c367f9f58296a7053f5c78a52fd02bfbb56a49/docs/specification/2025-11-25/server/tools.mdx) | 위와 동일 | 이름의 1~128자·문자 범위·서버 안 유일성은 권장 사항임을 확인 |
| [MCP 2026-07-28 schema.ts](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/271ecc9accafdd9b83a3c869fa67c22953b2af80/schema/2026-07-28/schema.ts) | `271ecc9accafdd9b83a3c869fa67c22953b2af80` | 6장의 기존 완료·캐시 필드 처리 유지. 이 버전도 `nextCursor?: Cursor`이므로 명시된 `null`은 문자열 커서가 아님 |

| 처리 | 2025-11-25 | 2026-07-28 |
| --- | --- | --- |
| 필수 `tools` 배열 | 검사 | 검사 |
| `resultType`·`ttlMs`·`cacheScope` | 필수로 요구하지 않음. 같은 이름의 확장 필드는 이름만 기타 필드로 기록하며 최신 규격 의미를 적용하지 않음 | 기존 규칙 유지. 완료 미확인과 캐시 위반 구분 |
| `nextCursor` | 없으면 끝, 문자열이면 다음 페이지 존재. 빈 문자열도 유효 | 동일 |
| `nextCursor: null` 등 비문자열 | `partial` / `next_cursor_invalid`. 읽은 Tool은 보존 | 동일 |
| Tool `execution` | 정의 안에 보존, 공식 필드로 인식. 내부 자료형·실행 의미는 검사하지 않음 | 기존 기타 필드 취급 유지 |

저장 응답은 입력의 `protocol_version`, stdio 조회는 SDK가 실제 협상한 버전으로 분기한다. 응답 모양으로 버전을 추측하거나 빠진 필수 필드를 만들어 넣지 않는다. 미지원 버전은 계속 실패다. `protocol.supported_versions` 배열을 추가하며, 기존 `protocol.supported_version` 단일 값은 이전 소비자 호환을 위해 `2026-07-28`로 유지한다.

개발용 서버를 `collect_live_demo(..., client_mode="legacy")`로 실행한 테스트는 SDK의 `initialize` 흐름에서 협상된 2025-11-25로 `tools/list`를 실제 요청한다. 강제로 버전 문자열을 바꿔 파싱한 것이 아니다. `live.negotiation.requested_mode`에는 호출자가 선택한 모드를 기록한다. 2026 전용 `x-mcp-header` 제외 여부는 2025 응답에 적용하지 않는다.

### 8-2. 플러그인 manifest의 서버 선언

근거는 [OpenClaw 2026.9.6 공식 문서의 MCP server reference](https://github.com/openclaw/openclaw/blob/eb377ac59e6c9fd6c7705028034812becf00271b/docs/plugins/manifest/surfaces.md#mcp-server-reference)이다. 태그 `v2026.9.6`의 커밋은 `eb377ac59e6c9fd6c7705028034812becf00271b`, 문서 blob은 `17bf429b7d2ff418018830cf3a6fa8fc19a5f202`으로 확인했다. 같은 버전 `src/plugins/manifest-types.ts`에 `mcpServers?: Record<string, PluginManifestMcpServer>`가 있고 `src/plugins/manifest.ts`가 해당 필드를 정규화해 읽는 것도 확인했다.

| 원천·출력 | 의미 |
| --- | --- |
| `--plugin-manifest <파일>` | 지정한 파일의 `mcpServers`만 정적으로 수집. 설정 모드와 상호 배타적 |
| `source.source_kind` / `evidence_type` | `openclaw_plugin_manifest` / `manifest` |
| `source.registry_path` | `mcpServers` |
| 서버별 선언 위치 | `mcpServers.<등록키>`, JSON Pointer `/mcpServers/<등록키>` |
| `command`·`args`·`cwd` 등 상대 경로 | 원문을 보존. 플러그인 루트 기준 해석이나 실행은 하지 않음 |
| 가림·중복·참조·오류 격리 | 기존 설정 수집 공통 경로로 처리 |

공식 문서는 플러그인이 활성화돼야 해당 서버가 포함되며 사용자 `mcp.servers` 설정이 기본 선언을 대체하거나 비활성화할 수 있다고 설명한다. 이 단계에서는 manifest에 적힌 사실만 기록한다. 활성화 상태, 사용자 설정과의 병합, 실제 등록·실행 성공을 확정하지 않는다. manifest 전체의 OpenClaw 유효성 검사, Plugin 자산 자체 수집, 공통 ID 생성도 범위 밖이다.

### 8-3. 재현과 검증 범위

- `examples/plugin-servers.json5`, `examples/tools-list-2025.json`: 직접 작성한 예제. 실제 팀 환경의 사본이 아니다.
- `tests/test_plugin_manifest.py`: 출처·상대 경로 보존, 키 충돌과 인증값 가림, 영역 없음/빈 영역/잘못된 구조, 서버별 오류 격리, 원본 덮어쓰기 방지와 CLI 종료 코드.
- `tests/test_protocol_2025.py`: 버전별 필수 필드 차이, 빈 목록·페이지·뒤 페이지 오류, 미지원 버전, 가림, 명시적 비문자열 커서.
- `tests/test_live_tools.py`: 개발용 서버의 2025-11-25 협상과 `tools/list`, 페이지·오류·한도·가림을 실제 stdio로 확인. `tools/call` 없음과 프로세스 종료를 함께 확인.
- 테스트베드 결과·수집률·누락은 제시하지 않는다. 실제 VM, 원격 HTTP, 인증 서버, Resource·Prompt 수집은 별도 단계다.

## 9. 서버 선언과 Tool 수집 결과의 연결 (`linking`) — 내부 개발용 초안

저장된 설정 수집 결과(`agent-scope.scanner.openclaw-mcp-config`)와 저장된 Tool 카탈로그 결과(`agent-scope.scanner.mcp-tools-catalog`)만 읽는다. 서버 접속·명령 실행·`tools/list`·`tools/call`을 하지 않는다. 형식은 `agent-scope.scanner.server-tool-links` `0.1.0-draft`이며 팀 공통 스키마가 아니다. 공통 자산 ID·해시 규칙(PR #11 협의안, Issue #10)과 공통 스키마(Issue #15)는 확정되지 않았고 이 모듈도 만들지 않는다. `declaration_ref`·`internal_ref`·라벨은 결과 파일 안에서만 쓰는 이름이다.

### 9-1. 연결 근거

연결(`linked`)은 카탈로그 서버의 `config_link` 세 값이 **모두** 맞을 때만 한다.

| 입력 | 역할 |
| --- | --- |
| `config_scan_ref` | 실행 때 `--config-scan 라벨=경로`로 붙인 라벨. 어느 설정 수집 결과인지 지정 |
| `registry_path` | 그 수집 결과의 `source.registry_path`와 같아야 함 |
| `registration_key` | 그 수집 결과 안의 같은 영역에서 정확히 하나의 선언과 같아야 함 |

- 등록키와 등록 영역이 같다는 사실만으로는 연결하지 않는다. 참조가 없거나 잘못된 경우 같은 등록키·영역의 선언을 `key_region_matches`에 후보로만 보여 준다.
- 물리 파일 경로(`source_path`)는 연결 근거도 자산 식별값도 아니다. `physical_source_path` 속성으로만 남기며 `trace.physical_path_is_identity`는 항상 `false`다. 경로 문자열을 `config_scan_ref`로 써도 라벨이 아니므로 연결되지 않는다.
- 가림 처리된 등록키(`<redacted…>`)는 파일마다 번호가 달라 같은 서버라는 근거가 되지 못하므로 연결하지 않는다. 라벨 형식은 `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`이며 대소문자를 구분한다. 형식을 통과해도 토큰 패턴·URL 자격증명·고엔트로피 문자열처럼 비밀값으로 보이는 라벨은 `label_status: invalid`로 거부한다. 거부한 라벨(설정 수집·카탈로그·`--subject` 모두)은 결과에 `label: null`로만 나가고 원문을 출력하지 않으며, 어떤 연결에도 쓰지 않는다(가려진 이름끼리 충돌해 잘못 연결되는 일이 없다). 내부 매칭용 값(`match_label`)과 출력용 값(`label`)은 분리돼 있고 매칭용 값은 결과에 나가지 않는다.

### 9-2. 상태와 사유 (`links[].link_status`, `reason`)

| 상태 | 사유 | 의미 |
| --- | --- | --- |
| `linked` | `config_scan_ref_registration_key_and_registry_path_match` | 입력 자료 사이의 연결. `declaration_ref`, `trace`, `basis`가 채워짐 |
| `unlinked` | `no_link_basis` | `config_link`가 없거나 등록키가 없음 (`server_ref`만으로는 잇지 않음) |
| `unlinked` | `registration_key_redacted` | 등록키가 가림 처리됨 |
| `unlinked` | `registry_path_missing` | 등록 영역을 입력이 밝히지 않음 |
| `unlinked` | `config_scan_ref_missing` | 참조 없음. 우연한 일치만으로 잇지 않음 |
| `unlinked` | `config_scan_ref_invalid` | 참조가 문자열이 아니거나 비어 있음 |
| `unlinked` | `config_scan_ref_unknown` | 그 라벨의 설정 수집 결과가 없음(라벨 미부여·형식 오류 포함) |
| `unlinked` | `registry_path_mismatch_with_referenced_scan` | 참조한 수집 결과의 등록 영역이 다름 |
| `unlinked` | `no_matching_declaration` | 참조한 수집 결과에 그 등록키 선언이 없음. 그 수집 결과가 불완전하면 `referenced_scan_status`로 알림. 선언이 없다는 확정이 아님 |
| `ambiguous` | `config_scan_ref_duplicate` | 같은 라벨이 둘 이상의 수집 결과에 붙음 |
| `ambiguous` | `multiple_matching_declarations` | 후보 선언이 둘 이상 |
| `ambiguous` | `declaration_key_duplicated_in_source` | 설정에서 등록키가 중복 선언돼 마지막만 남음. 입력이 가리킨 선언인지 알 수 없음 |
| `ambiguous` | `declaration_claimed_by_multiple_catalog_servers` | 같은 카탈로그 입력 안에서 둘 이상의 서버가 같은 선언을 가리킴 |

`ambiguous`는 후보를 `candidates`로 남기고 하나를 고르지 않는다. `linked`는 **입력 자료 사이의 연결**이다. 서버가 실제로 기동했다는 것, 런타임에 등록됐다는 것, Agent에 노출된다는 것, 호출할 수 있다는 것을 뜻하지 않는다. 전체 `collection.status`는 모든 카탈로그 서버가 모호함 없이 연결되고 입력이 모두 완전할 때만 `complete`다.

### 9-3. 선언 주체 (`declaring_subject`)

| 필드 | 값 |
| --- | --- |
| `kind` | `gateway`, `node`, `plugin` 또는 `null` |
| `kind_origin` | `user_provided`(`--subject`로 입력) / `inferred_unverified`(등록 영역·원천 종류에서 추정) / `unknown` |
| `inferred_kind_from_source` | 입력과 별개로 추정한 값. 입력과 다르면 `kind_conflicts_with_inference: true`와 `subject_kind_conflict` 사유를 남기되 어느 쪽도 확정하지 않음 |
| `id` / `id_origin` | 사용자가 입력한 식별값과 `user_provided`. 입력이 없으면 `null` / `not_collected` |
| `verified_by_scanner` | 항상 `false`. 스캐너가 직접 확인한 주체 정보는 없다 |

- 식별값(예: Gateway·Node `deviceId`)은 설정 파일에서 읽지 않는다. 입력이 없으면 만들거나 추정하지 않는다. 길이 1~200자의 비어 있지 않은 문자열이면 정규화·해시 없이 그대로 두되, 알려진 토큰 패턴과 URL 자격증명은 가린다(긴 hex 값은 엔트로피 기준으로 가리지 않음).
- 같은 라벨에 `--subject`가 둘 이상이면 어느 쪽도 쓰지 않는다. 존재하지 않거나 중복된 라벨, 잘못된 종류·식별값도 적용하지 않고 `inputs.subject_inputs[].problems`와 `subject_input_ignored` 사유로 남긴다.
- 주체 입력은 라벨이 붙은 설정 수집 결과 하나에만 적용되며 같은 서버 이름의 다른 설정 수집 결과로 번지지 않는다.

### 9-4. 같은 선언의 여러 관측과 서로 다른 자산

- `--catalog`를 여러 번 지정하면 각각이 별개의 관측이다. 서로 다른 카탈로그 입력이 같은 선언을 가리키면 모두 `linked`로 두고 `declarations[].linked_observations`에 나열한다. Tool 목록을 합치거나 덮어쓰지 않는다.
- 한 카탈로그 입력 안에서 둘 이상의 서버가 같은 선언을 가리키는 경우는 같은 서버의 중복인지 다른 서버인지 입력만으로 알 수 없어 모두 `ambiguous`로 보류한다.
- 같은 이름의 서버·Tool은 합치지 않는다. 서버는 `declaration_ref`, Tool은 카탈로그 입력 안의 `internal_ref`로 구분한다. 같은 서버 안의 중복 Tool 이름은 `name_repeated_in_server`, 다른 서버의 같은 이름은 `same_name_in_other_catalog_servers`(같은 카탈로그 입력 안에서만)로 표시만 한다.
- Tool의 `original_name`은 서버가 보고한 `name`이다. 가림 처리된 이름은 `original_name: null`, `withheld_by_redaction`으로 남기고 다른 Tool과 같은 이름으로 비교하지 않는다. Gateway·Node의 투영 이름(`<server>__<tool>`, `<server>_<tool>`)은 분해하지 않는다.
- 선언 쪽에 Tool 근거가 없으면 `tool_evidence: not_supplied`다. Tool 0개라는 뜻이 아니다.

### 9-5. 하지 않는 것

설정 대조, 수집률·누락 계산, 테스트베드 결과와의 비교, 서버·명령 실행과 접속, 공통 ID·해시 생성, 공통 스키마 변환. 입력 자료는 가상 예제와 직접 만든 자료뿐이며 테스트베드 자료로 검증하지 않았다. 사양 정정 여부가 확인되지 않은 테스트베드 자료는 입력으로 쓰지 않았다.

### 9-6. 종료 코드와 검증

종료 코드: 0 모든 카탈로그 서버가 모호함 없이 연결, 1 부분(미연결·모호·입력 불완전·라벨·주체 입력 문제), 2 인자 오류(`--subject` 형식 포함), 3 입력 실패(없는 파일·형식 불일치), 4 저장 실패. 테스트는 `tests/test_linking.py`다.

## 10. Resource·ResourceTemplate·Prompt 목록 수집 (`resources_prompts`) — 내부 개발용 초안

> 상태: 스캐너 내부 개발용 초안 `0.1.0-draft`. 구현은 `asset_scanner/resources_prompts.py`. 팀 공통 스키마와 공통 ID(Issue #10, PR #11 협의안)는 반영하지 않았다. 입력은 **저장된 응답 파일뿐**이며 서버를 실행하거나 접속하지 않고 `resources/read`·`prompts/get`·`tools/call`도 하지 않는다. 테스트베드 자료와는 대조하지 않았다.

### 10-1. 규격 근거와 고정 버전

확인일 2026-11-12. 아래 커밋 시점의 원본 파일을 내려받아(`raw.githubusercontent.com`, 저장소 `modelcontextprotocol/modelcontextprotocol`) 직접 읽었다. 요약 도구의 결과는 근거로 쓰지 않았다(6장 주의 참조). 내려받은 `schema.ts`의 해시가 기존 문서(6장·8장)에 기록한 값과 일치함을 확인했다.

| 버전 | 커밋 | 파일 | 해시 |
|---|---|---|---|
| 2025-11-25 | `c4c367f9f58296a7053f5c78a52fd02bfbb56a49` | `schema/2025-11-25/schema.ts` | git blob `850a083fa228bf40af6feca42e23fd26342d3c59` |
| 2025-11-25 | 같은 커밋 | `docs/specification/2025-11-25/server/resources.mdx` / `prompts.mdx` | git blob `8f8341c1b974de227a6380cdbaef2c79b1033912` / `354c6213b285f07824e990097ac6814d41f56b23` |
| 2026-07-28 | `271ecc9accafdd9b83a3c869fa67c22953b2af80` | `schema/2026-07-28/schema.ts` | SHA-256 `742750af0bb8c716e7030c4977c992b55d1adc4407e9e66997db5846baedc2cd` |
| 2026-07-28 | 같은 커밋 | `docs/specification/2026-07-28/server/resources.mdx` / `prompts.mdx` | git blob `f49dd8e6be3fd8f13911788ae5f5d4c87d2c53cd` / `5a6574be3c16715aaafb1c7973025c1bc3669474` |

결과 JSON의 `protocol.spec_basis`에도 같은 값을 기록한다(코드의 `SPEC_BASIS`와 같다). 문서 `.mdx`의 blob 해시는 내려받은 파일을 `git hash-object`로 계산한 값이다.

### 10-2. 목록마다 다른 규칙 (Tool 규칙을 복사하지 않고 각각 확인한 결과)

| 항목 | Tool (`tools/list`, 6장) | `resources/list` | `resources/templates/list` | `prompts/list` |
|---|---|---|---|---|
| 결과 배열 이름 | `tools` | `resources` | `resourceTemplates` | `prompts` |
| 항목 타입 | `Tool` | `Resource` | `ResourceTemplate` | `Prompt` |
| 필수 필드 | `name`, `inputSchema` | `uri`, `name` | `uriTemplate`, `name` | `name` |
| 선택 필드 (두 버전 동일) | `title`, `description`, `icons`, `outputSchema`, `annotations`(힌트), `_meta`, (2025만) `execution` | `title`, `description`, `mimeType`, `size`, `annotations`(`audience`·`priority` 0~1·`lastModified`), `icons`, `_meta` | `title`, `description`, `mimeType`, `annotations`, `icons`, `_meta` (`size` 없음) | `title`, `description`, `arguments`, `icons`, `_meta` (`annotations` 없음) |
| 하위 정의 | — | — | — | `arguments[]`: `name`(필수), `title`, `description`, `required`(불리언) |
| 능력 선언 | `tools` | `resources` | **`resources`** (목록 요청은 따로 있으나 능력은 하나) | `prompts` |
| 2025-11-25 응답 | `PaginatedResult` | 같음 | 같음 | 같음 |
| 2026-07-28 응답 | `PaginatedResult` + `CacheableResult` | 같음 | 같음 | 같음 |

- 두 버전에서 `Resource`·`ResourceTemplate`·`Prompt`·`PromptArgument`의 필드 정의는 같다. `Result`가 다르다: 2026-07-28은 `resultType`이 필수이고 목록 결과는 `ttlMs`·`cacheScope`를 더한다(세 목록의 `ListXResult`가 모두 `CacheableResult`를 상속하는 것을 `schema.ts`에서 확인). 2025-11-25의 `Result`에는 이 필드가 없으므로 요구하지도 만들어 넣지도 않는다(같은 이름의 필드가 2025 응답에 와도 2026의 의미를 적용하지 않고 `other_result_fields`에 이름만 남긴다).
- Tool에만 있는 규칙은 적용하지 않는다: `inputSchema`·`outputSchema` 검사, 이름 권장 형식, `x-mcp-header`. 대신 목록마다 위 필수 필드와 필드 자료형을 검사한다.
- `uri`는 `@format uri`, `uriTemplate`은 `@format uri-template`(RFC 6570)로 정의돼 있지만 이 모듈은 문법을 검증하지 않는다(문자열 여부만 확인).
- 규격은 `resources`·`prompts` 능력을 선언한 서버가 해당 목록 요청을 지원해야 한다고 쓴다(2026-07-28 문서는 `MUST respond`). "능력을 선언하지 않은 서버가 목록 요청을 받았을 때"의 응답은 규격에 정해져 있지 않다. 따라서 **미지원의 근거는 저장된 JSON-RPC `-32601`(Method not found) 응답뿐**이다(`METHOD_NOT_FOUND` 상수는 두 버전 `schema.ts`에 모두 정의돼 있다).
- 항목 식별값의 서버 안 유일성을 `MUST`로 정한 곳은 확인하지 못했다(`uri`·`name`은 "unique identifier"라고 서술). 중복은 합치지 않고 두 항목을 모두 유지하며 `duplicate_identifier_in_list` 경고(상태 불변)만 남긴다.

### 10-3. 입력: 목록 응답 묶음 (`mcp-lists-capture`)

```json
{ "format": "mcp-lists-capture", "origin": "synthetic_test_data",
  "servers": [ { "server_ref": "sample-docs", "protocol_version": "2026-07-28",
      "registration_key": "...", "registry_path": "mcp.servers", "config_scan_ref": "gw",
      "server_capabilities": { "resources": {}, "prompts": {} },
      "lists": { "resources": { "pages": [ <응답>, ... ] },
                 "resource_templates": { "pages": [ ... ] },
                 "prompts": { "pages": [ ... ] } } } ] }
```

- `server_ref`·`registration_key`·`registry_path`·`config_scan_ref`는 `tools-list-capture`와 같은 의미·같은 출력 형태(`config_link`)다. 이 모듈은 설정 수집 결과와 대조하지 않으며 `linking`도 이 결과를 읽지 않는다(기존 연결 기능과 출력은 바뀌지 않음).
- `protocol_version`은 서버마다 선언해야 한다(`2025-11-25`·`2026-07-28`). 없으면 응답 모양으로 추측하지 않고 `failed`로 기록한다.
- `lists`에 없는 목록은 응답이 없는 것이므로 `not_performed`다. `server_capabilities`는 저장된 능력 선언이며 `resources`·`prompts` 키의 존재만 옮긴다(`declared`/`not_declared`/`unknown`). 내용은 옮기지 않고 확인하지 않는다.
- 응답은 `{"jsonrpc","id","result"|"error"}` 형태이거나 `result` 객체만 있어도 된다.

### 10-4. 출력과 상태

`servers[].lists.<resources|resource_templates|prompts>`마다 따로 기록한다. 서버 항목은 `counts`(읽은 항목 수, 읽지 못했으면 `null`)와 서버 상태를 갖는다.

| 목록 `collection_status` | `outcome` | 의미 | `item_count` |
|---|---|---|---|
| `complete` | `items_listed` / `empty_list` | 끝까지 읽음 / 서버가 0개를 보고한 정상 빈 목록 | 개수 / `0` |
| `partial` | `incomplete_list` / `completion_unverified` | 일부만 읽음(남은 `nextCursor`, 한도 초과, 제외된 항목, 뒤 페이지 오류, 잘못된 커서·중복 키) / 2026-07-28 `resultType`을 해석하지 못해 완료를 확인하지 못함 | 읽은 수(전체 수 아님) |
| `failed` | `error_response`, `invalid_response_structure`, `no_response`, `input_required_result`, `unsupported_result_type` 등 | 읽지 못함. **0개가 아니다** | `null` |
| `unsupported` | `method_not_found` | 저장된 **첫** 응답이 JSON-RPC `-32601`. 서버가 메서드를 지원하지 않는다고 응답한 근거(`evidence`) | `null` |
| `not_performed` | `capability_not_declared` / `not_requested` | 입력에 이 목록의 응답이 없음. 능력 선언에 없음 / 능력 정보 없음·선언됨. **0개도 미지원도 아니다** | `null` |

- 서버 상태: 모든 목록이 `complete` 또는 `unsupported`이면 `complete`, 모두 `failed`/`not_performed`이면 `failed`(전부 미수행이면 `no_list_performed`), 그 밖에는 `partial`. `not_performed`가 하나라도 있으면 `partial`이다(수집하지 않은 목록을 완전 수집으로 보지 않음). 파일 전체는 서버 상태를 같은 방식으로 합치며 `item_counts`와 `item_counts_complete`를 둔다.
- 페이지 처리는 Tool 목록과 같은 규격(`PaginatedResult`)이다: `nextCursor`가 문자열이면 다음 페이지가 있다는 뜻이고 빈 문자열도 유효한 커서다. 커서 값은 저장하지 않는다. 마지막 페이지에 커서가 남았거나 마지막 페이지 뒤에 응답이 더 있거나 커서가 문자열이 아니면 `partial`이다. 개수 한도는 목록당 5000개(`MAX_ITEMS_PER_LIST`)이며 넘으면 `partial`이다.
- 규격 적합성(`spec_conformance`)은 수집 완전성과 별개다. `resultType`·캐시 필드 누락, 필수 필드 누락, 필드 자료형 위반은 위반으로 기록하지만 읽은 항목은 보존하고 상태를 바꾸지 않는다(단 `resultType`을 해석할 수 없으면 완료를 추정하지 않아 `completion_unverified`). 식별 필드(`uri`·`uriTemplate`·`name`)가 없는 항목은 식별할 수 없어 제외하고 목록을 `partial`로 둔다.

항목(`lists.*.items[]`) 필드:

| 필드 | 의미 |
|---|---|
| `kind` | `resource` / `resource_template` / `prompt` |
| `server_index`, `server_ref` | 소속 서버. 다른 서버의 같은 이름 항목과 합치지 않는다 |
| `internal_ref` | `capture-server[i]/<목록>[n]`. 이 파일 안에서만 쓰는 이름이며 공통 자산 ID가 아니다 |
| `identity.<uri, uriTemplate, name>` | `original_value`와 `status`(`as_reported`/`withheld_by_redaction`/`missing`/`invalid_type`) |
| `definition` | 서버가 제공한 정의를 가림 처리해 옮긴 것(`uri`·`name`·`description`·`mimeType`·`annotations`·`arguments`·`_meta` 등 **있는 것만**) |
| `definition_status`, `definition_issues` | 제한된 구조 검사 결과(`DEFINITION_VALIDATION`). 정상 사용 가능이라는 뜻이 아님 |
| `other_definition_fields` | 공식 필드 밖의 키 이름 (값은 `definition`에 가림 처리되어 있음) |
| `redactions`, `definition_altered` | 가림 위치·사유, 원본과 달라졌는지 |
| `trust` | `untrusted_server_provided` — 서버 제공 데이터이며 실행·접속하지 않는다 |

### 10-5. 가림과 식별값

- 정의는 Tool 정의와 같은 `_sanitize`로 가린다: URI의 사용자정보·쿼리 값·fragment·토큰 모양 경로 조각, 알려진 토큰 모양, 인증 이름 키(`token`·`password`·`authorization` 등) 아래 문자열 전체, 토큰 모양 객체 키(`<redacted-key-N>`), 고립된 surrogate, 비유한 숫자, `icons[].src`의 URL 자격증명, `arguments[]`의 설명·이름, 중첩 `_meta`. 서버 이름·오류 메시지도 기존 규칙(`_text`/`_safe_short`)을 따른다.
- `uriTemplate`은 RFC 6570 표현식(`{id}`, `{?fields}`, `{+path}`)이 URL 가림 규칙에 망가지지 않게 보호한 뒤 같은 규칙을 적용한다. 표현식 안의 변수 이름이 토큰처럼 보이면 `{<redacted>}`로 바꾼다. 템플릿을 확장하거나 해석하지 않는다. 템플릿의 쿼리 값 자리(`?k={v}`)는 URL 쿼리 값 규칙에 따라 가려져 표현식이 사라질 수 있다.
- **가려지거나 바뀐 식별값은 원본 식별값이 아니다.** `identity.*.original_value`를 비우고 `status: withheld_by_redaction`으로 표시한다. `definition`에 남는 가린 문자열(`<redacted>` 등)을 서버의 실제 `uri`·`name`으로 쓰면 안 되고, 다른 항목과 같은 값으로 비교하지도 않는다. 가려진 식별값은 서버 안 중복 판정에서도 제외한다. 서로 다른 원본이 같은 `<redacted>`로 보여도 합쳐지지 않는다(항목은 `internal_ref`로만 구분).
- 서버가 제공한 설명·인자·메타데이터는 콘솔에 출력하지 않는다.

### 10-6. 한계와 하지 않은 것

- 저장 시점의 응답이다. 지금 서버가 같은 목록을 반환하는지, 리소스를 읽을 수 있는지(`resources/read`), 프롬프트를 가져올 수 있는지(`prompts/get`), Agent에 노출되는지는 확인하지 않았다. 목록의 `uri`를 열거나 `uriTemplate`을 확장하지 않는다.
- 능력 선언은 입력에 저장된 값을 옮긴 것이며 서버와 협상한 결과를 확인한 것이 아니다.
- `unsupported`는 저장된 `-32601` 응답이 있을 때만 쓴다. 능력을 선언하지 않았다는 정보만으로 미지원으로 확정하지 않는다(`not_performed`).
- 검사는 제한된 구조 검사다(`DEFINITION_VALIDATION.not_checked` 참조). URI·템플릿 문법, `mimeType` 형식, 아이콘 접근성은 검사하지 않는다.
- 가림은 이름·모양 기반이다. 평범한 단어처럼 생긴 비밀값이 URI·설명에 있으면 가려지지 않으며, 32자 이상 무작위처럼 보이는 정상 `name`/`uri`는 가려질 수 있다.
- 서버 접속·실행, 실제 목록 조회(live), 공통 ID·공통 스키마, `linking`에 이 결과를 반영하는 것, 테스트베드 대조·수집률 계산은 이번 범위가 아니다.

### 10-7. 종료 코드와 검증

종료 코드는 다른 수집 CLI와 같다: 0 완전, 1 부분, 2 인자 오류, 3 실패(읽은 서버 없음), 4 저장 실패(입력과 같은 파일·저장 오류, 기존 결과 파일은 유지). 사용 예는 README의 "저장된 목록 응답에서 Resource·ResourceTemplate·Prompt 읽기" 참조. 테스트는 `tests/test_resources_prompts.py`(가상 응답만 사용)이며 `FAKE` 표식 값이 결과·표준출력·오류출력에 남지 않는 것, 상태 구분, 합치지 않음, 기존 Tool 카탈로그 출력 불변을 확인한다.

### 10-8. 검증 실행 기록 (2026-11-12)

이 기능과 문서를 반영한 뒤의 pytest 실행 결과다. 로그는 `asset-scanner/output/review-resources-prompts/`에 있다(`output/`은 `.gitignore` 대상이라 저장소에는 올라가지 않으므로 아래 표에 수치를 옮겨 적는다). 이 기록의 세 실행은 모두 같은 코드 상태에서 수행했다(영향 테스트 종료 후 소스·테스트·문서·예제 파일이 바뀌지 않았음을 수정 시각으로 확인).

수집된 테스트는 494개다(`collect.log`).

| 구분 | 범위 | 결과 | pytest 종료 코드 | 기록 |
|---|---|---|---|---|
| ① 영향 테스트 | 새 모듈·재사용한 `tools_catalog`·`linking`·가림·콘솔 인코딩·등록 영역·정책 필드 등 12개 파일 | 412 passed (311초) | **0** | `impact.log`, `impact.exit.txt` |
| ② 한 번의 전체 실행 | 494개 전체 | 458개 PASSED 기록 후 **중단** (92%). FAILED·ERROR 없음 | **기록 없음** (시스템 메모리 부족으로 Claude Code가 프로세스를 종료함) | `full.log` (`full.exit.txt` 없음) |
| ③ 분할 실행 | ②에서 끝내지 못한 36개 (모두 `tests/test_v7_review_fixes.py`)를 7개 묶음으로 실행 | 36 passed | 7개 모두 **0** | `split/b1`~`b7` `.log`·`.exit.txt` |

- **②는 통과로 보지 않는다.** 종료 코드가 없고 마지막 6개 테스트가 실행되지 않은 채 끝났다. 로그에 PASSED로 찍힌 458개 테스트 결과만 인정한다. 중단 당시 실행 중이던 테스트는 순서상 `test_r1_5_exactly_the_limit_with_a_cursor_left_is_partial_and_does_not_request_more`(개발용 MCP 서버를 별도 프로세스로 띄우는 stdio 테스트)이며, 로그에는 시작도 완료도 찍히지 않았다.
- **③은 ②의 이어 실행이다.** 같은 494개를 한 번에 통과시킨 결과가 아니다. 대조 결과: ②의 PASSED 458 + ③의 PASSED 36 = 494, 겹침 0, 누락 0, PASSED 외 상태 0. 따라서 "494개 전부가 각각 한 번 이상 통과했고, 실패한 것은 없다"까지가 확인된 사실이다. "한 번의 전체 실행이 종료 코드 0으로 끝났다"는 확인되지 않았다.
- ③의 묶음별 기록 (실행기는 시스템 여유 메모리 120MB 미만이면 해당 실행만 중단하도록 감시했으나 중단된 묶음은 없었다):

| 묶음 | 대상 | 결과 | 종료 코드 | 실행 중 python 최대 메모리 | 실행 중 시스템 최소 여유 메모리 |
|---|---|---|---|---|---|
| b1 | `test_r1_5_…` (중단 당시 실행 중이던 테스트) | 1 passed | 0 | 202 MB | 947 MB |
| b2 | `test_r1_6_…` | 1 passed | 0 | 207 MB | 890 MB |
| b3 | `test_r1_truncation…`·`default_limit…`·`user_limit…`·`static_catalog_cli…` | 4 passed | 0 | 207 MB | 139 MB |
| b4 | `test_r2_invalid_time_limits…` (매개변수 16개) | 16 passed | 0 | 128 MB | 269 MB |
| b5 | `test_r2_a_valid_positive_finite_value…` | 1 passed | 0 | 206 MB | 729 MB |
| b6 | `test_r2_the_public_function_validates_limits…` (매개변수 10개) | 10 passed | 0 | 89 MB | 746 MB |
| b7 | `test_r2_cli_and_function_share…`·`test_ground_truth…`·`test_r2_validate_limits_bounds…` | 3 passed | 0 | 241 MB | 605 MB |

- **중단 원인에 대한 판단 (추정)**: 중단 당시 테스트 자체의 결함이나 비정상적인 메모리 증가는 확인되지 않았다. 같은 테스트가 단독으로 통과했고 python 프로세스의 최대 메모리는 241MB 이하였다. 시스템 전체 메모리는 8GB 중 97%가 사용 중이었고 상위 사용 프로세스는 Claude Code·브라우저·메모 앱이었다. 묶음 3에서는 python이 207MB 이하인데도 시스템 여유가 139MB까지 내려갔다. 다만 당시 중단 시점의 메모리 사용 기록은 남아 있지 않아 원인을 확정하지는 못했다.
- 분할 실행기 첫 시도(b1)에서 종료 코드 칸이 비어 그 기록은 무효로 보고 실행기를 고쳐 다시 실행했다(Windows PowerShell 5.1의 `Start-Process` 종료 코드 문제). 위 표의 값은 고친 뒤의 기록이다.
- 서버를 띄우는 stdio 테스트(③의 b1·b2·b3·b5와 일부)는 프로젝트의 개발용 MCP 서버만 실행한다. 팀 테스트베드·외부 서버 접속은 없다.
