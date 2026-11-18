# 테스트베드 Ground Truth GitHub 확인 정리

- 확인일: 2026-11-16 (KST)
- 저장소: pbh0330/2026-Agent_Scope
- 최신 VM 수집 PR: [#24](https://github.com/pbh0330/2026-Agent_Scope/pull/24), 확인 당시 open·미병합
- 고정 기준 commit: `444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb`
- 확인 자료: [형식 README](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/README.md), P0/P1/P2 및 위협 구성 8개 JSON, [승인 목록](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/approved-servers.json), PR #24 본문·변경 내용.
- GitHub 원문을 직접 조회해 정리했다. 이번 작업에서 VM 재수집이나 스캐너·대시보드 재실행은 하지 않았다.

## 1. 무엇을 정답으로 기록했는가

테스트베드가 추가한 자산·관계와 위협 구성의 기대 판정을 기록한 비교 기준이다. 설정 선언(`declared`)과 MCP 서버가 광고한 목록(`advertised`)을 구분한다. 내장 Plugin 63종·Skill 57종은 제외하므로 전체 설치 자산 수로 해석하지 않는다.

P0/P1/P2는 전체 목록이다. S1~S5는 모두 P2를 기준으로 한 추가·변경·삭제 차분이며, 시나리오를 차례대로 누적 적용하는 형식이 아니다. `summary`는 차분 행 수가 아니라 적용 후 전체 집계다. 비교할 때 P2에 `added_assets`, `changed_assets`, `removed_assets`와 관계 추가·삭제를 적용해야 한다. 변경 속성의 `after:null`은 값 부재/미확인 의미를 보존하고 false로 바꾸지 않는다.

## 2. 구성별 정답 규모

아래 수치는 원문 JSON을 읽고 차분을 적용해 계산했다. 필수·선택은 `expected_alerts[].required`, unknown은 `expected_unknown`의 행 수다. 정상군의 0은 기대 경고 목록이 없다는 뜻이며 탐지 실행 결과가 아니다.

| 구성 | 전체 자산 | 전체 관계 | 필수 경고 | 선택·동반 경고 | unknown 조건 |
|---|---:|---:|---:|---:|---:|
| P0 | 17 | 16 | 0 | 0 | 0 |
| P1 | 57 | 56 | 0 | 0 | 0 |
| P2 | 67 | 67 | 0 | 0 | 0 |
| S1 | 77 | 77 | 4 | 2 | 0 |
| S1-T5 | 67 | 67 | 1 | 0 | 0 |
| S2 | 67 | 67 | 2 | 1 | 0 |
| S3 | 69 | 69 | 2 | 1 | 0 |
| S4 | 67 | 67 | 1 | 0 | 1 |
| S5-T1 | 67 | 67 | 1 | 2 | 0 |
| S5-T2 | 67 | 67 | 1 | 0 | 0 |
| S5-T3 | 67 | 67 | 0 | 0 | 1 |

| 자산 유형 | P0 | P1 | P2 |
|---|---:|---:|---:|
| Gateway | 1 | 1 | 1 |
| Node | 1 | 1 | 1 |
| MCP Server | 1 | 3 | 5 |
| Tool | 14 | 36 | 40 |
| Resource (Template 포함) | 0 | 10 | 11 |
| Prompt | 0 | 4 | 5 |
| Skill | 0 | 2 | 3 |
| Plugin | 0 | 0 | 1 |

원문: [P0](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/P0.json), [P1](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/P1.json), [P2](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/P2.json)。

- P0: fs-workspace 중심의 최소 구성. Tool 14개를 광고하지만 에이전트 노출은 read_text_file·list_directory 2개이며 나머지 12개는 필터로 차단된다.
- P1: fs-workspace·kg-memory·demo-everything, Node Skill 2개를 포함한다.
- P2: P1에 HTTPS inventory-remote, Plugin 등록 asset-catalog, Plugin 1개와 추가 Skill을 포함하는 위협 구성 기준선이다.
- inventory-remote는 Gateway에 선언되고 Node에서 실행된다. asset-catalog는 Plugin manifest 등록 서버다. 선언 주체와 실행 VM을 구분해야 한다.

## 3. 위협 구성과 기대 판정

| 구성 | P2 대비 핵심 변화 | 필수 기대 판정 |
|---|---|---|
| [S1](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/S1.json) | shadow-notes·node-helper·Plugin notes-sync 추가, inventory endpoint 8443→9443 | S1-C1 2건, S1-C2 1건, S1-C3 서버 1건 |
| [S1-T5](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/S1-T5.json) | inventory-remote 선언을 Gateway→Node로 이동, 관계 재연결 | S1-C4 선언 위치 이상. 이름은 승인되었으므로 미승인 서버로 판정하면 오답 |
| [S2](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/S2.json) | 파일 범위를 workspace→홈 전체로 확대, demo 도구 제외 필터 제거 | S2-C2 medium, S2-C1 high. get-env·gzip-file-as-resource 노출 false→true |
| [S3](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/S3.json) | inventory가 read_text_file·catalog_search를 추가 광고 | S3-C1 정의 차이 medium, S3-C2 정의 동일 low |
| [S4](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/S4.json) | 같은 Gateway .env 참조를 두 서버가 공유, Node에도 같은 참조 이름 사용 | S4-C1 medium. 저장소가 다른 Node 참조는 S4-C2 unknown |
| [S5-T1](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/S5-T1.json) | inventory HTTPS→HTTP | S5-C1 평문 전송 high |
| [S5-T2](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/S5-T2.json) | HTTPS에서 sslVerify=false 명시 | S5-C2 인증서 검증 비활성화 high |
| [S5-T3](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/S5-T3.json) | HTTPS에서 sslVerify 생략 | S5-C3 unknown. 생략을 false로 판정해 경고하면 실패 |

선택·동반 경고는 필수 정답 개수에 합산하지 않는다. S1의 Plugin 경고는 서버 경고에 묶어서 표현할 수 있다. `expected_no_alert`는 지정된 시나리오·조건 범위의 오탐 방지 기준이며 다른 모든 시나리오 경고를 금지하는 뜻은 아니다.

승인 목록은 서버 5개와 Plugin agentscope-asset-catalog를 정의한다. 서버 이름뿐 아니라 선언 VM·등록 주체·endpoint를 비교한다. 자격증명은 실제 값 대신 저장소·참조 이름·사용 위치로 비교한다.

## 4. 실측 범위와 남은 unknown

PR #24의 담당자 보고에 따르면 S1~S4는 2026-11-12 VM 구축·수집 완료이며 각 구성은 SNAP-2-P2에서 시작해 SNAP-3-S1~S4를 남겼다. GitHub 수집본 반영은 확인했으나 이번 작업에서 VM 상태를 직접 재현하지 않았다.

- S1: shadow-notes·node-helper 도구 4개 노출이 null→true로 갱신됐다. notes-sync 도구 2개는 Plugin 등록 서버가 probe 대상이 아니어서 null이다.
- S2: get-env·gzip-file-as-resource 노출 false→true가 차분에 추가됐다.
- S3: 추가 Tool 2개 노출이 true로 확인됐고 광고 예상본이 VM 수집본으로 교체됐다. catalog_search 정의 동일 비교는 inputSchema의 draft-07 래퍼 정규화를 전제로 한다.
- S4: 설정 기반 차분은 유지됐다. 다른 VM의 같은 참조 이름이 같은 비밀값이라는 근거는 없다.
- P2 asset-catalog 도구 노출도 probe 범위 밖이므로 광고 존재와 실제 에이전트 노출을 구분한다.
- S1-T5·S5-T1/T2/T3은 설정 사본을 통한 정적 검증이며 VM에 반영하지 않았다. 독립 결과 snapshot이 없다.

raw는 [ground-truth/raw](https://github.com/pbh0330/2026-Agent_Scope/blob/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth/raw)에 있으며 서버 advertised 목록, Gateway probe, Node describe, Plugin inspect, security audit 등이 근거다. raw/S2·S4에 모든 서버 광고 파일이 따로 있는 것은 아니며 생성기는 변경 없는 자료에 P2 raw를 재사용한다.

## 5. QA 연결 시 주의할 차이

1. **원천 정답과 가공 출력의 집계를 구분한다.** 이번 원천은 P0 17/16, P1 57/56, P2 67/67(자산/관계)이다. 기존 [11월 16일 연동 결과](QA_연동검증_20261116.md)는 P0 20/18, P1 61/60, P2 73/73으로 정책·인증 등 가공 자산이 포함된 다른 범위다. 숫자 차이만으로 누락·과수집을 판정하지 말고 ID·유형·범위 매핑으로 비교한다.
2. **공통 계약으로 명시적으로 변환한다.** 원천은 asset_key, resource/prompt 별도 유형을 쓰며 permission_auth 독립 자산은 없다. 공통 계약의 asset_id, resource_prompt 하위 유형, 정책·인증 자산은 변환·근거 연결이 필요하다. 원문에 schema_version·ground_truth_id/version 등 공통 full 정답 메타데이터가 없으므로 그대로 최종 0.7 계약 적합으로 처리하지 않는다.
3. **버전 의미를 구분한다.** environment는 OpenClaw 2026.9.6 / MCP 기준 2026-07-28을 기록하지만 P2 서버 5개의 실제 negotiated_protocol_version은 모두 2025-11-25다. 기준 버전과 협상 버전을 같다고 가정하지 않는다.
4. **관계 의미를 확인한다.** 원천은 PAIRED_WITH·DECLARES·ADVERTISES·ASSOCIATED_WITH를 사용한다. Plugin→Server가 ASSOCIATED_WITH인 부분은 공통 출력의 소속·관계 규칙에 맞춰 근거를 보존해 변환한다.
5. **unknown을 정상 통과나 실패로 합치지 않는다.** Plugin 도구 노출, 다른 저장소 자격증명 동일성, sslVerify 생략의 기본 동작은 각각 근거 범위에 맞게 유지한다.

## 6. 이번 문서 작업에서 수행한 확인

GitHub에서 조회한 11개 구성에 대해 메모리에서 차분을 적용했다. 모든 구성에서 자산 키 중복 0건, 관계 source/target의 존재하지 않는 자산 참조 0건이며 계산한 자산·관계 수와 각 summary가 일치했다. 이는 기본 구조 확인이며 전체 JSON Schema 적합성, 탐지 정확도 또는 실제 VM QA 통과를 뜻하지 않는다.

README의 필드표·완료일은 초기 설명에 머무르는 부분이 있다. 최신 시나리오 상태는 고정 commit의 각 JSON과 PR #24의 수집 범위를 함께 확인한다.

