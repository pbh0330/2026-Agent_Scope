# 토큰 사용량 수집 · 비용 모니터링

AI 에이전트 보안 자산 식별·가시화 기술 개발 프로젝트의 토큰 사용량 수집·비용 모니터링 파트
(`feature/token-collector`). 담당: 정철 · 목표 완성: 2026-11-15

OpenClaw 공식 텔레메트리는 토큰·비용을 채널·프로바이더·모델 단위까지만 나누고 **도구·MCP 서버 단위로는
나누지 않는다.** 이 파트는 OpenClaw 트레이스(모델 호출·도구 실행 스팬)로 도구별 토큰·비용을 근사 귀속하고,
대시보드와 자산 그래프에서 쓸 수 있는 메트릭과 호출 단위 기록으로 내보낸다.

```
OpenClaw ─OTLP→ otelcol-agentscope(커스텀 Collector) ─┬─ 도구별 토큰·비용 메트릭 + exemplar(trace_id) → Prometheus/Grafana
                                                      ├─ 트레이스 원본 → Tempo (traceId로 실행 기록 조회)
                                                      └─ 원본 스팬 파일 → agentscope-usage → usage.json (자산 ID 연결)
```

## 폴더 구조

| 경로 | 내용 |
|---|---|
| `collector/attribution/` | 귀속 핵심 로직(순수 Go): 순차·병렬·배치·귀속불가 판정, 순차 구간 토큰 공식, 단가 |
| `collector/tokenattributionconnector/` | OTel Collector 커넥터(traces → metrics). 실시간 도구별 메트릭 |
| `collector/usagereport/` | usage.json 생성기(`agentscope-usage`). 통합 스키마 14절 UsageReport, 자산 ID 매핑 |
| `collector/builder-config.yaml`, `Dockerfile` | 커스텀 Collector 빌드(OCB) / 컨테이너 이미지 |
| `collector/otelcol-agentscope-config.yaml` | Windows 로컬 단독 실행 설정 |
| `pipeline/` | docker-compose: 커스텀 Collector + Tempo + Prometheus(exemplar) + Grafana |
| `scripts/traceid_attribution/` | Python 프로토타입. Go 결과의 비교 기준, 테스트 픽스처 추출, 판정 근거 감사 |
| `docs/` | 개발계획서와 검증 기록(아래 표) |

| 문서 | 내용 |
|---|---|
| `docs/token-usage-cost-monitoring-devplan-v2.md` | 개발계획서(09.20 작성, 09.21 수정) |
| `docs/0921-diagnostics-otel-verification-log.md` | 텔레메트리 실측 검증(마일스톤 0) |
| `docs/week3-accuracy-validation.md` | 정확도 검증, 실제 배치·병렬 사례 |

## 실행

```powershell
# 1) 실시간 도구별 메트릭 (Windows 로컬, 빌드 방법은 collector/README.md)
.\otelcol-agentscope.exe --config .\otelcol-agentscope-config.yaml    # http://localhost:9464/metrics

# 2) 호출 단위 기록 usage.json (collector/usagereport/README.md)
.\agentscope-usage.exe --env <environment_id> --profile <profile_id> --input .\agentscope-traces.jsonl --out .\usage.json

# 3) 전체 파이프라인 (Docker 필요, 실제 기동 테스트 필요 — pipeline/README.md)
cd pipeline; docker compose up -d --build
```

## 테스트

```bash
cd collector/attribution && go test ./...                 # 판정 로직, 실제 로그 3개로 Python 결과와 일치 확인
cd collector/tokenattributionconnector && go test ./...   # 메트릭 합계·누적·exemplar·재전송 중복 방지
cd collector/usagereport && go test ./...                 # usage.json: null 규칙·중복 제거·자산 매핑
cd scripts/traceid_attribution && python3 test_attribution.py
```

## 진행 기록

| 날짜 | 내용 |
|---|---|
| 09.21~22 | 텔레메트리 실측: 스팬 traceId 연결 정상, model.call 스팬에 토큰 속성 존재 → 스팬만으로 귀속 가능. OpenClaw가 exemplar를 내보내지 않음 확인(이후 커넥터가 직접 붙임) |
| 2주차 | Python 귀속 알고리즘, Collector·Prometheus·Grafana 파이프라인 |
| 09.28 | 정확도 검증: 판정 근거 감사 도구, 버그 2건 수정, 실제 배치·병렬 사례 확보(병렬은 MCP 서버 `supportsParallelToolCalls` 설정 시에만 발생) |
| 09.28~29 | Go 커넥터로 실시간화, 실제 OpenClaw 요청으로 동작 확인 |
| 10.01 | PR 리뷰 4건 반영(데이터소스 uid, 시간대 정렬, 재전송 중복 집계, 모델별 비용) |
| 10.02 | usage.json 생성기(자산 ID 매핑, 원본 스팬 파일 저장) |
| 10.03 | docker-compose를 커스텀 Collector로 교체, Tempo 추가, exemplar가 스크랩 주기에 안 잡히던 문제 수정 |

## 남은 일

- docker-compose 전체 기동 테스트(Docker 있는 PC에서) — 구성요소별 검증만 완료
- 환경·Gateway ID를 텔레메트리에 붙이는 방식(`OTEL_RESOURCE_ATTRIBUTES`) 실측 후 usage.json·메트릭에 반영
- `pipeline/prometheus/rules.yml`의 코어 비용 rule 단가 placeholder 처리 방식 결정
- usage.json `schema_version`·집계 API·플러그인 도구 매핑 팀 합의

## 규칙

- 파일명은 영문(ASCII). 한글 파일명은 Windows에서 압축 전달 시 깨짐.
- 원본 로그·원본 스팬 파일(`otel-debug-log*.txt`, `agentscope-traces*.jsonl`)과 실행 파일은 커밋하지 않는다(`.gitignore`).
  테스트 픽스처는 스팬 속성 중 `openclaw.*`, `gen_ai.*`만 남긴 것을 쓴다.
