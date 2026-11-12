# 자산 수집 확대: Plugin·Skill, Gateway·Node identity, Permission/Auth (내부 개발용 초안)

> 상태: 스캐너 내부 초안 `0.1.0-draft` · 작성일 2026-11-12
> 이 문서의 필드명과 구조는 **팀 공통 스키마가 아닙니다.** 공통 자산 ID 규칙(Issue #10, PR #11)과 공통 스키마(PR #18 초안)는 확정하지도 구현하지도 않았고, 현재 내부 출력 형식을 확장했습니다. 출력의 `internal_ref`·`ref`는 그 파일 안에서만 쓰는 이름입니다.
> 팀 8종 자산 분류에서 이 문서가 다루는 것은 Plugin, Skill, Gateway, Node, Permission/Auth의 **수집**이며, 팀 테스트베드와는 대조하지 않았습니다.

## 0. 공통 원칙

| 원칙 | 내용 |
|---|---|
| 읽기 전용 | 세 모듈은 기본적으로 명령을 실행하지 않고 서버에 접속하지 않으며 플러그인 코드를 import·실행하지 않습니다(① `plugin_skill_assets`·② `node_gateway_identity`는 사용자가 `--openclaw-bin`과 직접 조회 옵션을 명시한 경우에만 허용 목록의 읽기 조회를 [`openclaw_direct`](openclaw-direct.md)로 실행). 입력은 호출자가 명시한 파일·디렉터리뿐이고 홈 디렉터리 등을 자동 탐색하지 않습니다. |
| 값의 출처 구분 | **정적 파일에서 관측**한 값, **설정에 선언**된 값, **저장된 명령 출력**의 값, **사용자가 제공**한 값을 서로 다른 필드에 둡니다. 어느 것도 스캐너가 런타임에서 확인한 값이 아닙니다(`verified_by_scanner: false`). |
| 없는 값을 만들지 않음 | 원천에 없는 필드는 생략합니다. 기본값·활성 여부·"유효한 정책"을 계산해 채우지 않습니다. |
| 가려진 식별값 | 비밀값처럼 보여 가려졌거나 바뀐 식별값(`id`, `name`, `deviceId`)은 `original_value: null`, `status: withheld_by_redaction`으로 표시하고 같은 값 비교·연결에 쓰지 않습니다. |
| 인증정보 | 원문·길이·해시를 출력·로그·식별 입력에 저장하지 않습니다. 종류(`secret_ref`/`env_ref`/`literal_withheld`)와 참조 이름만 남깁니다. |
| 합치지 않음 | 같은 `id`·이름이라는 이유만으로 항목을 합치지 않습니다. 연결은 경로·참조 등 명시적 근거가 있을 때만 합니다. |

## 1. 근거 자료 (설치 버전 OpenClaw 2026.9.6)

확인일 2026-11-12. 이전에 받아 둔 npm 패키지 `openclaw@2026.9.6`(tarball, `output/openclaw-9.6/`)의 문서와 번들 코드를 **정적으로 읽었습니다.** OpenClaw를 설치·실행하지 않았고 팀 테스트베드에도 접속하지 않았습니다. 번들 코드 확인은 해당 구현을 텍스트로 읽은 것이며 실행 결과로 확인한 것이 아닙니다.

| 대상 | 근거 | 확인한 내용 |
|---|---|---|
| Plugin 매니페스트 | 패키지 `docs/plugins/manifest.md` "Top-level field reference" | `openclaw.plugin.json`의 필수 `id`(= `plugins.entries.<id>`에 쓰이는 정식 id), 선택 `name`·`description`·`version`·`kind`·`channels`·`providers`·`skills`(플러그인 루트 기준 상대 경로 skill 디렉터리)·`mcpServers`·`requiresPlugins`·`enabledByDefault` 등. `mcpServers`는 플러그인이 활성일 때 존재하는 정적 MCP 서버 선언 |
| Plugin 패키지 정보 | `docs/plugins/manifest/package-json.md` | `package.json`의 `openclaw.install.npmSpec`/`clawhubSpec`/`localPath`/`minHostVersion`/`expectedIntegrity`, `openclaw.compat.pluginApi`, `openclaw.extensions` |
| Plugin 런타임 레코드 | 번들 코드 `PluginRecord` 타입, `runPluginsListCommand` | `openclaw plugins list --json`은 `{workspaceDir, workspaceScope, registry:{source, diagnostics}, plugins:[PluginRecord], diagnostics}`를 출력(레코드는 `agentHarnessIds`만 뺀 `PluginRecord`). `PluginRecord` 필드: `id`·`name`·`version`·`packageName`·`origin`(`bundled`/`global`/`workspace`/`config`)·`source`·`rootDir`·`enabled`·`explicitlyEnabled`·`activated`·`status`(`loaded`/`disabled`/`error`) 등. 문서: `docs/cli/plugins/list.md` |
| Skill 형식 | `docs/tools/skills.md` "SKILL.md format" | 필수 `name`·`description` frontmatter, 선택 `homepage`·`user-invocable`·`disable-model-invocation`·`command-dispatch` 등. frontmatter는 YAML을 먼저 해석하고 실패하면 한 줄 해석, 중첩 `metadata`는 JSON5로 다시 읽음. 설정 키는 skill 이름, `metadata.openclaw.skillKey`가 있으면 그 값 |
| Skill 설정 | `docs/tools/skills-config.md` | `skills.allowBundled`, `skills.load.extraDirs`, `skills.entries.<key>.{enabled, apiKey, env, config}`, `agents.defaults.skills`·`agents.entries.*.skills` |
| Skill 런타임 레코드 | 번들 코드 `buildSkillStatus` | `openclaw skills list --json`의 항목 필드: `name`·`description`·`source`·`bundled`·`filePath`·`baseDir`·`skillKey`·`disabled`·`blockedByAllowlist`·`eligible`·`modelVisible` 등 |
| Node identity | `docs/cli/node.md`, 번들 코드 `runNodeIdentityShow` | `openclaw node identity --json` → `{deviceId, publicKey}`. 로컬 상태 DB의 `device_identities`/`primary` 행을 읽고 **신원이 없으면 만들지 않고** 오류로 끝남(`loadDeviceIdentityIfPresentAsync`) |
| Gateway identity | 번들 코드 `systemHandlers["gateway.identity.get"]`, `gateway call` 구현 | 메서드 `gateway.identity.get`(범위 `operator.read`)이 `{deviceId, publicKey}`를 반환. `openclaw gateway call`은 `callGatewayReadOnlyCli`를 쓰고 `--json`이면 결과를 그대로 출력. 이 메서드는 공개 문서에는 없고 번들 코드와 팀 구축 기록에서만 확인함 |
| 정책·인증 설정 | `docs/gateway/config-tools/tool-policy.md`, `docs/gateway/config-gateway.md`, `docs/nodes/mcp-and-skills.md`, `docs/gateway/config-extensions.md`, `docs/tools/skills-config.md` | 3.2절 표의 설정 경로와 값 형식. `gateway.auth.mode`는 `none`/`token`/`password`/`trusted-proxy` |

**근거가 부족한 부분** (추측으로 채우지 않았습니다): `plugins list --json`·`skills list --json`의 전체 JSON 스키마를 문서로 확인하지 못해 번들 코드의 타입·생성 코드로 필드를 정했습니다. 플러그인 설치 기록(SQLite 플러그인 인덱스 `config_machine_state`)은 읽지 않았습니다. 이 버전에서 `gateway.nodes.*` 키 전체의 허용 범위는 설정 스키마로 확인하지 못했고 문서에 나온 키만 수집합니다.

## 2. ① Plugin·Skill 자체 정보 (`asset_scanner/plugin_skill_assets.py`)

```powershell
.\.venv\Scripts\python.exe -m asset_scanner.plugin_skill_assets --plugin-dir examples\plugin-sample --config examples\permission-auth.json5 --output output\plugin-skill.result.json
```

입력(모두 선택, 하나 이상 필요): `--plugin-dir`(여러 번), `--skills-dir`(여러 번), `--config`, `--plugins-list-json`, `--skills-list-json`. 종료 코드 0 완전 · 1 부분 · 2 인자 오류 · 3 실패 · 4 저장 실패.

### 값의 출처

| 출처 | 필드 | 의미 |
|---|---|---|
| 정적 파일 관측 | `manifest.declared`, `package`, `supply_source`, `frontmatter`, `metadata_openclaw` | `openclaw.plugin.json`·`package.json`·`SKILL.md` frontmatter에서 읽은 값. `observed_from`에 파일 경로와 `evidence_type: static_file` |
| 설정 선언 | `declared_activation` | `--config`의 `plugins.*`·`skills.*`에 **적힌** 값. 실제 로딩·활성 상태가 아니며 기본값·자동 활성화 규칙을 적용하지 않음 |
| 저장된 명령 출력 | `runtime_observation`, `runtime_only` | 저장해 둔 `plugins list --json`·`skills list --json` 출력의 값. 출력에 실행 시각이 없어 `observed_at`은 null이고 파일 수정 시각(`file_modified_at`)을 따로 표시(관측 시각이 아님) |
| 사용자 지정 | `root_dir.provided_by`, `observed_from.provided_by` | 어느 경로를 읽을지 사용자가 정했다는 사실. 경로의 종류(번들·관리형 등)는 판단하지 않음 |

### Plugin 항목

`identity`(`id`·`name`, 가림 시 `withheld_by_redaction`), `manifest`(선언된 문서화 필드와 `declared_keys`), `package`·`supply_source`(`package.json`의 이름·버전·`install_hints`; `expectedIntegrity`는 값을 저장하지 않고 `expected_integrity_declared`만), `mcp_servers`, `skills_declared`, `declared_activation`, `runtime_observation`, `issues`.

- **Plugin ↔ MCP 서버**: 같은 매니페스트의 `mcpServers`를 기존 수집기(`collect_plugin_manifest`)로 읽어 `mcp_servers.records[]`에 그대로 넣습니다(`link_basis: declared_in_same_manifest`, 선언 위치 `mcpServers.<키>`). 선언이 있다는 뜻이며 서버 실행·로딩·등록 성공을 뜻하지 않습니다.
- **Plugin ↔ Skill**: 매니페스트 `skills`의 상대 경로를 **플러그인 루트 안에서만** 읽습니다. 절대 경로·`..`로 루트를 벗어나면 읽지 않고 `skills_path_outside_plugin_root`를 기록합니다.
- **설정 연결**: `plugins.entries.<id>`가 매니페스트 `id`와 같을 때(문서가 정한 키)만 `declared_activation`을 붙이고, `listed_in_allow`/`listed_in_deny`도 같은 id 기준입니다. skill은 `metadata.openclaw.skillKey` 또는 `name`으로 `skills.entries.<key>`와 연결합니다. 항목이 없으면 `entry_declared: false`, 활성 여부는 null이며 "활성"/"비활성"으로 추정하지 않습니다.
- **런타임 관측 연결**: 플러그인은 `id`와 `rootDir`이 **모두** 맞을 때만, skill은 `SKILL.md` 경로가 같을 때만 연결합니다. `id`만 같고 경로가 다른 레코드는 `runtime_candidates_not_linked`로 알리고 합치지 않습니다. 디렉터리 입력과 맞지 않는 레코드는 `runtime_only`에 별개 항목으로 남습니다.

### Skill 항목

`identity.name`, `folder_name`·`name_matches_folder`, `frontmatter`(문서화된 키만), `metadata_openclaw`(`skillKey`·`primaryEnv`·`requires`·`install` 개수 등 문서화된 부분), `config_key`, `body_size_bytes`. **본문은 저장하지 않습니다**(작성자가 제공한 비신뢰 데이터). 디렉터리 탐색은 깊이 1(지정한 폴더 또는 그 바로 아래 폴더들), 심볼릭 링크는 따르지 않고, 디렉터리당 500개 한도입니다.

### 한계

- frontmatter 해석기는 YAML 라이브러리 없이 한 줄 `key: value`, JSON5 값, 들여쓰기 중첩 매핑·목록, 흐름 목록만 읽습니다. 블록 스칼라(`>`/`|`)·앵커 등은 값을 추정하지 않고 `frontmatter_unparsed_keys`에 키 이름만 남깁니다(그 키가 필수 필드이면 `required_field_missing` 표시).
- 설치 경로·설치 출처(플러그인 인덱스), 실제 로딩 여부, 등록된 Tool·훅 목록(저장된 출력에 적힌 이름만 옮김), skill의 의존 바이너리·환경변수 충족 여부는 확인하지 않았습니다.
- 번들 플러그인 63개 등 실제 패키지 전체를 스캔한 결과가 아닙니다. 가상 예제(`examples/plugin-sample/`)와 테스트용 임시 폴더로만 검증했습니다.

## 3. ② Gateway·Node 자체 정보 (`asset_scanner/node_gateway_identity.py`)

```powershell
.\.venv\Scripts\python.exe -m asset_scanner.node_gateway_identity --gateway-identity gw=examples\gateway-identity.sample.json --observed-at gw=2026-11-12T09:00:00+09:00 --output output\identity.result.json
```

**이 모듈은 기본적으로 명령을 실행하지 않습니다**(직접 조회 옵션을 명시한 경우만 [openclaw-direct.md](openclaw-direct.md)의 규칙으로 두 명령을 실행). 사용자가 미리 저장한 `openclaw gateway call gateway.identity.get --json`(Gateway) 또는 `openclaw node identity --json`(Node) 출력 파일을 읽습니다. 두 명령은 1장에서 확인한 읽기 전용 원천입니다.

| 필드 | 설명 |
|---|---|
| `kind` | 어느 플래그로 받았는지(`gateway`/`node`) |
| `origin` | `observed_from_stored_command_output` |
| `device_id`, `public_key` | `{original_value, status}`. `deviceId`는 길이 1~200·공백 없음, 긴 hex도 엔트로피로 가리지 않음. `publicKey`는 base64url(20~200자)만 저장하고 PEM·개인 키 모양은 저장하지 않음(`invalid_format`) |
| `observation` | `command`, `read_only_command`, `required_scope`(Gateway는 `operator.read`), `basis`(근거), `observed_at`·`observed_at_origin`, `file_modified_at`, `collected_at`, `executed_by_scanner: false`, `verified_by_scanner: false` |
| `unknown_fields` | 알려진 필드 외의 **이름만**. 값은 읽지 않음 |

- **관측 시각**: 출력 파일에는 실행 시각이 없습니다. `--observed-at 라벨=ISO8601`(시간대 필수)로 사용자가 선언한 경우에만 `observed_at`을 `operator_declared`로 기록합니다. 파일 수정 시각은 관측 시각이 아니라고 명시해 따로 둡니다.
- **`--subject`와의 구분**: `linking`의 `--subject`는 사용자가 입력한 값(`user_provided`)입니다. `linking --observed-identity 라벨=파일`로 이 모듈의 결과를 붙이면 `declaring_subject.observed_identity`에 **별도 필드**로 들어가며 사용자 입력(`id`, `id_origin`)을 덮어쓰지 않습니다. 둘이 다르면 `id_conflicts_with_user_provided: true`와 `observed_identity_conflict`를 기록하고 어느 쪽도 고르지 않습니다. 옵션을 주지 않으면 기존 출력에 필드가 더해지지 않습니다.
- 감싼 형태(`{ok, payload}` 등)는 추측해서 풀지 않고 `device_id: missing`으로 실패 처리합니다. 같은 `deviceId`가 여러 입력에 있어도 합치지 않습니다.
- 공통 자산 ID를 정하지 않았으므로 `deviceId`를 공통 ID로 확정하지 않습니다.

### 한계

- 저장된 출력이 **지금 실행 중인** Gateway·Node의 값인지, `deviceId`가 공개키에서 유도된 값인지, 페어링·승인 상태는 확인하지 않았습니다.
- `gateway.identity.get`은 서버 쪽 구현이 `loadOrCreateProcessDeviceIdentityAsync`를 쓰므로 실행 중인 Gateway 프로세스에서는 신원이 이미 있다는 전제입니다. 이 모듈은 호출하지 않습니다.
- Node 설정에서 식별값을 읽거나(예: `nodeHost` 설정), 장치 목록·페어링 목록은 수집하지 않습니다.

## 4. ③ Permission/Auth (`asset_scanner/permission_auth.py`)

```powershell
.\.venv\Scripts\python.exe -m asset_scanner.permission_auth --config examples\permission-auth.json5 --output output\permission-auth.result.json
```

설정 파일(JSON5)에서 문서에 있는 정책·인증 경로의 **선언 값**을 원천 항목 단위로 수집합니다. `$include`·환경변수는 해석하지 않습니다(`unresolved`에 기록, 수집 상태 `partial`).

**집계하지 않습니다.** 팀이 집계 단위(Permission/Auth 자산을 무엇으로 묶을지)를 협의 중이므로 `scope.aggregation: none`이며 항목마다 `config_path`·`config_pointer`·`applies_to`·`doc_basis`를 가진 원천 항목으로 보존합니다. 허용/거부의 최종 결과, 기본값, 우선순위, 그룹(`group:fs`)·프로필 펼치기는 계산하지 않습니다(`scope.not_collected`).

### 수집 경로

| 분류 | 경로 | `applies_to.scope` | 값 |
|---|---|---|---|
| `tool_policy` | `tools.{profile,allow,alsoAllow,deny}` | `global_tools` | 문자열 / 문자열 목록(순서·패턴 그대로) |
| | `tools.byProvider.<id>.{…}` | `provider` | 같음 |
| | `agents.entries.<id>.tools.{…}`, `….tools.elevated.enabled` | `agent` | 같음 / 불리언 |
| | `tools.toolsBySender.<키>.{allow,alsoAllow,deny}` | `sender_group` | 목록. **발신자 키는 값을 저장하지 않음**(종류 `e164`/`id`/`username`/`name`/`channel`/`any`만) |
| | `tools.elevated.enabled`, `tools.elevated.allowFrom.<채널>` | `global_tools` | 불리언 / **개수만**(사용자 ID·전화번호 값 저장 안 함) |
| `skill_policy` | `agents.defaults.skills`, `agents.entries.*.skills`, `skills.allowBundled` | `agent_defaults`/`agent`/`skills_global` | 목록 |
| `gateway_auth` | `gateway.auth.{mode,allowTailscale,trustedProxy.userHeader}`, `gateway.trustedProxies` | `gateway` | 문자열(문서화된 값 여부 표시)·불리언·목록 |
| | `gateway.auth.{token,password}` | `gateway` | **인증정보**: 종류와 참조 이름만 |
| `gateway_remote_client_auth` | `gateway.remote.{token,password}` | `gateway` | 인증정보(원격 클라이언트용 필드, 서버 인증을 구성하지 않음) |
| `node_policy` | `gateway.nodes.commands.{allow,deny}`, `gateway.nodes.pluginTools.enabled`, `gateway.nodes.allowSkills`, `gateway.nodes.pairing.autoApproveLocal`, `nodeHost.skills.enabled` | `gateway_nodes`/`node_host` | 목록·불리언 |
| `plugin_policy` | `plugins.{enabled,allow,deny}` | `plugins_global` | 불리언·목록 |
| `install_policy` | `security.installPolicy.{enabled,targets,exec.command,exec.args,exec.timeoutMs,…,exec.passEnv,exec.trustedDirs}` | `install_policy` | 값. `exec.args`는 비밀 이름 플래그 값 가림, `exec.env`는 **이름만** |
| `mcp_server_auth` | `mcp.servers.<키>.{auth,oauth.identity,oauth.scope,oauth.authProfileId,oauth.redirectUrl,oauth.clientMetadataUrl,clientCert,clientKey}` 및 `nodeHost.mcp.servers.<키>` | `mcp_server` | 문자열. 인증서·키 파일은 **선언 여부만** |

- **적용 대상 연결**: `mcp_server` 항목의 `applies_to`는 설정 수집기와 같은 `declaration_path`·`declaration_pointer`·`registration_key`를 가져 기존 서버 선언과 같은 위치로 연결됩니다(`link_basis: same_declaration_path_as_config_scan`). 그 밖의 대상은 설정 안의 키(Provider·Agent id)로 구분합니다. 같은 이름의 다른 위치 항목과 합치지 않습니다.
- **인증정보**: `credential.kind`는 `literal_withheld`(평문, 값·길이·해시 없음), `secret_ref`(`source`·`provider`·`id`), `env_ref`(`ref_names`), `invalid_secret_ref`입니다. 참조는 `unresolved`에도 이름만 기록합니다.
- 자료형이 틀리면 `value_kind: invalid_type`으로 항목은 남기되 값은 저장하지 않고 `field_type_invalid`를 기록합니다. 문서에 없는 열거값(예: `gateway.auth.mode: "magic"`)은 그대로 보존하고 `value_documented: false`로만 표시하며 오류로 만들지 않습니다.
- 선언이 없으면 항목이 없습니다. **"선언 없음"은 "정책 없음"이 아닙니다**(문서의 기본 동작이 적용될 수 있음). `item_count: 0`은 `no_declared_items`로 구분합니다.

### 한계

- 수집 경로는 1장에서 문서로 확인한 것만입니다. 채널별 접근 제어(`allowFrom` 등), 샌드박스 설정, 실행 승인 파일, 런타임 승인·페어링 상태는 수집하지 않습니다.
- 중복 키와 `$include`는 이 모듈이 읽는 최상위 영역(`tools`·`agents`·`gateway`·`nodeHost`·`plugins`·`skills`·`security`·`mcp`)에서만 문제로 봅니다.
- `gateway.nodes.*` 중 문서에 나오지 않는 키는 읽지 않습니다(스키마로 허용 범위를 확인하지 못함).

## 5. 검증 수준 구분

| 구분 | 내용 |
|---|---|
| **가상 입력 검증** | 세 모듈 모두 테스트가 만든 임시 폴더·설정·출력 파일과 `examples/`의 가상 자료로만 검증했습니다(`tests/test_plugin_skill_assets.py`, `test_node_gateway_identity.py`, `test_permission_auth.py`). 정상·경계·오류·가림·중복 키·합치지 않음·명령 미실행·코드 미실행을 포함합니다. |
| **실제 환경에서 관측한 것** | 없음. 실제 OpenClaw 설치, 실제 `plugins list`/`skills list`/`node identity`/`gateway call` 출력, 실제 플러그인·skill 디렉터리를 입력으로 쓰지 않았습니다. |
| **아직 확인하지 못한 환경** | 팀 테스트베드(문서상 OpenClaw 2026.9.6) 설정·플러그인·skill, 실제 CLI 출력의 필드 일치, 번들 플러그인 전체, 2026.9.6 이외 버전. 테스트베드 사양 정정본을 받기 전에는 대조·수집률·누락 계산을 하지 않습니다. |

## 6. 검증 실행 기록 (2026-11-12)

로그는 `asset-scanner/output/review-assets/`에 있습니다(`output/`은 `.gitignore` 대상이라 저장소에는 올라가지 않으므로 수치를 옮겨 적습니다). 이 PC는 RAM 8GB이고 최근 전체 실행이 메모리 부족으로 중단된 적이 있어 **파일 단위로 순차 실행**했으며 각 실행의 pytest 종료 코드(`$LASTEXITCODE`)를 직접 기록했습니다.

| 대상 | 결과 | pytest 종료 코드 | 로그 |
|---|---|---|---|
| `tests/test_plugin_skill_assets.py` (①) | 30 passed | **0** | `plugin-skill-final.log`, `.exit.txt` |
| `tests/test_node_gateway_identity.py` + 기존 `tests/test_linking.py` (②, `linking` 변경의 회귀) | 116 passed (33 + 83) | **0** | `identity-linking.log`, `.exit.txt` |
| `tests/test_permission_auth.py` (③) | 18 passed | **0** | `perm-final.log`, `.exit.txt` |
| 예제 CLI 3종(`examples/plugin-sample/`, `permission-auth.json5`, `gateway-identity.sample.json`) | 모두 완전 수집 | 각 **0** | `example-*.json` |

- 개발 중 실패하고 고친 것(최종 통과 로그가 아닌 중간 로그에 남음): ① skill frontmatter의 중첩 `metadata:` 블록이 JSON5로만 해석돼 YAML 매핑을 읽지 못했고(문서가 지원한다고 한 형식), 숫자 값(`homepage: 5`)을 문자열로 읽었습니다 → 들여쓰기 매핑·목록 해석기와 숫자 해석을 추가했습니다. ③ 테스트 기대 두 건이 구현 의도와 달랐고(분류 `node_policy`, 계산하지 않은 영역 설명 문구) 테스트를 고쳤습니다.
- 변경하지 않은 기존 모듈의 테스트는 반복하지 않았습니다. 이번 세션 시작 전 백업과 파일 해시를 비교해 기존 파일 중 바뀐 것은 `asset_scanner/linking.py` 하나뿐임을 확인했습니다(옵션 `--observed-identity`를 줄 때만 필드가 더해지며 기본 출력은 같음).
- **한 번의 전체 실행이 종료 코드 0으로 끝난 기록은 없습니다.** 전체 635개 중 이번 세션 이전 494개는 별도 기록(중단된 전체 실행에서 PASSED 458개 + 분할 실행 36개, [field-mapping 10-8](field-mapping.md))이 있고, 이번에 더한 141개(30 + 33 + 18 + 60)는 위 파일 단위 실행과 [live-discovery 9장 기록](live-discovery.md)으로 확인했습니다.
- 위 검증은 모두 **가상 입력**입니다. 실제 OpenClaw 환경에서 얻은 입력으로 확인한 것은 없습니다.
