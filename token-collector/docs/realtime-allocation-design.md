# 병렬·배치 구간 배분 실시간 반영 설계 (2026-10-12)

병렬·배치 구간 배분(방안 B)은 지금 `agentscope-usage --tool-results`로 만드는 usage.json에만 반영된다.
이 문서는 같은 배분을 Collector 커넥터에서 실시간으로 계산해 Grafana 대시보드에 보이게 하는 설계다.

## 1. 지금 구조와 빈 곳

```
OpenClaw ─OTLP→ Collector ─ tokenattribution 커넥터 ─→ Prometheus/Grafana   (순차 구간만 토큰)
   └ 플러그인(agentscope-token-guard) ─→ agentscope-tool-results.jsonl ─→ agentscope-usage ─→ usage.json (병렬·배치 배분)
```

- 커넥터는 OpenClaw 스팬만 받는다. 플러그인이 센 결과별 토큰 수(c_i)는 파일에만 있어 커넥터가 모른다.
- 배분 계산(`attribution.AllocateByCounts`)은 이미 있다. 빠진 것은 **c_i를 커넥터까지 실시간으로 보내는 길**과
  **c_i가 올 때까지 구간 확정을 잠깐 미루는 처리**다.

## 2. 전달 방식

| 방식 | 내용 | 판단 |
|---|---|---|
| A. 플러그인이 OTLP 스팬으로 보냄 | 결과별 토큰 수를 짧은 스팬 하나(`agentscope.tool_result.count`)로 만들어 OpenClaw와 같은 Collector(4318)로 전송 | **채택**. 커넥터가 이미 받는 traces 파이프라인에 그대로 들어감. 수신기·파이프라인 추가 없음 |
| B. Collector가 JSONL 파일을 따라 읽음 | filelog 수신기 → logs 파이프라인 → 커넥터 | 수신기 추가(빌드 변경), logs→metrics 입력을 따로 받아 traces 상태와 공유해야 함. 컨테이너에서 PC 파일 경로를 마운트해야 함 |
| C. OpenClaw 스팬에 속성으로 붙임 | tool.execution 스팬에 토큰 수 추가 | 불가. 스팬은 diagnostics-otel이 만들고 이미 끝난 뒤에 수가 나옴 |

방식 A의 부수 효과:

- 같은 스팬이 Tempo와 원본 스팬 파일에도 저장된다. Tempo에서 해당 요청의 실행 기록 안에 "결과별 토큰 수"가 함께 보이고,
  usage.json 생성기도 원본 스팬 파일만으로 배분할 수 있게 된다(`--tool-results` 없이도 가능, 기존 옵션은 유지).

### 카운트 스팬 형식

| 항목 | 값 |
|---|---|
| 이름 | `agentscope.tool_result.count` |
| trace_id | 원래 요청의 trace id(before_tool_call의 `ctx.trace.traceId`). 없으면 새로 생성 |
| 시작·끝 | 토큰 계산 시작·끝 시각 |
| 속성 | `gen_ai.tool.call.id`, `openclaw.toolName`, `agentscope.counted_tokens`(int), `agentscope.count.source`(anthropic-count-tokens / openai-usage), `agentscope.count.skipped_blocks` |
| 리소스 | `service.name=agentscope-token-guard` |
| 전송 | OTLP/HTTP JSON, `POST {otlpEndpoint}/v1/traces` (외부 라이브러리 없이 fetch) |

결과 내용은 담지 않는다(크기·토큰 수만).

## 3. 커넥터 변경

1. `ConsumeTraces`: `agentscope.tool_result.count` 스팬을 받으면 `tracker.AddCount(tool_call_id, tokens, now)`.
   카운트는 run과 별개로 tool_call_id → 토큰 수 맵에 보관(보관 시간 `count_ttl`, 기본 10분).
2. `Tracker.collect`: run을 판정한 뒤 보관 중인 카운트로 `AllocateByCounts`를 적용한다.
   - 순차 결과: 지금과 같이 닫는 model.call 도착 + grace 후 확정.
   - **병렬·배치 결과: 구간 단위로 함께 확정**한다. 구간의 모든 도구 카운트가 모이면 즉시 배분해 확정하고,
     모이지 않았으면 닫는 model.call 도착 후 `count_wait`(기본 15초)까지 기다렸다가 배분 없이(지금처럼 호출 수·시간만) 확정한다.
   - run이 끝나거나(idle 포함) 메모리 상한에 걸리면 기다리지 않고 그 시점 카운트로 확정한다.
