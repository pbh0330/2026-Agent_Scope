# 토큰 사용량 수집 · 비용 모니터링

AI 에이전트 보안 자산 식별·가시화 기술 개발 프로젝트 — 토큰 사용량 수집·비용 모니터링 파트
(`feature/token-collector` 브랜치 작업물).

OpenClaw 공식 텔레메트리는 토큰·비용을 채널/프로바이더/모델/에이전트 단위까지만 분해하고
**도구·MCP 서버 단위로는 분해하지 않는다.** 이 폴더는 그 간극(“얼마나 썼는지는 알아도
무엇 때문에 썼는지는 모른다”)을 메우기 위한 검증 로그, 귀속(attribution) 알고리즘,
관측 파이프라인을 담고 있다.

담당: 정철 · 목표 완성 시점: 2026-11-15 (4주 압축 일정 적용, 2026-09-20 시작)

> 저장소 최상위 `README.md`(브랜치 전략)는 그대로 두고, 이 파트 작업은
> `token-collector/` 폴더 하나로 모아서 `feature/token-collector` 브랜치에
> 추가하는 방식으로 진행합니다.

## 폴더 구조

```
docs/       개발계획서, 마일스톤 0(exemplar 연결) 검증 로그, 3주차 정확도 검증 결과
scripts/    traceId+타임스탬프 기반 도구별 토큰/비용 귀속 알고리즘 (Python 프로토타입, 검증 기준)
collector/  위 로직을 Go로 옮긴 OTel Collector 커넥터 + 커스텀 Collector 빌드 설정 (실시간 동작)
pipeline/   OTel Collector + Prometheus + Grafana 관측 파이프라인 (docker-compose)
```

## 지금까지 확인된 것 (마일스톤 0, 2026-09-22)

- **exemplar 연결 안 됨.** 실제 캡처 로그(28만 줄 이상)에 `Exemplar` 필드가 0건 —
  메트릭↔트레이스 자동 연결(exemplar)에 의존한 설계는 불가능함을 확인.
- **스팬 간 traceId 연결은 정상.** `openclaw.model.call` / `openclaw.tool.execution`
  스팬이 같은 traceId로 정상적으로 묶임. 게다가 `model.call` 스팬 자체에
  input/output 토큰 수가 이미 속성으로 들어 있어서, **메트릭 조인 없이 스팬만으로
  귀속 계산이 가능**하다는 걸 확인함 — 자세한 내용은 `docs/` 참고.
- `openclaw.cost.usd` 메트릭은 이번 캡처엔 안 보였음 — `scripts/`, `pipeline/`
  양쪽 다 토큰 수 × 단가로 직접 계산하는 근사치를 씀.

## 3주차: 정확도 검증 (2026-09-28)

- **패턴 판별(순차/병렬/배치)은 원본 타임스탬프로 감사(audit) 가능함을 확인.**
  `scripts/traceid_attribution/audit_attribution.py`로 판정 근거(스팬 시작/종료
  시각)를 사람이 직접 확인할 수 있게 함.
- **버그 발견·수정**: model.call 없이 끝난 run의 도구 호출이 결과에서 조용히
  누락되던 문제 → `"unattributed"`로 명시 기록하도록 수정.
- **리스크 발견·완화**: 도구 스팬 타임스탬프 누락 시 병렬이 배치로 오분류될 수
  있는 문제 → note에 경고 남기도록 수정. 회귀 테스트 3건 추가(총 7건 전부 통과).
- **단가 이슈 발견**: 실제 `openclaw.json`(school-gateway)의 모델 단가가
  input/output/cache 전부 0으로 설정돼 있음 — 학교 게이트웨이가 종량제 과금을
  안 하기 때문. Anthropic 공식 정가(참고용, 실제 청구액 아님)를 자동 대체하도록
  `attribution.py`를 고침.
- **실제 batch·parallel 사례 확보·검증**: 웹챗으로 다중 도구 호출을 유도해 batch 사례를
  얻었고, 병렬이 안 나온 원인(MCP 서버에 `supportsParallelToolCalls` 미설정 시 순차 실행)을
  OpenClaw 소스로 확인한 뒤 설정을 바꿔 parallel 사례까지 확보. 순차·배치·병렬 판정 모두
  실데이터로 검증 완료.

자세한 내용: `docs/week3-accuracy-validation.md`

## 4주차 착수: Go 커넥터로 실시간화 (2026-09-28)

- 귀속 로직을 Go로 옮겨 OTel Collector **커넥터(traces → metrics)** 로 구현하고, 필요한
  부품만 넣은 커스텀 Collector(`otelcol-agentscope`, 약 37MB)를 OCB로 빌드.
- 실제 로그 3개로 파이썬 결과와 판정·토큰 수가 일치함을 테스트로 확인하고, 사용자 PC에서
  실제 OpenClaw 요청으로 도구별 토큰·비용 메트릭이 `/metrics`에 실시간 반영되는 것 확인.
- 도구별 토큰·비용 메트릭에 트레이스 ID를 exemplar로 붙여서 메트릭 → 트레이스 이동 가능.
- 이식 중 파이썬 쪽 버그 1건 발견·수정: 마지막 model.call 뒤 도구가 `unattributed`가 아닌
  `sequential`/`batch`로 잘못 표시되던 문제(회귀 테스트 2건 추가, 총 9건).

자세한 내용: `collector/README.md`

## 사용법

```bash
# 1) 캡처한 OTel Collector debug 로그로 도구별 토큰/비용 귀속 계산
cd scripts/traceid_attribution
python3 attribution.py <otel-debug-log.txt> [openclaw.json]   # 단가표 실제값은 openclaw.json에서 로드
python3 test_attribution.py                                    # 순차/병렬/배치 분류 로직 단위 테스트
python3 audit_attribution.py <otel-debug-log.txt>               # 패턴 판정 근거(원본 타임스탬프) 감사용 출력

# 2) 실시간: 커스텀 Collector 실행 (빌드 방법은 collector/README.md)
.\otelcol-agentscope.exe --config .\otelcol-agentscope-config.yaml   # http://localhost:9464/metrics

# 3) Prometheus + Grafana로 코어 메트릭(토큰 총량/근사 비용/응답시간) 상시 모니터링
cd pipeline
docker compose up -d
# Grafana: http://localhost:3000 (admin/admin)
```

각 폴더 안의 README/코드 주석에 더 자세한 내용과 TODO가 있음.

## 아직 안 끝난 것

- `pipeline/prometheus/rules.yml`은 여전히 단가 placeholder임 — `attribution.py`처럼
  "게이트웨이 단가 0이면 Anthropic 공식 정가로 자동 대체"하는 로직을 Prometheus
  recording rule(정적 상수)에도 반영할지 결정 필요.
- `pipeline/docker-compose.yml`을 커스텀 Collector(`collector/`)로 바꾸는 Dockerfile 작업과,
  도구별 토큰·비용 Grafana 패널(exemplar → 트레이스 연결 포함) 추가.
