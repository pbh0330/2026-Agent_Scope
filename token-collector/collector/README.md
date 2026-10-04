# otelcol-agentscope — 도구별 토큰·비용 귀속 커스텀 Collector

파이썬 프로토타입(작성자 개인 저장소 보관)으로 검증한 귀속 로직을 Go로 옮겨서
OpenTelemetry Collector **커넥터(traces → metrics)** 로 만든 것. OpenClaw가 보내는
트레이스를 실시간으로 받아 도구·MCP 서버별 토큰·비용 메트릭을 Prometheus로 내보낸다.
로그를 캡처해서 파이썬을 따로 돌리던 오프라인 방식과 달리, Collector만 켜두면 계속 동작한다.

## 폴더 구조

```
attribution/                 핵심 로직(외부 라이브러리 없는 순수 Go). 파이썬 프로토타입과 동일한 판정
  classify.go                  패턴 판정(순차/병렬/배치/귀속불가) + 순차 구간 토큰 귀속 공식
  tracker.go                   실시간용: 스팬을 run별로 모으고 확정 가능한 구간만 결과로 내보냄
  pricing.go                   openclaw.json 단가 로딩, 단가 0이면 Anthropic 공식 정가(참고용)로 대체
  testdata/                    실제 캡처 로그 3개(순차·배치·병렬)의 스팬 + 파이썬 결과(비교 기준)
tokenattributionconnector/   Collector 커넥터(위 로직을 감싸서 스팬 입력 → 누적 메트릭 출력)
usagereport/                 usage.json 어댑터: 원본 스팬 파일 → 통합 스키마 14절 UsageReport(호출 단위 기록 + 자산 매핑)
builder-config.yaml          OCB(OpenTelemetry Collector Builder) 빌드 설정
otelcol-agentscope-config.yaml  로컬 PC(Windows) 실행 설정 예시
```

## 동작 방식

1. OpenClaw → Collector(OTLP 4318)로 `openclaw.model.call`, `openclaw.tool.execution`,
   `openclaw.run` 스팬이 들어오면 run(부모 스팬)별로 모은다.
2. 도구 구간 결과는 **확정 가능한 시점에만** 내보낸다.
   - 그 구간을 닫는 다음 `model.call`이 도착하고 `grace`(기본 2초)가 지났을 때
   - `openclaw.run` 스팬이 도착했을 때(나머지 전부. 마지막 model.call 뒤 도구는 `unattributed`)
   - `run_idle_timeout`(기본 10분) 동안 새 스팬이 없을 때
3. 확정이 끝난 run의 식별자는 30분(또는 `run_idle_timeout` 중 큰 값) 동안 기억한다. 그 사이 같은
   run의 스팬이 재전송되면 새 run으로 세지 않고 버린다(중복 집계 방지, `dropped_spans`로 집계).
4. 판정은 매번 run 전체를 다시 계산하므로 오프라인 분석(파이썬)과 결과가 같다.
   순차 구간 토큰 = `다음.input - 이전.input - 이전.output` (직전 응답 재편입분 제외).
5. `metrics_flush_interval`(기본 5초)마다 누적값 전체를 Prometheus 익스포터로 보낸다.

도구 실행 후 대시보드 반영까지는 보통 10~40초 걸린다. 다음 model.call이 끝나야
입력 토큰을 알 수 있는 공식 구조상의 지연 + OpenClaw 전송 주기(5초) + Prometheus 스크랩
주기가 합쳐진 값이다.

## 내보내는 메트릭 (Prometheus 이름)

| 메트릭 | 설명 | 주요 라벨 |
|---|---|---|
| `openclaw_tool_attribution_calls_total` | 도구 호출 수 | `tool_name`, `tool_source`, `mcp_server`, `attribution_pattern` |
| `openclaw_tool_attribution_tokens_total` | 순차 구간에서 도구에 귀속된 근사 토큰(추정치) | `tool_name`, `mcp_server`, `gen_ai_request_model`, `attribution_estimated="true"` |
| `openclaw_tool_attribution_cost_usd_total` | 위 토큰 × 입력 단가(추정치) | 위 + `pricing_source`(`config` / `reference_list_price`) |
| `openclaw_tool_attribution_duration_milliseconds` | 도구 실행 시간 히스토그램(병렬·배치의 대리 지표) | `tool_name`, `attribution_pattern` |
| `openclaw_tool_attribution_anomalies_total` | 신뢰도 낮은 사례 수 | `reason`(`negative_delta`/`missing_tokens`/`missing_timestamps`) |
| `openclaw_tool_attribution_pending_runs` | 확정 대기 중인 run 수 | |
| `openclaw_tool_attribution_dropped_spans_total` | 이미 확정된 run으로 늦게·중복(재전송)으로 들어와 집계에서 뺀 스팬 수 | |

