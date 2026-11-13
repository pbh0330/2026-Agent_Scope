# QA 실행 결과

이 문서는 실행 시점의 QA 보고서다. 결함의 현재 상태·담당자·수정 이력은 GitHub Issue에서 관리하고, 여기에는 테스트 판정·측정 지표·잔여 위험과 Issue 링크를 기록한다. 실행마다 이 양식을 복사해 고유 실행 ID로 보관한다. Issue가 해결되어도 과거 실행 결과를 변경하지 않고 7절 또는 새 실행 보고서에 재검증 결과를 추가한다.

## 1. 실행 정보

| 항목 | 값 |
|---|---|
| 실행 ID | RUN-YYYYMMDD-01 |
| 실행 일시 | TBD |
| 실행자 | TBD |
| 대상 PR·Issue | TBD |
| 스캐너 commit | TBD |
| 대시보드 commit | TBD |
| 어댑터·탐지·토큰 commit | TBD (각각 기록) |
| 환경 ID·논리 프로필 ID·선택 snapshot_id | TBD |
| 문서 개정 / 데이터 계약 | v0.7.5 / 0.7.0-draft (실행 적용 여부 기록) |
| 출력 스키마 버전 | TBD (준비 기준 0.7.0-draft) |
| 분류 기준 | Gateway 포함 8종 확정 / 분류 PR #1, 계약 검토 PR #18 HEAD 9085e8deb4820b3c7582224f3e5dbac42e28a52d |
| ID 규칙·정답 생성기·변환기 버전/commit | TBD |
| full 정답 경로·차분 적용 규칙 | TBD |
| 실행 기준 시나리오 문서·ID·버전 | S1~S5 / 문서 버전 TBD |
| Ground Truth 버전 | GT-001 |
| 기준 스냅샷 ID | TBD |
| 프로파일·위협 구성 ID | TBD |
| 정답 JSON 경로·commit | TBD |
| 스키마 기준 문서·commit·합의 여부 | TBD ([공통 스키마](https://github.com/pbh0330/2026-Agent_Scope/blob/9085e8deb4820b3c7582224f3e5dbac42e28a52d/docs/schema-design-draft.md) 0.7.0-draft, 세부 계약 합의 확인) |
| 수집 범위·인증 맥락 | TBD (안전한 참조) |
| 환경 차이 | 없음 / 내용 기록 |

## 2. 요약

| 구분 | 수량 |
|---|---:|
| 전체 계획 | 43 |
| 실행 완료 (Pass + Fail) | 0 |
| Pass | 0 |
| Fail | 0 |
| Blocked | 0 |
| N/A | 0 |
| NOT_RUN | 43 |

전체 계획 = Pass + Fail + Blocked + N/A + NOT_RUN이다. 아래 표는 현재 계획한 43개 테스트의 초기 상태이며 실행별 대상이 달라지면 행과 집계를 함께 갱신한다. Blocked와 N/A는 실행 완료 수에 포함하지 않는다.

**종합 판정:** 로컬 사전 검증 통과. 계획된 인수 QA 43개는 NOT_RUN이며 전체 인수 판정은 미실시.

**주요 잔여 위험:** 실제 팀 테스트베드 수집, full 정답과 실제 출력의 ID 매핑, S1~S5 탐지, 대시보드·사용량 연동은 이번 로컬 사전 검증에서 확인하지 않았다.

### 2.1 로컬 사전 검증 결과

| 항목 | 기록 |
|---|---|
| 실행 ID·일자 | RUN-20261113-LOCAL-01 / 2026-11-13 (KST) |
| 환경·대상 | Windows PowerShell / Python 3.14.4 / 로컬 `.pr5-review/asset-scanner` 및 P0 검토 fixture |
| 스캐너 자동 테스트 | 232개 통과, 31.48초, 종료 코드 0 |
| P0 검토 fixture 검사 | 자산 17개·관계 16개의 ID·참조·소속·상태·집계 검사 통과, 종료 코드 0 |
| 상세 보고서 | [로컬 사전 검증 결과](QA_로컬사전검증_20261113.md) |
| 자동 테스트 증적 | [공유용 JUnit XML](evidence/RUN-20261113-LOCAL-01/scanner-tests.public.xml) |

232개는 스캐너 자동 테스트의 수이며 위 43개 인수 QA와 집계 단위가 다르다. P0 검사는 검토 fixture에 대한 제한된 검사로 전체 JSON Schema 적합성이나 실제 수집 정확도를 보증하지 않는다. 실제 stdio 조회 테스트는 제외했다. 1절의 TBD 항목은 향후 인수 QA 실행 정보를 기록할 자리이며 이번 사전 검증의 실행 정보는 이 절과 상세 보고서에 기록한다.

## 3. 테스트 결과

아래 QA-S1~QA-S5 행은 계획된 필수 검증 대상이다. 테스트 ID를 유지하고 실행한 시나리오 문서 버전과 기대 조건을 기록한다. 현재 결과는 미실행이며, 실행 시 기준이나 환경 미확정으로 검증할 수 없는 항목은 `Blocked`와 사유를 남긴다. 미실행·Blocked 항목을 완료로 처리하지 않는다.

| 테스트 ID | 결과 | 실제 결과 요약 | 증적 ID·위치 | 결함 Issue 번호·URL | 실행자·일시 |
|---|---|---|---|---|---|
| QA-S1-01 | NOT_RUN |  |  |  |  |
| QA-S1-02 | NOT_RUN |  |  |  |  |
| QA-S2-01 | NOT_RUN |  |  |  |  |
| QA-S2-02 | NOT_RUN |  |  |  |  |
| QA-S3-01 | NOT_RUN |  |  |  |  |
| QA-S3-02 | NOT_RUN |  |  |  |  |
| QA-S4-01 | NOT_RUN |  |  |  |  |
| QA-S4-02 | NOT_RUN |  |  |  |  |
| QA-S5-01 | NOT_RUN |  |  |  |  |
| QA-S5-02 | NOT_RUN |  |  |  |  |
| QA-COL-01 | NOT_RUN |  |  |  |  |
| QA-COL-02 | NOT_RUN |  |  |  |  |
| QA-COL-03 | NOT_RUN |  |  |  |  |
| QA-COL-04 | NOT_RUN |  |  |  |  |
| QA-COL-05 | NOT_RUN | 사전 증적: 가상 설정의 오류·부분 수집 자동 테스트 통과. 실제 팀 설정 인수 검증 필요 | [LOCAL-01](QA_로컬사전검증_20261113.md) |  |  |
| QA-COL-06 | NOT_RUN | 사전 증적: 가상 설정의 빈 목록·등록 영역 부재 구분 통과. 실제 목록 조회 검증 필요 | [LOCAL-01](QA_로컬사전검증_20261113.md) |  |  |
| QA-COL-07 | NOT_RUN |  |  |  |  |
| QA-COL-08 | NOT_RUN |  |  |  |  |
| QA-COL-09 | NOT_RUN |  |  |  |  |
| QA-COL-10 | NOT_RUN |  |  |  |  |
| QA-REL-01 | NOT_RUN | 사전 증적: P0 검토 fixture의 방향·유형·소속·참조 검사 통과. 실제 출력 검증 필요 | [LOCAL-01](QA_로컬사전검증_20261113.md) |  |  |
| QA-REL-02 | NOT_RUN |  |  |  |  |
| QA-REL-03 | NOT_RUN |  |  |  |  |
| QA-REL-04 | NOT_RUN |  |  |  |  |
| QA-SCHEMA-01 | NOT_RUN | 사전 증적: P0 검토 fixture의 핵심 필드·ID·참조 검사 통과. 전체 스키마·실제 출력 검증 필요 | [LOCAL-01](QA_로컬사전검증_20261113.md) |  |  |
| QA-SCHEMA-02 | NOT_RUN |  |  |  |  |
| QA-SCHEMA-03 | NOT_RUN |  |  |  |  |
| QA-SCHEMA-04 | NOT_RUN |  |  |  |  |
| QA-SCHEMA-05 | NOT_RUN |  |  |  |  |
| QA-SEC-01 | NOT_RUN | 사전 증적: 가짜 비밀값 비노출 자동 테스트 통과. 실제 연동·저장 증적·화면 검증 필요 | [LOCAL-01](QA_로컬사전검증_20261113.md) |  |  |
| QA-SEC-02 | NOT_RUN |  |  |  |  |
| QA-UI-01 | NOT_RUN |  |  |  |  |
| QA-UI-02 | NOT_RUN |  |  |  |  |
| QA-UI-03 | NOT_RUN |  |  |  |  |
| QA-UI-04 | NOT_RUN |  |  |  |  |
| QA-NFR-01 | NOT_RUN |  |  |  |  |
| QA-NFR-02 | NOT_RUN |  |  |  |  |
| QA-INT-01 | NOT_RUN |  |  |  |  |
| QA-INT-02 | NOT_RUN |  |  |  |  |
| QA-USAGE-01 | NOT_RUN |  |  |  |  |
| QA-USAGE-02 | NOT_RUN |  |  |  |  |
| QA-USAGE-03 | NOT_RUN |  |  |  |  |
| QA-USAGE-04 | NOT_RUN |  |  |  |  |

## 4. 정확도 측정

| 항목 | 정답 수 | 올바른 결과 | 누락 | 오탐 | 측정값 |
|---|---:|---:|---:|---:|---:|
| 전체 자산 | TBD | TBD | TBD | TBD | TBD |
| Gateway | TBD | TBD | TBD | TBD | TBD |
| Node | TBD | TBD | TBD | TBD | TBD |
| MCP Server | TBD | TBD | TBD | TBD | TBD |
| Tool | TBD | TBD | TBD | TBD | TBD |
| Resource/Template/Prompt | TBD | TBD | TBD | TBD | TBD |
| Skill | TBD | TBD | TBD | TBD | TBD |
| Plugin | TBD | TBD | TBD | TBD | TBD |
| Permission/Auth | TBD | TBD | TBD | TBD | TBD |
| 전체 관계 | TBD | TBD | TBD | TBD | TBD |
| 기대 경고 | TBD | TBD | TBD | TBD | TBD |

- 자산 수집 재현율: `TBD / TBD = TBD`
- 수집 자산 중 오탐 비율: `TBD / TBD = TBD`
- 관계 정확도: `TBD / TBD = TBD`
- 시나리오 기대 조건 충족률: `충족한 조건 수 / 실행한 합의된 조건 수 = TBD`
- Ground Truth 조건 ID별 기대/실제 결과, 판정 및 증적을 기록한다. 미실행·Blocked 조건은 분모에서 제외하고 별도 집계하며, 실행한 조건이 없으면 `N/A`로 기록한다.
- 정상 환경 오탐 수: `TBD`

분모가 0인 지표는 `N/A`로 기록한다. 부분 수집의 누락과 수집 실패 범위를 함께 기록하고 누락을 삭제로 단정하지 않는다.

| 계층 | 정답 자산 수 | 올바르게 수집한 자산 수 | 누락 | 수집 재현율 | 실패·미수집 범위 |
|---|---|---|---|---|---|
| declared | TBD | TBD | TBD | TBD | TBD |
| advertised | TBD | TBD | TBD | TBD | TBD |

전체 자산은 8종 고유 ID로 계층 간 중복을 제거해 집계한다. Gateway 그룹·Host/Client/Agent 문맥은 제외하고 Permission/Auth를 대상 수만큼 중복 계산하지 않는다. 관계 수에는 target_refs 보조 선을 포함하지 않는다.

| 유형 | 지원 여부 | 정상 0건/미지원/실패·부분 수집 | 범위 제외·미수집 사유 | 증적 |
|---|---|---|---|---|
| TBD (8종 각각 기록) | TBD | TBD | TBD | TBD |

QAResult 기계 출력의 PASS/FAIL/PARTIAL은 문서 실행 상태와 별도로 보존한다. PARTIAL을 Pass로 합치지 않고 미평가 범위와 limitations를 기록한다. 분모 0은 문서에서 N/A, 기계 출력에서 value=null과 사유로 기록한다.

| Ground Truth 조건 ID | TC ID | 기대 결과 | 실제 결과 | 판정 | 증적 ID·위치 | 결함 Issue |
|---|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | NOT_RUN | TBD | TBD |

조건별 Pass·Fail·Blocked·N/A·NOT_RUN 수를 별도 기록한다. 조건 충족률은 Pass / (Pass + Fail)로 계산하고 미실행·Blocked·N/A는 제외한다. 제외 건수도 함께 보고하며 충족률만으로 QA 완료를 판정하지 않는다.

## 5. 성능 측정

| Server 수 | 자산 수 | 1차 | 2차 | 3차 | 중앙값 | 실패 수 |
|---:|---:|---:|---:|---:|---:|---:|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## 6. 가시화 평가

S1~S5 각각에 대해 관련 자산·관계·경고 근거와 탐색 경로를 평가한다. 아래 확인 대상을 담당자와 합의한 세부 조건으로 구체화하고, 실제 평가 후 결과를 기록한다.

| 시나리오 | 시작 화면 | 확인 대상 | 탐색 단계 수 | 성공 여부 | 관찰 내용 |
|---|---|---|---:|---|---|
| S1 | TBD | Gateway/Node→Server→Tool 및 근거 | TBD | TBD | TBD |
| S2 | TBD | Server→Tool→권한·추론 근거 | TBD | TBD | TBD |
| S3 | TBD | 동명 Tool의 Server별 차이 | TBD | TBD | TBD |
| S4 | TBD | 공유 자격증명 참조 자산 | TBD | TBD | TBD |
| S5 | TBD | 위험 endpoint 영향 경로 | TBD | TBD | TBD |

## 7. 재검증 기록

| 결함 Issue 번호·URL | 수정 commit | 재검증 테스트 | 결과 | 증적 | 확인자·일시 |
|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD |

## 8. 승인

| 역할 | 이름 | 판정·의견 | 일자 |
|---|---|---|---|
| QA | TBD | TBD | TBD |
| 스캐너 담당 | TBD | TBD | TBD |
| 대시보드 담당 | TBD | TBD | TBD |
| 팀장 | TBD | TBD | TBD |

## 9. 첫 연동 증적과 범위별 판정

이 파일은 43개 계획 항목의 미실행 양식이다. 기존 37개에 INT 2개·USAGE 4개를 추가했으며 과거 실행 결과를 갱신한 것이 아니다. [로컬 사전 검증](QA_로컬사전검증_20261113.md)의 232개 자동 테스트 통과는 전체 인수 TC 통과로 환산하지 않는다.

| 비교 범위 | 기준/버전 | 기대 수 | 실제 수 | 차이·근거·판정 |
|---|---|---|---|---|
| 원천 P0 자산 | 실제 인수 full 정답 commit TBD | TBD (검토 fixture 17과 구분) | TBD | TBD |
| 추가 정책/인증 자산 | 적용 정책·증적 TBD | TBD | TBD | TBD |
| 저장 관계 / 구현 관계 / 화면 보조 선 | 각각 구분 | TBD | TBD | TBD |
| ID matched / ambiguous / unmatched | 매핑기 버전 TBD | TBD | TBD | TBD |
| 탐지 required / optional / unknown / not_applicable | 규칙·정책 버전 TBD | TBD | TBD | TBD |
| 사용량 파일/API/화면 | 조회 구간·필터·페이지·배분 버전 TBD | TBD | TBD | TBD |

원천·변환 출력, 정책/정답, 수집 범위·인증 맥락, 화면 증적을 연결한다. 선택 경고의 분모·심각도 차이 판정은 합의 내용을 기록한다. 추가 정책 자산은 곧바로 오탐으로 세지 않으며 포함 범위와 근거를 먼저 검토한다.
