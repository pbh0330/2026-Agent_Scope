# QA Ground Truth

2026-11-16 기준 원천 정답과 기존 실행 증적을 연결한 기준서다. 정답 ID는 **GT-20261116-444f558**이며, 아래 정답 수는 테스트베드 commit `444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb`에 한정해 고정한다. 팀의 최종 0.7 계약 승인과는 별개다.

## 1. 기준 환경과 범위

| 항목 | 고정값·상태 |
|---|---|
| 원천 | [GitHub 고정 commit](https://github.com/pbh0330/2026-Agent_Scope/tree/444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb/testbed/ground-truth) |
| 작성·검토 | 원천: 테스트베드 담당 / QA 정리: Codex, 2026-11-16 / 담당자 최종 검토 대기 |
| 보관·집계 | [기준 인덱스](evidence/GT-20261116-444f558/index.json), 같은 디렉터리의 source·full·links |
| 정상군 | P0/P1/P2, SNAP-2-P0/P1/P2 |
| 위협군 | S1~S4: 담당자 VM 실측 SNAP-3-S1~S4. S1-T5·S5-T1/T2/T3: 설정 사본 정적 검증 |
| 적용 규칙 | 각 위협 파일을 P2에 독립 적용. 시나리오 간 누적 적용 금지 |
| 자산 범위 | 테스트베드 추가 자산. stock Plugin 63종·Skill 57종 제외 |
| 환경·프로필 | 출력 environment_id=agentscope-testbed, profile_id=tb-openclaw. 구성 ID=P0 등은 별도 |
| OpenClaw | 2026.9.6, 실제 설치 commit 미확인 |
| MCP | 기준 버전 2026-07-28 / P2 서버 5개 협상 버전 2025-11-25 |
| 연결 실행 | RUN-20261116-INTEGRATION-01, 저장 자료 기반·live_query=false |
| 출력 계약 | 실제 0.6.0-draft / 최종 인수 준비 0.7.0-draft, 문서 v0.7.5 |
| 구현 기준 | 스캐너 0b2ff6b·대시보드 cef7f2f·시나리오 4b0007f. [실행 정보](evidence/RUN-20261116-INTEGRATION-01/execution.json) 참조 |

동일 commit의 값만 이 정답으로 판정한다. 원천 변경 시 새 Ground Truth ID와 새 실행 보고서를 만들고 과거 증적을 보존한다. 제안 중인 ID 규칙을 확정값으로 사용하지 않는다.

## 2. 구성별 정답 수와 실행 연결

원천은 기대값, 출력은 기존 실행 관측값이다. 필수·선택·unknown은 원천 기대 조건 행 수다. 정상군의 0은 원천 expected_alerts가 없다는 뜻이며 정상 탐지 판정은 별도 기대 결과를 사용한다.

| 구성 | 원천 자산 | 원천 관계 | 필수 경고 | 선택 경고 | unknown | 관측 자산/관계 | 저장 비교 PASS | ID 매핑 증적 |
|---|---:|---:|---:|---:|---:|---|---:|---|
| P0 | 17 | 16 | 0 | 0 | 0 | 20/18 | expected 없음 | [17/17](evidence/GT-20261116-444f558/links/P0.json) |
| P1 | 57 | 56 | 0 | 0 | 0 | 61/60 | expected 없음 | [57/57](evidence/GT-20261116-444f558/links/P1.json) |
| P2 | 67 | 67 | 0 | 0 | 0 | 73/73 | 5 | [67/67](evidence/GT-20261116-444f558/links/P2.json) |
| S1 | 77 | 77 | 4 | 2 | 0 | 83/83 | 10 | [77/77](evidence/GT-20261116-444f558/links/S1.json) |
| S1-T5 | 67 | 67 | 1 | 0 | 0 | 73/73 | 5 | [67/67](evidence/GT-20261116-444f558/links/S1-T5.json) |
| S2 | 67 | 67 | 2 | 1 | 0 | 72/72 | 6 | [67/67](evidence/GT-20261116-444f558/links/S2.json) |
| S3 | 69 | 69 | 2 | 1 | 0 | 75/75 | 6 | [69/69](evidence/GT-20261116-444f558/links/S3.json) |
| S4 | 67 | 67 | 1 | 0 | 1 | 74/74 | 4 | [67/67](evidence/GT-20261116-444f558/links/S4.json) |
| S5-T1 | 67 | 67 | 1 | 2 | 0 | 73/73 | 7 | [67/67](evidence/GT-20261116-444f558/links/S5-T1.json) |
| S5-T2 | 67 | 67 | 1 | 0 | 0 | 73/73 | 2 | [67/67](evidence/GT-20261116-444f558/links/S5-T2.json) |
| S5-T3 | 67 | 67 | 0 | 0 | 1 | 73/73 | 2 | [67/67](evidence/GT-20261116-444f558/links/S5-T3.json) |

구성 간 동일 자산이 반복되므로 자산 수를 구성 간 합산해 환경 전체 자산 수로 사용하지 않는다. 관측 출력의 추가 정책·인증 자산은 원천 정답 수에 더하지 않는다.

### 정상군 유형별 내역

| 원천 유형 | P0 | P1 | P2 |
|---|---:|---:|---:|
| gateway | 1 | 1 | 1 |
| node | 1 | 1 | 1 |
| mcp_server | 1 | 3 | 5 |
| tool | 14 | 36 | 40 |
| resource (template 포함) | 0 | 10 | 11 |
| prompt | 0 | 4 | 5 |
| skill | 0 | 2 | 3 |
| plugin | 0 | 0 | 1 |
| permission_auth 독립 자산 | 원천 미작성 | 원천 미작성 | 원천 미작성 |

공통 계약의 resource_prompt와 하위 유형으로 변환한다. Permission/Auth가 원천 독립 자산에 없다는 이유로 실환경에 존재하지 않는다고 판정하지 않는다. 가공 출력의 추가 자산은 설정·정책 근거로 별도 인수한다. 숫자를 맞추기 위해 자산을 추가·삭제하지 않는다.

## 3. 기대 조건과 기존 TC

조건 식별 키는 **구성 + scenario_id + condition_id + target**이다. 필수 경고는 구성별 합계 **12행**, 선택 경고 **6행**, unknown **2행**이다. 모든 행이 저장된 expected.json의 조건에 연결되며 해당 저장 판정은 PASS다. 조건별 target·실제 asset_id·alert_id·check_id는 2절 links의 condition_links에서 확인한다.

| 구성 | 조건·대상 | 기대 결과 | 관련 TC |
|---|---|---|---|
| S1 | S1-C1 shadow-notes / node-helper | 각 high/high, 필수 2건 | QA-S1-01 |
| S1 | S1-C2 inventory-remote | endpoint 8443→9443, high/high | QA-S1-01 |
| S1 | S1-C3 notes-sync | 미승인 Plugin 등록, high/high. Plugin 자체 경고는 선택 | QA-S1-01 |
| S1-T5 | S1-C4 inventory-remote | Node 선언 위치 이상 medium/high. C1 미승인으로 오판 금지 | QA-S1-01 |
| S2 | S2-C2 fs-workspace | 홈 전체 범위 확대 medium/high | QA-S2-01 |
| S2 | S2-C1 demo-everything | get-env·gzip-file-as-resource 제외 해제 high/high | QA-S2-01 |
| S3 | S3-C1 inventory-remote/read_text_file | 동명·정의 차이 medium/high | QA-S3-01 |
| S3 | S3-C2 inventory-remote/catalog_search | 동명·정의 동일 low/medium | QA-S3-01 |
| S4 | S4-C1 fs-workspace | 같은 Gateway 저장소의 참조 공유 medium/high | QA-S4-01 |
| S4 | S4-C2 demo-everything | 다른 Node 저장소의 같은 이름은 unknown. 공유 경고 금지 | QA-S4-01, QA-SCHEMA-03 |
| S5-T1 | S5-C1 inventory-remote | HTTP 평문 high/high | QA-S5-01 |
| S5-T2 | S5-C2 inventory-remote | sslVerify=false 명시 high/high | QA-S5-01 |
| S5-T3 | S5-C3 inventory-remote | 생략은 unknown. C2 경고 금지 | QA-S5-02, QA-INT-02 |

표의 등급은 severity/confidence 기대값이다. S3-C2 정의 비교는 inputSchema draft-07 래퍼 정규화 규칙을 기록한다. 선택·동반 경고는 필수 검지율 분모에 넣지 않는다. expected_no_alert는 지정된 시나리오·대상 범위에 적용하며 전 시나리오 경고 금지로 확대하지 않는다.

기존 **47조건 PASS**는 정상·필수/선택 경고·금지 경고·unknown 등의 비교기 검사 수다. 필수 경고 12건이나 인수 TC 43개와 집계 단위가 다르다. 이 문서의 정답 고정으로 기존 TC의 미실행 조건을 통과 처리하지 않는다.

## 4. 전체 목록·ID·관계

- 전체 정답은 [P0 full](evidence/GT-20261116-444f558/full/P0.json), [P1 full](evidence/GT-20261116-444f558/full/P1.json), [P2 full](evidence/GT-20261116-444f558/full/P2.json) 및 같은 full 디렉터리의 위협 구성 JSON이다. 기존 가상 GT-A/GT-R 예시 표를 실제 정답 목록으로 대체했다.
- source는 원천 JSON, full은 차분을 펼친 원천 형식, links는 실행 대응표다. full이라는 이유로 0.7 공통 계약 변환이 끝난 것은 아니다.
- 차분 변경 전 값을 대조하고 after를 적용한 뒤 자산·관계의 명시 삭제·추가를 반영한다. null을 false로 바꾸지 않는다. S1-T5는 Server 교체와 6개 관계 재연결을 포함한다. 삭제 자산에 대한 관계 참조가 남으면 입력 불일치로 중단한다.
- 원천 asset_key와 출력 project.canonical_key를 대조해 후보 1개는 matched, 복수는 ambiguous, 없으면 unmatched로 기록한다. 이번 11개 구성은 원천 자산 모두 matched다. 전체 속성·관계 동등성 검증 완료를 의미하지 않는다.
- inventory-remote의 Gateway 선언·Node 실행을 구분한다. Plugin 서버의 원천 ASSOCIATED_WITH와 공통 소속·DECLARES 변환은 근거를 확인한다. 원천 PAIRED_WITH를 실제 출력에 근거 없이 보강하지 않는다.
- Tool 광고와 에이전트 노출은 별도다. P0 광고 14개·노출 2개, Plugin asset-catalog·notes-sync의 노출 null을 유지한다.

## 5. 실행결과 연결과 남은 인수 항목

[QA 실행결과](QA_실행결과.md)는 43개 TC 총괄, [연동 보고서](reports/QA_연동검증_20261116.md)는 저장 자료 실행, [TC 증적 연결](reports/QA_TC증적연결_20261116.md)은 항목별 판정 범위를 관리한다. 이번 원천·키·조건 연결은 기존 실행 증적에 대한 후속 검사이며 VM을 다시 실행한 기록이 아니다.

확정한 항목: 원천 commit, 구성별 자산·관계·기대 조건 수, 원천 키와 출력 ID 대응, 저장 기대 판정 연결.

저장 입력 11개 구성의 3회 재현성은 [11월 17일 후속 검증](reports/QA_저장자료후속검증_20261117.md)에서 확인했다. 원천 노출 true와 출력 null의 차이가 있는 설정 사본 4개 구성은 변경 서버를 재측정하지 않은 범위로 별도 기록했다.

남은 항목: 추가 정책/인증 자산의 근거·속성·적용 대상 인수, 전체 속성·관계 동등성, 최종 0.7 계약·공통 ID 규칙, 실제 VM 재수집과 그 반복 검증·화면/API. 선택 경고와 등급 차이의 최종 채점 규칙은 담당자 확인을 남긴다. 이 미완료 사항 때문에 이미 확인한 원천 정답 수를 TBD로 되돌리지 않는다.

현재 준비 기준은 [로컬 스키마 v0.7.7](reference/schema-design-draft-v0.7.7.md)의 16.1~16.2절이다. 데이터 계약은 `0.7.0-draft`이며 위 표의 v0.7.5는 기존 실행 기준이다. 현재 source/full/links/index는 고정 원천 형식과 실행 대응 자료이며 공통 GroundTruth·QAResult 계약으로 변환한 출력이 아니다. 공통 ground_truth_id/version, gt_asset_id, 별도 증적 namespace와 ID 매핑·metrics·limitations는 계약 합의 후 변환·검증한다. 문서 개정만으로 원천 파일·해시·정답 수를 변경하지 않는다.

## 6. 재생성과 변경 관리

2026-11-18 [제출 범위 결정](QA_제출범위_20261118.md)에 따라 현재 원천 형식·해시·ID 매핑을 유지한다. 공통 GroundTruth/QAResult 전환은 이번 제출의 선행 조건이 아니며 원천→출력의 누락·병합·참조·경고 검증은 계속 수행한다.

`python QA/reports/link_ground_truth.py`로 source·full·links·index를 재생성한다. 입력은 .parts-snapshots-20261116의 고정 원천 사본과 기존 실행 data다. 원천 summary, 변경 전 값, 키 중복·관계 참조를 검사하고 index에 원본 바이트의 SHA-256을 기록한다. GitHub 최신본을 자동 갱신하는 명령은 아니다. 고정 사본 교체 시에는 GitHub commit과 내용을 다시 확인한다.

| 버전 | 일자 | 변경 |
|---|---|---|
| GT-001 | 과거 준비본 | 예시·TBD 인수 양식 |
| GT-20261116-444f558 | 2026-11-16 | 원천 수 확정, 11개 full 정답·실제 출력 ID·저장 조건 연결 |

배경과 원천 세부 사항은 [Ground Truth 확인 정리](reports/QA_GroundTruth_확인정리_20261116.md)를 참조한다.

