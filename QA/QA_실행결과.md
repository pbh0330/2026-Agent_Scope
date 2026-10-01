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
| 출력 스키마 버전 | TBD |
| 실행 기준 시나리오 문서·ID·버전 | S1~S5 / 문서 버전 TBD |
| Ground Truth 버전 | GT-001 |
| 기준 스냅샷 ID | TBD |
| 프로파일·위협 구성 ID | TBD |
| 정답 JSON 경로·commit | TBD |
| 스키마 기준 문서·commit·합의 여부 | TBD (준비 기준 0.2.0-draft) |
| 수집 범위·인증 맥락 | TBD (안전한 참조) |
| 환경 차이 | 없음 / 내용 기록 |

## 2. 요약

| 구분 | 수량 |
|---|---:|
| 전체 계획 | 32 |
| 실행 완료 (Pass + Fail) | 0 |
| Pass | 0 |
| Fail | 0 |
| Blocked | 0 |
| N/A | 0 |
| NOT_RUN | 32 |

전체 계획 = Pass + Fail + Blocked + N/A + NOT_RUN이다. 아래 표는 현재 계획한 32개 테스트의 초기 상태이며 실행별 대상이 달라지면 행과 집계를 함께 갱신한다. Blocked와 N/A는 실행 완료 수에 포함하지 않는다.

**종합 판정:** TBD

**주요 잔여 위험:** TBD

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
| QA-COL-05 | NOT_RUN |  |  |  |  |
| QA-COL-06 | NOT_RUN |  |  |  |  |
| QA-COL-07 | NOT_RUN |  |  |  |  |
| QA-COL-08 | NOT_RUN |  |  |  |  |
| QA-REL-01 | NOT_RUN |  |  |  |  |
| QA-REL-02 | NOT_RUN |  |  |  |  |
| QA-SCHEMA-01 | NOT_RUN |  |  |  |  |
| QA-SCHEMA-02 | NOT_RUN |  |  |  |  |
| QA-SCHEMA-03 | NOT_RUN |  |  |  |  |
| QA-SCHEMA-04 | NOT_RUN |  |  |  |  |
| QA-SEC-01 | NOT_RUN |  |  |  |  |
| QA-SEC-02 | NOT_RUN |  |  |  |  |
| QA-UI-01 | NOT_RUN |  |  |  |  |
| QA-UI-02 | NOT_RUN |  |  |  |  |
| QA-UI-03 | NOT_RUN |  |  |  |  |
| QA-UI-04 | NOT_RUN |  |  |  |  |
| QA-NFR-01 | NOT_RUN |  |  |  |  |
| QA-NFR-02 | NOT_RUN |  |  |  |  |

## 4. 정확도 측정

| 항목 | 정답 수 | 올바른 결과 | 누락 | 오탐 | 측정값 |
|---|---:|---:|---:|---:|---:|
| 전체 자산 | TBD | TBD | TBD | TBD | TBD |
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

전체 자산은 계층 간 중복을 제거해 집계한다.

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
