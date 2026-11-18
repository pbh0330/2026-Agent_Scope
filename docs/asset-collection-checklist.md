# 자산별 수집 항목 확인표 — 스캐너·테스트베드 검토용

> 2026-10-28 PR #1 전체 댓글 재확인: [정리 및 반영 내역](https://github.com/pbh0330/2026-Agent_Scope/pull/1). 추가 확인 항목은 아래와 같습니다.
>
> Node의 `~/.openclaw/node.json`은 확정 수집 원천으로 사용하지 않습니다. `~/.openclaw/state/openclaw.sqlite` 저장이라는 테스트베드 담당의 정정 제보는 설치 버전별 실측 대기입니다. DB 직접 읽기보다 검증된 CLI/API의 안전한 필드 수집을 우선 검토합니다. 댓글의 명령·필드 오타를 실제 명령으로 복사하지 않습니다.
>
> Gateway→Node `PAIRED_WITH` 후보에 양끝 identity, 페어링 증적, 조회 시각·범위·완전성을 요청합니다. 현재 연결 여부와 분리하며 실패·부분 조회는 해제로 처리하지 않습니다. P2는 Gateway 선언과 Node VM 실행을 각각 입증합니다. Permission과 Authentication은 안전한 실제 출력 한 건씩, P0는 공통 snapshot과 full 정답 및 ID 대응을 요청합니다. 모두 확인 대기입니다.

> 작성일: 2026-10-28 · 수정일: 2026-11-03 · 상태: 스캐너 확인 대기 / 확정된 수집 명세 아님
> 8종 분류안과 ID 규칙 후보를 실제로 수집할 수 있는지 확인하기 위한 표입니다. 분류·식별 규칙을 확정하는 문서가 아닙니다.

## 담당자 작성 방법

PR #11의 `docs/asset-id-rules-proposal` 브랜치에서 이 문서의 3절 응답란과 4절 확인 사항을 수정해 주세요. 저장소 쓰기 권한이 있고 브랜치 제한이 없다면 같은 브랜치에 커밋하면 기존 PR에 반영됩니다. GitHub 웹에서 수정할 때도 커밋 대상 브랜치를 확인해 주세요. 직접 커밋할 수 없으면 PR 리뷰나 이슈 #10에 같은 항목으로 답변을 남겨 주세요.

- 스캐너 담당: 수집 가능 여부, 실제 명령·파일·필드, 비밀값을 제거한 근거, 제약, 확인자·확인일을 작성합니다. 아직 확인하지 않은 항목은 확인 대기로 유지합니다.
- 테스트베드 담당: 기존 관측과 추가 실측을 구분하고 환경·프로필·버전 및 근거를 기록합니다. 프로필·초기화·재설치·복제·재페어링 결과를 보완합니다.
- ID 후보 변경이 필요하면 확인표의 제약·대안을 먼저 기록하고 ID 규칙 문서의 해당 후보와 함께 검토합니다. 담당자별 관측 결과를 팀 공통 규칙 확정으로 처리하지 않습니다.

## 1. 작성 기준

