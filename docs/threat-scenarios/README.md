# 위협 시나리오 (S1~S5)

AI 에이전트(OpenClaw + MCP) 환경에서 자산 스캐너·탐지 모듈·대시보드가 공통으로 쓰는 위협 시나리오 문서입니다.

- 버전: **v2.1** (2026-11-08, v2.0: 2026-10-06)
- 담당: 고혜림 (위협 시나리오·대시보드)
- 분석 방식: 정적 설정 분석. 실제 호출·공격 성공은 판정하지 않습니다.

## 시나리오

구현·검증 순서는 S1 → S2 → S4 → S3 → S5입니다. 위험 등급(P1~P3)은 v2.0과 같습니다.

| 순서 | ID | 시나리오 | 위험 등급 | 공격 표면 | 조건 | 상태 |
|---|---|---|---|---|---|---|
| 1 | [S1](scenario-s1.md) | 비인가 MCP Server 등록 및 노출 | P1 | A (관련 B) | S1-C1 ~ C4 | draft · 테스트베드 S1 구성 완료 |
| 2 | [S2](scenario-s2.md) | 악성 또는 과도한 권한의 도구 광고 | P2 | A, C | S2-C1 ~ C4 | draft · 구성 요청 |
| 3 | [S4](scenario-s4.md) | 과도한 자격증명 공유로 인한 피해 범위 확대 | P2 | C (관련 A, B) | S4-C1 ~ C4 | draft · 구성 요청 |
| 4 | [S3](scenario-s3.md) | Tool 이름 충돌을 이용한 호출 대상 위장 | P3 | A | S3-C1 ~ C3 | draft · 구성 요청 |
| 5 | [S5](scenario-s5.md) | 보안이 약한 연결을 통한 MCP Server 위장 가능성 | P3 | A (관련 C) | S5-C1 ~ C5 | draft · 구성 요청 |

공격 표면: A = MCP 통신 경계, B = Skill·Plugin 공급망, C = 권한·자격증명

각 시나리오 문서 끝의 **부록 A**에 v2.1 확정 사항(조건 ID, 판정 기준, 검증 케이스)이 있습니다. 본문과 다르면 부록 A가 우선합니다.

## 문서

| 파일 | 내용 | 주로 보는 사람 |
|---|---|---|
| [threat-scenario-spec.md](threat-scenario-spec.md) | 공통 작성·검증 규격 v2.1 | 전체 |
| [scenario-s1.md](scenario-s1.md) ~ [scenario-s5.md](scenario-s5.md) | 시나리오별 정상·위험 상태, 탐지 조건, 검증 | 전체 |
| [scenario-catalog.json](scenario-catalog.json) | 공통 스키마 0.7 13절 ScenarioDefinition 카탈로그 | 탐지 모듈, 대시보드 |
| [expected-results.md](expected-results.md) | S1~S5 기대 경고·비경고·판단 불가, QA 케이스 대응 | QA, 테스트베드 |
| [policies/expected-tool-policy.json](policies/expected-tool-policy.json) | S2 기준 정책 (서버별 허용 노출 도구·파일 범위) | 탐지 모듈 |

QA 문서(`QA/QA_테스트케이스.md`, `QA/QA_GroundTruth.md`)에서 위협 시나리오를 참고할 때는 이 폴더를 기준으로 합니다.

## v2.1에서 바뀐 것

1. **구현 우선순위** S1 → S2 → S4 → S3 → S5 확정 (정수 1~5, 위험 등급과 별도)
2. **조건 ID** `S<n>-C<m>` 도입, QA 케이스 `QA-S<n>-01`(위험)·`-02`(정상)와 대응. S5의 `S5-01`~`05`는 `S5-C1`~`C5`
3. **판정 기준 확정**
   - S1: 승인 Server가 다른 위치에서 선언 → 탐지 (medium). 미승인 Plugin을 통한 등록(출처 이상) 추가. 무결성 이상은 제외
   - S2: 읽기 전용 Tool만 노출돼도 접근 범위가 넓어지면 탐지 (medium)
   - S3: 이름과 정의가 모두 같아도 탐지 (confidence medium)
   - S4: 다른 저장소의 같은 참조 이름 → 판단 불가. 자격증명이 승인되지 않은 Endpoint로 전송 → 탐지 (S1 Case 2 동반)
   - S5: https인데 sslVerify 항목 없음 → 판단 불가
4. **기대 결과** 문서 추가. 테스트베드 정답 형식(P2 대비 변경분 + `expected_alerts`)을 쓰고, 공통 스키마 16.1절 `expected_evaluations` 변환 규칙을 적음
5. **관계 이름** v2.0 이름과 공통 스키마 0.7 이름 대응표 추가

## 연결된 작업

| 브랜치 / 폴더 | 관계 |
|---|---|
| `feature/testbed-threat-s1` → `testbed/profiles/S1`, `testbed/ground-truth/S1.json` | S1 위험 구성과 정답. 기대 결과 3절이 이 파일을 기준으로 함 |
| `testbed/ground-truth/approved-servers.json` | S1·S4-C3 기준 정책 |
| `docs/schema-design-draft.md` (develop) | 공통 스키마 0.7 — 13절 DetectionReport·ScenarioDefinition, 16절 GroundTruth·QAResult |
| `feature/dashboard` → `dashboard/` | S1~S5 평가 결과 표시 |

## 원칙

- 실제 비밀값은 수집·기록·표시하지 않습니다. 자격증명은 참조 이름과 저장 위치만 씁니다.
- 서버가 보낸 설명·스키마는 신뢰하지 않는 데이터로 다룹니다.
- 확인하지 못한 것은 `unknown`으로 남기고 정상으로 세지 않습니다.