토큰·비용·호출 수 메트릭에는 해당 도구 스팬의 `trace_id`/`span_id`가 **exemplar**로 붙는다
(`enable_open_metrics: true` 필요). Grafana에서 메트릭 → 트레이스로 바로 이동하는 데 쓴다.
exemplar는 시리즈마다 최근 `max_per_data_point`(기본 5)건을 계속 유지한다. flush마다 비우면 Prometheus
스크랩 주기(15초)보다 짧은 5초 동안만 보여서 저장되지 않는 문제가 있었다(10.03 수정).
`pricing_source="reference_list_price"`는 학교 게이트웨이 단가가 0이라 Anthropic 공식 정가를
참고용으로 쓴 값이며 실제 청구액이 아니다.

## usage.json (호출 단위 기록, 대시보드·QA용)

메트릭은 누적값이라 호출별 기록과 자산 매핑을 담을 수 없다. 실행 설정의 `file/traces` 익스포터가 원본
스팬을 `agentscope-traces.jsonl`로 남기고, `usagereport/`의 `agentscope-usage`가 그 파일로 PR #1 스키마
14절 형식의 `usage.json`을 만든다. 자세한 내용은 [usagereport/README.md](usagereport/README.md).

## 빌드

Go 1.26 이상 필요(Collector v0.161.0 요구사항).

```bash
cd token-collector/collector
go install go.opentelemetry.io/collector/cmd/builder@v0.161.0
builder --config builder-config.yaml                 # → _build/otelcol-agentscope
# Windows용: _build 폴더에서
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o otelcol-agentscope.exe .
```

결과물은 약 37MB(otelcol-contrib 386MB 대비). `_build/`와 실행 파일은 커밋하지 않는다.

컨테이너 이미지는 `Dockerfile`이 같은 과정을 이미지 안에서 수행한다. 보통은 `../pipeline/docker-compose.yml`이
자동으로 빌드하므로 따로 실행할 필요가 없다(Tempo·Prometheus·Grafana 연동 포함, `../pipeline/README.md`).

## 실행 (Windows 로컬 테스트베드)

```powershell
cd C:\Users\<사용자>\.openclaw
.\otelcol-agentscope.exe --config .\otelcol-agentscope-config.yaml
# 확인: 브라우저에서 http://localhost:9464/metrics
```

기존 `otelcol-contrib`와 같은 4318 포트를 쓰므로 둘 중 하나만 켠다. OpenClaw의 코어 메트릭
(`openclaw_tokens_total` 등)도 같은 `/metrics`로 함께 나온다.

## 테스트

```bash
cd attribution && go test ./...                 # 판정 로직 + 실제 로그 3개로 파이썬 결과와 일치 확인
cd ../tokenattributionconnector && go test ./... # 커넥터: 메트릭 합계·누적·exemplar·단가 로딩
cd ../usagereport && go test ./...               # usage.json: 파이썬 결과 일치·null 규칙·중복 제거·자산 매핑
```

테스트 픽스처는 파이썬 프로토타입의 `export_fixtures.py`(개인 저장소 보관)로 만들었다
(스팬 속성 중 `openclaw.*`, `gen_ai.*`만 남김).

## 검증 기록 (2026-09-28)

- 순수 Go 로직: 파이썬 단위 테스트 9건을 옮긴 테스트 + 실제 로그 3개에서 파이썬과 판정·토큰 수 일치.
  공식을 1만 틀려도 비교 테스트가 실패하는지(뮤테이션) 확인.
- 빌드한 Collector에 실제 로그 3개를 OTLP로 재전송 → `/metrics` 값이 파이썬 결과와 일치
  (exec 649, ls 19, fs__list_directory_with_sizes 264토큰, batch 4건, parallel 4건).
- 사용자 PC(Windows)에서 실제 OpenClaw 웹챗 요청으로 실시간 동작 확인: 한 요청 안에서
  목록 조회(sequential, 264토큰) → 파일 2개 동시 읽기(parallel 2건)가 몇 초 안에 반영됨.

## 아직 안 한 것

- usage.json의 `schema_version`·집계 API·플러그인 도구 매핑은 팀 합의 대기(usagereport/README.md 참고).
- docker-compose(Tempo·Prometheus exemplar·Grafana 연결)는 샌드박스에서 구성요소별로만 검증했다.
  사용자 PC에서 `docker compose up` 후 Grafana 점 → Tempo 이동을 확인해야 한다(`../pipeline/README.md`).
- 캐시 토큰을 input과 따로 보고하는 프로바이더(Anthropic 직접 호출 + 프롬프트 캐싱)라면
  `include_cache_in_prompt: true`가 필요할 수 있다. 지금 테스트베드(school-gateway)는 캐시 0이라 미검증.