- [ID 생성 규칙](asset-id-rules-proposal.md)의 식별 후보와 [8종 분류 협의안](https://github.com/pbh0330/2026-Agent_Scope/pull/1)을 기준으로 작성했습니다.
- MCP 원천 필드는 2026-07-28 공식 문서를 참고했습니다. 실제 서버의 구현 버전과 출력은 별도 확인해야 합니다.
- 아래 ‘기존 근거’는 앞서 확인한 [이슈 #10 코멘트](https://github.com/pbh0330/2026-Agent_Scope/issues/10#issuecomment-6012426423)의 보고 내용입니다. 이번 문서 작성 중 최신 댓글이나 PR #12 raw 출력을 재검증한 것은 아닙니다.
- **스캐너 수집 가능 여부는 모두 확인 대기**입니다. 테스트베드에서 값이 관측됐다는 사실과 스캐너에서 수집할 수 있다는 판단을 구분합니다.

## 2. 자산별 수집 항목

‘식별 후보’는 프로젝트에서 조합할 정보입니다. 부모·선언 주체 ID는 프로젝트가 생성하는 값이며 MCP 공식 응답 필드가 아닙니다. Resource/Template/Prompt와 Permission/Auth는 수집 항목이 달라 하위 유형별로 행을 나눴습니다.

| 자산 유형 | 원천·조회 후보 | 수집할 식별 후보 | 함께 확인할 속성·관계 | 기존 근거 및 남은 질문 |
| --- | --- | --- | --- | --- |
| Gateway | Gateway identity 출력. 정확한 명령·필드 경로 확인 필요 | `deviceId`; 환경·프로필 범위 포함 여부 미정 | 환경·프로필, 설정 출처, 선언 서버 | 댓글에서 반복 조회·P0/P1/P2 변경 시 identity 유지 보고. 프로필별 차이·초기화·재설치·복제 결과 확인 필요. `deviceId` 단독 식별은 제안 상태 |
| Node | Node identity 출력, Gateway `devices list` | Node `deviceId`; 환경·프로필 범위 포함 여부 미정 | 페어링 대상 Gateway, 실행 위치 | 댓글에서 `paired[].deviceId`와 일치 보고. 재페어링 전후 값 확인 필요. 재페어링 시 ID 유지 및 `PAIRED_WITH` 관계로 표현하는 안 검토 |
| MCP Server | Gateway·Node 원본 설정, Plugin manifest의 `mcpServers`; `mcp list`와 대조 | 선언 주체의 완전한 ID + 원본 설정 위치 + 서버 등록 키 | 선언 주체·실행 위치 구분, 연결 방식, 비밀값을 제외한 실행·접속 정보 | 댓글에서 플러그인 서버가 `mcp list`에 없고 manifest에만 존재한다고 보고. Plugin을 선언 주체로 연결 가능한지, 논리 경로와 include 원본 추적 가능 여부 확인 |
| Tool | 해당 서버의 `tools/list` → `tools[]` | MCP Server ID + 원래 `name` | `title`, `description`, `inputSchema`, 선택 `outputSchema`·`annotations` | 댓글에서 Gateway·Node 투영 이름이 다르다고 보고. 접두사가 붙기 전 원래 `name`을 스캐너가 확보할 수 있는지 확인 |
| Resource | `resources/list` → `resources[]` | MCP Server ID + 하위 유형 `resource` + `uri` | `name`, 선택 `title`·`description`·`mimeType` | 문서상 원천 필드 정리됨. 실제 지원·응답 예시와 URI 원문 보존 가능 여부 확인 |
| ResourceTemplate | `resources/templates/list` → `resourceTemplates[]` | MCP Server ID + 하위 유형 `resource_template` + `uriTemplate` | `name`, 선택 `title`·`description`·`mimeType` | 실제 지원·응답 예시 확인. 템플릿 문자열과 구체 Resource URI를 구분해 수집 가능한지 확인 |
| Prompt | `prompts/list` → `prompts[]` | MCP Server ID + 하위 유형 `prompt` + 원래 `name` | 선택 `title`·`description`·`arguments` | 실제 지원·응답 예시 확인. 표시 제목과 식별용 `name`을 구분 가능한지 확인 |
| Skill | 설치 위치·선언 정보·원천 메타데이터. 정확한 파일·명령 확인 필요 | 환경·프로필 범위 + 정규화한 설치 위치 + 원천 식별자 | 공급 출처, 표시 이름, 활성 여부, 섀도잉 정보 | 원천 식별자의 실제 필드 확인 필요. 동명 설치본, 섀도잉, 경로 이동 시 식별 방식 협의 필요 |
| Plugin | 설치 위치와 manifest. 정확한 파일·필드 경로 확인 필요 | 환경·프로필 범위 + 정규화한 설치 위치 + manifest ID | 공급 출처, 버전, 활성 여부, 선언 서버 | manifest ID 수집 가능 여부와 동명·동일 ID 복수 설치본 구분 확인. 서버 선언과 Plugin 연결 가능 여부 확인 |
| Permission | 원본 권한 정책 설정. 정확한 파일·키 경로 확인 필요 | 환경·프로필 범위 + 원본 설정 위치 + 설정 키 + 하위 유형 `permission` | 정책 내용 중 안전한 항목, 적용 대상 참조 | 독립 정책 한 건의 경계와 공통 정책·대상별 설정 구분 확인. 하나의 정책을 여러 대상 때문에 중복 생성하지 않도록 협의 |
| Authentication | 원본 인증 설정·참조. 정확한 파일·키 경로 확인 필요 | 환경·프로필 범위 + 원본 설정 위치 + 설정 키 + 하위 유형 `authentication` | 인증 방식, 안전한 참조 정보, 적용 대상 | 댓글에서 `openclaw mcp show`가 환경변수를 실제 값으로 풀어 출력한다고 보고하여 원천에서 제외 제안. 비밀값 없이 원본 참조를 수집할 경로 확인 |

원본 설정 위치는 **선언 주체 ID + 원천 종류 + 키 경로의 논리 경로로 식별하고 물리 경로는 속성으로 보관**하자는 댓글 제안이 있습니다. 기존 문서의 설치 위치 기반 후보와 적용 범위가 다르므로, Skill·Plugin까지 같은 원칙을 적용할지는 별도 확인합니다.

## 3. 스캐너 담당 응답란

- 확인자·확인일: 김규민 / 2026-11-18
- 구현 기준: [PR #5 ee9c1e0](https://github.com/pbh0330/2026-Agent_Scope/commit/ee9c1e02a660c23e1a445680df2905ae41be463b)
- 검증: Linux·Python 3.12.14 / 994 passed·0 failed·0 skipped / pytest 종료 코드 0
- 입력 조건: 직접 작성한 가상 설정·목록 응답·Skill/Plugin·서비스 파일, 가짜 OpenClaw CLI, 개발용 MCP 서버
- 실환경 미검증: 실제 OpenClaw·OVA·외부 업무 서버·최신 Windows 전체 실행
- 판정 기준: 명시한 원천 필드의 수집 가능 여부. 공통 ID 미정과 실환경 미검증은 별도 구분
- 근거: [최신 원천·필드·가상 출력 발췌](https://github.com/pbh0330/2026-Agent_Scope/blob/ee9c1e02a660c23e1a445680df2905ae41be463b/asset-scanner/docs/source-collection-closure-20261118.md), [기존 가상 입력·스캐너 출력](https://github.com/pbh0330/2026-Agent_Scope/blob/ee9c1e02a660c23e1a445680df2905ae41be463b/asset-scanner/docs/virtual-samples-and-outputs.md)

**994개 테스트 구성**

- 44개 파일의 조건별 사례 수. 동일 기능의 정상·누락·자료형 오류·실패 조건 포함
- 설정·등록 정보: 92개
- include 병합·출처·읽기 경계: 95개
- 저장 MCP 목록·버전·능력: 135개
- MCP 통신·TLS·인증·한도: 185개
- Plugin·Skill 파일·설치 기록: 94개
- Gateway·Node·가짜 OpenClaw CLI 조회 처리: 94개
- Permission/Auth·서비스 계정 선언: 58개
- 서버 선언–Tool 목록 연결: 83개
- 가림·출력·기존 결함 회귀: 158개
- 분류 방식: 파일의 주된 목적 기준, 중복 집계 없음
- 통신 조건: 실제 stdio·루프백 HTTP/HTTPS 통신, 임시 CA·가짜 인증값 사용
- 목록 확인: `pytest --collect-only`로 구성 확인. 통과 수는 앞선 단일 전체 실행 결과

**자산별 수집 상태 — 아래 예시는 가상 입력의 출력**

- **Gateway — 가능(지정 identity 원천)**
  - 원천·필드: 저장/직접 조회 identity → `identities[].device_id.original_value`, `public_key`, `origin`, `observation`
  - 제약: 환경·프로필 공통 ID는 합의 대기; 초기화·복제 후 identity 유지 실측 대기
- **Node — 가능(identity·devices 원천)**
  - 원천·필드: `node identity --json`, `devices list --json` → `device_id`, `client.clientId/clientMode`, `reported_pairing_state`, `source_pointer`
  - 예시·제약: `clientId: node-host`는 종류 라벨. paired 기록과 connected는 별도. 공통 `PAIRED_WITH` 자동 생성·SQLite 자동 탐색 미지원
- **MCP Server — 가능(지원 등록 영역의 선언)**
  - 원천·필드: `mcp.servers`, `nodeHost.mcp.servers`, manifest `mcpServers` → `registration_key`, `declared`, `declaration_path/pointer`
  - 예시·제약: `registration_key: s`, `declaration_path: mcp.servers.s`. 실행 위치·성공·노출은 선언만으로 판정하지 않음
- **Tool — 가능(목록 정의)**
  - 원천·필드: `tools/list` → `definition.name/title/description/inputSchema/outputSchema/annotations`, `server_ref`
  - 예시·제약: `name: read_demo`. 선택 필드 미제공 시 생성 안 함; 목록 존재를 노출·호출 가능으로 간주하지 않음
- **Resource — 가능(목록 정의)**
  - 원천·필드: `resources/list` → `definition.uri/name/title/description/mimeType/size/annotations`
  - 예시·제약: `uri: file:///srv/sample-docs/readme.md`. `resources/read` 미실행
- **ResourceTemplate — 가능(목록 정의)**
  - 원천·필드: `resources/templates/list` → `definition.uriTemplate/name/title/description/mimeType`
  - 예시·제약: `uriTemplate: file:///srv/sample-docs/{path}`. 구체 URI와 별도 보존; 템플릿 확장 미실행
- **Prompt — 가능(목록 정의)**
  - 원천·필드: `prompts/list` → `definition.name/title/description/arguments`
  - 예시·제약: `name: summarize_doc`. `prompts/get` 미실행
- **Skill — 일부 가능**
  - 원천·필드: 지정 `SKILL.md`·설정·JSON 목록 → `identity.name.original_value`, `observed_from.skill_file`, `config_key`, `frontmatter`, `metadata_openclaw`, `install_origin`
  - 예시·제약: `name: demo`. YAML 부분집합; 전체 설치 자동 탐색·설치본 인덱스·경로 이동 후 동일성·섀도잉 계산 미지원
- **Plugin — 일부 가능**
  - 원천·필드: 지정 manifest/package·JSON 목록·저장 inspect → `identity.id`, `root_dir`, `mcp_servers`, `plugin_inspect_outputs[].install`
  - 예시·제약: `source: npm`, `version: 1.2.3`. id+rootDir 일치 시 설치본 연결. SQLite 자동 탐색·무결성 검증 미지원; 설치 시각을 last_updated로 대체하지 않음
- **Permission — 일부 가능(지원 정책 원천)**
  - 원천·필드: 설정·지정 승인 문서 → `category`, `config_path/pointer`, `applies_to`, `value_kind/value`; 지정 systemd → `units[].declarations`
  - 예시·제약: `tools.allow: [read]`, `tools.deny: [browser]`. 지원 경로의 허용·차단 모두 보존. 모든 채널 정책 미지원; 서비스 선언을 실제 UID/GID로 간주하지 않음
- **Authentication — 일부 가능(종류·참조)**
  - 원천·필드: 지원 인증 설정·서버 선언 → `credential.kind/ref/ref_names`, `credentials`
  - 예시·제약: `kind: literal_withheld`. 자격증명 원문·그 해시 비저장. OAuth issuer/audience/expiry 자동 수집 미구현; 원천·접근 범위 확인 필요

**요청된 식별 원천의 연결 기준**

- 선언–목록 연결: `config_scan_ref + registry_path + registration_key` 일치 시 연결; 이름만 같은 항목은 병합 안 함
- 선언 주체·경로: `trace.declaring_subject`, `logical_location`, `physical_source_path` 별도 보존; 물리 경로를 ID로 사용 안 함
- 주체 입력: `--subject` 사용자 입력과 `--observed-identity` 관측값 분리; 충돌 기록
- include: `--resolve-includes` 사용 시 원본 파일·사슬·필드/원소별 출처 보존; 추가 허용 경계 지원
- 환경·프로필: 직접 조회의 `--profile/--dev`, `--config-path`, `--state-dir`, `--openclaw-home` 지원. 모든 결과의 공통 환경/프로필 ID 필드는 미정
- 복수 설치: 같은 이름/ID·다른 디렉터리는 별도 보존. Plugin은 id+rootDir, Skill은 파일 경로로 관측 연결; 영속 ID·섀도잉 규칙은 미확정
- Permission/Auth 경계: 원천 키 경로 또는 명시한 목록 원소 단위. allow/deny 배열은 각각 보존하고 대상마다 복제 안 함; 공통 정책 묶음 경계는 협의 대기

## 4. 공통 확인 사항

| 확인 항목 | 요청 내용 | 담당·상태 |
| --- | --- | --- |
| 반복 수집 | 같은 원천의 식별 후보 값이 반복 조회에서 동일한지 전후 출력 제공 | 스캐너·테스트베드 / 확인 대기 |
| 프로필·초기화·복제 | Gateway·Node의 프로필 차이, state 초기화·재설치, VM 복제 시 `deviceId` 변화·중복 기록 | 테스트베드 / 기존 댓글에서 미확인 |
| 설정 출처 | 설정 병합·include·Plugin 등록 뒤에도 선언 주체와 원본 키 경로를 복원할 수 있는지 확인 | 스캐너 / 확인 대기 |
| 목록 완전성 | 페이지 끝까지 수집했는지와 조회 범위·인증 맥락을 기록. 정상 0건·미지원·실패·부분 수집 구분 | 스캐너 / 확인 대기 |
| 이름·URI 보존 | 원래 이름·URI·템플릿 문자열을 보존하고 표시명·투영 이름과 구분 | 스캐너 / 확인 대기 |
| 비밀값 제외 | 원본 비밀값 및 그 해시를 식별 입력·공유 출력에 포함하지 않고 안전한 참조만 수집 | 스캐너·테스트베드 / 확인 대기 |
| 필수 식별값 누락 | 빈 문자열이나 공통 `unknown`으로 정상 ID를 만들지 않고 식별 미완료로 기록하는 안 검토 | 스캐너·QA / 협의 대기 |
| ID 공통 구현 | 식별 범위·직렬화·정규화·해시 길이·버전 합의 후 스캐너와 Ground Truth의 공통 함수·테스트 벡터 적용 가능 여부 확인 | 스캐너·테스트베드·QA / 협의 대기 |

수집 가능 여부가 확인되면 이슈 #10에 유형별 결과와 미결정 항목을 정리합니다. 이 표를 채우는 것만으로 ID 규칙 채택이나 이슈 종료를 확정하지 않습니다.

**스캐너 공통 확인 응답 — 김규민 / 2026-11-18**

- 반복·프로필·초기화·복제: 가상 원천 테스트와 실제 환경 반복/재설치/재페어링 실측 분리; 후자는 대기
- 출처: 등록 영역·등록키·논리/물리 경로·include 출처 보존. 공통 선언 주체 ID는 미생성
- 완전성: 정상 빈 목록·partial·failed·unsupported·not_performed 구분; 페이지·커서·한도·제외 사유 기록
- 이름·URI: 원래 name/uri/uriTemplate과 title 구분; 가림·변경된 값을 원본 동일성 입력으로 사용 안 함
- 비밀값: 지원 원천의 종류·안전한 참조만 보존. 가짜 인증값 비노출 검증; 실제 인증 유효성은 미판정
- 필수 값 누락: missing/not_collected/withheld_by_redaction 보존; 빈 문자열·공통 unknown으로 정상 ID 발급 안 함
- ID 공통 구현: 미구현. 범위·정규화·직렬화·해시·원천 중복·정책 경계 합의 후 공통 함수·테스트 벡터 연동
- 이번 응답의 의미: 현재 수집 범위와 제약 공유. ID 규칙 확정·Issue #10 종료·PR 병합은 포함하지 않음
