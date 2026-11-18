# QA 실행 결과

이 문서는 실행 시점의 QA 보고서다. 결함의 현재 상태·담당자·수정 이력은 GitHub Issue에서 관리하고, 여기에는 테스트 판정·측정 지표·잔여 위험과 Issue 링크를 기록한다. 실행마다 이 양식을 복사해 고유 실행 ID로 보관한다. Issue가 해결되어도 과거 실행 결과를 변경하지 않고 7절 또는 새 실행 보고서에 재검증 결과를 추가한다.

## 1. 실행 정보

| 항목 | 값 |
|---|---|
| 실행 ID | RUN-20261117-SAVED-01 + RUN-20261116-TC-MAPPING-01 (증적 종합) |
| 실행 일시 | 최신 후속 실행 2026-11-17 (KST); 과거 실행별 일시는 해당 보고서 참조 |
| 실행자 | Codex 실행·증적 대조 / 담당자 검토 전 |
| 대상 PR·Issue | TBD |
| 스캐너 commit | 0b2ff6bb2dd2f87e95550223008050e960cd07af |
| 대시보드 commit | cef7f2f251f7936e5fbf010e31178535b9d7b088 |
| 어댑터·탐지·토큰 commit | TBD (각각 기록) |
| 환경 ID·논리 프로필 ID·선택 snapshot_id | TBD |
| 문서 개정 / 데이터 계약 | 기존 실행 기준 v0.7.5 / 0.7.0-draft. 현재 후속 준비는 로컬 v0.7.7 참조 |
| 출력 스키마 버전 | 실제 연동 출력 0.6.0-draft / 최종 인수 준비 기준 0.7.0-draft |
| 분류 기준 | Gateway 포함 8종 확정 / 분류 PR #1, 계약 검토 PR #18 HEAD 9085e8deb4820b3c7582224f3e5dbac42e28a52d |
| ID 규칙·정답 생성기·변환기 버전/commit | TBD |
| full 정답 경로·차분 적용 규칙 | [GT-20261116-444f558](QA_GroundTruth.md), evidence/GT-20261116-444f558/full/ 구성별 JSON. 각 위협 차분을 P2에 독립 적용 |
| 실행 기준 시나리오 문서·ID·버전 | PR #7 4b0007f / S1~S5 v2.1 |
| Ground Truth 버전 | GT-20261116-444f558 (기존 실행 증적에 2026-11-16 후속 연결) |
| 기준 스냅샷 ID | TBD |
| 프로파일·위협 구성 ID | TBD |
| 정답 JSON 경로·commit | testbed/ground-truth/*.json @ 444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb. [고정 인덱스](evidence/GT-20261116-444f558/index.json) |
| 스키마 기준 문서·commit·합의 여부 | TBD ([공통 스키마](https://github.com/pbh0330/2026-Agent_Scope/blob/9085e8deb4820b3c7582224f3e5dbac42e28a52d/docs/schema-design-draft.md) 0.7.0-draft, 세부 계약 합의 확인) |
| 수집 범위·인증 맥락 | TBD (안전한 참조) |
| 환경 차이 | 없음 / 내용 기록 |

현재 준비 기준은 [로컬 스키마 v0.7.7](reference/schema-design-draft-v0.7.7.md)이며 원격 PR #18 `9085e8d`와 구분한다. 실제 검증한 InventorySnapshot은 0.6.0-draft이고 최신 UsageReport 구현은 0.7.0-draft다. 사용량 파일/API 연동 검증 완료를 뜻하지 않는다. 독립 검사 179개는 대시보드 cef7f2f 기준이며 후속 검토에서 확인한 ba926b5의 실행 결과로 재사용하지 않는다. S3 outputSchema·최상위 $schema 비교의 추가 회귀는 실행 전이다. 현재 10 Pass·3 Blocked·30 NOT_RUN은 유지한다.

## 2. 요약

2026-11-18 [제출 범위 결정](QA_제출범위_20261118.md)을 적용했다. 아래 43개 판정은 전체 원계획의 마지막 실행 현황이며 새 검증 결과가 아니다. 전체 0.7 스키마·정책 전환·페어링은 제출 선행 조건에서 유예했으나 기존 3 Blocked를 Pass로 바꾸지 않는다. 제출 완료 여부는 기준서의 필수 연동·탐지·화면·사용량·보안 확인과 잔여 위험으로 별도 평가한다.

| 구분 | 수량 |
|---|---:|
| 전체 계획 | 43 |
| 실행 완료 (Pass + Fail) | 10 |
| Pass | 10 |
| Fail | 0 |
| Blocked | 3 |
| N/A | 0 |
| NOT_RUN | 30 |

전체 계획 = Pass + Fail + Blocked + N/A + NOT_RUN이다. 아래 표는 2026-11-17 저장 자료 후속 실행을 반영한 현재 판정이다. NOT_RUN 중 부분 확인한 범위와 미실행 하위 조건은 각 행에 구분한다. Blocked와 N/A는 실행 완료 수에 포함하지 않는다.

**종합 판정:** 저장 자료 기반 10개 Pass, 3개 Blocked, 30개 최종 판정 미완료(NOT_RUN). 전체 인수 완료는 아니다. 최신 스캐너 자동 테스트 691개 통과·21개 실패는 별도 실행 결과로 유지한다.

**주요 잔여 위험:** 미확정 0.7 정책/스키마 계약과 페어링 증적, 화면·실제 재수집·사용량·반복/성능 검증이 남아 있다. TC와 자동 테스트의 집계는 분리한다.

### 2.1 로컬 사전 검증 결과

| 항목 | 기록 |
|---|---|
| 실행 ID·일자 | RUN-20261113-LOCAL-01 / 2026-11-13 (KST) |
| 환경·대상 | Windows PowerShell / Python 3.14.4 / 로컬 `.pr5-review/asset-scanner` 및 P0 검토 fixture |
| 스캐너 자동 테스트 | 232개 통과, 31.48초, 종료 코드 0 |
| P0 검토 fixture 검사 | 자산 17개·관계 16개의 ID·참조·소속·상태·집계 검사 통과, 종료 코드 0 |
| 상세 보고서 | [로컬 사전 검증 결과](reports/QA_로컬사전검증_20261113.md) |
| 자동 테스트 증적 | [공유용 JUnit XML](evidence/RUN-20261113-LOCAL-01/scanner-tests.public.xml) |

232개는 스캐너 자동 테스트의 수이며 위 43개 인수 QA와 집계 단위가 다르다. P0 검사는 검토 fixture에 대한 제한된 검사로 전체 JSON Schema 적합성이나 실제 수집 정확도를 보증하지 않는다. 실제 stdio 조회 테스트는 제외했다. 1절의 TBD 항목은 향후 인수 QA 실행 정보를 기록할 자리이며 이번 사전 검증의 실행 정보는 이 절과 상세 보고서에 기록한다.

## 3. 테스트 결과

### 2026-11-19 최종 준비 점검

원격 스캐너가 82c7579로 갱신돼 저장 입력 11개 구성을 재생성했다. P0의 과거 $schema URL 차이 28건은 이번 입력에서 재현되지 않았다. 대시보드 과장 문구의 2개 파일 최소 패치를 별도 검토 사본에 적용하고 빌드·새 생성 데이터 화면 37개 검사를 통과했다. 원격 대시보드 패치 반영은 아직 하지 않았다. 실제 VM 호출 자료는 미확보, 최신 Windows 영향 테스트는 실행 완료 결과를 얻지 못해 종합 판정을 변경하지 않는다. [최종 준비 보고서](reports/QA_최종준비점검_20261119.md)를 따른다.

### 2026-11-18 최신 스캐너부터 재생성

스캐너 ee9c1e0→대시보드 8f56930으로 저장 자료 11개 구성을 새로 생성했다. 종료 코드 0, 기대 조건 47개 PASS, 자체 계약 검사 오류 0건, 독립 대조 64개·새 데이터 화면 로딩/부정 입력 37개 통과다. 기존 공유 출력과 자산 키→ID 대응 및 관계 수가 유지됐다. [최신 스캐너 연동 보고서](reports/QA_최신스캐너연동_20261118.md)를 참조한다. VM 재수집·실제 호출 매핑·스캐너 전체 회귀 테스트는 별도이며 기존 인수 TC 종합 판정을 변경하지 않는다.

### 2026-11-18 사용량·화면 연결

대시보드 8f56930의 공유 P2(0.7.0-draft)를 토큰 6e4cf5c API에 연결했다. 원본 PC 기록은 16건 unmatched, 노출 이름을 바꾼 통제 입력은 2건 matched이며 파일/API 값이 일치했다. 실제 Vite 프록시·브라우저에서 전체 15,769토큰과 매핑 서버 3,920토큰·2회 호출을 확인했다. 11개 구성 3개 화면과 부정 입력 거부 등을 포함한 자동 검사 61개 통과·0개 실패, 자체 계약 검사 오류 0건·빌드 통과다. [상세 보고서](reports/QA_사용량화면연동_20261118.md)를 따른다. 실제 VM 호출·최신 스캐너 재생성·전체 UI/TC 조건을 완료한 것은 아니므로 기존 43개 종합 판정을 유지한다. 앞의 0.6 출력·미실행 설명은 과거 실행 범위이며 이번 0.7 출력 확인을 대체하지 않는다.

### 2026-11-17 저장 자료 후속 실행

고정 입력 11개 구성을 연속 3회 스캐너→어댑터→탐지로 생성했다. 시간 필드 제외 후 snapshot·detections가 모두 동일하고 독립 검사 179개 통과·0개 실패를 확인했다. 선택 경고 6행과 설정 사본 노출 차이 4행은 별도 관찰로 보존한다. QA-COL-03 및 QA-NFR-02를 저장 입력 범위의 Pass로 변경했다. [후속 보고서](reports/QA_저장자료후속검증_20261117.md)를 참조한다. VM 재수집·화면·사용량 API와 자동 테스트 실패 21개는 이번 실행 범위가 아니다.

### 2026-11-16 저장 자료 연동 검증

#### Ground Truth 후속 연결

[QA Ground Truth](QA_GroundTruth.md)에 원천 정답 수를 고정하고 [인덱스](evidence/GT-20261116-444f558/index.json)에 기존 출력·기대 검사 위치를 연결했다. 정상군 원천 자산/관계는 P0 17/16, P1 57/56, P2 67/67이며 가공 출력 20/18·61/60·73/73과 범위를 구분한다. 11개 구성의 원천 asset_key가 출력 canonical_key와 모두 일대일로 연결됐다. 자산별 asset_id와 기대 조건별 check_id·alert_id는 해당 인덱스와 같은 디렉터리의 links/<구성>.json을 참조한다.

원천 필수 경고 12행·선택 경고 6행·unknown 2행이 저장 비교 검사에 연결됐다. 기존 47개 PASS는 금지 경고와 정상 조건 등을 포함하는 별도 검사 수다. 이번 후속 검사는 전체 속성·관계 동등성, 추가 정책/인증 자산 정답 확정, 전체 0.7 계약 또는 VM 재수집을 수행하지 않았다. 기존 8 Pass·3 Blocked·32 NOT_RUN은 유지한다.

최신 대시보드 cef7f2f·시나리오 4b0007f 및 테스트베드 VM 수집 PR #24의 444f558을 사용해 스캐너→어댑터→탐지·비교 출력을 생성했다. 종료 코드 0, 11개 구성 생성 및 9개 구성의 기대 조건 47개 PASS를 확인했다. 11개 구성에서 ID 중복·없는 owner_ref가 없고 Gateway 참조가 실제 Gateway 자산을 가리킨다. [보고서](reports/QA_연동검증_20261116.md)를 참조한다. 화면·사용량 API·0.7 계약 전체는 미검증이며 기존 인수 TC와 별도 집계한다.

### 최신 스캐너 후속 검증

2026-11-13 `RUN-20261113-CURRENT-01`, PR #5 커밋 `0b2ff6b`에서 23개 테스트 파일을 순차 실행했다. 합계 **712개 중 691개 통과·21개 실패**이며, 단일 전체 실행 결과로 집계하지 않는다. 입력 보존 테스트의 디렉터리 읽기 오류 1건과 OpenClaw 모의 CLI 테스트 실패 20건을 확인했다. UTF-8 코드페이지 재실행에서도 모의 CLI 실패 수는 같았다. [최신 스캐너 보고서](reports/QA_최신스캐너검증_20261113.md)를 참조한다.

별도 [P0 저장 자료 검증](reports/QA_P0저장자료검증_20261113.md)에서 서버 1개·Tool 14개 및 선언값·MCP 버전을 확인했다. 스키마 URL 끝의 #가 변경 표시 없이 제거되는 차이 28건은 검토가 필요하다. 실제 팀 P0 접속·전체 연동은 미수행이며 아래 인수 판정과 분리한다.

### 개발 서버 stdio 후속 검증

2026-11-13 `RUN-20261113-STDIO-01`에서 기존에 제외했던 `tests/test_live_tools.py`를 실행하여 **27개 통과(47.65초, 종료 코드 0)**를 확인했다. 개발용 MCP 서버 실제 조회·페이지 처리·오류/시간 초과·비밀값 가림·프로세스 정리를 검증했다. [실행 보고서](reports/QA_stdio검증_20261113.md)와 [JUnit 증적](evidence/RUN-20261113-STDIO-01/scanner-stdio.public.xml)을 참조한다. 실제 팀 테스트베드 및 전체 인수 검증은 남아 있으며, 이후 2026-11-16 TC별 증적 대조 결과는 아래 판정표에 반영했다. 이전 232개와 이번 27개는 별도 실행으로 관리한다.

아래는 기존 43개 TC에 실제 증적을 연결한 현재 판정이다. 정적 저장 자료에서 완료한 항목은 Pass, 기준·원천이 없어 인수를 완료할 수 없는 항목은 Blocked다. 일부 확인한 항목은 NOT_RUN을 유지하되 미실행 하위 조건을 명시한다. [판정 범위와 근거](reports/QA_TC증적연결_20261116.md)를 함께 읽는다.

| 테스트 ID | 결과 | 실제 결과 요약 | 증적 ID·위치 | 결함 Issue 번호·URL | 실행자·일시 |
|---|---|---|---|---|---|
| QA-S1-01 | NOT_RUN | 부분 확인: S1 기대 10조건 통과. 신규 자산·등록 Plugin 관계·금지 결과의 TC별 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-S1-02 | Pass | P2 승인 기준 구성에서 자산 보존 및 S1 경고 0건 확인 | [대조표](reports/QA_TC증적연결_20261116.md) · [검사](evidence/RUN-20261116-TC-MAPPING-01/checks.json) | 미등록 | Codex / 2026-11-16 |
| QA-S2-01 | NOT_RUN | 부분 확인: S2 기대 6조건 통과. 위험 Tool 정의·추론 관계·금지 결과 확인 남음; P0 정의 변경 표시 차이 28건 별도 검토 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-S2-02 | Pass | P2 제한된 정상 구성의 Tool 수집 및 S2 경고 0건 확인 | [대조표](reports/QA_TC증적연결_20261116.md) · [검사](evidence/RUN-20261116-TC-MAPPING-01/checks.json) | 미등록 | Codex / 2026-11-16 |
| QA-S3-01 | Pass | S3 동명 read_text_file/catalog_search의 별도 ID·소유 Server·ADVERTISES 및 S3 경고 확인 | [대조표](reports/QA_TC증적연결_20261116.md) · [검사](evidence/RUN-20261116-TC-MAPPING-01/checks.json) | 미등록 | Codex / 2026-11-16 |
| QA-S3-02 | Pass | P2 정상 구성의 Tool 자산 보존 및 S3 경고 0건 확인 | [대조표](reports/QA_TC증적연결_20261116.md) · [검사](evidence/RUN-20261116-TC-MAPPING-01/checks.json) | 미등록 | Codex / 2026-11-16 |
| QA-S4-01 | NOT_RUN | 부분 확인: S4 기대 4조건 통과. 저장소 범위·공유 참조·비노출 및 미평가 scope/audience 구분 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-S4-02 | Pass | P2 정상 자격증명 참조 구성 보존 및 S4 경고 0건 확인 | [대조표](reports/QA_TC증적연결_20261116.md) · [검사](evidence/RUN-20261116-TC-MAPPING-01/checks.json) | 미등록 | Codex / 2026-11-16 |
| QA-S5-01 | NOT_RUN | 부분 확인: T1/T2 기대 9조건 통과. 대상 Server/Tool 연결·금지 표현의 TC별 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-S5-02 | Pass | P2 정상 연결 설정 보존 및 S5 경고 0건 확인; T3 생략은 unknown인 별도 증적 | [대조표](reports/QA_TC증적연결_20261116.md) · [검사](evidence/RUN-20261116-TC-MAPPING-01/checks.json) | 미등록 | Codex / 2026-11-16 |
| QA-COL-01 | NOT_RUN | 부분 확인: 유형 수집 모듈 통과. 8종 통합 입력·하위유형·내장 포함/제외 기준의 인수 검증 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-COL-02 | Pass | P1 Gateway/Node 양쪽 서버 선언과 tb-gw/tb-node 위치 보존 확인 | [대조표](reports/QA_TC증적연결_20261116.md) · [검사](evidence/RUN-20261116-TC-MAPPING-01/checks.json) | 미등록 | Codex / 2026-11-16 |
| QA-COL-03 | Pass | 고정 저장 입력 11개 구성 3회에서 ID 유지·중복 없음 및 동명 Tool 별도 ID·owner 확인. 실제 VM 재수집은 별도 | [후속 보고서](reports/QA_저장자료후속검증_20261117.md) · [검사](evidence/RUN-20261117-SAVED-01/checks.json) | 해당 없음 | Codex / 2026-11-17 |
| QA-COL-04 | NOT_RUN | 부분 확인: 누락값 추정 금지·필수 구조 오류 JUnit 통과. 공통 출력 연동 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-COL-05 | NOT_RUN | 부분 확인: 파싱 오류·서버별 격리 자동 테스트 통과. 정상/오류 파일 혼합 배치의 전체 결과 보존 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-COL-06 | NOT_RUN | 부분 확인: 실제 개발 서버 빈 tools/list·오류 구분 통과. 공통 collection/전체 scan 상태 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-COL-07 | NOT_RUN | 부분 확인: 실제 개발 서버 페이지 중간 실패·이전 Tool 보존 통과. 공통 작업/전체 scan partial 연동 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-COL-08 | NOT_RUN | 목록 실패 입력을 전후 snapshot과 diff/화면까지 연결하는 부정 입력 실행 필요 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-COL-09 | NOT_RUN | 부분 확인: resource/prompt 정상 빈 목록·미지원·실패 구분 JUnit 통과. 소비자 표시 경로 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-COL-10 | NOT_RUN | 부분 확인: P2 및 Plugin 선언 관련 증적 있음. 선언 주체와 실행 위치의 원천별 대조 필요 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-REL-01 | Pass | 11개 구성에서 Server 대상 DECLARES 방향·주체 및 ADVERTISES/owner 일치 확인. 다른 DECLARES 대상은 계약 검토 범위 | [대조표](reports/QA_TC증적연결_20261116.md) · [검사](evidence/RUN-20261116-TC-MAPPING-01/checks.json) | 미등록 | Codex / 2026-11-16 |
| QA-REL-02 | NOT_RUN | MAY 관계별 evidence/confidence 및 실제 행위 미확정 표현 대조 실행 필요 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-REL-03 | Blocked | 차단: 구현은 0.6 정책 표현 사용. 0.7 target_refs·하위유형·집계 계약 적용 기준 미확정; 정책 다중대상 인수 불가 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-REL-04 | Blocked | 차단: 현재 어댑터 출력은 PAIRED_WITH 미생성. 실제 페어링 목록의 정상/실패·재페어링 증적 및 판정 규칙 미확보 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-SCHEMA-01 | Blocked | 차단: 출력은 0.6.0-draft. 0.7.0-draft 전체 형식·필수값 검증 계약/검사기 미확보; Gateway/owner/중복 부분 검사는 통과 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-SCHEMA-02 | NOT_RUN | 버전 식별 증적은 있으나 0.6→0.7 변환 또는 명시적 비호환 거부 입력 실행 필요 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-SCHEMA-03 | NOT_RUN | 부분 확인: S5-T3 unknown 및 정적 null 있음. false의 대상·정책 참조와 전 상태 배열 검사 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-SCHEMA-04 | NOT_RUN | 중복/없는 참조/잘못된 TargetRef 주입 및 유효 partial 소비자 수용을 같은 경로로 실행 필요 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-SCHEMA-05 | NOT_RUN | 부분 확인: P0 canonical_key ID 매핑 및 중복·Gateway/owner 검사 있음. 정책·증적 참조·매핑 모호성 인수 확인 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-SEC-01 | NOT_RUN | 부분 확인: 최신 스캐너의 가짜 비밀값 결과·콘솔 비노출 통과. 화면·다운로드·ID/정답 경로 점검 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-SEC-02 | NOT_RUN | 부분 확인: 잘못된 자료형·처리 한도 관련 자동 테스트 있음. 합의 한도와 확장 필드·전체 오류 격리 대조 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-UI-01 | NOT_RUN | 데이터 생성은 완료. 브라우저에서 8종·관계·집계 표시 대조 미실행 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-UI-02 | NOT_RUN | 동명 Tool 데이터 분리는 확인. 화면의 Server/endpoint/권한 표시 미실행 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-UI-03 | NOT_RUN | 경고 근거 데이터는 생성. 화면 탐색·클릭 단계 측정 미실행 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-UI-04 | NOT_RUN | 선택값 누락 입력의 실제 화면 렌더링 미실행 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-NFR-01 | NOT_RUN | 서버 수 단계별 3회 측정·중앙값 기록 미실행 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-NFR-02 | Pass | 고정 저장 입력 11개 구성 연속 3회, 시간 필드 제외 snapshot·detections 동일. 실제 VM 재수집은 별도 | [후속 보고서](reports/QA_저장자료후속검증_20261117.md) · [검사](evidence/RUN-20261117-SAVED-01/checks.json) | 해당 없음 | Codex / 2026-11-17 |
| QA-INT-01 | NOT_RUN | 부분 확인: 저장 VM 자료→스캐너→어댑터/탐지 연결 완료. 실제 재수집·화면·추가 정책 범위별 최종 대조 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-INT-02 | NOT_RUN | 부분 확인: 필터·sslVerify 입력 및 두 MCP 버전 증적 있음. false/누락/manifest/보강값 우선순위 전체 대조 남음 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-USAGE-01 | NOT_RUN | 토큰 코드만 확보. 실제 어댑터 ID 기준 matched/ambiguous/unmatched 매핑 실행 필요 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-USAGE-02 | NOT_RUN | 환경·프로필·버전 불일치 입력 및 거부/변환 실행 필요 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-USAGE-03 | NOT_RUN | usage 파일·실행 API·화면의 동일 구간·전체 페이지 집계 비교 미실행 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |
| QA-USAGE-04 | NOT_RUN | 고정분 k·경계·null·음수·합계 보존 입력 실행 및 허용 오차 기준 기록 필요 | [대조표](reports/QA_TC증적연결_20261116.md) | 미등록 | Codex / 2026-11-16 |

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

이 파일은 43개 계획 항목의 현재 판정과 과거 실행 요약을 관리한다. 기존 37개에 INT 2개·USAGE 4개를 추가했으며 과거 실행 결과를 갱신한 것이 아니다. [로컬 사전 검증](reports/QA_로컬사전검증_20261113.md)의 232개 자동 테스트 통과는 전체 인수 TC 통과로 환산하지 않는다.

| 비교 범위 | 기준/버전 | 기대 수 | 실제 수 | 차이·근거·판정 |
|---|---|---|---|---|
| 원천 P0 자산 | 실제 인수 full 정답 commit TBD | TBD (검토 fixture 17과 구분) | TBD | TBD |
| 추가 정책/인증 자산 | 적용 정책·증적 TBD | TBD | TBD | TBD |
| 저장 관계 / 구현 관계 / 화면 보조 선 | 각각 구분 | TBD | TBD | TBD |
| ID matched / ambiguous / unmatched | 매핑기 버전 TBD | TBD | TBD | TBD |
| 탐지 required / optional / unknown / not_applicable | 규칙·정책 버전 TBD | TBD | TBD | TBD |
| 사용량 파일/API/화면 | 조회 구간·필터·페이지·배분 버전 TBD | TBD | TBD | TBD |

원천·변환 출력, 정책/정답, 수집 범위·인증 맥락, 화면 증적을 연결한다. 선택 경고의 분모·심각도 차이 판정은 합의 내용을 기록한다. 추가 정책 자산은 곧바로 오탐으로 세지 않으며 포함 범위와 근거를 먼저 검토한다.

