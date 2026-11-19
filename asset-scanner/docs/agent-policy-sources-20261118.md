# Agent별 권한 정책 원천 수집 보완

- 기준: 스캐너 `ee9c1e02a660c23e1a445680df2905ae41be463b` 이후 변경
- 원천: OpenClaw [`eb377ac59e6c9fd6c7705028034812becf00271b`](https://github.com/openclaw/openclaw/blob/eb377ac59e6c9fd6c7705028034812becf00271b/src/config/zod-schema.agent-runtime.ts)
- 근거 정의: `CommonToolPolicyFields`, `ToolPolicySchema`, `ToolPolicyWithProfileSchema`, `AgentToolsSchema`, `ElevatedAllowFromSchema`, `MessageToolConfigSchema`, `ToolsSchema`
- 수집기: `permission_auth`; CLI 옵션과 의존성 변경 없음
- 범위: 지정한 설정·선택 include의 선언값 수집. Agent 실행·메시지 전송·정책 적용·공통 ID 계산 없음

## 추가 경로와 출력

| 원천 경로 | 수집 값 | 적용 범위 |
|---|---|---|
| `agents.entries.*.tools.byProvider.*` | profile·allow·alsoAllow·deny | `agent_provider`, `agent_key`, `provider` |
| `agents.entries.*.tools.toolsBySender.*` | allow·alsoAllow·deny | `agent_sender_group`, `agent_key`, 발신자 종류. 실제 발신자 키 비공개 |
| `agents.entries.*.tools.elevated.allowFrom.*` | 선언된 항목 수. 발신자 값 비공개 | `agent_elevated_sender_allowlist`, `agent_key`, `provider` |
| `agents.entries.*.tools.sandbox.tools` | allow·alsoAllow·deny | Agent 범위와 해당 설정 경로 |
| `tools.sandbox.tools.alsoAllow` | 문자열 목록 | 전역 sandbox 선언 |
| `tools.subagents.tools` | allow·alsoAllow·deny | `global_subagent_tools` |
| `tools.agentToAgent` | enabled·allow | `agent_to_agent` |
| `tools.sessions.visibility` | self·tree·agent·all의 선언값 | `session_visibility` |
| `tools.message.crossContext` 및 Agent별 같은 경로 | allowWithinProvider·allowAcrossProviders | `global_message_cross_context` 또는 `agent_message_cross_context` |

- 원천 항목별 `config_path`, `config_pointer`, `applies_to`, `value_kind/value`, `doc_basis` 보존
- include 사용 시 기존 `include_origin` 보존
- 서로 다른 Agent·Provider의 같은 Tool 이름도 별도 원천으로 보존
- 없는 필드·기본값 생성, allow/deny 우선순위·와일드카드 확장·실효 권한 계산 없음
- `complete`는 읽은 범위의 수집 상태. 전체 OpenClaw 설정의 유효성·정책 허용 결과를 의미하지 않음
- 전체 설정 스키마 검증은 `scope.not_collected`의 `full_openclaw_config_validation`으로 명시

## 가림과 원천 식별

- 발신자 ID·전화번호: 기존 비공개 정책 유지
- `toolsBySender` 키: 발신자 종류 자리표시자로 기록
- 표시 경로가 원래 경로와 달라지거나 설정 키가 가려진 항목: `config_path_redacted: true`, `original_config_pointer_available: false`
- 해당 경로를 원본 식별 입력으로 사용하지 않음
- 같은 자리표시자가 생겨도 항목 병합 없음. 결과 내 `ref`는 각각 별도로 부여하며 영속 ID로 쓰지 않음
- Provider/Agent/서버 키에 포함된 URL 인증정보: 경로·적용 대상·진단 경로에서 가림
- JSON Pointer: 원래 키의 `/`와 `~` 이스케이프 유지. 가린 키가 있으면 표시용 포인터로 구분
- 승격 허용 목록: 문자열·유한 숫자만 개수로 기록. boolean·null·객체·비유한 숫자는 잘못된 자료형으로 기록

## 가상 출력 발췌

입력 조건: 사람이 작성한 `writer` Agent, Provider 키 `local/model`, 허용 목록 `[read]`. 실제 OpenClaw 출력이 아님.

```json
{
  "category": "tool_policy",
  "config_path": "agents.entries.writer.tools.byProvider[\"local/model\"].allow",
  "config_pointer": "/agents/entries/writer/tools/byProvider/local~1model/allow",
  "applies_to": {
    "scope": "agent_provider",
    "agent_key": "writer",
    "provider": "local/model"
  },
  "value_kind": "string_list",
  "value": ["read"]
}
```

## 검증

- 신규 테스트: `tests/test_agent_policy_sources.py`
- 조건: 가상 JSON/JSON5·include 파일. 실제 OpenClaw·OVA·메시지 전송 없음
- 재현: 최초 20개 사례에서 18개 실패·2개 통과. 기존 수집 누락과 actor 목록의 boolean 오인 확인
- 추가 재현: 공유 ToolPolicy 사용처·세션/교차 전송 선언 8개 실패. MCP 등록키가 가려졌는데 가림 상태가 false로 남는 사례 1개 실패
- 수정 후 영향 검사: 109개 통과, pytest 종료 코드 0
- 전체 검사: Linux / Python 3.12.14 / pytest 9.1.1, **1,028 passed / 0 failed / 0 skipped**, pytest 종료 코드 **0**, 196.75초. 이번 코드로 한 번에 완료했으며 이전 실행 결과와 합산하지 않음
- 구성: 테스트 파일 45개. 기준 코드의 994개 사례와 이번 회귀 34개 포함. 실제 OpenClaw·OVA 검증 또는 모든 요구사항 충족을 뜻하는 수치는 아님

## 남은 범위

- 채널별 접근 제어 전체, 설치 자동 탐색, Skill YAML 전체 문법, OAuth 메타데이터 자동 수집: 이번 변경에 포함하지 않음
- 공통 정책 묶음·원천 중복 처리·ID 규칙·실효 권한: 팀 협의 범위 유지
- 실제 OpenClaw의 정책 동작·프로필·출력 대조: 실환경 검증 대기
