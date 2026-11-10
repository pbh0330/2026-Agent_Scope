# P0 공통 스냅샷 검토 초안

이슈 #15 검토용 `P0.inventory.review.json`이다. 실제 스캐너 실행 결과·확정 GroundTruth·최종 ID 계약이 아니다. 스키마 0.7.0-draft의 전체 InventorySnapshot 구조를 검토하기 위한 별도 파일이며 기존 testbed/ground-truth/P0.json은 변경하지 않는다.

## 근거와 범위

- 원천 commit: `febb72e9ba0747a4b9d9fa714dbccca8cbc0c7d4` (PR #12 HEAD).
- [P0 정답](https://github.com/pbh0330/2026-Agent_Scope/blob/febb72e9ba0747a4b9d9fa714dbccca8cbc0c7d4/testbed/ground-truth/P0.json): Gateway 1, Node 1, MCP Server 1, Tool 14 및 관계 16을 변환.
- [서버 광고 원문](https://github.com/pbh0330/2026-Agent_Scope/blob/febb72e9ba0747a4b9d9fa714dbccca8cbc0c7d4/testbed/ground-truth/raw/P0/fs-workspace.advertised.json): Tool 14개의 공식 정의와 실제 협상 버전 2025-11-25를 보존.
- [Gateway 설정](https://github.com/pbh0330/2026-Agent_Scope/blob/febb72e9ba0747a4b9d9fa714dbccca8cbc0c7d4/testbed/profiles/P0/tb-gw.openclaw.json): fs-workspace 선언과 toolFilter를 사용. 필터를 Permission 자산 1개로 분리하는 **집계 제안**을 적용.
- 결과: 자산 18개(Gateway 1·Node 1·Server 1·Tool 14·Permission 1), 관계 16개(PAIRED_WITH 1·DECLARES 1·ADVERTISES 14).
- 권한 적용은 target_refs로 표현하므로 별도 관계 수를 임의로 늘리지 않는다.
- Resource/Template/Prompt·Skill·Plugin이 없다는 판정을 하지 않는다. 내장 Plugin/Skill과 인증 자산은 검증 범위 밖이다.

## 검토용 값과 제약

- 모든 `review-p0:` ID는 원천 asset_key에 기반한 임시 검토 ID다. #10의 해시 ID를 선결정하지 않는다. 환경·프로필·snapshot ID도 검토용이다.
- 모든 시각 2026-11-10T00:00:00Z는 **가상 fixture 메타데이터**다. 원천 관측·서버 조회 시각이 아니다. 실제 연동 시 수집 시작/종료·증적 관측 시각을 다시 확보해야 한다.
- evidence는 고정 commit의 저장소 자료를 참조한다. Gateway·Node와 페어링은 정답 문서의 간접 근거를 사용했으며 실제 identity·페어링 CLI를 재실행하지 않았다.
- Tool EXPOSED·호출 가능·사용 여부는 null로 남긴다. 정답의 exposed_to_agent를 검증된 대상별 판정으로 복사하지 않는다.
- 원천 정의는 미실행·미조회 데이터로 취급한다. 이 변환은 공식 규격 전체 검증·일반 비밀값 가림 구현이 아니다.
- scan.status=partial: 인증·내장 자산과 실제 스캐너 연동은 미수행이다. 정답 17개와 초안 18개의 차이는 필터 자산화 제안이며 누락/중복으로 바로 채점하지 않는다.
- ground_truth_review 및 permission_auth_and_builtin_assets는 **검토용 scope 제안**이다. 원본 MCP 인증 맥락은 알 수 없어 auth_context_ref=null과 사유를 남겼다.
- 현행 스캐너가 지원하는 MCP 2026-07-28과 원천 협상 2025-11-25의 차이는 해결되지 않았다. 이 파일 작성으로 스캐너의 버전 지원이 추가되지 않는다.

## #15에서 확인할 항목

1. Permission/Auth 집계 단위, 필터와 대상 참조 표현.
2. #10 최종 ID로 교체하고 선언 주체·Tool 소속·페어링 방향 검증.
3. 원천 프로토콜 버전 수용 및 증적·수집 scope·필수 메타데이터 합의.
4. 실제 스캐너 출력으로 교체한 후 대시보드·QA 동일 파일 인수.
5. 필드 자료형뿐 아니라 자산·관계·증적·수집 결과 참조와 예상 집계를 검증.

로컬 검증: `python docs/examples/p0/validate_review.py`. JSON 구문·핵심 필수 필드·ID 중복·소속/대상/증적/수집 참조·집계를 확인한다. 전체 JSON Schema 적합성이나 실제 수집 완료를 보증하지 않는다.
