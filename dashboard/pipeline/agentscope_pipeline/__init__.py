"""AgentScope 대시보드 데이터 파이프라인.

팀 산출물(자산 스캐너 출력, 테스트베드 원본, 위협 시나리오 규칙, 토큰 수집기 usage.json)을
공통 스키마 v0.6.0-draft 형식(snapshot / detections / diff / usage)으로 묶어 대시보드에 전달한다.
"""

SCHEMA_VERSION = "0.6.0-draft"
PRODUCER = {"name": "agentscope-dashboard-pipeline", "version": "0.1.0"}
