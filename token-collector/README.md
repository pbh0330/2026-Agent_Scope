# token-collector — 토큰 사용량 백엔드

에이전트 스코프 MVP의 토큰 파트(담당 이정철). OpenClaw 에이전트가 도구를 부를 때마다 그 도구가 쓴 토큰을 계산하고,
대시보드 UI에 사용량을 JSON으로 준다. 토큰 소비가 기준을 넘으면 경고하거나 막는 소비 브레이크도 포함한다.

| 하는 일 | 구성 요소 |
|---|---|
| 도구 호출별 토큰·추정 비용 계산(순차 실측, 병렬·배치 배분) | `backend/attribution`, `backend/usagereport` |
| 대시보드 Token Usage 화면·자산 사용량 백엔드 | `backend/usageapi`(사용 현황 API) |
| 결과별 토큰 수 측정, 소비 브레이크 | `plugin/`(OpenClaw 플러그인 agentscope-token-guard) |
| 테스트베드(tb-gw) 설치 | `deploy/testbed/`, `docs/testbed-setup.md` |

## 구성

```
tb-gw (VM 하나 안에서 동작)
  OpenClaw 게이트웨이 ─ diagnostics-otel ─┐
     └ token-guard 플러그인 ─ 결과별 토큰 수 ┴─▶ Collector(otelcol, 127.0.0.1:4318) ─▶ agentscope-traces.jsonl
                └─▶ agentscope-tool-results.jsonl(브레이크 기록 등)                          │
                                                                                              ▼
  스캐너 스냅샷(선택, 자산 ID 연결) ──────────────────────────────────▶ 사용 현황 API(:8088) ─▶ 대시보드 UI
                                                                     usage.json 생성기 ─▶ usage.json(QA·통합 스키마 14절)
```

- 원본 스팬 파일이 기준 데이터다. 사용 현황 API와 usage.json은 같은 계산(`usagereport.Build`)을 쓴다.
- 도구 결과 내용은 어디에도 저장하지 않는다(크기·토큰 수·도구 이름·호출 ID만). API 키는 환경 변수로만 쓴다.
- 모든 토큰·비용은 추정치다. 비용은 공식 정가 기준 참고값이며 청구 금액이 아니다.

## 폴더

| 경로 | 내용 |
|---|---|
| `backend/attribution/` | 귀속 핵심 로직(표준 라이브러리만): 구간 판정(순차/병렬/배치/귀속불가), 순차 공식, 병렬 배분, 참고 정가 |
| `backend/usagereport/` | usage.json 생성기 `agentscope-usage`(통합 스키마 14절 UsageReport, 자산 ID 매핑) |
| `backend/usageapi/` | 사용 현황 API `agentscope-usage-api`. API 명세는 [backend/usageapi/README.md](backend/usageapi/README.md) |
| `plugin/` | OpenClaw 플러그인. 설정·기록 형식은 [plugin/README.md](plugin/README.md) |
| `deploy/testbed/` | tb-gw 설치: Collector 설치 스크립트, Collector 설정, systemd 사용자 서비스 |
| `docs/testbed-setup.md` | 테스트베드 적용 가이드(키 환경 변수, Collector, diagnostics-otel, 플러그인, 확인, 기록 전달) |
| `docs/accuracy-summary.md` | 계산 방법과 PC 실측 정확도 요약 |

## 빠른 확인(로컬, Go 1.24 이상)

```bash
cd token-collector/backend/usageapi
go run ./cmd/agentscope-usage-api --env env-pc --profile profile-pc --input testdata/pc-1029.traces.jsonl
# 다른 창에서
curl http://127.0.0.1:8088/api/v1/usage/summary
```

10.29 PC 실측 데이터(16건)로 답한다. 결과: 호출 16, 귀속 토큰 15,769(순차 2,268 / 병렬 배분 13,501).

## 테스트

```bash
cd backend/attribution && go test ./...   # 판정·순차 공식·병렬 배분(실제 캡처 로그 3개)
cd backend/usagereport && go test ./...   # usage.json: null 규칙·중복 제거·자산 매핑·병렬 배분
cd backend/usageapi && go test ./...      # API: 10.29 값 재현·묶음·구간·오류·경로 미노출
cd plugin && node --test test/*.test.ts   # 플러그인: 크기 측정·토큰 계산(가짜 API)·브레이크·OTLP 전송
```

## 정확도

병렬 배분 값은 같은 파일을 순차로 따로 읽은 값과 ±3% 안에서 맞았다(10.13 7건, 10.29 13건). 자세한 내용은 [docs/accuracy-summary.md](docs/accuracy-summary.md).

## 이전 이력

이 브랜치는 11.03에 MVP 백엔드만 남기고 다시 정리했다. 1~9주차 검증 로그, Python 프로토타입, Grafana·Prometheus·Tempo 구성,
Collector 커넥터(실시간 메트릭) 등 이전 커밋은 작성자 개인 저장소(`dlwjdcjf0/openclaw-token-attribution`, 브랜치 `archive/team-pr3-1103`)에 보관한다.

## 규칙

- 파일명은 영문(ASCII).
- 원본 스팬 파일, 플러그인 기록, 실행 파일은 커밋하지 않는다(`.gitignore`). 테스트 데이터는 호스트 이름·경로 속성을 지운 것만 쓴다.
- API 키·게이트웨이 토큰은 저장소와 문서에 쓰지 않는다.
