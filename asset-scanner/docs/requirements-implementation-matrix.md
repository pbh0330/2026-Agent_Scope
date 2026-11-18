# 요구사항 ↔ 스캐너 구현 대응표 (2026-11-17)

> 스캐너 `feature/scanner-config` (HEAD `0b2ff6bb`, 이번 작업의 미커밋 수정 포함). 문서 내용을 **모두 확정 요구사항으로 취급하지 않았습니다.** 각 행에 성격(확정/협의안)을 따로 적었습니다.
> 공통 자산 ID·공통 스키마는 구현하지 않았습니다. 결과의 `internal_ref`·순번·라벨은 영속 ID가 아닙니다.
> 상태 표기: **구현** · **부분 지원** · **미지원** · **실환경 검증 대기**(코드·저장 자료·가상 테스트로만 확인, 실제 OpenClaw/VM 직접 검증 없음). 대부분의 구현 항목은 마지막 상태를 함께 가집니다.

## 0. 근거 문서와 고정 커밋

| 약칭 | 문서 | 고정 위치 (`git show`로 읽음) | 문서가 밝힌 성격 |
|---|---|---|---|
| **기획서** | `docs/project-plan-draft.md` v0.5 (blob `9c7f048f`) | `origin/docs/schema-issue-15-p0` = `f5958ec6f07b66b782030971671fb5cc286c8644` (`origin/develop` `314bd5c`과 동일 blob) | 팀 검토용 초안. **8종 자산 분류만 "확정 반영"**(2026-10-31). 상세 판정·ID·수집 원천은 별도 |
| **공격표면** | `docs/mcp-attack-surface.md` v2.0 (blob `d6b16fe2`) | 위와 같음 | 정의서. 9.0절 8종 확정. 11절 "현재 단계 정적 자산 **최소 수집 필드**". "ID 후보와 실제 수집 지원 여부는 별도 확인" |
| **스키마** | `docs/schema-design-draft.md` v0.7.7 (blob `4edbe777`, 데이터 계약 `0.7.0-draft`) | 위와 같음 (`develop`은 blob `b063cb7f`로 다름 → 최신인 이 브랜치 기준) | **협의안**. "8종 분류는 확정, 그 밖의 필드·필수 조건·관계 허용값은 구현 계약 초안" |
| **확인표** | `docs/asset-collection-checklist.md` (PR #11) | `refs/pull/11/head` = `7e436461bb72b9839bd1fe0fd6bcd5c0f7518c7b` | "스캐너 확인 대기 / 확정된 수집 명세 아님" |
| **ID 제안** | `docs/asset-id-rules-proposal.md` (PR #11) | 위와 같음 | **협의안** (Issue #10). 확정 아님 |
| (참고) 스캐너 근거 | OpenClaw `2026.9.6` npm 패키지 문서(정적 읽기) | `output/openclaw-9.6/openclaw-2026.9.6.tgz` (sha256 `1a7355691bc0e605…`) | 제품 문서. 구현·실행으로 확인한 것은 아님 |

사본은 `asset-scanner/output/requirements-20261117/src/`에 있습니다(Git 제외).

**스캐너 담당 범위**(기획서 6.1: "수집 범위, 안정 ID, 예제 출력, 수집 오류 처리"). 아래 "담당 범위" 열의 뜻: ● 스캐너 구현 대상 / ◐ 호출 측(어댑터·대시보드)과 나눔 / ○ 다른 담당(분석·QA·대시보드·사용량).

## 1. 자산 8종 (확정 분류)

근거: 기획서 2.2, 공격표면 9.0, 스키마 3절(8종만 확정). 식별 기준·필드는 협의안.

| # | 자산 | 담당 범위 | 구현 위치 · 출력 필드 | 상태 | 누락·필요 작업 |
|---|---|---|---|---|---|
| 1 | Gateway | ● | `node_gateway_identity.py`: `device_id`·`public_key`(`origin`, `observation`). 설정의 Gateway 정책은 `permission_auth.py` | 구현(저장 출력)·직접 조회 구현 · **실환경 검증 대기** | 환경·프로필 범위(사용자 입력만 `--subject`), "Gateway 자산" 자체의 설정 근거 연결. 초기화·복제 후 유지 미확인 |
| 2 | Node | ● | 같은 모듈 `kind: node`. 페어링 근거 `devices list`는 **읽지 않음** | 부분 지원 · 실환경 검증 대기 | `PAIRED_WITH` 근거(`devices list --json`)·`state/openclaw.sqlite` 설정 원천 미지원 → 합의 후 파서 추가 |
| 3 | MCP Server | ● | `collector.py`: `registration_key`·`declaration_path/pointer`·`declared`·`credentials`·`unresolved`, 신규 `declared_extra`·`include_origin`. Plugin 선언: `--plugin-manifest` | 구현 · 실환경 검증 대기 | 실행 위치 필드 없음(미지원, 아래 B-6). `mcp list`·`mcp probe` 대조 모듈 없음 |
| 4 | Tool | ● | `tools_catalog.py`(저장 응답), `live_discovery.py`(실제 목록 조회): `definition.name/title/description/inputSchema/outputSchema/annotations`, `alteration` | 구현 · 실환경 검증 대기 | Gateway·Node 투영 이름 ↔ 원래 name 연결 미지원 |
| 5 | Resource/Template/Prompt | ● | `resources_prompts.py`: `kind`(`resource`/`resource_template`/`prompt`), `identity`, `definition`, `alteration` | 구현 · 실환경 검증 대기 | — |
| 6 | Skill | ● | `plugin_skill_assets.py`: `identity`·`frontmatter`·`metadata_openclaw`·`config_key` | 부분 지원 · 실환경 검증 대기 | 설치 경로·출처(플러그인 인덱스), `skills list --json` 실제 출력 없음 |
| 7 | Plugin | ● | 같은 모듈: `identity`·`manifest`·`package`(신규 `entry_points`·`dependencies`)·`supply_source`·`mcp_servers`·`declared_activation` | 부분 지원 · 실환경 검증 대기 | 설치 기록·설치본 manifest(VM) 확인 못 함. 서명·무결성 **검증**은 미구현(선언만) |
| 8 | Permission/Auth | ◐ | `permission_auth.py`: 원천 항목별 `category`·`config_path`·`applies_to`·`credential`·`include_origin`. 신규 `update_policy` | 부분 지원 · 실환경 검증 대기 | 실효 권한 판정·집계 단위(팀 협의) 미구현 — 의도적 |

## 2. 공격표면 정의서 11절 최소 수집 필드 (정의서 기준, 구현 합의 여부는 문서에 명시 없음)

### 11.1 MCP 연결·서버

| # | 필드 | 담당 | 구현 · 출력 | 상태 | 누락·필요 작업 |
|---|---|---|---|---|---|
| B-1 | host_id, client_id | ○ | 없음. 스캐너가 알 수 없는 개념 | **미지원** | 정의 주체·입력 방식 합의 |
| B-2 | server_id | ◐ | `internal_ref`만. 공통 ID 없음 | **미지원**(의도적) | 공통 ID 규칙 합의 후 |
| B-3 | 서버 이름·선언 위치·source path | ● | `registration_key`, `declaration_path`, `declaration_pointer`, `source_path`(물리), 신규 `include_origin`(상대 경로) | 구현 · 실환경 검증 대기 | 물리 경로는 공유·ID 입력 부적합(속성만) |
| B-4 | command/args 또는 endpoint, transport | ● | `declared.command/url/transport`(비밀 가림), `credentials` | 구현 | — |
| B-5 | TLS 검증 여부 | ● | 선언 `declared.sslVerify`(적힌 값만), 실제 조회는 `description.tls`(항상 검증, 끌 수 없음) | 구현 | 생략된 `sslVerify`는 값을 만들지 않음(unknown 처리는 분석 몫) |
| B-6 | 선언 주체 vs 실행 위치 | ◐ | 선언 위치만. 실행 위치 필드 **없음** | **미지원** | "별도 증적이 있을 때 기록"(9.0) — 증적 종류 합의 필요 |
| B-7 | protocol_version | ● | 저장 응답 `declared_protocol_version`, 실제 조회 협상값 | 구현 · 실환경 검증 대기 | — |
| B-8 | server capabilities | ● | 실제 조회 `capabilities_from_wire`(서버가 보낸 필드만), 저장 목록은 `declared_capabilities`(resources·prompts 키 존재만) | 부분 지원 | 저장 목록 경로는 전체 보존 아님 |
| B-9 | client capabilities, extensions | ○ | 없음(SDK 기본값을 덧붙이지 않음) | **미지원** | 요구 범위 확인 |
| B-10 | declared / discovered | ● | 선언 존재, 목록 조회 결과(`collection_status`) | 구현 | — |
| B-11 | 정적 정책 판정 exposed·potentially_callable | ○ | 없음. `toolFilter` 값은 선언만 | **미지원**(의도적) | 판정 규칙은 분석 담당과 합의(스키마도 "필터 일치만으로 EXPOSED 금지") |
| B-12 | collected_at | ◐ | identity·plugin 모듈의 `collected_at`. 설정·카탈로그는 `generated_at`만 | 부분 지원 | 스키마 11절: 시작·종료 시각은 호출 측 래퍼가 제공 |
| B-13 | catalog hash, capability hash | ● | 없음 | **미지원** | 해시 대상·직렬화 합의(서버 제공 정의의 가림·정규화 후 값 기준 여부) |

### 11.2 Tool·Resource·Prompt

| # | 필드 | 담당 | 구현 · 출력 | 상태 | 누락·필요 작업 |
|---|---|---|---|---|---|
| T-1 | Tool: name, title, description, inputSchema, outputSchema, annotations | ● | `definition` 전체 + `alteration`(변경 여부·사유) | 구현 | 수정 완료: `$schema` 끝 `#` 보존 |
| T-2 | Resource: uri, name, description, mimeType, size | ● | `identity`·`definition` | 구현 | — |
| T-3 | Prompt: name, description, arguments | ● | 같음 | 구현 | — |
| T-4 | server_id(소속) | ◐ | `server_ref`+`config_link`(`linking`). 공통 server_id 없음 | 부분 지원 | 공통 ID |
| T-5 | exposure state | ○ | 없음 | **미지원**(의도적) | B-11과 같음 |

### 11.3 Skill·Plugin

| # | 필드 | 담당 | 구현 · 출력 | 상태 | 누락·필요 작업 |
|---|---|---|---|---|---|
| S-1 | package_id, name, version | ● | `package.name/version`, `identity` | 구현 | — |
| S-2 | provider | ● | `supply_source`(npmSpec/clawhubSpec/localPath 힌트). provider 필드 자체는 없음 | 부분 지원 | provider 정의 합의 |
| S-3 | source_type·source_uri·registry | ● | `install_hints`(문서화된 키만) | 부분 지원 | 설치 기록(플러그인 인덱스·SQLite) 미지원 |
| S-4 | hash/signature 존재 여부 | ● | `expected_integrity_declared`, 신규 `supply_source.integrity` | 구현(존재 여부만) | — |
| S-5 | 검증 결과·modified 상태 | ○ | `verification: not_performed` | **미지원**(의도적) | **허용 레지스트리·서명 키 등 신뢰 기준 합의 전에는 구현하지 않음** |
| S-6 | entry point, script/binary 유형 | ● | **신규** `package.entry_points`(`extensions`·`runtimeExtensions`·`setupEntry`·`runtimeSetupEntry`, 경계 이탈 표시, 실행·import 안 함) | 구현(경로 문자열) | script/binary 유형 판별·실행 위치는 미지원 |
| S-7 | 등록 Server·Tool·hook | ● | `mcp_servers.records`, **신규** manifest `contracts`·`activation_keys` | 부분 지원 | hook 목록은 저장된 `plugins list` 출력에만(실제 JSON 없음) |
| S-8 | dependency 목록 | ● | **신규** `package.dependencies`(이름·범위, URL 인증정보 가림), `required_platform_packages` | 구현(선언만) | 설치·해석 버전·취약점은 미확인 |
| S-9 | pinned, update channel, auto-update, last_updated | ● | npmSpec 안 정확 버전은 값 그대로. **신규** `permission_auth`의 `update_policy`(`update.channel`·`update.auto.enabled`·`update.checkOnStart`·`nodeHost.autoUpdate.enabled`) | 부분 지원 | "pinned" 판정 규칙·`last_updated`·환경변수(`OPENCLAW_NO_AUTO_UPDATE`) 미수집 |

### 11.4 권한·자격증명

| # | 필드 | 담당 | 구현 · 출력 | 상태 | 누락·필요 작업 |
|---|---|---|---|---|---|
| P-1 | credential reference ID·type·대상 | ● | `credential.kind`(`literal_withheld`/`secret_ref`/`env_ref`), `ref_names`, `applies_to` | 구현 | 같은 환경변수 이름만으로 공유 자격증명 단정하지 않음(스키마 5.1) |
| P-2 | OAuth: scope·identity·redirect | ● | `mcp_server_auth`: `auth`·`oauth.identity/scope/authProfileId/redirectUrl/clientMetadataUrl` | 구현(선언) | issuer·audience·만료·사용자별 분리 **판정**은 미지원 |
| P-3 | process identity, sandbox, command 권한 | ○ | `gateway.nodes.commands.*`·`security.installPolicy.exec.*`, **(11.4절 보완)** sandbox·`tools.exec.*`·호스트 승인 문서(`--exec-approvals-file`) | 구현 완료(선언) · 실환경 검증 대기 | 자세한 상태는 11.4절. 실효 권한 계산은 합의 대기 |
| P-4 | 파일 읽기·쓰기 범위 | ○ | 없음(서버 광고 정의의 경로는 서버가 제공한 값) | **미지원** | 원천 합의 |
| P-5 | 네트워크 허용 목적지 | ○ | 없음 | **미지원** | 원천 합의 |
| P-6 | Tool filter | ● | `declared.toolFilter` include/exclude 원형 | 구현 | 노출 결과 계산 안 함 |
| P-7 | approval mode | ● | **신규** `declared_extra.codex.defaultToolsApprovalMode`(Codex app-server 한정 선언) | 부분 지원 | 다른 런타임의 승인 원천 미확인 |
| P-8 | 적용 정책과 판정 결과 | ○ | 선언만. **판정 결과는 만들지 않음** | **미지원**(의도적) | 실효 권한 판정 규칙 합의 |

## 3. 스키마·PR #11 확인표 요구 (협의안)

| # | 요구 항목 | 근거 | 성격 | 담당 | 구현 · 출력 | 상태 | 누락·필요 작업 |
|---|---|---|---|---|---|---|---|
| C-1 | 수집 상태 구분: 정상 빈 결과 / 미지원 / 실패 / 부분 | 기획서 4.1·5.3, 스키마 11.2, 확인표 4절 | 기획서는 방향, 스키마는 협의안 | ● | `collection.status/outcome`, 목록별 `complete/partial/failed/unsupported/not_performed`, `registry_absent`≠`empty_registry` | 구현 | — |
| C-2 | 비밀값·해시 비저장 | 기획서 4.1, 확인표 4절 | 방향(원칙) | ● | `redaction.py`, `credential`, `values_withheld` | 구현 | 실제 환경 비밀값에 대한 검증 없음(자리표시자로만) |
| C-3 | 동명 Tool 구분(서버별) | 기획서 4.1, 스키마 3절 | 방향 | ● | 서버별 항목, 병합하지 않음, `duplicate_tool_name_in_server` | 구현 | 서버 ID는 공통 ID 합의 후 |
| C-4 | 설정 출처 복원(include·Plugin 등록) | 확인표 4절 "설정 출처" | 확인 요청(협의) | ● | 논리 경로 `declaration_path`. **신규** `$include` 해석 + `include_origin`(`--resolve-includes`) | 구현(옵션) · 실환경 검증 대기 | 공식 병합 규칙 구현(배열 연결·빈 배열 `{}`·형제 키). `OPENCLAW_INCLUDE_ROOTS`만 미지원(경계 밖은 오류로 기록) |
| C-5 | 반복 수집 시 동일 식별 | 확인표 4절, 기획서 5.3 | 확인 요청 | ● | 같은 입력 결정적 출력(저장 자료로 확인). 원천 값 유지는 P0~P2 3시점 동일 | 부분 지원 · 실환경 검증 대기 | 초기화·복제·재페어링 미확인 |
| C-6 | 환경·프로필·선언 주체 | 스키마 11절(호출 측 제공), 3절 `context.profile_id`, 확인표 | 협의안 | ◐ | 사용자 입력 `--subject`(`user_provided`)와 관측 `observed_identity`를 **별도 필드**로 보존, 충돌 시 `observed_identity_conflict`. 직접 조회 `scope`(프로필 이름·전달 환경변수 이름) | 부분 지원 | `environment_id`·`profile_id` 필드는 어댑터 입력으로 정의됨 — 스캐너 출력 필드는 합의 전 추가하지 않음 |
| C-7 | 필수 식별값 누락 시 "식별 미완료" | 확인표 4절, ID 제안 | 협의안 | ● | `missing`·`not_collected`·`withheld_by_redaction`. "식별 완료/미완료" 상태 자체는 **미정의** | 부분 지원 | 상태 정의 합의 |
| C-8 | 안정 ID(공통 ID) | 기획서 6.1(담당), 스키마 3절 | **협의 중** | ● | **구현하지 않음** | **미지원**(의도적) | Issue #10 합의 후 |
| C-9 | `PAIRED_WITH` 관계·근거 | 확인표 요약, 스키마 15절 | 협의안 | ● | 없음(`devices list` 파서 없음) | **미지원** | 파서 + 페어링 증적 형식 합의 |
| C-10 | 환경변수·SecretRef 해석 | — | — | — | 해석하지 않음(이름만) → partial | 의도적 | 해석 정책(누구의 환경인지) 합의 |
| C-11 | MCP 목록 조회의 인증 전달 | 확인표 목록 완전성·인증 맥락 | 확인 요청 | ● | **수정** `live_discovery`: 같은 헤더를 옵션으로 제공하면 선언 `${VAR}`를 대체(`declared_header_replacements`) | 구현 · 실환경 검증 대기 | OAuth·SSE 미지원(후속) |

## 4. 이번에 확인된 누락과 처리

| 우선순위 | 누락 | 처리 | 남은 일 |
|---|---|---|---|
| 1 | 인증 헤더 `${VAR}` 선언이 있으면 옵션 제공에도 조회 거부 | **수정·테스트(16개)** | OVA의 `inventory-remote`로 실환경 확인 |
| 2 | `$include` 미해석 → 정책·서버가 다른 파일에 있으면 수집 누락 | **구현(옵션)**: 문서화된 병합 규칙, 경계·깊이(10)·크기(2MB)·순환·개수(64) 제한, 원본 파일 상대 경로 기록. Collector·Permission/Auth 연동 | **구현됨(후속)**: 공식 구현(`eb377ac`)에 맞춘 병합, `live_discovery`·`plugin_skill_assets --config`도 연동. 남은 한계: `OPENCLAW_INCLUDE_ROOTS`(추가 경계) 미지원 |
| 3 | Plugin 진입점·의존성·호환 정보 | **구현** | 설치본·인덱스 미확인 |
| 4 | MCP 서버 승인 모드·타임아웃·병렬 힌트 | **구현**(`declared_extra`, 기존 계약 유지) | — |
| 5 | 업데이트 정책(채널·자동 업데이트) | **구현** | 환경변수 미수집 |
| 6 | 환경·프로필 구분 | 확인: 사용자 입력과 관측값 분리 보존됨 | 필드 합의 |

## 5. 합의 없이 구현하지 않은 것

| 항목 | 이유 | 필요한 합의 |
|---|---|---|
| 공통 자산 ID, `internal_ref`의 영속화 | Issue #10 협의 중 | 직렬화·해시·범위(환경·프로필·복제) |
| 서명·무결성 **검증** | 신뢰 기준(허용 레지스트리·공개키·검증 시점) 없음 | 신뢰 앵커 정의, 검증 실패의 의미 |
| 실효 권한 판정, exposed·potentially_callable | 우선순위·기본값 계산 규칙 없음, 스키마도 금지 | 판정 규칙·담당 |
| `host_id`·`client_id`·`environment_id`·`profile_id` 출력 | 스키마가 호출 측 제공으로 정의 | 어댑터와의 경계 |
| Permission/Auth 집계 단위 | 팀 협의 중 | 하위 유형·target_refs 규칙 |
| 실행 위치 기록 | 증적 종류 미정 | 증적 형식 |

## 6. 대시보드 어댑터 전달 확인 (읽기 전용, 다른 팀원 코드는 수정하지 않음)

대상: `origin/feature/dashboard` `8f56930af9f2b9b8491b0df6c26ba6c4a4dc8cc5`의 `dashboard/pipeline/agentscope_pipeline/adapter.py`(701줄, 사본 sha256 `d8971779e1f0…`). `git show`로 읽기만 했고 실행하지 않았습니다. 어댑터 입력은 모듈 설명(1~30행) 기준으로 **설정 수집 결과(`servers[]`)·테스트베드 raw·설정 사본**이며, `permission_auth`·`plugin_skill_assets`·`node_gateway_identity` 출력은 입력 목록에 없습니다(어댑터가 raw `*-identity.json`·`plugin-inspect.*.json`·설정 사본에서 직접 만듦).

| 스캐너 출력 | 어댑터 전달 여부 | 근거(어댑터 줄) | 필요한 매핑 제안 (합의 대기, 어댑터 수정은 해당 담당) |
|---|---|---|---|
| `servers[].declared` | **전달** → `product.config` | 352 | — |
| `servers[].declared_keys`·`other_declared_keys` | **이름만 전달** → `project.scanner_metadata` | 379~380 | — |
| **`servers[].declared_extra`**(`requestTimeoutMs`·`connectionTimeoutMs`·`supportsParallelToolCalls`·`codex.*`) | **전달되지 않음.** 어댑터가 값을 보강하는 키는 `sslVerify`·`toolFilter` 둘뿐(355행) | 355~358 | `product.config.<같은 이름>`에 복사(스키마 5절 "같은 이름·같은 중첩 경로"). `codex`는 `agents`·`defaultToolsApprovalMode`만 복사하고 스캐너의 주석 필드(`*_documented_value`·`scope_note`·`other_keys`)는 제외. `scanner_metadata`에 `declared_extra_keys` 추가 |
| `servers[].include_origin` | **전달되지 않음.** 증적 `source_ref`가 `<host>:~/.openclaw/openclaw.json`로 고정 | 349 | 증적 `field_path`/`note`에 원본 파일 상대 경로·include 사슬 기록. 논리 경로 `declaration_path`는 이미 전달됨 |
| `collection.includes`·`reasons[]` | **첫 사유 코드만 전달**(`c["reasons"][0]["code"]`), `includes` 상세는 미전달 | 329 | 수집 결과 `details`에 `includes.issues` 코드 목록 추가. `partial` 사유 `include_resolution_incomplete`를 보존(첫 항목이 아닐 수 있음) |
| Tool `definition` | **전달** → `mcp.definition`. 이번 수정으로 `$schema` 끝 `#`이 보존돼 원본과 같아짐 | 564, 595 | — |
| Tool·목록 `alteration`·`definition_altered`·`redactions` | **전달되지 않음** | (사용처 없음) | 스키마 11.3: 증적에 보존. 증적 `redaction_status`/`redacted_fields`(113~128행 형식)에 `alteration.reasons`·`difference_without_recorded_reason` 반영 |
| Plugin `package.entry_points`·`dependencies`·`supply_source.integrity` | **전달되지 않음**(어댑터는 raw `plugin-inspect`만 사용) | 10, 428 | 스키마 5.1 `supply_chain`: `package_id`←`package.name`, `version`, `source_uri`←`install_hints.npmSpec`, `integrity_status`←**`unknown`**(`verification: not_performed`이므로 `verified` 금지) |
| `permission_auth` 모듈의 `update_policy`·`include_origin` | **전달되지 않음**(어댑터가 정책 자산을 자체 생성) | 264~290 | 입력으로 쓸지·집계 단위는 팀 협의(Permission/Auth 집계 단위 미정) |
| `live_discovery`의 `declared_header_replacements` | 입력 아님(어댑터는 저장 광고 raw 사용) | — | 실제 조회 결과를 입력으로 받게 될 때 증적에 이름만 보존 |

결론: 이번에 추가한 스캐너 필드는 **기존 어댑터 경로로는 대시보드에 도달하지 않습니다.** 기존 필드(`declared`·`declared_keys`·`other_declared_keys`·`definition`)는 계약을 바꾸지 않았으므로 기존 전달에는 영향이 없다고 판단하지만, 어댑터를 실행해 확인한 것은 아닙니다(읽기 전용 코드 확인).

## 7. `$include` 실패와 실행 허용 (live_discovery)

수집 결과의 `partial`과 조회 실행 허용은 **별개**입니다.

| 상황 | 수집 결과(`collector`) | `live_discovery` 실행·접속 |
|---|---|---|
| include 문제가 선택한 서버 선언의 위치와 같거나 상위·하위(등록 영역·최상위 포함) | `partial` + `include_resolution_incomplete` | **거부** `include_unresolved`(사유 코드 목록만 알림) |
| 비밀처럼 보이는 키가 서로 다른 파일에서 같은 자리표시자로 가려져 합쳐졌을 수 있음(`masked_key_collision`) | `partial` | **거부** |
| 같은 위치 배열(공식: 연결)·빈 `$include: []`(공식: `{}`) | `complete`(정상 병합) | **허용** — 이전의 "배열 병합 미확정" 판정은 폐기 |
| 다른 서버의 include 문제 | `partial` | **허용**(사유는 `declaration.include_origin.issues`에 기록) |
| `--resolve-includes` 없음 | include를 읽지 않음, `unresolved` | 서버 선언 안의 `$include`는 `unresolved_reference`로 거부(기존 동작) |

판정 코드: `live_discovery._include_issue_affects`. 위치를 알 수 없는 문제는 안전하게 "영향 있음"으로 봅니다. 회귀 테스트: `tests/test_live_include_refusal.py`(수정 전 10개 실패 → 수정 후 14개 통과).

## 9. `$include` 배열 병합·Plugin/Skill 연동 갱신 (2026-11-17, 공식 구현 근거)

근거: openclaw/openclaw 고정 커밋 `eb377ac59e6c9fd6c7705028034812becf00271b`의 `src/config/includes.ts`·`src/infra/deep-merge.ts`·`src/config/includes.test.ts`(사본 `output/openclaw-includes-src/`). 공식 `deepMerge`는 `arrays: "concat"`이다.

| 항목 | 이전 | 현재 | 상태 |
|---|---|---|---|
| 같은 위치 배열 | 뒤 값으로 대체 + `array_merge_unverified`로 partial·조회 거부 | **연결**(순서·중복 보존). 이슈·partial·거부 없음 | 구현 |
| 형제 키 | 형제가 덮어씀 | 포함 내용과 같은 병합(형제 배열은 **뒤에 연결**), 포함 내용이 객체가 아니면 오류 | 구현 |
| 자료형 충돌·null | — | 뒤의 값이 대체(참고 기록 `type_conflict_later_value_wins`, 이슈 아님) | 구현 |
| 금지 키(`__proto__`·`prototype`·`constructor`) | — | 병합 시 제거(참고 기록) | 구현 |
| 하드링크·2MB·경로·순환·깊이 10 | 일부 | 공식과 동일하게 거부(하드링크 포함) | 구현 |
| 원소별 출처 | 객체 키 단위 | 배열 원소·중첩 값까지 출처(파일·include 사슬) | 구현 |
| `plugin_skill_assets --config` | 미연동 | `--resolve-includes` 연동: 활성화·허용·차단 선언에 `origin(s)`(원본 파일·논리 키 경로, 배열은 원소별) | 구현(옵션 생략 시 기존 동작) |
| 실제 실패(누락·구문·경로 이탈) | 거부 | 거부 유지 | 유지 |
| `OPENCLAW_INCLUDE_ROOTS` | 미지원 | 미지원(경계 밖은 오류) | 미지원 |

테스트: `test_config_includes_official.py`(공식 테스트 케이스·deep-merge 분기에서 정한 기대값), `test_plugin_skill_config_includes.py`, 갱신된 `test_config_includes.py`·`test_live_include_refusal.py`.

| 빈 `$include` 배열 | 오류(`include_type_invalid`)로 거부·partial | 공식대로 `{}`(형제 키는 보존). 중첩·배열 원소 위치 포함. 불필요한 partial·조회 거부 없음 | 구현 |

## 10. 전체 회귀 결과의 구분 (2026-11-17~18)

| 구분 | 내용 | 기록 |
|---|---|---|
| 전체 회귀(배열 병합·Plugin/Skill 연동 후) | 32개 파일 **모두 pytest 종료 코드 0**, **830 passed / 0 failed / 2 skipped** (파일별 실행의 합) | `output/arrays-20261117/per-file-exitcodes.txt` |
| skip 2건 | 심볼릭 링크 생성 권한 없음(`test_config_includes.py`), Windows 하드링크(`test_config_includes_official.py`, 공식 테스트도 win32 skip) → **경계 밖 심볼릭 링크·하드링크 거부는 이 PC에서 미확인** | 같은 파일 |
| 빈 include 배열 수정 후(영향 파일만) | 13개 파일 모두 종료 코드 0. 신규 `test_config_includes_empty_array.py` 11개(수정 전 9개 실패 재현 → 통과) | `output/empty-array-20261118/affected-exitcodes.txt` |

수정 후 전체 파일을 다시 돌리지는 않았습니다. 빈 배열 수정은 `config_includes.py`만 바꿨고 이를 쓰는 모듈의 테스트를 모두 다시 실행했습니다.

## 11. 기획서·공격표면 11절 재대조 (2026-11-18, 최신 로컬 구현 기준)

기준: `origin/develop` `314bd5c5400f76e2a95e80b19708002cf358f3d8`의 `docs/project-plan-draft.md`(blob `9c7f048f`, v0.5, 8종 분류만 "확정 반영")와 `docs/mcp-attack-surface.md`(blob `d6b16fe2`, v2.0) 11절 "최소 수집 필드". 두 문서 모두 `origin/docs/schema-issue-15-p0` `f5958ec`의 같은 blob과 동일. PR #11 확인표(`7e43646`)는 **원천값 확인 항목으로만** 참고했고, PR #18 스키마(v0.7.7)의 미확정 계약 필드·공통 ID 규칙은 확정 요구사항으로 구현하지 않았다.

**판정 원칙(정정)**: "특정 예제·문서에 값이 없었다"와 "지원되는 원천 자체가 없다"를 구분한다. 원천이 있는데 스캐너가 읽지 않으면 **실제 미구현**이며 원천 미제공이나 합의 대기로 돌려 적지 않는다. 정의만 정해지지 않은 항목은 "원천 있음 + 정의 합의 대기"로 적는다. 일부 행은 아래 12절에서 정정했다.

상태 구분: **구현 완료**(코드·가상 테스트 통과) · **실제 미구현**(원천·근거가 있으나 아직 구현하지 않음) · **원천 미제공**(OpenClaw 문서·출력에 그 값이 없음, 스캐너가 만들 수 없음) · **합의 대기**(규칙·신뢰 기준·소유 주체가 정해지지 않음) · **실환경 검증 대기**(실제 OpenClaw/VM으로 확인하지 못함). 구현 완료 항목은 모두 실환경 검증 대기를 함께 가진다. **미구현을 `unknown` 등으로 출력해 완료 처리하지 않았다**: 값을 모르면 필드를 만들지 않거나 상태(`not_collected`·`not_performed`·`invalid_type`)를 명시한다.

### 11.1 MCP 연결·서버

| 항목 | 상태 | 구현 위치·출력 | 비고 |
|---|---|---|---|
| host_id | **합의 대기**(정의) | 없음 | 후보 원천은 있음(Gateway `deviceId`, 호스트명 등)이나 무엇을 `host_id`로 볼지 정해지지 않음 |
| client_id | **실제 미구현**(원천 관측됨) | 없음 | 원천 경로: `devices list --json`의 `paired[].clientId`(함께 `clientMode`·`role`). 저장 실측(`origin/feature/testbed-threat-vm-capture` `444f558`의 `testbed/ground-truth/raw/P1·P2/tb-gw.devices-list.json`)에서 **관측값은 `"node-host"`**(`clientMode: "node"`). 이 값은 클라이언트 종류·역할을 나타내는 라벨로 보이며 **`deviceId`나 공통 자산 ID와 같지 않고 대체하지 않는다**(같은 종류의 클라이언트가 여러 개일 수 있음). 스캐너에 `devices list` 파서가 없어 원천값·경로를 아직 수집하지 않음 |
| server_id | **합의 대기** | `internal_ref`(영속 ID 아님) | 공통 ID 규칙(Issue #10) |
| 서버 이름·선언 위치·source path | 구현 완료 | `registration_key`, `declaration_path/pointer`, `source_path`(물리), `include_origin` | 물리 경로는 ID 입력 부적합 |
| command/args·endpoint·transport | 구현 완료 | `declared`, `credentials` | |
| TLS 검증 여부 | 구현 완료 | `declared.sslVerify`(선언), live `description.tls` | 생략 시 값을 만들지 않음 |
| protocol_version | 구현 완료 | 저장 캡처 `declared_protocol_version`, live 협상값, 신규 `requested_protocol_version_as_provided` | |
| server capabilities·extensions | 구현 완료 | live `capabilities_from_wire`(서버가 보낸 값), 저장 캡처 `tools_catalog`·`resources_prompts`의 `capabilities_as_provided`·`server_info_as_provided`(제공된 값, 가림 후, 검증 안 함). `resources_prompts`의 기존 `declared_capabilities` 요약은 유지 | `extensions`는 능력 객체 안의 값으로 보존(별도 필드 아님). 입력에 없으면 만들지 않음 |
| client capabilities | **구현 완료** | live `client_capabilities_sent`(스캐너의 SDK 클라이언트가 **실제로 보낸** initialize 또는 요청별 `_meta`를 관찰, `is_openclaw_client: false`), 저장 캡처 `client_capabilities_as_provided`(제공된 값·`client_sender` 출처만) | OpenClaw 클라이언트가 보낸 값은 아님. 캡처에 없으면 만들지 않음 |
| declared / discovered | 구현 완료 | 선언 존재, 목록 조회 결과 | |
| exposed·potentially_callable(정적 정책 판정) | **합의 대기** | 없음(`toolFilter` 값만 선언으로) | 판정 규칙 미정, 스키마도 "필터 일치만으로 EXPOSED 금지" |
| collected_at | **합의 대기** | identity·plugin 모듈 `collected_at`, 나머지 `generated_at` | 스키마 11: 시작·종료 시각은 호출 측 래퍼가 제공 |
| catalog hash·capability hash | **합의 대기** | 없음 | 해시 대상·직렬화·정규화(가림 후 값 기준 여부) 미정 |

### 11.2 Tool·Resource·Prompt

| 항목 | 상태 | 비고 |
|---|---|---|
| Tool name·title·description·inputSchema·outputSchema·annotations, Resource uri·name·description·mimeType·size, Prompt name·description·arguments | 구현 완료 | 정의 원문 보존(`$schema` `#` 수정, `alteration` 기록) |
| 소속 server_id | **합의 대기** | `server_ref`·`config_link`(`linking`)로 연결, 공통 ID 아님 |
| exposure state | **합의 대기** | 11.1의 exposed 판정과 같음 |

### 11.3 Skill·Plugin

| 항목 | 상태 | 구현·출력 | 비고 |
|---|---|---|---|
| package_id·name | 구현 완료 | Plugin `package.name`·manifest `id`, Skill `identity.name` | |
| provider | **실제 미구현(힌트만) + 정의 합의 대기** | **신규** Plugin `package.declared_provider_hints`(`author_name`·`repository`·`homepage`, npm 표준 필드), Skill ClawHub `owner_handle`·SKILL.md `homepage` | OpenClaw 문서가 정의한 "공급자" 필드는 없음. 무엇을 provider로 볼지 합의 전에는 `provider` 필드를 만들지 않음 |
| version | 구현 완료 | Plugin `package.version`, Skill ClawHub `install_origin.installed_version`(기록값) | Skill 자체 버전 필드는 SKILL.md 문서에 없음(원천 미제공) |
| commit | **구현 완료(있을 때만)** | **신규** Plugin `package.git_head`(npm `gitHead`, 형식만 확인) | 소스 체크아웃·로컬 설치에는 없을 수 있음(예제에 없다는 것이 원천 부재는 아님). 검증하지 않음 |
| source_type·source_uri·registry | 구현 완료 | Plugin `install_hints`+`declared_source_kinds`(npm/clawhub/local_path), Skill `install_origin.registry/source_url/requested_reference` | 로컬·Git 설치 Skill은 기록 파일이 없어 원천 미제공 |
| hash/signature 존재 여부 | 구현 완료 | Plugin `expected_integrity_declared`, Skill 설치 명세 `sha256_declared` | 값은 저장하지 않음 |
| 검증 결과 | **합의 대기** | `verification: not_performed` | 허용 레지스트리·서명 키 등 신뢰 기준 미정. 서명 검증 성공을 추정하지 않음 |
| modified 상태 | **원천 확인 대기** | 없음 | `444f558`의 P2 `plugin inspect`(`tb-gw.plugin-inspect.agentscope-asset-catalog.json`)에는 **modified 상태를 나타내는 필드가 없다**. 설치 시점 기록(`install.acceptedSurfaceHash`·`acceptedSurfaceAt`)은 있으나 이를 modified 판정 근거로 단정하지 않는다. 실제 원천은 OVA·실제 환경에서 확인한 뒤 정하며 정의도 합의 대기 |
| entry point | 구현 완료 | Plugin `package.entry_points`. Skill은 진입 파일이 SKILL.md | 파일 존재·내용은 확인·실행하지 않음 |
| script/binary 유형 | **미판정**(설치 명세는 수집) | Skill `install_specs[].kind`는 설치 방식, `bins`는 요구/설치 명세 | brew/node/go/uv/download를 실제 실행물의 script/binary 유형으로 간주하지 않음. 실행 파일·본문은 검사하지 않음 |
| 실행 위치 | **합의 대기** | 없음 | 증적 형식 미정 |
| 등록 Server·Tool·hook | 구현 완료(부분) | Plugin `mcp_servers`·manifest `contracts` | hook 목록은 저장된 `plugins list --json` 출력에만 있음(실환경 검증 대기) |
| dependency 목록 | 구현 완료 | Plugin `package.dependencies`, Skill `requires`·`install_specs` | 설치·해석 버전·취약점은 미확인 |
| pinned·update channel·auto-update | 구현 완료(범위 한정) | `update_policy`(OpenClaw 자체), Plugin `npmSpec` 값 | "pinned" 판정 규칙은 합의 대기. Plugin별 채널은 원천 미제공 |
| last_updated | **원천 확인 대기**(Plugin·Skill) | Skill `install_origin.installed_at_ms`는 별도의 설치 시각 기록으로만 수집 | Plugin `install.installedAt`과 Skill `installed_at_ms` 모두 last_updated로 대체하지 않음. `444f558` P2 `plugin inspect`에도 last_updated 필드가 없음 |

### 11.4 권한·자격증명

| 항목 | 상태 | 구현·출력 | 비고 |
|---|---|---|---|
| credential reference ID·type·대상 | 구현 완료 | `credential.kind`, `ref_names`, `applies_to` | 값·길이·해시 비저장 |
| OAuth scope·identity·redirect | 구현 완료 | `mcp_server_auth` | |
| OAuth issuer·audience·만료·사용자별 분리 판정 | **합의 대기**(비밀 접근 범위) + 일부 **실제 미구현** | `oauth.identity`(shared/per-requester 선언)는 구현 | issuer·audience는 서버 메타데이터(네트워크 조회), 만료는 OpenClaw 상태 저장소의 토큰 기록이 원천이나 **비밀이 섞인 저장소를 읽는 범위가 합의되지 않아** 읽지 않음. 원천이 없는 것이 아님 |
| process identity | 구현 완료(부분) + **실제 미구현** | sandbox `docker.user` | Gateway·Node 서비스 실행 사용자는 서비스 유닛 파일 등이 원천(OpenClaw 문서 밖, 지정 입력 필요) — 아직 읽지 않음 |
| sandbox | **신규 구현 완료** | `sandbox_policy`: `agents.defaults.sandbox.*`, `agents.entries.*.sandbox.{mode,scope,workspaceAccess}`, `tools.sandbox.tools.{allow,deny}` | 근거 `docs/gateway/config-agents/sandbox.md`. 에이전트별 docker/ssh/browser 재정의는 문서에 예시 없어 미수집 |
| command 권한 | **신규 구현 완료** | `exec_policy`: `tools.exec.{mode,security,ask,host,strictInlineEval,applyPatch.*,grantExpiryDays}`, 에이전트별 `mode/security/ask`, 호스트 승인 문서(`--exec-approvals-file`) | 근거 `built-in-tools.md`·`exec-approvals.md`. 최종 실효 결과는 계산하지 않음 |
| 파일 읽기·쓰기 범위 | **구현 완료(선언)** | sandbox `workspaceAccess`·`docker.binds`·`workspaceRoot`, **정정 추가** `tools.fs.workspaceOnly`(전역·에이전트별, `file_policy`) | `tools.exec.applyPatch.workspaceOnly`는 문서가 키 이름만 밝혀 자료형을 추측하지 않고 미수집(`not_collected`에 사유 기록). 앞선 "문서에 키 없음" 기재는 문서 일부만 검색한 오류였음 |
| 네트워크 | **구현 완료(선언)** | `docker.network/dns/extraHosts`, sandbox `browser.network/cdpSourceRange`, `tools.web.{search,fetch}.enabled`, **정정 추가** `browser.ssrfPolicy.{dangerouslyAllowPrivateNetwork,allowPrivateNetwork,allowedHostnames,blockedHostnames}`, `cron.webhookSsrfPolicy.{allowedHostnames,blockedHostnames,dangerouslyAllowPrivateNetwork}` → `network_policy` | 채널별 `network.dangerouslyAllowPrivateNetwork`·모델 제공자 `request.allowPrivateNetwork`는 **실제 미구현**(원천 있음, 범위 밖으로 `not_collected` 기록). 접근 가능 여부·내부망/외부망 판정은 합의 대기(계산 안 함) |
| Tool filter | 구현 완료 | `declared.toolFilter` | |
| approval mode | **구현 완료** | `exec_policy`(mode/ask), `declared_extra.codex.defaultToolsApprovalMode`, 승인 문서 `defaults/agents.*.{security,ask,askFallback,autoAllowSkills}`, 허용 목록 `pattern`·`mcpTools` | 승인 문서는 사용자 지정 경로의 읽기 전용 입력 |
| 적용 정책과 판정 결과 | **합의 대기**(의도적) | 선언만 | 우선순위·기본값 계산 금지 |

### 11.5 이번 보완에서 재현→수정한 실제 누락

| 누락 | 재현 | 수정 후 |
|---|---|---|
| Skill `description: >`·`\|`·여러 줄 값, 중첩 메타데이터의 목록-매핑 | `test_skill_frontmatter_yaml.py` 15개 실패 | 17개 통과(`skill_frontmatter.py`) |
| sandbox·exec·네트워크 스위치·승인 문서 미수집 | `test_permission_sandbox_exec.py` 10개 실패 | 11개 통과 |
| Skill 설치 명세·설치 기록 미수집 | `test_skill_origin_and_install.py` 6개 실패 | 7개 통과 |
| 저장 캡처의 서버 능력·정보 미보존(`tools_catalog`) | `test_capability_snapshot.py` 5개 실패 | 5개 통과 |
| Plugin 출처 종류 | `test_plugin_origin_fields.py` 1개 실패 | 통과 |

## 12. 상태 판정 정정 (2026-11-18 후속)

앞선 11절 초안에서 **원천이 있는데도 "원천 미제공"으로 적은 항목**을 정정했다. 원인: 고정 패키지 문서의 일부(8개)만 검색하고 "문서에 없다"고 단정함. 전체 문서(`package/docs/*.md`)를 다시 검색해 `tools.fs.workspaceOnly`·`browser.ssrfPolicy`·`cron.webhookSsrfPolicy`·`cron.webhookToken`을 확인했고 수집을 추가했다.

| 항목 | 이전 기재 | 정정 |
|---|---|---|
| client_id | 원천 미제공 + 합의 대기 | **실제 미구현**(원천 관측: `devices list`의 `paired[].clientId`, 관측값 `node-host`; deviceId·공통 ID와 동일시하지 않음) |
| client capabilities | 실제 미구현 | **구현 완료**(live 실제 전송값, 저장 캡처 제공값) |
| provider | 원천 미제공 | 힌트 구현 + 정의 합의 대기 |
| commit | 원천 미제공 | 구현 완료(있을 때) |
| modified 상태·Plugin last_updated | 원천 미제공 → (중간 정정) 실제 미구현(원천: `plugin inspect`) | **원천 확인 대기**: `444f558` P2 `plugin inspect`에 두 필드가 없고 `installedAt`을 대체 근거로 쓰지 않음. 중간 정정의 "plugin inspect가 원천"은 틀렸음 |
| OAuth issuer·만료 | 원천 미제공 | 합의 대기(비밀 접근 범위)·일부 실제 미구현 |
| process identity(서비스 실행 사용자) | 원천 미제공 | 실제 미구현(원천: 서비스 유닛 파일) |
| 파일 읽기·쓰기 범위(`tools.fs`) | 원천 미제공 | **구현 완료**(`file_policy`) |
| 네트워크 허용 목적지 | 원천 미제공 + 합의 대기 | 선언 구현 완료(브라우저·웹훅 SSRF 정책), 채널·제공자별은 실제 미구현, 판정은 합의 대기 |

**진짜 "원천 미제공"으로 남는 것**: OpenClaw 문서·출력에 해당 개념이 없는 항목 — Skill 자체 버전 필드(SKILL.md 문서에 없음), `host_id`의 OpenClaw 정의. 그 밖에는 모두 위처럼 원천이 있거나 정의 합의 문제다.

### Skill 파서의 YAML 지원 범위 (정확한 기재)
`skill_frontmatter.py`는 YAML **부분집합**만 읽는다. 지원: 중첩 매핑·목록(목록 안 매핑 포함), 블록 스칼라(`|`·`>`, chomping `-`/`+`, 들여쓰기 지시자 1~9), 여러 줄 평문·따옴표 스칼라(접기), 흐름 값(JSON5), 주석, 숫자·불리언·null. **미지원**(키 이름만 `frontmatter_unparsed_keys`에 남김): 앵커·별칭·태그, 복합 키(`?`), 탭 들여쓰기, 다중 문서, 병합 키(`<<`), 복잡한 흐름 구조. 한도: 깊이 20·노드 2000·문자열 64KiB. 숫자로 해석되는 값(예: 숫자만으로 된 `sha256`)은 정수로 읽고 문자열로 바꾸지 않는다. 완전한 YAML 1.2 구현이 아니다. 큰따옴표 escape는 JSON 호환 범위만 지원하며 미지원 문법은 원문을 추측해서 재작성하지 않는다. 흐름 값과 metadata JSON5 폴백도 같은 한도·중복 키 검사를 적용한다. 2026-11-18 업로드본 후속 검증은 [검증 기록](verification-20261118.md) 참조.
