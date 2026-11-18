# QA 실패 조사·수정과 OpenClaw 원천 검증 결과 (2026-11-17)

> 상태: 스캐너 내부 정리 · 작성일 2026-11-17 · 대상 브랜치 `feature/scanner-config`, HEAD `0b2ff6bb2dd2f87e95550223008050e960cd07af`
> 공통 자산 ID 규칙(Issue #10, PR #11)과 공통 스키마(PR #18)는 확정·구현하지 않았습니다. 이 문서의 `internal_ref`·순번·라벨은 결과 파일 안에서만 쓰는 이름이며 영속 ID가 아닙니다.
> 이번 작업에서 **커밋·push·PR/Issue 댓글·병합을 하지 않았습니다.**

## 1. 실제 로컬 상태

| 항목 | 확인 결과 |
|---|---|
| 브랜치·HEAD | `feature/scanner-config`, `0b2ff6bb…` — 지시서의 마지막 확인 커밋과 **같음**(차이 없음) |
| 작업 트리 | 추적 파일 변경 없음. 미추적 파일 12개(`scanner-review*.zip`, 검토 메모 등)는 그대로 보존 |
| 가상환경 | `asset-scanner\.venv\Scripts\python.exe`, Python 3.14.4 |
| 기존 로그 | `asset-scanner/output/` 하위 기존 로그 보존. 이번 로그는 새 디렉터리에만 기록 |
| 원격 | `git fetch`로 PR #25(`refs/qa/pr25`), PR #11(`refs/qa/pr11`) 참조만 내려받음. 다른 팀원 브랜치는 병합·체크아웃하지 않고 `git show`로만 읽음. reset·clean·강제 덮어쓰기 없음 |

## 2. QA 실패 21건 조사·수정

QA 보고서(`QA/reports/QA_최신스캐너검증_20261113.md`, PR #25): 712개 중 691 통과·21 실패(`test_live_tools` 1, `test_openclaw_direct` 20).

### 2.1 `test_live_tools.py` 1건 — 테스트의 디렉터리 처리 결함

- **재현**: 이 PC에서 같은 PermissionError로 재현(`examples/plugin-sample` 디렉터리에 `read_bytes()`).
- **원인**: `test_ground_truth_and_example_inputs_are_not_modified_by_any_live_run`가 `examples` 직속 항목 모두를 파일로 읽음. 입력이 변경된 것이 아니라 테스트 코드 문제(QA 보고서의 판단과 일치).
- **수정**: 디렉터리를 건너뛰지 않고 **하위 파일까지 재귀로 해시**하고, 디렉터리의 존재 자체도 기록해 추가·삭제도 검출하게 함. 검증 범위는 이전보다 넓어졌고 약해지지 않음. 비어 있는 입력으로 통과하지 못하도록 `assert before` 추가.
- **결과**: 34 passed, pytest 종료 코드 0.

### 2.2 `test_openclaw_direct.py` 20건 — 모의 CLI `.cmd` 셔임의 인코딩

이 PC(ASCII 경로)에서는 처음부터 45개가 통과해 **QA와 같은 조건이 아니면 재현되지 않았습니다.** 원인 후보(한글 경로·배치 파일·명령 인자·인코딩)를 분리해 확인했습니다.

| 가설 | 확인 방법 | 결과 |
|---|---|---|
| pytest 임시 폴더(`--basetemp`)에 한글 | `C:\scratch_한글경로\bt`로 실행 | **45 통과** — 원인 아님 |
| 셔임 본문에 한글 경로(`sys.executable`·`fake_openclaw.py`) | 한글 폴더로 저장소를 복사하고 HEAD의 원본 테스트 실행 | **20 실패 / 25 통과** — QA와 **같은 건수로 재현** |
| 셔임 파일 인코딩 | 같은 셔임을 UTF-8 / cp949로 각각 실행 | UTF-8: python이 `can't open file`(종료 코드 2), cp949: 정상(종료 코드 0) |
| `chcp 65001` | 셔임 첫 줄에 넣고 시험 | **미검증.** 시험 환경에 PATH를 주지 않아 `chcp` 명령 자체를 찾지 못했으므로 유효한 시험이 아님. QA가 보고한 "chcp 65001 재실행으로 해결 안 됨"을 이 PC에서 독립 확인하지 못함. 셔임을 ASCII로 만들면 코드페이지와 무관해지므로 수정에는 영향 없음 |

- **원인**: 테스트 픽스처가 `.cmd` 셔임을 UTF-8로 쓰는데 `cmd.exe`는 배치 파일을 **OEM 코드페이지(한국어 Windows cp949)** 로 읽음. 셔임 본문에 들어간 한글 경로(사용자 폴더·저장소 위치 등)가 깨져 "지정된 경로를 찾을 수 없습니다"(QA의 stderr, cp949 바이트가 깨진 문자열)로 실패. **제품 코드(`openclaw_direct.py`)의 결함이 아님**: 스캐너는 셔임 경로를 `Popen` 인자 배열로 넘기며 이는 유니코드를 그대로 전달함.
- **수정**(`tests/test_openclaw_direct.py`, 테스트 픽스처만): 셔임 본문을 ASCII로 두고 파이썬·스크립트 경로는 환경변수(`FAKE_OPENCLAW_PY`, `FAKE_OPENCLAW_SCRIPT`)로 전달. `cmd`는 환경변수를 유니코드로 확장하므로 코드페이지와 무관. 두 변수를 허용 환경변수(`PASS`)에 추가. 테스트 삭제·의미 약화 없음. 한글 경로를 피한 것이 아니라 **한글 경로에서 통과**하도록 고침.
- **수정 전후 비교(한글 경로 사본 `C:\scratch_한글경로\repo2`)**: HEAD 원본 20 실패 / 25 통과(종료 코드 1) → 수정본 **45 통과**(종료 코드 0). 실제 경로(ASCII)에서도 45 통과.
- **한계**: QA 환경(한글 경로)을 그대로 재현한 것이 아니라 **한글 경로로 복사한 사본에서 같은 실패 건수를 재현**한 것입니다. QA PC의 실제 경로는 확인하지 못했습니다.

### 2.3 회귀 실행 결과 (파일 단위 순차, pytest 종료 코드 직접 기록)

로그: `asset-scanner/output/qa-repro-20261117/per-file-exitcodes.txt`. 실행 전 HEAD는 위와 같고 전체를 한 번에 실행하지 않았습니다(이 PC는 RAM 8GB). 중단된 실행은 없었습니다.

| 파일 | 통과 | pytest 종료 코드 |
|---|---|---|
| test_collector | 22 | 0 |
| test_console_encoding | 4 | 0 |
| test_key_collision | 7 | 0 |
| test_linking | 83 | 0 |
| test_live_discovery | 60 | 0 |
| test_live_https | 32 | 0 |
| **test_live_tools** (수정) | **34** | **0** |
| test_node_gateway_identity | 33 | 0 |
| **test_openclaw_direct** (수정) | **45** | **0** |
| test_permission_auth | 18 | 0 |
| test_plugin_manifest | 13 | 0 |
| test_plugin_skill_assets | 30 | 0 |
| test_policy_fields | 26 | 0 |
| test_pr5_feedback | 31 | 0 |
| test_protocol_2025 | 22 | 0 |
| test_registry_path | 26 | 0 |
| test_resources_prompts | 53 | 0 |
| test_review_fixes | 31 | 0 |
| test_safety | 6 | 0 |
| test_secrets | 4 | 0 |
| test_tools_catalog | 48 | 0 |
| test_v5_review_fixes | 43 | 0 |
| test_v7_review_fixes | 41 | 0 |
| **합계 (23개 파일)** | **712 통과 / 0 실패** (URL 수정 전, 2.3절) | 모두 0 |

이 합계는 **파일별 실행의 합**이며 단일 pytest 전체 실행 결과가 아닙니다(QA 보고서와 같은 방식). 총 건수 712는 QA 보고서와 같고, 수정한 두 파일의 건수(34 = 33+1, 45 = 25+20)도 QA의 통과·실패 합과 같습니다. 나머지 파일별 건수는 QA 증적과 개별 대조하지 않았습니다.

## 3. 실제 OpenClaw 원천 검증

### 3.1 실제 환경 접근 여부 — **없음 (직접 검증 불가)**

| 확인 | 결과 |
|---|---|
| PATH의 `openclaw`·`openclaw.cmd`, npm 전역 설치 | 없음 |
| 사용자 홈 `~\.openclaw` | 없음 |
| WSL 배포판 | 없음(설치된 배포판 없음) |
| 팀 테스트베드 VM 접속 정보 | 이 세션에 없음 |

따라서 **설치 버전·프로필·설정 위치·조회 대상·검증 시점을 직접 관측한 기록은 없습니다.** 재설치·복제·재페어링·초기화 검증도 수행하지 않았고 **모두 미확인**입니다. `openclaw_direct`의 실제 실행도 하지 않았습니다. 아래는 **테스트베드 담당이 VM에서 이미 수집해 브랜치에 올린 저장 자료를 스캐너로 분석한 결과**이며 "실제 환경 직접 검증"이라고 쓰지 않습니다.

### 3.2 분석한 저장 자료

| 항목 | 내용 |
|---|---|
| 출처 | 원격 브랜치 `origin/feature/testbed-threat-vm-capture` 커밋 `444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb`(2026-11-12) — `git show`로 읽기만 함(병합·체크아웃 없음) |
| 수집 시점 | 파일 내 시각 기준 **2026-10-04**(`mcp-probe.json generatedAt` P0 06:38Z, P2 06:49Z). 이 시점은 테스트베드 담당이 기록한 것이며 스캐너가 확인한 것이 아님 |
| 환경(문서 기록) | OpenClaw 2026.9.6 (eb377ac), Ubuntu 24.04.5 LTS, MCP 2026-07-28 (`ground-truth/P*.json`의 `environment`, `build-log-snap0-snap1.md`). **스캐너가 설치 버전을 확인한 것이 아님** |
| "프로필" 뜻 | 테스트베드의 구성 세트 P0/P1/P2(누적 구성). OpenClaw의 `--profile`(상태·설정 분리)과 다릅니다. 저장 자료는 모두 기본 위치 `~/.openclaw`입니다 |
| 사본 처리 | 설정 사본은 자리표시자(`<DUMMY_TOKEN>`, `<TB_USER>`)로 가린 것이며 VM 원본 파일이 아님 |
| 보관 위치 | `asset-scanner/output/testbed-stored-20261117/inputs/`(Git 제외 경로) |

스캐너 실행 환경: Windows 10, Python 3.14.4, 이 저장소 HEAD. 모든 실행의 종료 코드는 `output/testbed-stored-20261117/results/exitcodes.txt`에 있습니다.

### 3.3 요청 항목별 결과

#### (1) Gateway·Node 식별값

| 확인 | 결과 | 구분 |
|---|---|---|
| 실제 출력 필드 | `{deviceId, publicKey}` 두 필드만. `deviceId`는 64자리 hex, `publicKey`는 base64url(43자) | 저장 자료 + 스캐너 파싱(`node_gateway_identity`, 종료 코드 0, 6건 `identity_read`) |
| 사용자 입력과 관측값 구분 | 스캐너는 `--subject id=`(사용자 입력, `user_provided`)와 저장된 출력에서 읽은 값(`observed_identity`)을 **별도 필드**로 보존. 가상 사용자 입력 `user-input-gw`와 관측값이 다르면 `observed_identity_conflict`를 기록하고 어느 쪽도 고르지 않음(저장 자료로 확인, `linking-P2-conflict-demo.log`) | 저장 자료 |
| 반복 조회 시 유지 | P0·P1·P2 **3개 시점의 저장 출력에서** Gateway `deviceId`·`publicKey` 동일, Node `deviceId`·`publicKey` 동일. `devices list`(P1·P2)의 `paired[].deviceId`와 Node `deviceId` 일치, `nodes describe`(P1·P2·S1~S4)에도 같은 Node `deviceId` 포함. Gateway와 Node 값은 서로 다름 | 저장 자료(`identity-stability-check.txt`) |
| 직접 조회 | **미실행**(OpenClaw 없음) | 미확인 |
| 같은 세션에서 연속 반복 | 시점별 1회씩의 저장 출력뿐이라 짧은 간격 반복 조회는 **미확인** | 미확인 |
| 프로필별 차이(OpenClaw `--profile`)·초기화·재설치·복제·재페어링 | **미확인** | 미확인 |

#### (2) MCP 서버

| 확인 | 결과 |
|---|---|
| 선언 주체와 논리 경로 | Gateway 설정 `mcp.servers.<등록 키>`, Node 설정 `nodeHost.mcp.servers.<등록 키>`, Plugin manifest `mcpServers.<키>`. 스캐너 출력은 `registration_key`·`declaration_path`·`declaration_pointer`로 구분(물리 경로 `source_path`는 속성) |
| 저장 설정 사본 수집 (P0/P1/P2, 종료 코드) | P0 Gateway 1개(0)·Node 등록 영역 없음(0), P1 Gateway 1·Node 2(0), P2 Gateway 2(**1, partial**)·Node 2(**1, partial**). 정답 목록의 서버 선언 위치와 키 일치 |
| P2가 partial인 이유 | `inventory-remote`의 `headers.Authorization`이 `${INVENTORY_MCP_TOKEN}` 환경변수 참조. 스캐너는 참조를 풀지 않아 `unresolved`(이름만 기록, 값 없음)로 두고 상태를 partial로 표시. 의도된 동작 |
| 등록키 ↔ 목록 결과 연결 | `linking`: P2 서버 5개 중 **4개 linked**(`config_scan_ref`·`registry_path`·`registration_key` 일치), `asset-catalog` 1개 **unlinked**(`registry_path_missing`, 당시 manifest 원본 없음). 이후 GitHub 고정 커밋의 manifest **사본**을 더해 5개 모두 linked(3.6절, VM 설치본 검증 아님) |
| 선언 위치와 실행 위치 | 스캐너는 **선언 위치만** 기록. 실행 위치 필드는 없음. 예: `inventory-remote`는 Gateway 설정에 선언되고 tb-node에서 구동된다는 사실은 테스트베드 README의 기록이지 스캐너 출력이 아님 |
| `toolFilter` | 설정에 적힌 `include`/`exclude`를 선언값으로 수집(`fs-workspace` include 2개, `demo-everything` exclude 2개). 실제 노출 결과는 계산하지 않음 |
| `mcp list`와 대조 | 스캐너에 `mcp list` 출력을 읽는 모듈이 없음. SNAP-1의 저장 출력(텍스트)만 있고 P0~P2 시점의 `mcp list` 출력은 저장 자료에 없음. `mcp show`는 환경변수를 풀어 출력한다는 보고가 있어 허용 목록에도 없음 |
| MCP 목록 조회 | 저장된 광고 원본(`*.advertised.json`)을 capture 형식으로 감싸(`convert_advertised.py`, 값 변경 없음) `tools_catalog`·`resources_prompts`로 읽음. 실제 서버에는 접속하지 않았고 `tools/call`·`resources/read`·`prompts/get`도 하지 않음 |

#### (3) 환경·프로필

| 항목 | 현재 동작 | 구분 |
|---|---|---|
| 선언 주체 종류·식별값 | `linking --subject 라벨=종류[,id=값]` — 사용자 입력만 받음(`user_provided`) | 외부 입력 |
| 관측 시각 | `--observed-at 라벨=ISO8601` — 사용자가 선언한 값만 `operator_declared`로 기록 | 외부 입력 |
| OpenClaw 프로필 | 직접 조회에서만 `--profile`/`--dev`로 OpenClaw에 전달하고 범위 정보만 결과에 기록(미실행) | 외부 입력(직접 조회 한정) |
| 환경(`env-a` 등) 라벨·프로필 자동 판별 | 없음. 설정 파일에서 읽지 않음 | **미지원** |
| 출력 위치 | `linking` 결과의 `declaring_subject`, 직접 조회 결과의 `observation.scope` | — |

#### (4) Plugin·Skill 복수 설치본

| 확인 | 결과 | 구분 |
|---|---|---|
| 같은 `id`의 Plugin 두 설치본 | 항목 **2개로 별도 보존**(합치지 않음). 구분 근거는 `observed_from`·`root_dir`의 경로뿐이며 **경고가 없음**(`duplicate_id` 같은 이슈 코드 없음) | **가상 테스트**(`examples/plugin-sample` 복사본 2개) |
| 같은 이름의 Skill 두 설치본 | 항목 2개로 별도 보존, 경고 없음 | **가상 테스트**(P1 Skill 복사본) |
| 런타임 관측과의 연결 | `id`와 `rootDir`이 모두 맞을 때만 연결, 같은 `id`지만 경로가 다르면 `runtime_candidates_not_linked`(코드 확인, `plugin_skill_assets.py`) | 코드 확인 |
| 제약 | 경로는 스캐너 PC의 입력 경로이며 사본 위치에 따라 달라짐 — 설치 경로의 정규화·논리 경로 규칙은 팀 합의 전 | — |
| 실제 설치 Plugin·Skill | 저장 자료의 `plugins list`·`skills list`는 **텍스트 표**라 `--plugins-list-json`·`--skills-list-json`으로 읽을 수 없음. P2 Plugin은 `plugin inspect` JSON뿐인데 이 형식도 `--plugins-list-json`으로는 실패(종료 코드 3, `all_inputs_failed`) | 저장 자료 |
| Skill 파일 수집 | P1 Node Skill 2종, P2 Gateway workspace Skill 1종의 `SKILL.md`를 `--skills-dir`로 수집(종료 코드 0, complete). 경로는 입력 사본 경로이며 VM 설치 경로(`~/.openclaw/skills/...`)가 아님 | 저장 자료 |

#### (5) Permission / Authentication

| 확인 | 결과 |
|---|---|
| 원천 항목 구분 | 항목마다 `config_path`·`config_pointer`·`applies_to`·`doc_basis`를 가진 원천 항목으로 보존(`scope.aggregation: none`) |
| 저장 설정 사본 결과 | P0·P1·P2·S1~S4의 Gateway 설정: 항목 3개(`/tools/profile`="full", `/gateway/auth/mode`="token", `/gateway/auth/token`=`literal_withheld`). Node 설정: 선언 없음(`no_declared_items`). 모두 종료 코드 0 |
| allow/deny 선언 | **저장된 설정 사본에는 `tools.allow/deny` 등 허용·차단 선언이 없음.** 이 수집 경로는 가상 예제(`examples/permission-auth.json5`)와 테스트로만 검증됨 |
| MCP 서버 수준 선언 | `toolFilter.include/exclude`는 MCP 수집 결과(`declared`)에 있음 |
| 인증 참조 | 인증값은 종류(`literal_withheld`)만 기록하고 값·길이·해시는 저장하지 않음. 서버 인증 헤더는 환경변수 **이름**만(`INVENTORY_MCP_TOKEN`). 결과·로그 전체에서 `<DUMMY_TOKEN>`·`Bearer ` 문자열 검색 **0건** |
| 표현 한계 | 최종 실효 권한을 계산하지 않았습니다. "선언 없음"은 "정책 없음"이 아닙니다. 환경변수·`$include`·SecretRef는 해석하지 않았고, 인증 참조의 실제 존재·유효성은 확인하지 않았습니다 |

### 3.4 정답 목록(P2)과의 이름·서버 단위 대조 (저장 자료 분석)

`results/compare-with-groundtruth-P2.txt` 참조. 이름만으로 매핑하지 않고 서버별로 비교했습니다.

| 항목 | 정답 목록 | 스캐너 결과 |
|---|---|---|
| Tool | 40개(5개 서버) | 40개, 서버별 이름 집합 **모두 일치** |
| Resource(템플릿 포함) | 11개(템플릿 2) | resources 9 + templates 2 = 11 |
| Prompt | 5개 | 5개 |
| 능력 미선언 서버(`fs-workspace`·`asset-catalog` 등) | — | Resource·Prompt는 `not_performed/capability_not_declared`(0개가 아님) |

이는 같은 저장 자료를 양쪽이 쓴 것이므로 **스캐너 파싱의 정확성**을 보여 줄 뿐, 실제 서버 조회의 수집률이 아닙니다.

### 3.5 F1 수정: URL 원문 보존과 변경 기록 (2026-11-17)

**수정 내용** (`redaction.py`, `tools_catalog.py`, `resources_prompts.py`)
- `Redactor.sanitize_url`: 가릴 것(사용자정보·query 값·fragment·토큰 모양 경로)이 없으면 **원문을 그대로 반환**. 가림이 있어 재조립해야 할 때만 재조립하고, 그 과정에서 끝의 빈 `#`·`?`가 사라지면 사유 `url_empty_marker_dropped`를 기록. 기존 URL 인증정보 가림(`url_userinfo`·`url_query_values`·`url_fragment`·`url_path_token`)은 그대로.
- 새 `describe_alteration(원본, 결과 정의, redactions)`: 정의마다 `alteration = {altered, reasons[], difference_without_recorded_reason}`를 기록. `definition_altered`는 이 값의 `altered`(가림이 기록됐거나 원본과 실제 내용이 다름)이며, **내용이 달라졌는데 사유가 없으면** `difference_without_recorded_reason: true`로 드러남. Tool·Resource·ResourceTemplate·Prompt 모두 적용. 기존 필드 `redactions`·`definition_altered`는 유지(필드 추가만).
- 범위 안내문(`redaction_note`)에 URL 보존과 `alteration` 설명 추가.

**회귀 테스트** `tests/test_url_preservation.py`(15개): 수정 전 **7개 실패**(종료 코드 1: 끝 `#`·`?` 보존 3, Tool 정의 보존·altered 3, Resource·Prompt 1) → 수정 후 15개 통과(종료 코드 0). URL 인증정보·query·fragment 가림 유지와 가림 시 사유 기록도 포함. 가상 자료 테스트.

**전체 회귀**(파일 단위 순차, `output/url-fix-20261117/per-file-exitcodes.txt`): 24개 파일, pytest 종료 코드 모두 **0**, 기존 712개 + 신규 15개 = **727 통과 / 0 실패**. 안내문 수정이 실행 도중이어서 영향 파일 6개를 다시 실행해 모두 종료 코드 0(`rerun-after-note-edit.txt`).

**저장 자료 재분석 [저장 자료 분석 — 실제 환경 직접 검증 아님]** (`results/p2-definition-diff-after-fix.txt`): 같은 저장 광고 원본을 수정 후 코드로 다시 읽어 원본 정의와 JSON 단위로 비교.

| 구분 | 수정 전 | 수정 후 |
|---|---|---|
| Tool 40개 중 원본과 다른 정의 | 38개(`definition_altered`는 모두 false) | **0개**, `altered` 모두 false |
| Resource·Template·Prompt 16개 중 다른 정의 | 확인 안 함 | **0개** |
| 사유 없이 달라진 정의 | — | 0개 |

한계: 이 자료에는 비밀값이 든 URL이 없어 "실제 가림이 일어난 정의"의 기록은 **가상 테스트**로만 확인했습니다. 서버가 보낸 값이 아닌 저장 파일(테스트베드 도구가 수집)이 원본이라, 저장 파일 이전 단계의 변형은 알 수 없습니다.

### 3.6 Plugin manifest 사본 검증 (2026-11-17) — **GitHub 고정 커밋의 사본이며 VM 설치본 검증이 아님**

| 항목 | 내용 |
|---|---|
| 출처 | `origin/feature/testbed-threat-vm-capture` 커밋 `444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb`의 `testbed/plugins/agentscope-asset-catalog/openclaw.plugin.json`(blob `28ae0c7cfb`)·`package.json`(blob `18ff667498`). `develop`·`feature/testbed-profiles`의 같은 경로와 blob 동일. 이 두 파일만 `git show`로 가져옴(`index.js`·`mcp-server.mjs`는 가져오지 않았고 코드는 실행·import하지 않음). 해시: `output/plugin-manifest-20261117/source-pin.txt` |
| 분류 | **GitHub 사본 분석.** 실제 VM 설치본, 실제 OpenClaw 로딩 결과가 아님 |

**결과** (`output/plugin-manifest-20261117/results/`, 종료 코드 `exitcodes.txt`)

| 확인 | 결과 |
|---|---|
| `--plugin-manifest` 수집 | 종료 코드 0, `complete`, 등록 영역 `mcpServers`, 서버 1개(`mcpServers.asset-catalog`, `enabled` 미선언) |
| Plugin 수집(`plugin_skill_assets --plugin-dir`) | 종료 코드 0, `identity.id = agentscope-asset-catalog`, 패키지 `@agentscope/openclaw-asset-catalog` 0.1.0, `mcp_servers.records[0]`의 선언 위치 `mcpServers.asset-catalog` |
| 설정 선언과의 연결 | P2 Gateway 설정 사본(`plugins.entries.agentscope-asset-catalog.enabled: true`)을 함께 주면 `declared_activation.entry_declared/entry_enabled = true`(선언값이며 실제 로딩·활성이 아님) |
| 등록 키 ↔ 목록 결과 `linking` | P2 서버 **5개 모두 linked**(Gateway 2·Node 2·Plugin 1), unlinked 0. 이전에는 `asset-catalog`가 `registry_path_missing`로 unlinked였음. 종료 코드 1은 설정 수집 2건이 환경변수 참조로 `partial`(`config_scan_not_complete`)이기 때문 |
| 연결의 의미 | `linked`는 입력 자료 사이의 연결이며 서버가 기동·노출·호출 가능하다는 뜻이 아님. 선언 주체 종류는 `--subject pl=plugin`(사용자 입력)으로 기록 |

**GitHub 사본 ↔ 저장된 VM `plugin inspect` 출력(2026-10-04) 대조** (`manifest-vs-vm-inspect.txt`; VM 출력은 저장 자료이며 이것도 직접 관측이 아님)

| 필드 | 일치 |
|---|---|
| `id`, `name` | 일치 |
| `mcpServers.asset-catalog`(transport·command·args) | 일치 |
| 패키지 버전 0.1.0 | 일치 |
| `description` | **불일치**(GitHub: "Testbed P2 plugin that contributes … through the manifest mcpServers field." / VM 출력: "Contributes the asset-catalog MCP server (testbed P2).") |

불일치는 GitHub 사본이 VM에 설치된 시점 이후 갱신됐거나 설치본이 다른 소스에서 만들어졌음을 시사하지만 **원인은 확인하지 못했습니다.** 따라서 이 사본으로 "VM 설치본이 이 manifest와 같다"고 말할 수 없고, OVA 수령 후 설치된 파일의 해시와 비교해야 합니다([ova-verification-procedure.md](ova-verification-procedure.md) 단계 3-2). 설치 경로(`rootDir`·`install.installPath`)와 `origin: global`은 저장된 VM 출력에만 있고, 사본 분석 결과의 경로는 입력 사본 경로입니다.

### 3.7 OVA 구동 준비: 이 PC 점검 (읽기 전용)

VMware·VirtualBox·ovftool 모두 미설치, 메모리 총 7.9GB(여유 1.1GB), C: 여유 8GB, 펌웨어 가상화 활성. 사양서 요구(tb-gw RAM 6GB·디스크 150GB, tb-node RAM 4GB·디스크 80GB)에 못 미쳐 **이 PC에서 두 VM 구동은 부적합**합니다. 설치·설정 변경은 하지 않았습니다. 자세한 값과 대안은 [ova-verification-procedure.md 0절](ova-verification-procedure.md).

### 3.8 요구사항 대조·인증 전달·`$include`·필드 보완 (2026-11-17, 후속 작업)

| 항목 | 내용 |
|---|---|
| 대응표 | [requirements-implementation-matrix.md](requirements-implementation-matrix.md) — 기획서·공격표면·스키마·확인표를 고정 SHA와 성격(확정/협의안)별로 코드와 대조. 어댑터 전달 확인은 6절, `$include` 실행 허용 규칙은 7절 |
| 인증 전달 수정 | `live_discovery`: 같은 헤더를 `--bearer-env`/`--auth-header-env`로 명시 제공하면 설정의 `${VAR}` 선언을 대체. 수정 전 재현 8개 실패 → `tests/test_live_auth_override.py` 18개 통과(로컬 시험 서버, 가짜 토큰) |
| `$include` | 신규 `config_includes.py`(`--resolve-includes`): 문서화된 규칙·경계·깊이 10·2MB·64개·순환. 이후 공식 구현에 맞춰 보완(3.9절): 배열 연결·빈 배열 `{}`. `OPENCLAW_INCLUDE_ROOTS`만 미지원. `tests/test_config_includes.py` 20개 통과·1개 skip(심볼릭 링크 생성 권한 없음 — 경계 이탈 심볼릭 링크 거부는 이 PC에서 **미확인**) |
| `$include` 실패 시 실행 거부 | 선택 서버에 영향이 있으면 `include_unresolved`로 거부, 무관한 문제는 허용(수집은 partial). 수정 전 10개 실패 → `tests/test_live_include_refusal.py` 14개 통과 |
| Plugin 보완 | 진입점·의존성·설치 힌트·manifest `contracts`·`activation_keys`. `tests/test_plugin_origin_fields.py` 5개. 서명·무결성 **검증은 미구현**(선언 여부만) |
| MCP 선언 값 | `declared_extra`(타임아웃·병렬 힌트·`codex`). `tests/test_mcp_declared_extra.py` 5개. 기존 `declared`·`other_declared_keys` 계약 유지 |
| 업데이트 정책 | `permission_auth`의 `update_policy`. `tests/test_permission_update_policy.py` 2개 |
| 저장 자료 분석 | P2 Gateway 설정 사본으로 접속 없이 대상 생성: 옵션 없음 → `unresolved_reference`, `--bearer-env` → 허용(`output/requirements-20261117/results/p2-auth-target-build.txt`). 저장된 P2 설정에서 `update.checkOnStart=false`(Gateway·Node), `nodeHost.autoUpdate.enabled=false` 수집. **실제 서버 접속·실제 환경 검증 아님** |

**전체 회귀**(파일 단위 순차, 중복 실행 없음, `output/req-impl-20261117/per-file-exitcodes.txt`): 29개 파일 **모두 pytest 종료 코드 0**, 777 통과 · 0 실패 · 1 skip(`test_config_includes.py`, 심볼릭 링크 권한). 이 실행은 이후 추가한 `test_live_include_refusal.py`와 그 수정으로 바뀐 코드를 포함하지 않으므로, 수정 뒤 영향 파일을 다시 실행했습니다(`affected-rerun.txt`): `test_live_include_refusal` 14, `test_live_auth_override` 18(기대 코드 `unresolved_reference`→`include_unresolved`로 맞춘 뒤 재실행), `test_config_includes` 20+1 skip, `test_live_discovery` 60, `test_live_https` 32, `test_live_tools` 34, `test_linking` 83 — 모두 종료 코드 0. **한 번의 전체 실행으로 합산한 값이 아니라 파일별 실행의 합입니다.**

### 3.9 `$include` 공식 구현 대조·Plugin/Skill 연동·빈 배열 (2026-11-17~18)

| 항목 | 내용 |
|---|---|
| 근거 | `openclaw/openclaw` `eb377ac59e6c9fd6c7705028034812becf00271b`의 `src/config/includes.ts`·`src/infra/deep-merge.ts`·`includes.test.ts`(사본 `output/openclaw-includes-src/`). 공식 `deepMerge`는 `arrays: "concat"` |
| 보완 | 배열 **연결**(순서·중복 보존), 형제 키는 같은 병합(배열은 뒤에 연결), 객체 재귀 병합, 자료형 충돌은 뒤의 값, 금지 키 제거, 하드링크 거부, **배열 원소별 출처**. 정상 해석되는 배열은 partial·조회 거부 아님 |
| 빈 `$include: []` | 이전 최종 코드는 오류(`include_type_invalid`)로 거부했음 → 공식(`reduce(deepMerge, {})`)대로 `{}`. 수정 전 9개 실패 재현 → `test_config_includes_empty_array.py` 11개 통과 |
| Plugin·Skill 연동 | `plugin_skill_assets --config --resolve-includes`: 허용·차단·활성화 선언에 원본 파일·논리 키 경로 기록(배열은 원소별). 옵션 생략 시 기존 동작 |
| 유지한 거부 | 파일 누락·구문 오류·경로 이탈·순환·깊이·크기·하드링크는 계속 오류이며 선택한 서버에 영향이 있으면 조회 거부 |
| 전체 회귀(보완·연동 후) | 32개 파일 모두 종료 코드 0, **830 passed / 0 failed / 2 skipped**(`output/arrays-20261117/per-file-exitcodes.txt`) |
| 빈 배열 수정 후 | 영향 13개 파일 모두 종료 코드 0(`output/empty-array-20261118/affected-exitcodes.txt`). 전체 파일 재실행은 하지 않음 |
| skip 2건 | 심볼릭 링크 권한 없음, Windows 하드링크 — **해당 거부는 이 PC에서 미확인**(코드는 구현, OVA·권한 있는 환경에서 확인) |
| 저장 자료 vs 직접 검증 | 이 항목은 가상 설정·공식 소스 기준 테스트이며 실제 OpenClaw·VM의 `$include` 사례는 **미확인** |

### 3.10 Skill YAML·Permission 원천·Skill 출처·능력 스냅샷·client capabilities (2026-11-18) — **Windows 중단 당시의 과거 상태**

아래 표는 RAM 부족으로 중단됐을 때의 기록이다. 이후 업로드한 스냅샷을 Linux에서 검증하고 추가 결함을 수정했다. **현재 결과는 [2026-11-18 후속 검증](verification-20261118.md)**을 기준으로 하며, 이 표의 미실행 상태나 과거 통과 수와 합산하지 않는다.

| 항목 | 코드 | 회귀 테스트 | 마지막으로 확인된 실행 결과 |
|---|---|---|---|
| Skill YAML 부분집합 해석기(`skill_frontmatter.py`) | 구현 | `test_skill_frontmatter_yaml.py` 17개 | 수정 전 15개 실패 재현 → 17개 통과(개별 실행, 이후 코드 변경 없음) |
| sandbox·exec·네트워크 스위치·호스트 승인 문서(`--exec-approvals-file`) | 구현 | `test_permission_sandbox_exec.py` | 11개 통과(개별 실행). **이후 `tools.fs`·`browser.ssrfPolicy`·`cron.*` 선언과 테스트 4개를 추가했고 아직 실행하지 못함** |
| Skill 설치 명세·`.clawhub/origin.json` | 구현 | `test_skill_origin_and_install.py` | 7개 통과(개별 실행). **이후 `sha256_state` 분리와 테스트(약 16개)를 추가했고 아직 실행하지 못함** |
| 능력 스냅샷(`tools_catalog`) | 구현 | `test_capability_snapshot.py` | 5개 통과(개별 실행). **이후 `resources_prompts` 보존으로 계약을 바꿔 테스트를 수정했고 아직 실행하지 못함** |
| `resources_prompts` 서버 능력·정보 보존 | 구현 | `test_capability_snapshot.py`·`test_client_capabilities.py`·`test_resources_prompts.py`(기존 `FAKE-CAP` 테스트를 새 계약으로 수정) | **미실행** |
| client capabilities(직접 조회 실제 전송값·저장 캡처 제공값) | 구현(`_TapTransport` 쓰기 스트림 관찰) | `test_client_capabilities.py`(신규) | **미실행.** 직접 조회 시험은 로컬 시험 서버 프로세스를 띄우므로 메모리 여유가 필요 |
| Plugin `declared_provider_hints`·`git_head` | 구현 | `test_plugin_origin_fields.py` | **미실행**(이전 6개는 통과했으나 이후 테스트 2개 추가) |

**전체 회귀 현황**: 직전 전체 회귀(`output/gaps-20261118/per-file-exitcodes.txt`)는 시스템 메모리 부족으로 **중단**되어 9개 파일(모두 종료 코드 0)만 기록됐고, 이후 코드 변경 때문에 그 기록은 최종 코드의 결과가 아니다. 이번 코드 변경 후에는 메모리 여유가 부족해(점검 시 0.5~0.7GB) **테스트를 실행하지 않았다**. 이전·중간 코드의 통과 수를 최종 전체 통과로 합산하지 않는다. 메모리 여유가 확인되면 영향 파일부터 순차 실행하고 이 표를 실제 종료 코드와 통과 수로 갱신해야 한다.

## 4. 발견한 사항 (F1은 수정함, 나머지는 코드 변경 없음)

| # | 내용 | 영향 | 제안 |
|---|---|---|---|
| F1 | **수정함(2026-11-17, 2.4절 참조)**: Tool 정의의 `inputSchema.$schema` URL 끝 `#`이 출력에서 사라지는데 `definition_altered: false`였음(P2 도구 40개 중 38개가 원본과 다름). 원인: `redaction.py`의 `sanitize_url`이 비밀값이 없어도 `urlunsplit(urlsplit())`로 재조립해 빈 fragment·query 표식을 제거. QA P0 보고서의 "# 제거 28건"과 같은 현상으로 보임(QA 자료는 직접 대조하지 않음) | 정의 원문 보존·변경 추적 신뢰도 | 아래 2.4절 |
| F2 | `node_gateway_identity`의 라벨은 Gateway·Node를 통틀어 유일해야 함(같은 라벨 `P0`을 양쪽에 쓰면 `label_duplicate`) | 사용법 | 문서화 |
| F3 | `devices list --json`(페어링)·`nodes describe`·`mcp probe`·`plugin inspect`·`plugins/skills list`(텍스트)를 읽는 모듈이 없음 | `PAIRED_WITH`·Plugin 설치 경로 수집 불가 | 확인표에 "미지원"으로 기록 |
| F4 | Plugin·Skill 같은 `id`·이름의 복수 설치본에 경고가 없음 | 동명 구분 협의 필요 | 팀 협의 항목 |

## 5. 미확인 항목

- 실제 OpenClaw 설치 환경·테스트베드 VM에서의 직접 조회(설치 버전, 프로필, 실제 설정 위치, 실제 CLI 출력과 필드 일치).
- 같은 세션 반복 조회, 초기화·재설치·VM 복제·재페어링 후 `deviceId` 유지.
- OpenClaw `--profile` 사용 시 설정·상태 위치와 identity 차이.
- 실제 원격 HTTPS MCP 서버(`inventory-remote`)에 대한 `tools/list` 등 목록 조회(로컬 시험 서버로만 검증됨).
- VM에 **설치된** Plugin manifest에서의 `asset-catalog` 수집(GitHub 사본은 3.6절에서 검증했으나 VM 출력과 `description`이 다름).
- 허용·차단(allow/deny) 선언이 실제로 있는 설정 사본.
- `$include`·환경변수·SecretRef 해석.

## 6. 서진님께 요청할 수 있는 자료

실제 검증을 이어가려면 아래가 필요합니다. 비밀값은 제거한 사본이면 충분하고 원본·토큰·키는 요청하지 않습니다.

1. **접속 방법**: 테스트베드 VM에 스캐너를 실행할 수 있는 읽기 전용 접근(또는 스캐너가 있는 PC에서 쓸 수 있는 OpenClaw 설치 경로와 실행 파일) — VM 접속 계정·방법은 담당자가 정해 주세요. 스캐너는 허용 목록의 읽기 조회만 실행합니다.
2. **조회 대상 확정**: 사용할 OpenClaw 프로필(`--profile` 사용 여부), 설정·상태 위치(`OPENCLAW_CONFIG_PATH`/`OPENCLAW_STATE_DIR`), Gateway 접속 URL(`--expect-gateway-url`용).
3. **`--json` 출력 저장본**: `openclaw plugins list --json`, `openclaw skills list --json`(저장 자료는 텍스트 표라 읽을 수 없음), `openclaw devices list --json`.
4. **Plugin 원본**: `agentscope-asset-catalog`의 `openclaw.plugin.json`·`package.json`(비밀값 제거).
5. **allow/deny가 있는 설정 사본**: 허용·차단 선언 수집을 실제 자료로 확인하기 위한 것.
6. **복제·재설치·재페어링 전후 `identity` 출력**: 유지 여부 확인(테스트베드 담당 작업).

## 7. 산출물 위치

| 종류 | 위치 |
|---|---|
| 회귀 실행 종료 코드 | `asset-scanner/output/qa-repro-20261117/per-file-exitcodes.txt` |
| 저장 자료 분석 로그·결과 | `asset-scanner/output/testbed-stored-20261117/results/` (`exitcodes.txt`, `compare-with-groundtruth-P2.txt`, `identity-stability-check.txt` 등) |
| 입력 사본·변환 스크립트 | `asset-scanner/output/testbed-stored-20261117/inputs/`, `captures/`, `convert_advertised.py` (`output/`은 Git 제외) |
| 수정한 코드 | `tests/test_live_tools.py`, `tests/test_openclaw_direct.py`(QA 21건, 테스트만) · `asset_scanner/redaction.py`, `tools_catalog.py`, `resources_prompts.py`, 신규 `tests/test_url_preservation.py`(F1) |
| OVA 검증 절차(준비본) | [ova-verification-procedure.md](ova-verification-procedure.md) · 점검 기록 `output/host-check-20261117/host-check.txt` · manifest 사본 결과 `output/plugin-manifest-20261117/` |
| 확인표 답변 초안 | [asset-collection-checklist-scanner-reply-draft.md](asset-collection-checklist-scanner-reply-draft.md) |
