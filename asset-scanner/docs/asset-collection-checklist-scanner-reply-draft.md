# 자산별 수집 항목 확인표 — 스캐너 담당 응답 초안

> **후속 상태(809775e 이후 수집 보완):** 이 문서의 기존 본문은 해당 시점의 검토·검증 기록입니다. devices/clientId, 서비스 실행 계정 선언, 네트워크·Agent 정책, 추가 include 경계, Plugin 설치 기록의 현재 구현은 [원천 수집 누락 보완표](source-collection-closure-20261118.md)를 참조하세요. 후속 구현은 이 문서와 함께 반영합니다. 이전 본문의 수치·제약은 당시 기록이며, 현재 상태는 보완표를 우선 참조합니다.


> 상태: **초안 · 스캐너 담당 검토 전** · 작성일 2026-11-17 · 대상: PR #11 `docs/asset-collection-checklist.md`(최신 `refs/pull/11/head`) 3절·4절
> 이 문서는 PR #11에 올리기 전의 초안입니다. 이번 작업에서 PR·Issue 댓글을 등록하지 않았습니다.
> **공통 자산 ID 규칙과 공통 스키마는 확정하거나 구현하지 않았습니다.** 스캐너 출력의 `internal_ref`·순번·라벨은 결과 파일 안에서만 쓰는 이름이며 영속 ID가 아닙니다. 이 표의 "수집 가능"은 ID 규칙 채택을 뜻하지 않습니다.

## 0. 근거 구분과 검증 환경

| 구분 | 뜻 | 이 문서의 표기 |
|---|---|---|
| 코드 확인 | 스캐너 소스·번들 문서를 읽은 것. 실행 결과 아님 | **[코드]** |
| 가상 테스트 | 테스트가 만든 임시 폴더·`examples/`의 가상 자료로 실행 | **[가상]** |
| 저장 자료 분석 | 테스트베드 담당이 VM에서 수집해 브랜치에 올린 파일을 스캐너로 실행 | **[저장]** |
| 실제 환경 직접 검증 | 실제 OpenClaw·VM에서 스캐너가 직접 조회 | **없음 — 이번에 수행하지 못함** |