3. `metrics.go`: 토큰·비용을 `Sequential && HasTokens`일 때만 더하던 조건을 `(Sequential || AllocationMethod != "") && HasTokens`로 바꾼다.
   라벨은 기존 `attribution_pattern`(sequential / parallel / batch)으로 구분되므로 새 라벨은 추가하지 않는다.
   배분 못 한 병렬·배치 구간은 anomalies에 `missing_counts` 사유로 센다.
4. 설정 추가: `count_wait`(기본 15s), `count_ttl`(기본 10m). 플러그인이 없으면 카운트가 오지 않으므로 병렬·배치는 count_wait 뒤 지금과 같이 동작한다
   (플러그인 미설치 환경에서도 기존 동작 유지).

### 시간 관계(10.12 PC 실측 기준)

- 토큰 계산은 결과 저장 후 1.4~3.1초에 끝남 → 카운트 스팬은 diagnostics-otel 내보내기 주기(5초) 안팎에 도착.
- 병렬 구간을 닫는 model.call은 결과 저장 후 모델 응답 시간만큼 뒤에 끝남(수 초). 대부분 카운트가 먼저 도착하므로
  지연은 늘지 않고, 늦는 경우만 최대 count_wait만큼 반영이 늦어진다.

## 4. 플러그인 변경

- 설정 `otlpEndpoint`(기본 없음 = 보내지 않음). PC·테스트베드에서는 `http://localhost:4318`.
- before_tool_call에서 `toolCallId → ctx.trace.traceId`를 기억해 두고, token_count 기록 시 카운트 스팬을 함께 전송.
- 전송 실패는 `count_export_error`로 기록만 하고 에이전트 실행에는 영향 없음. JSONL 기록은 그대로 유지.

## 5. 대시보드 변경

- "도구별 귀속 토큰 증가량" 패널: 순차 실측분과 병렬·배치 배분분을 `attribution_pattern`으로 나눠 쌓아 보여 줌
  (예: `sum by (tool_name, attribution_pattern) (increase(openclaw_tool_attribution_tokens_total[5m]))`).
- 배분 못 한 구간 수(`missing_counts`)를 작은 패널로 표시해 플러그인 미설치·계산 실패를 바로 알 수 있게 함.

## 6. 테스트 계획

| 단계 | 내용 |
|---|---|
| 단위 | Tracker: 카운트가 먼저/나중에 도착, 일부만 도착 후 count_wait 경과, run 종료 시 즉시 확정, 재전송 중복 |
| 단위 | 커넥터: 카운트 스팬 → 병렬 구간 메트릭 합계 = 구간 증가분, 플러그인 없음 → 기존과 동일 |
| 단위 | 플러그인: OTLP JSON 형식, trace id 연결, 전송 실패 처리 |
| 연동 | 10.12 PC 데이터 재전송: 실시간 메트릭의 병렬 구간 값이 usage.json 배분값(593 / 3,327)과 같은지 |
| 실측 | PC에서 병렬 요청 → Grafana 패널에 병렬분 표시, 점(exemplar) → Tempo에서 카운트 스팬 확인 |

## 7. 확인 필요

- before_tool_call의 `ctx.trace.traceId`가 diagnostics-otel이 내보내는 스팬의 trace id와 같은지(같아야 Tempo에서 한 요청으로 묶임).
  달라도 커넥터 배분은 tool_call_id로 맞추므로 동작에는 지장 없음.
- Collector 컨테이너의 4318이 플러그인(게이트웨이 프로세스)에서 닿는지(PC는 localhost, 테스트베드는 Collector 위치에 따라).

## 8. 일정

| 시점 | 내용 |
|---|---|
| ~10.14 | PC 병렬 반복 테스트로 배분 방식 확정(필요 시 AllocateByCounts만 수정) |
| ~10.18 | 커넥터·플러그인 구현, 단위·연동 테스트 |
| ~10.21 | PC 실측, 대시보드 패널 수정 |
| 10.25 전 | 중간보고서에 실시간 반영 결과 포함 |
