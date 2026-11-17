# P0 공통 스냅샷 검토 초안

이슈 #15 검토용 `P0.inventory.review.json`이다. 실제 스캐너 실행 결과·확정 GroundTruth·최종 ID 계약이 아니다. 스키마 0.7.0-draft의 전체 InventorySnapshot 구조를 검토하기 위한 별도 파일이며 기존 testbed/ground-truth/P0.json은 변경하지 않는다.

## 근거와 범위

- 원천 commit: `febb72e9ba0747a4b9d9fa714dbccca8cbc0c7d4` (PR #12 HEAD).
- [P0 정답](https://github.com/pbh0330/2026-Agent_Scope/blob/febb72e9ba0747a4b9d9fa714dbccca8cbc0c7d4/testbed/ground-truth/P0.json): Gateway 1, Node 1, MCP Server 1, Tool 14 및 관계 16을 변환.
- [서버 광고 원문](https://github.com/pbh0330/2026-Agent_Scope/blob/febb72e9ba0747a4b9d9fa714dbccca8cbc0c7d4/testbed/ground-truth/raw/P0/fs-workspace.advertised.json): Tool 14개의 공식 정의와 실제 협상 버전 2025-11-25를 보존.
- [Gateway 설정](https://github.com/pbh0330/2026-Agent_Scope/blob/febb72e9ba0747a4b9d9fa714dbccca8cbc0c7d4/testbed/profiles/P0/tb-gw.openclaw.json): fs-workspace 선언과 toolFilter를 기존 Server 설정 필드에 유지한다. 미합의 Permission 자산 추가는 철회했다.
- 결과: 기존 정답과 같은 자산 17개(Gateway 1·Node 1·Server 1·Tool 14), 관계 16개(PAIRED_WITH 1·DECLARES 1·ADVERTISES 14). 고정 원천 예제의 비교 기준이며 전체 환경의 수집률 분모가 아니다.
- Resource/Template/Prompt·Skill·Plugin이 없다는 판정을 하지 않는다. 내장 Plugin/Skill과 인증 자산은 검증 범위 밖이다.

## 검토용 값과 제약

- 모든 `review-p0:` ID는 원천 asset_key에 기반한 임시 검토 ID다. #10의 해시 ID를 선결정하지 않는다. 환경·프로필·snapshot ID도 검토용이다.
- 모든 시각 2026-11-10T00:00:00Z는 **가상 fixture 메타데이터**다. 원천 관측·서버 조회 시각이 아니다. 실제 연동 시 수집 시작/종료·증적 관측 시각을 다시 확보해야 한다.
- evidence는 고정 commit의 저장소 자료를 참조한다. Gateway·Node와 페어링은 정답 문서의 간접 근거를 사용했으며 실제 identity·페어링 CLI를 재실행하지 않았다.
- Tool EXPOSED·호출 가능·사용 여부는 null로 남긴다. 정답의 exposed_to_agent를 검증된 대상별 판정으로 복사하지 않는다.
- 원천 정의는 미실행·미조회 데이터로 취급한다. 이 변환은 공식 규격 전체 검증·일반 비밀값 가림 구현이 아니다.
- 범위 밖 내장·인증 자산의 미수행 작업과 임시 scope를 제거했다. scan.status=partial은 가져온 Tool 자료의 원래 인증 맥락·페이지 완전성 메타데이터를 확인하지 못했기 때문이다. 실제 조회 실패를 뜻하지 않는다. 실제 출력 상태는 실제 수집 계획과 결과로 계산한다.
- scope는 기존 gateway_config/tools_list를 사용한다. 정답 기반 선언 자료는 gateway_config의 수동 가져오기로 표시했으며 직접 수집이 아니다. 원래 MCP 인증 맥락은 알 수 없어 auth_context_ref=null과 사유를 남겼다.
- 2026-11-11 확인한 스캐너 #5(c9d20ae122bea665111c7c69625022595ac9d4c9)는 MCP 2025-11-25·2026-07-28을 버전별 규칙으로 처리한다. 버전 지원 공백은 해소됐으며 원천 협상 2025-11-25는 유지한다. 개발용 서버 stdio 검증·전체 332개 테스트 통과는 담당자 보고다. 실제 팀 P0 서버 수집 및 본 검토 파일과의 대조는 아직 수행하지 않았다.

로컬 검증: `python docs/examples/p0/validate_review.py`. JSON 구문·핵심 필수 필드·ID 중복·소속/대상/증적/수집 참조·집계를 확인한다. 전체 JSON Schema 적합성이나 실제 수집 완료를 보증하지 않는다.