| 항목 | 내용 |
|---|---|
| 스캐너 | `feature/scanner-config` `0b2ff6bb2dd2f87e95550223008050e960cd07af`(미커밋 변경: 테스트 2개 수정), Windows 10, Python 3.14.4 |
| 회귀 테스트 | QA 21건 수정 후 23개 파일 712 통과, F1 수정 후 24개 파일 **727 통과·0 실패**, 파일별 pytest 종료 코드 모두 0([결과](qa-fix-and-source-validation-20261117.md#35-f1-수정-url-원문-보존과-변경-기록-2026-11-17)) |
| 저장 자료 | `origin/feature/testbed-threat-vm-capture` `444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb`. 파일 내 시각 2026-10-04. 테스트베드 문서 기록: OpenClaw 2026.9.6 (eb377ac), Ubuntu 24.04.5, MCP 2026-07-28. **스캐너가 설치 버전을 확인한 것이 아님** |
| 확인일 | 2026-11-17 |
| 사본 | 설정 사본은 자리표시자(`<DUMMY_TOKEN>`·`<TB_USER>`)로 가린 것. VM 원본이 아님 |
| 확인자 | 스캐너 담당 확인 대기 |

"프로필 P0/P1/P2"는 테스트베드의 누적 구성 세트이며 OpenClaw `--profile`이 아닙니다(저장 자료는 모두 기본 위치 `~/.openclaw`).

## 1. 요약

| 자산·하위 유형 | 수집 가능 여부 | 주 근거 | 핵심 제약 |
|---|---|---|---|
| Gateway | **일부 가능** | [저장] identity 출력 파싱 | 환경·프로필 범위는 사용자 입력만. 직접 조회·초기화·복제 후 유지 미확인 |
| Node | **일부 가능** | [저장] identity 출력 파싱 | 페어링(`devices list`)·SQLite 설정은 읽는 모듈 없음 |
| MCP Server | **일부 가능** | [저장] 설정 사본 수집, 정답 목록과 선언 위치 일치 | 실행 위치 필드 없음. Plugin 선언 서버는 manifest 원본 필요. 환경변수 참조는 partial |
| Tool | **가능** | [저장] 40개 정답 일치, [가상] 로컬 시험 서버 | 투영 이름 연결 미지원, 팀 서버 직접 조회 미확인(스키마 URL `#` 소실은 F1로 수정, 저장 자료 재분석에서 원본과 동일) |
| Resource | **가능** | [저장] 9개, [가상] | 능력 미선언 서버는 `not_performed`(0개 아님). URI 원문 보존은 가림 규칙의 영향을 받음 |
| ResourceTemplate | **가능** | [저장] 2개, [가상] | 템플릿과 구체 URI를 별도 하위 유형으로 보존. 확장하지 않음 |
| Prompt | **가능** | [저장] 5개, [가상] | `prompts/get` 하지 않음 |
| Skill | **일부 가능** | [저장] `SKILL.md` 3종 | `skills list --json` 실제 출력 없음(저장본은 텍스트 표). 설치 경로는 입력 경로 |
| Plugin | **일부 가능** | [가상] manifest·[코드] `plugins list` | 저장 자료엔 manifest 원본·JSON 목록 없음. 동명 복수 설치본 경고 없음 |
| Permission | **일부 가능**(선언만) | [저장] 설정 사본, [가상] allow/deny | 저장 자료에 allow/deny 선언 없음. 실효 권한 계산 안 함 |
| Authentication | **일부 가능**(참조만) | [저장] 설정 사본 | 인증값은 종류·참조 이름만. `$include`·환경변수·SecretRef 미해석 |

## 2. 자산별 상세

### 2.1 Gateway

| 항목 | 내용 |
|---|---|
| 원천·명령 | `openclaw gateway call gateway.identity.get --json`(범위 `operator.read`). 저장본을 `--gateway-identity [라벨=]파일`로 읽음. 직접 조회 `--query-gateway-identity`는 구현돼 있으나 **실행하지 못함**([openclaw-direct.md](openclaw-direct.md)) |
| 출력 필드 | `deviceId`(64자리 hex), `publicKey`(base64url 43자) 두 개뿐 |
| 안전한 예시 | 저장본 `testbed/ground-truth/raw/P2/tb-gw.gateway-identity.json`: `{"deviceId":"e3e14de2…eddaa4","publicKey":"ETUwKz4j…CyuA"}` → 스캐너 결과 `identities[].device_id = {original_value, status: "as_reported"}`, `origin: observed_from_stored_command_output` (`identity-P0P1P2.json`) |
| 사용자 입력과 관측값 | `linking --subject gw=gateway,id=…`은 `user_provided`, 저장 출력은 `declaring_subject.observed_identity`로 **별도 필드**. 값이 다르면 `observed_identity_conflict`를 남기고 선택하지 않음 [저장] |
| 반복 조회 | P0·P1·P2 세 시점의 저장 출력에서 `deviceId`·`publicKey` 동일 [저장]. 같은 세션의 반복 조회는 저장 자료가 시점별 1건이라 **미확인** |
| 누락·제약 | 환경·프로필 범위(스캐너가 알 수 없음, 외부 입력 필요). 저장 출력에는 실행 시각이 없어 `--observed-at`으로 선언한 값만 `operator_declared`. 프로필(`--profile`)·초기화·재설치·복제 후 유지 **미확인**. `deviceId` 단독 식별의 적합성은 팀 협의 사항 |
| 근거 링크 | [asset-collection.md 3장](asset-collection.md), [`node_gateway_identity.py`](../asset_scanner/node_gateway_identity.py), [`test_node_gateway_identity.py`](../tests/test_node_gateway_identity.py), 결과 `output/testbed-stored-20261117/results/identity-*.json` |
| 검증 | [저장] 2026-11-17, 스캐너 `0b2ff6b`, 자료 `444f558`(2026-10-04 수집). [직접] 없음 |

### 2.2 Node

| 항목 | 내용 |
|---|---|
| 원천·명령 | `openclaw node identity --json` → `{deviceId, publicKey}`(신원이 없으면 만들지 않고 오류 종료, [코드]). 페어링 근거 `openclaw devices list --json`은 **스캐너가 읽지 않음** |
| 안전한 예시 | `{"deviceId":"b8cd252a…48da921","publicKey":"oLLtJA2i…zn6yjNQH4"}`. `devices list`의 `paired[].deviceId`와 일치, `nodes describe`에도 같은 값 포함(스캐너 밖의 대조 스크립트 `identity-stability-check.txt`) |
| 반복 조회 | P0·P1·P2 세 시점 동일, P1·P2의 `paired[].deviceId`와 일치 [저장]. 재페어링 전후는 **미확인** |
| 누락·제약 | `PAIRED_WITH` 근거(`devices list`, 페어링 시각·상태)와 Node 설정이 있는 `state/openclaw.sqlite`는 읽지 않음(**미지원**). Node 설정 `~/.openclaw/node.json`은 수집 원천으로 쓰지 않음 |
| 근거 링크 | [asset-collection.md 3장](asset-collection.md), `testbed/ground-truth/raw/P1/tb-gw.devices-list.json`(필드: `paired[].deviceId`·`role`·`connected`·`nodeSurface.caps/commands`) |
| 검증 | [저장] 같음. [직접] 없음 |

### 2.3 MCP Server

| 항목 | 내용 |
|---|---|
| 원천 | Gateway 설정 `mcp.servers.<키>`, Node 설정 `nodeHost.mcp.servers.<키>`(`--registry-path`), Plugin manifest `mcpServers.<키>`([README](../README.md)) |
| 출력 필드 | `registration_key`, `declaration_path`, `declaration_pointer`, `declared`(비밀 제외), `credentials`(참조 이름만), `collection_status`, `issues`, `unresolved`. 물리 경로는 `source_path` 속성 |
| 안전한 예시 | P2 Gateway: `registration_key: "inventory-remote"`, `declaration_path: "mcp.servers.inventory-remote"`, `declared: {url: "https://tb-node:8443/mcp", transport: "streamable-http", sslVerify: true}`, `credentials.headers.entries[0] = {name: "Authorization", value_kind: "literal_with_env_ref", ref_names: ["INVENTORY_MCP_TOKEN"]}`, `unresolved: [{kind: "env_var", name: "INVENTORY_MCP_TOKEN"}]` |
| 저장 자료 결과 | P0 Gateway 1·Node 영역 없음, P1 Gateway 1·Node 2, P2 Gateway 2·Node 2. 서버 수·등록 키·선언 위치가 정답 목록과 일치 [저장]. P2는 환경변수 참조 때문에 `partial`(종료 코드 1, 의도된 동작) |
| 연결 | `linking`으로 등록 키 ↔ 목록 결과: P2 5개 중 4개 linked, `asset-catalog`(Plugin manifest 선언) unlinked [저장]. `linked`는 입력 자료 간 연결이며 실행·노출 여부를 뜻하지 않음 |
| 선언 위치 vs 실행 위치 | 스캐너는 **선언 위치만** 기록(실행 위치 필드 없음 — **미지원**). 예: `inventory-remote`는 Gateway에 선언되고 tb-node에서 구동된다는 사실은 테스트베드 README의 기록 |
| 누락·제약 | `mcp list`·`mcp probe` 출력을 읽는 모듈 없음. `mcp show`는 환경변수를 풀어 출력한다는 보고가 있어 허용 목록 밖. `$include`·환경변수 해석 안 함. Plugin 선언 서버는 manifest 원본 필요(GitHub 사본으로는 연결 확인, VM 설치본은 미확인) |
| 설정 분할(`$include`) | `--resolve-includes`(선택)로 OpenClaw 2026.9.6 문서의 공식 구현(`openclaw/openclaw` `eb377ac`)의 병합(단일=대체, 배열=**연결**·순서·중복 보존, 빈 배열=`{}`, 형제 키는 같은 병합으로 뒤에, 객체 재귀 병합, 자료형이 다르면 뒤의 값)·경계(최상위 설정 폴더)·깊이 10·파일 2MB·하드링크·순환을 읽기 전용으로 처리하고 배열 원소별 출처까지 서버마다 `include_origin`(파일 상대 경로·include 사슬·필드별 덮어쓴 파일)을 기록. 기본값은 기존대로 읽지 않고 `unresolved`. `collector`·`permission_auth`·`plugin_skill_assets --config`·`live_discovery`가 같은 해석기를 씁니다. **`OPENCLAW_INCLUDE_ROOTS`(추가 경계)만 미지원**(경계 밖은 오류 기록). 해석하지 못한 include가 선택한 서버에 영향을 주면 조회를 거부하고 수집 결과는 partial. **[가상]**만 검증, 실제 설정 분할 사례는 미확인 |
| 추가 선언 값 | 문서화된 `requestTimeoutMs`·`connectionTimeoutMs`·`supportsParallelToolCalls`·`codex.agents`·`codex.defaultToolsApprovalMode`를 `declared_extra`에 선언 값 그대로 기록(기존 `declared`·`other_declared_keys` 계약 유지). 승인 모드는 Codex app-server 한정 선언이며 실제 동작이 아님 |
| 근거 링크 | [README 등록 영역 선택](../README.md), [snap1-validation.md](snap1-validation.md), [`collector.py`](../asset_scanner/collector.py), [`config_includes.py`](../asset_scanner/config_includes.py), [`linking.py`](../asset_scanner/linking.py), 결과 `results/collector-P*-*.json`, `linking-P2.json` |
| 검증 | [저장]·[가상] 2026-11-17. [직접] 없음 |

### 2.4 Tool

| 항목 | 내용 |
|---|---|
| 원천 | 해당 서버의 `tools/list` → `tools[]`. 저장 응답은 `tools_catalog`, 실제 조회는 `live_discovery`(허용 목록: 목록 조회만, `tools/call` 차단) |
| 출력 필드 | `definition.name`(서버가 준 원래 이름), `title`, `description`, `inputSchema`, `outputSchema`, `annotations`, 소속 서버(`server_ref`) |
| 안전한 예시 | `server_ref: "P2:inventory-remote"`, `definition.name: "inventory_list_hosts"`, `definition_status: "passed_limited_checks"` |
| 저장 자료 결과 | 5개 서버 40개. 정답 목록 P2의 서버별 이름 집합과 **모두 일치** [저장]. 같은 자료를 양쪽이 쓴 것이라 파싱 정확성만 확인 |
| 누락·제약 | Gateway 투영 이름(`fs-workspace__list_directory`)은 `mcp probe`에만 있고 스캐너가 읽지 않음 — 투영 이름과 원래 이름의 연결은 **미지원**. 목록에 있다는 것은 Agent 노출·호출 가능을 뜻하지 않음. **F1(수정함)**: 스키마 `$schema` URL 끝 `#` 소실과 `definition_altered` 오표시를 고쳤고, 저장 자료 재분석에서 40개 정의가 원본과 동일(이전 38개 상이). 정의별 `alteration`에 변경 여부·사유 기록 [저장]·[가상] |
| 근거 링크 | [README Tool 카탈로그](../README.md), [`tools_catalog.py`](../asset_scanner/tools_catalog.py), [live-discovery.md](live-discovery.md) |
| 검증 | [저장] 2026-11-17. 로컬 시험 서버 통신 [가상]. **실제 팀 서버 직접 조회 미확인** |

### 2.5 Resource · ResourceTemplate · Prompt

| 항목 | Resource | ResourceTemplate | Prompt |
|---|---|---|---|
| 원천 | `resources/list` → `resources[]` | `resources/templates/list` → `resourceTemplates[]` | `prompts/list` → `prompts[]` |
| 식별 필드 | `uri`, `name` | `uriTemplate`, `name` | `name` |
| 함께 수집 | `title`·`description`·`mimeType`·`size`·`annotations` | `title`·`description`·`mimeType` | `title`·`description`·`arguments[]` |
| 저장 자료 결과 | 9개(P1 `kg-memory` 1, `demo-everything` 7, P2 `inventory-remote` 1) | 2개(`demo-everything`) | 5개(`demo-everything` 4, `inventory-remote` 1) |
| 정답 목록 대조 | resource 11 = 9 + 2(템플릿은 `subtype: template`) 일치 | 같음 | 5 일치 |

- 모듈: `resources_prompts`(저장 응답), `live_discovery`(실제 조회). 응답에 **있는 것만** 옮기고 표시 제목과 식별용 `name`을 구분. 같은 이름의 resource·template·prompt는 합치지 않음.
- 능력을 선언하지 않은 서버(`fs-workspace`, `asset-catalog` 등)는 `not_performed/capability_not_declared`로 **0개와 구분** [저장].
- 제약: `resources/read`·`prompts/get`을 하지 않으므로 내용·실제 읽기 가능 여부는 미확인. URI·템플릿에도 비밀 가림 규칙이 적용돼 가려진 값은 원본 식별값으로 쓰지 않음(`withheld_by_redaction`).
- 근거 링크: [README](../README.md), [`resources_prompts.py`](../asset_scanner/resources_prompts.py), 결과 `results/resources-prompts.json`. 검증: [저장]·[가상]. [직접] 없음.

### 2.6 Skill

| 항목 | 내용 |
|---|---|
| 원천 | `SKILL.md` frontmatter(`--skills-dir`), 설정 `skills.entries.<key>`, `openclaw skills list --json`(저장본 또는 직접 조회) |
| 직접 조회 | `skills list`는 **기본 거부**: Gateway RPC를 쓰고 로컬 장치 신원을 새로 만들어 페어링 요청으로 이어질 수 있음 [코드]. `--accept-skills-list-gateway-rpc`로 명시 동의해야만 실행 |
| 안전한 예시 | `identity.name: "node-disk-report"`, `folder_name`, `name_matches_folder`, `frontmatter`(문서화된 키만), `body_size_bytes`(본문은 저장하지 않음) |
| 저장 자료 결과 | P1 Node Skill 2종, P2 Gateway workspace Skill 1종 complete [저장]. 경로는 입력 사본 경로이며 VM의 설치 경로(`~/.openclaw/skills/…`)가 아님 |
| 동명 복수 설치본 | 같은 이름의 두 디렉터리 → **항목 2개 별도 보존, 경고 없음**. 구분은 입력 경로뿐 [가상] |
| 출처·의존성·YAML(2026-11-18) | frontmatter는 YAML 부분집합 해석기로 블록 스칼라(`description: >`)·중첩 목록-매핑을 읽음(앵커·별칭·태그는 확장하지 않고 키만 남김). `metadata.openclaw.install[]`의 `id·kind·formula·bins·label·os`와 download의 `url·archive·extract·stripComponents·targetDir`, `sha256`은 **선언 여부(`sha256_declared`)와 값 유효성(`sha256_state`: valid_format/invalid_format/invalid_type/null/empty/absent)을 분리**해 기록(값 비저장, 숫자를 문자열로 바꾸지 않음). 설치 출처는 `<skill>/.clawhub/origin.json`(없으면 원천 미제공)의 기록값(`registry`·`slug`·`installedVersion`·`installedAt` 등)을 옮길 뿐 검증하지 않음 [가상] |
| 누락·제약 | `skills list --json` 실제 출력 없음(저장본 `tb-gw.skills-list.txt`는 텍스트 표라 읽을 수 없음). 섀도잉·우선순위·활성 여부(`eligible`)는 저장 목록 출력에만 있고 계산하지 않음. 설치 경로 정규화 규칙은 팀 합의 전 |
| 근거 링크 | [asset-collection.md 2장](asset-collection.md), [`plugin_skill_assets.py`](../asset_scanner/plugin_skill_assets.py), `results/skills-P*.json`, `virtual-duplicate-skill.json` |
| 검증 | [저장]·[가상] 2026-11-17. [직접] 없음 |

### 2.7 Plugin

| 항목 | 내용 |
|---|---|
| 원천 | `openclaw.plugin.json`(필수 `id`, `mcpServers`, `skills`)·`package.json`(`--plugin-dir`), `openclaw plugins list --json`(저장본/직접 조회; `{plugins:[PluginRecord]}`의 `id`·`rootDir`·`origin`·`enabled`·`status`) |
| 직접 조회 | `plugins list --json`은 허용 목록에 있고 Gateway에 접속하지 않음 [코드]. **실행하지 못함** |
| 안전한 예시 | `identity.id: "sample-voice"`, `manifest.declared`, `mcp_servers.records[].link_basis: "declared_in_same_manifest"` ([가상] `examples/plugin-sample`) |
| 저장 자료 | P2 Plugin `agentscope-asset-catalog`는 **`plugin inspect` JSON뿐**(`id`, `rootDir`, `origin: global`, `install.installPath`, `mcpServers.asset-catalog`). `--plugins-list-json`으로 읽으면 실패(종료 코드 3). `plugins list` 저장본은 텍스트 표라 읽을 수 없음. 저장 자료에는 manifest 원본이 없어 수집하지 못했음. 이후 **GitHub 고정 커밋(`444f558`)의 manifest·package.json 사본**은 수집 성공(종료 코드 0, `mcpServers.asset-catalog`)하고 `linking`에서 P2 서버 5개 모두 linked — 단 **VM 설치본이 아닌 사본**이며 저장된 VM 출력과 `description`이 달라 설치본과의 동일성은 미확인([검증 문서 3.6절](qa-fix-and-source-validation-20261117.md)) |
| 동명·동일 ID 복수 설치본 | 같은 `id`의 두 설치본 → **항목 2개 별도 보존, 경고 없음**. 구분은 입력 경로. 런타임 관측과는 `id`와 `rootDir`이 모두 맞을 때만 연결하고 같은 `id`·다른 경로는 `runtime_candidates_not_linked` [가상]·[코드] |
| 출처·진입점·의존성 | `package.entry_points`(`openclaw.extensions`·`runtimeExtensions`·`setupEntry`·`runtimeSetupEntry` 경로 문자열, 패키지 밖을 가리키면 표시, 실행·import 안 함), `package.dependencies`(이름·버전 범위, URL 인증정보 가림), `required_platform_packages`, manifest `contracts`·`activation_keys`, `supply_source.integrity`(선언 여부만, `verification: not_performed`). **서명·무결성 검증은 신뢰 기준 합의 전이라 구현하지 않음** [가상] |
| 누락·제약 | 설치 경로·설치 출처(SQLite 플러그인 인덱스)는 읽지 않음. Plugin ↔ MCP 서버 연결은 같은 manifest의 `mcpServers`로만(`declared_in_same_manifest`)이며 로딩·등록 성공을 뜻하지 않음 |
| 공급자·commit(2026-11-18) | `package.json`의 `author`(이름만)·`repository`·`homepage`는 `declared_provider_hints`로, `gitHead`는 `git_head`로 선언 값만 기록. **무엇을 provider로 볼지는 합의 전**이라 `provider` 필드를 만들지 않음. 이메일·URL 인증정보 비저장 [가상] |
| 근거 링크 | [asset-collection.md 2장](asset-collection.md), [`plugin_skill_assets.py`](../asset_scanner/plugin_skill_assets.py), `results/virtual-duplicate-plugin.json`, `plugin-skill-p2-inspect-as-list.log` |
| 검증 | [가상]·[GitHub 사본] 2026-11-17, [코드]. 저장 자료(VM 출력)의 `plugins list` 텍스트·`plugin inspect`는 `--plugins-list-json` 형식과 맞지 않아 읽지 못함. [직접] 없음 |

### 2.8 Permission

| 항목 | 내용 |
|---|---|
| 원천 | 설정 `tools.{profile,allow,alsoAllow,deny}`, `tools.byProvider`, `agents.entries.<id>.tools`, `tools.toolsBySender`, `tools.elevated`, `plugins.{allow,deny}`, `gateway.nodes.*`, `nodeHost.skills.enabled` 등(`permission_auth`, [asset-collection.md 4장](asset-collection.md)) |
| 출력 필드 | 원천 항목마다 `category`, `config_path`, `config_pointer`, `applies_to{scope,…}`, `value`, `doc_basis`. `scope.aggregation: none`(집계하지 않음) |
| 안전한 예시 | `{category: "tool_policy", config_pointer: "/tools/profile", applies_to.scope: "global_tools", value: "full"}` [저장] |
| 저장 자료 결과 | P0·P1·P2·S1~S4 Gateway 설정 각 3항목(`/tools/profile`, `/gateway/auth/mode`, `/gateway/auth/token`), Node 설정은 `no_declared_items`. 종료 코드 모두 0 |
| allow/deny | **저장된 설정 사본에는 허용·차단 선언이 없음.** 수집 경로는 가상 예제·테스트로만 검증([가상]). MCP 서버 수준 `toolFilter.include/exclude`는 MCP 수집 결과의 `declared`에 선언값으로 있음 [저장] |
| 업데이트 정책 | `update.channel`·`update.auto.enabled`·`update.checkOnStart`·`nodeHost.autoUpdate.enabled`를 `update_policy`로 수집(OpenClaw 문서 `install/updating/automatic-updates.md`). 저장된 P2 설정 사본에서 Gateway `update.checkOnStart=false`, Node `update.checkOnStart=false`·`nodeHost.autoUpdate.enabled=false` 확인 [저장] |
| 설정 분할 | `--resolve-includes` 사용 시 항목마다 `include_origin`(원본 파일) 기록. 사용하지 않으면 정책이 다른 파일에 있을 수 있음을 `unresolved`로 표시 |
| 표현 | **최종 실효 권한을 계산했다고 쓰지 않습니다.** 허용·차단 선언을 원천 항목 그대로 수집할 뿐이며 기본값·우선순위·그룹(`group:fs`) 펼치기·프로필 적용은 계산하지 않음. "선언 없음"은 "정책 없음"이 아님 |
| 파일·네트워크 범위(2026-11-18 정정) | 전체 문서 검색으로 확인된 `tools.fs.workspaceOnly`(전역·에이전트별 → `file_policy`), `browser.ssrfPolicy.*`·`cron.webhookSsrfPolicy.*`(→ `network_policy`), `cron.webhookToken`(→ `webhook_auth`, 값 비저장)을 추가. 앞서 "문서에 키 없음"이라 쓴 것은 일부 문서만 검색한 오류였음. 채널·제공자별 네트워크 정책과 `applyPatch.workspaceOnly`(자료형 근거 없음)는 `not_collected`에 사유 기록 |
| 후속 보완(2026-11-18) | 문서 근거(고정 패키지 `eb377ac`)가 있는 **sandbox**(`agents.defaults.sandbox.*`·에이전트별 `mode/scope/workspaceAccess`·`tools.sandbox.tools.*`), **명령 권한**(`tools.exec.{mode,security,ask,host,strictInlineEval,applyPatch.*,grantExpiryDays}`), **네트워크 스위치**(`tools.web.{search,fetch}.enabled`), **호스트 승인 문서**(사용자가 `--exec-approvals-file`로 경로를 지정한 읽기 전용 입력: `defaults`·`agents.<id>.{security,ask,askFallback,autoAllowSkills}`·허용 목록 `pattern`·`mcpTools`)를 선언 값으로 수집. 인자 해시·마지막 사용 명령·경로·시각·id·소켓 토큰은 저장하지 않음. [가상] 검증([예시](virtual-samples-and-outputs.md)) |
| 누락·제약 | 채널 접근 제어, 런타임 승인·페어링 상태, 에이전트별 sandbox.docker/ssh/browser 재정의(문서에 예시 없음), 일반 파일·네트워크 허용 목록(문서에 키 없음)은 수집하지 않음. 하나의 정책 경계와 적용 대상 중복 방지 규칙은 팀 협의 사항 |
| 검증 | [저장]·[가상] 2026-11-17. [직접] 없음 |

### 2.9 Authentication

| 항목 | 내용 |
|---|---|
| 원천 | `gateway.auth.{mode,token,password,allowTailscale,trustedProxy.*}`, `gateway.remote.{token,password}`, `mcp.servers.<키>.{auth,oauth.*,clientCert,clientKey}`, MCP 서버 `headers`·`env`의 참조 |
| 출력 필드 | `credential.kind`: `literal_withheld`·`secret_ref`(`source`·`provider`·`id`)·`env_ref`(`ref_names`)·`invalid_secret_ref`. MCP 서버는 `credentials.headers.entries[].{name, value_kind, ref_names}` |
| 안전한 예시 | `{category: "gateway_auth", config_pointer: "/gateway/auth/token", credential: {kind: "literal_withheld"}}`, `ref_names: ["INVENTORY_MCP_TOKEN"]` [저장] |
| 목록 조회 시 인증 전달 | 설정에 `Authorization: Bearer ${VAR}`가 선언돼 있어도 사용자가 같은 헤더를 `--bearer-env`/`--auth-header-env`로 명시 제공하면 선언을 **대체**하고(선언값은 사용하지 않음) 기록(`declared_header_replacements`: 헤더 이름·선언 참조 이름·제공 옵션·환경변수 **이름**·이름 일치 여부)을 남김. 다른 필드·다른 헤더의 참조는 기존대로 거부. 실제 P2 설정 사본으로 접속 없이 대상 생성 확인 [저장], 로컬 시험 서버로 조회 확인 [가상]. 실제 `inventory-remote` 조회는 OVA 후 |
| 비밀값 처리 | 원문·길이·해시를 출력·로그·식별 입력에 저장하지 않음. 이번 모든 결과·로그에서 `<DUMMY_TOKEN>`·`Bearer ` 검색 **0건** [저장]. 이 검사는 자리표시자에 대한 것이며 실제 비밀값에 대한 검증이 아님 |
| 적용 대상 | `mcp_server_auth`는 수집기와 같은 `declaration_path`·`declaration_pointer`·`registration_key`로 서버 선언과 연결(`same_declaration_path_as_config_scan`) |
| 누락·제약 | `$include`·환경변수·SecretRef 해석 안 함 → 참조가 있으면 수집 상태 `partial`. 참조된 환경변수·SecretRef가 **실제로 존재하는지·유효한지는 미확인**. `openclaw mcp show`는 사용하지 않음(환경변수 값을 풀어 출력한다는 보고). 환경별 `.env`(`~/.openclaw/.env`) 파일 읽기 미지원 |
| 검증 | [저장] 2026-11-17. [직접] 없음 |

> **client capabilities**: 직접 조회는 스캐너의 SDK 클라이언트가 **실제로 보낸** 값을 `client_capabilities_sent`로 기록하며 OpenClaw 클라이언트의 값이 아닙니다(`is_openclaw_client: false`). 저장 캡처는 제공된 값과 `client_sender` 출처만 기록하고 없으면 만들지 않습니다. 서버 능력·정보도 `tools_catalog`·`resources_prompts` 모두 입력에 제공된 내용을 별도 필드(`*_as_provided`)에 가림 후 보존합니다(기존 `declared_capabilities` 요약 유지). 실환경 검증 전입니다.
>
> 요구사항 문서(기획서·공격표면·스키마·확인표)와 스캐너 구현의 항목별 대응·상태·누락은 [requirements-implementation-matrix.md](requirements-implementation-matrix.md)에 있습니다. 문서 내용을 모두 확정 요구사항으로 보지 않고 성격을 구분했습니다.

> **어댑터 전달**: 이번에 추가한 스캐너 필드(`declared_extra`·`include_origin`·`alteration` 등)는 현재 대시보드 어댑터(`origin/feature/dashboard` `8f56930`)로 전달되지 않습니다(읽기 전용 확인). 필요한 매핑 제안은 [대응표 6절](requirements-implementation-matrix.md)에 있습니다. `$include` 문제가 있어도 수집 결과가 `partial`일 뿐 실제 조회 허용과는 별개이며, 선택한 서버에 영향이 있으면 조회를 거부합니다([7절](requirements-implementation-matrix.md)).

## 3. 4절 공통 확인 사항 응답 초안

| 확인 항목 | 현재 상태 | 근거 |
|---|---|---|
| 반복 수집 | 같은 설정 사본(P2 Gateway)을 두 번 실행한 결과가 `generated_at` 외에 동일하고 등록 키·선언 경로도 같음(스캐너의 결정성이며 원천의 유지가 아님). 실제 원천의 시점 간 유지는 P0·P1·P2 3개 시점에서 Gateway·Node `deviceId`·`publicKey` 동일 **[저장]**. 같은 세션 반복·초기화·복제·재페어링은 **미확인** | `identity-stability-check.txt`, `repeat-check.txt` |
| 프로필·초기화·복제 | **미확인**(실제 환경 없음). 테스트베드 담당 보완 필요 | — |
| 설정 출처 | 선언 주체별 `declaration_path`·`declaration_pointer`·`registration_key`로 복원 가능. `$include` 병합 전 원본 키 경로 추적과 Plugin 등록 후 복원은 **일부**(manifest 원본 필요) | 2.3 |
| 목록 완전성 | 목록마다 `complete`(빈 목록 포함)·`partial`·`failed`·`unsupported`·`not_performed`를 구분. 페이지 끝까지 수집 여부와 `nextCursor` 잔여를 기록. 조회 범위·인증 맥락의 상세 기록은 직접 조회에서만 [가상] | [README](../README.md), [live-discovery.md](live-discovery.md) |
| 이름·URI 보존 | 서버가 준 `name`·`uri`·`uriTemplate`을 `definition`/`identity`에 보존하고 표시 제목과 구분. 단 비밀처럼 보여 가려진 값은 원본 식별값으로 쓰지 않음. F1(스키마 URL `#` 소실)은 수정했고 비밀값이 없는 URL은 원문 보존 [저장]·[가상] | 2.4 |
| 비밀값 제외 | 원문·길이·해시 미저장. 이번 결과에서 자리표시자 문자열 0건 [저장] | 2.9 |
| 필수 식별값 누락 | 필수 값이 없으면 빈 문자열·`unknown`으로 채우지 않고 `missing`·`not_collected`·`withheld_by_redaction`으로 기록. "식별 완료/미완료" 상태 자체는 **정의하지 않음**(팀 협의 대기) | [id-requirements-and-testbed-request.md](id-requirements-and-testbed-request.md) |
| ID 공통 구현 | **구현하지 않음.** 합의 전 `internal_ref`·순번·라벨은 영속 ID가 아님 | — |

## 4. 테스트베드·서진님께 요청할 자료

실제 환경 직접 검증을 이어가려면 필요합니다. 비밀값은 제거한 사본이면 충분합니다.

1. 스캐너를 실행할 수 있는 **읽기 전용 접근 방법**(VM 접속 또는 OpenClaw 설치 경로). 스캐너는 허용 목록의 읽기 조회만 실행합니다.
2. 조회 대상: OpenClaw `--profile` 사용 여부, 설정·상태 위치, Gateway 접속 URL.
3. `openclaw plugins list --json`, `openclaw skills list --json`, `openclaw devices list --json` 저장본(현재 저장본은 텍스트 표).
4. `agentscope-asset-catalog`의 `openclaw.plugin.json`·`package.json`.
5. allow/deny 선언이 있는 설정 사본.
6. 복제·재설치·재페어링 전후 identity 출력.

## 5. 이 초안의 한계

- 실제 OpenClaw 환경에서 스캐너를 실행한 결과가 없습니다. "수집 가능"은 **저장 자료(2026-10-04, 자리표시자 사본)와 가상 자료**에서 확인된 범위입니다.
- 저장 자료와 정답 목록은 같은 환경에서 나온 것이라 대조는 파싱 정확성 확인이지 독립 검증이 아닙니다.
- 3·4절의 담당 확인 상태와 확인자는 스캐너 담당 검토 후 채워야 합니다.

> 최종 검증(2026-11-17~18): 전체 회귀 32개 파일 종료 코드 0, 830 passed / 0 failed / 2 skipped. skip(심볼릭 링크 권한·Windows 하드링크)에 해당하는 경계 이탈 거부는 **이 PC에서 미확인**입니다. Plugin·Skill 설정의 허용·차단·활성화 선언에는 `origins`(원본 파일·논리 키 경로, 배열은 원소별)가 붙습니다.
