# diagnostics-otel 검증 로그 (2026-09-21)

**목적**: 마일스톤 0(exemplar 연결 여부 검증)을 위한 사전 점검 — 테스트베드 OpenClaw 게이트웨이에서 `diagnostics.otel` 설정으로 OTel Collector까지 실제로 텔레메트리가 전송되는지 확인.

**환경**: 테스트베드 담당자(ssesa) PC, Windows, OpenClaw 2026.9.5 (ec9c1a1), Node.js 24.19.0, agent model `school-gateway/claude-haiku-4-5-20251001`.

**결론 먼저**: OpenClaw → OTel Collector 전송 경로 자체는 검증 완료(성공). 다만 `diagnostics-otel` 익스텐션을 켜면 게이트웨이가 수 분간 완전히 멈추는 심각한 안정성 버그를 반복 재현했고, 이는 OpenClaw 자체의 미해결 오픈 이슈와 동일 패턴이다. 마일스톤 0의 핵심 질문(exemplar 연결 여부)은 이 문제 때문에 아직 답하지 못했다.

---

## 1. 초기 시도 — 설정만 추가

`openclaw.json`에 아래 `diagnostics` 블록만 병합하고 게이트웨이를 재시작.

```json
"diagnostics": {
  "otel": {
    "enabled": true,
    "endpoint": "http://localhost:4318",
    "protocol": "http/protobuf",
    "traces": true,
    "metrics": true,
    "logs": false,
    "sampleRate": 1.0,
    "flushIntervalMs": 1000,
    "captureContent": false
  }
}
```

검증용 OTel Collector(debug exporter, verbosity: detailed)를 같은 머신에서 기동해두고 대기.

**결과**: 콜렉터에 아무것도 안 찍힘. 게이트웨이 시작 로그(콘솔 + 파일 로그 `openclaw-2026-09-21.log`)에도 `otel`/`diagnostics`/`telemetry` 관련 줄이 단 한 줄도 없음(`Select-String`으로 확인, 매치 0건).

## 2. 원인 규명 — 익스텐션 별도 설치 필요

공식 문서 확인 결과, `diagnostics-otel`은 게이트웨이 코어 기능이 아니라 별도 익스텐션(`extensions/diagnostics-otel`)이었음. 설정만으로는 활성화되지 않고 플러그인 설치 + 명시적 허용이 필요했다.

- 출처: [Set up OpenTelemetry export · OpenClaw](https://docs.openclaw.ai/gateway/opentelemetry/setup)

```bash
openclaw plugins install clawhub:@openclaw/diagnostics-otel
```

및 `openclaw.json`에 다음 추가:

```json
"plugins": {
  "allow": ["diagnostics-otel"],
  "entries": { "diagnostics-otel": { "enabled": true } }
}
```

설치 자체는 성공(`openclaw plugins list`에서 `diagnostics-otel` — `enabled` 확인).

## 3. 1차 재시작 — 게이트웨이 프리징

설치 직후 재시작 시 설정 검증 경고 발생:

```
plugins.entries.diagnostics-otel: Plugin "diagnostics-otel" config validation is deferred
while its state migration is pending; existing settings are preserved.
```

이후 게이트웨이가 응답 없이 멈춤. liveness 진단 로그:

```
16:19:35 [diagnostic] liveness warning: reasons=event_loop_delay,event_loop_utilization
  interval=169s degradedFor=176s eventLoopDelayP99Ms=168845.9 eventLoopDelayMaxMs=168845.9
  eventLoopUtilization=1 cpuCoreRatio=0.813 phase=sidecars.model-runtime
```

Ctrl+C(SIGINT)도 즉시 반응하지 않고 약 150초 뒤에야 처리됨. 최종적으로 아래 에러와 함께 시작 실패:

```
[gateway] sidecars failed to start: Error: prepared model runtime publication
(workspace plugins; agent main) timed out
```

동일 증상이 OpenClaw 저장소 이슈로 보고돼 있음(원인 미특정, 메인테이너 해결책 없음, 오픈 상태):

- [Issue #152981 — Gateway startup hangs ~17분, 동일 에러 메시지](https://github.com/openclaw/openclaw/issues/152981)
- [Issue #139583 — 대형 설정에서 동일 타임아웃 재현](https://github.com/openclaw/openclaw/issues/139583)

## 4. plugins.allow 화이트리스트 함정

`diagnostics-otel`을 비활성화하고 재시작했더니 이번엔 다른 문제 발견 — 로드된 플러그인이 `memory-core` 1개뿐(원래 13개: anthropic, browser, canvas, cua-computer, device-pair, file-transfer, geolocation, linux-node, memory-core, ollama, openai, talk-voice, xai).

원인: `plugins.allow`는 "추가 허용"이 아니라 **화이트리스트**로 동작 — 목록에 없는 플러그인은 번들 플러그인이라도 전부 제외됨.

- 출처: [Configuration — MCP, skills, and plugins · OpenClaw](https://docs.openclaw.ai/gateway/config-extensions) ("`allow`: optional allowlist (only listed plugins load). `deny` wins.")

기존 13개 플러그인을 전부 `allow`에 다시 나열하고 `diagnostics-otel`을 추가하는 것으로 수정.

## 5. 2차 재시도 — 시작은 성공, 실행 중 재차 프리징

`plugins.allow` 수정 후 재시작 → 이번엔 시작 자체는 성공(모든 플러그인 정상 로드, 정상적으로 `ready` 도달, 웹챗 연결·API 호출 정상 응답).

그러나 이후 실행 중에 다시 대규모 이벤트 루프 정지 발생. 담당자가 연결을 끊은 시점에 그동안 버퍼링돼 있던 텔레메트리 배치가 한꺼번에 콜렉터로 플러시됨.

콜렉터 수신 데이터 핵심 내용:

- `openclaw.telemetry.exporter.events` (exporter=diagnostics-otel, signal=traces/metrics, status=started, reason=configured) — StartTimestamp 16:32:06 KST. 즉 익스포터 자체는 이 시점에 정상 기동.
- `openclaw.liveness.warning` 스팬 — Trace ID `4da3fc895a025504469c42a23380ce5e`, Span ID `9c96453f95f144b0`, Status: Error, message `event_loop_delay:event_loop_utilization:cpu`.
- `openclaw.liveness.event_loop_delay_p99_ms` = **366146ms(약 366초 = 6.1분)**, `event_loop_utilization` = 1(100%), `interval_ms` = 365960 — 즉 liveness 모니터 자신도 6분간 스스로를 체크하지 못할 정도로 프로세스 전체가 멎어있었음.
- 리소스 속성 정상 수신: `service.name: openclaw`, `host.name: DESKTOP-2EN6NM2`, `process.pid: 31292`, `process.runtime.name: nodejs` 등.
- 그 외 정상 메트릭도 함께 도착: `openclaw.memory.rss_bytes`(약 724MB), `openclaw.memory.heap_used_bytes`(약 389MB), `openclaw.gc.duration_ms`(GC 39회, 정상 범위 — GC가 원인은 아님).

## 6. 최종 판단

| 항목 | 결과 |
|---|---|
| OpenClaw → OTel Collector 전송 경로 | **검증 완료(정상)** — ResourceSpans/ResourceMetrics, Trace ID/Span ID, 리소스 속성 모두 정상 수신 |
| `diagnostics.otel` 설정만으로 활성화 가능 여부 | 불가 — `diagnostics-otel` 플러그인 별도 설치 + `plugins.allow` 등록 필요 |
| `plugins.allow` 동작 방식 | 화이트리스트(명시 안 하면 기존 플러그인도 제외) — 신규 플러그인 추가 시 기존 목록 전체를 함께 적어야 함 |
| `diagnostics-otel` 활성화 시 안정성 | **불안정** — 시작 단계·실행 중 모두에서 이벤트 루프가 최대 6분까지 블로킹. OpenClaw 자체 미해결 이슈(#152981)와 동일 패턴 |
| exemplar 연결 여부(마일스톤 0 본 질문) | **미확인** — 실제 "도구 호출→모델 응답" 시나리오까지 안정적으로 도달하지 못해 다음 주로 이월 |

## 7. 다음 단계 제안

1. 학교 게이트웨이 상시 운영본은 `diagnostics-otel` 비활성화 상태로 복구(완료).
2. 격리된 별도 테스트베드에서, 혹은 필요한 최소 시간만 켰다 바로 끄는 방식으로 exemplar 확인용 최소 시나리오("MCP 도구 1회 호출 → 모델 응답")만 빠르게 재시도.
3. `sampleRate`를 낮추거나(`1.0` → `0.2` 등) `flushIntervalMs`를 늘려서 블로킹 재현 여부가 달라지는지 확인 — 익스포터 자체의 동기 처리 부하 때문이라면 완화될 수 있음.
4. 플러그인 버전을 고정하거나 이전 버전으로 다운그레이드 가능한지 확인.
5. 안정화가 계속 안 되면 exemplar 판정은 `logging.file` 기반 수동 조인 경로(개발계획서 2.2절 4단계 대안)로 우회하는 것도 검토.

## 참고 링크

- [Set up OpenTelemetry export · OpenClaw](https://docs.openclaw.ai/gateway/opentelemetry/setup)
- [Configuration — MCP, skills, and plugins · OpenClaw](https://docs.openclaw.ai/gateway/config-extensions)
- [openclaw/extensions/diagnostics-otel · GitHub](https://github.com/openclaw/openclaw/tree/main/extensions/diagnostics-otel)
- [Issue #152981 — model runtime publication timed out](https://github.com/openclaw/openclaw/issues/152981)
- [Issue #139583 — 동일 타임아웃, 대형 설정](https://github.com/openclaw/openclaw/issues/139583)

---

# 9/22 재검증 — 마일스톤 0 최종 결론

**목적**: 9/21에 미확인으로 남았던 exemplar 연결 여부를 실제 "MCP 도구 1회 호출 → 모델 응답" 시나리오로 재검증.

**환경**: 동일 테스트베드(ssesa PC, DESKTOP-2EN6NM2), OpenClaw 2026.9.5, gateway `localhost:18789` (token 인증, loopback bind).

## 8. 진행 경과

1. 웹챗 컨트롤 UI(`http://localhost:18789`) 접속 — 이번엔 프리징 없이 정상 로드. 다만 게이트웨이 토큰 인증에서 초반에 `token_missing` → `token_mismatch`가 반복 발생(원인: 입력한 토큰 값이 실행 중인 프로세스의 것과 불일치 — `openclaw.json`의 `gateway.token` 필드를 신뢰하지 말고 `openclaw gateway auth-token --show`로 받은 값을 써야 함). 이 값으로 재입력 후 정상 연결.
2. 웹챗에 테스트 메시지 2회 전송 (`워크스페이스에 어떤 파일들이 있는지 확인해줘` 계열) → 둘 다 `fs__list_directory_with_sizes` MCP 도구 호출을 정상적으로 유발.
3. 콜렉터 콘솔(PowerShell, `otelcol.exe` 직접 실행 — Docker 미설치 환경)이 5초 flush 간격으로 너무 빨리 스크롤되어 육안 확인/복사가 사실상 불가능했음. 해결: 기존 프로세스 `Ctrl+C` 후

   ```powershell
   .\otelcol.exe --config=otel-collector-config.yaml 2>&1 | Tee-Object -FilePath "C:\Users\ssesa\.openclaw\otel-debug-log.txt"
   ```

   로 재기동해 콘솔 출력을 파일로 동시 캡처(스크롤 버벅임은 콜렉터/게이트웨이 문제가 아니라 터미널이 출력 속도를 못 따라가는 UI 현상으로 확인됨 — 실제 collector→gateway 간 이벤트 루프 블로킹은 재현되지 않음).
4. 캡처된 로그(약 16MB, 28만 줄 이상)를 UTF-16LE → UTF-8 변환 후 직접 분석.

## 9. 핵심 결과

### 9-1. 스팬 트레이스 연결 — 정상

두 번째 테스트 메시지 턴에서 아래 스팬들이 **동일한 TraceID**(`93aad0ab62cb43c4e84d08324eb29588`)로 묶여 있음을 확인:

| Span 이름 | Kind | 비고 |
|---|---|---|
| `openclaw.context.assembled` | Internal | Parent ID `3ce0ed27e161bf1f` |
| `openclaw.model.call` | Client | `gen_ai.*` 속성 포함, input 48292 / output 102 tokens (모델 API 호출 1회분) |
| `openclaw.tool.execution` | Internal | `fs__list_directory_with_sizes` (MCP, `bundle-mcp`) |
| `openclaw.model.usage` | Internal | 턴 전체 합산 input 96950 / output 540 tokens — 웹챗에 표시된 "출력 토큰 540개"와 정확히 일치 |
| `openclaw.message.processed` | Internal | 턴 종료, root span (Parent ID 없음) |

참고로 `openclaw.gateway.rpc.dispatch/handler/response` 계열 스팬(웹챗 UI의 RPC 통신 계층)은 이것과 별개로 호출마다 서로 다른 독립 TraceID를 가짐 — 원래 찾던 model/tool 스팬과는 무관.

### 9-2. Exemplar 연결 여부 — **연결 안 됨 (확인 완료)**

- 캡처된 로그 전체(28만 줄+)에서 `Exemplar` 문자열 매치 **0건**.
- `gen_ai.client.token.usage` 히스토그램 메트릭은 정상적으로 도착하지만(`HistogramDataPoints`, `Count`/`Sum`/`Min`/`Max`/`Buckets`까지 전부 출력됨), 그 어떤 데이터 포인트에도 `Exemplars` 필드 자체가 나타나지 않음.
- 즉 스팬 레벨 트레이스 연결(9-1)은 정상 동작하지만, 메트릭 쪽에는 그 트레이스를 가리키는 exemplar가 아예 기록되지 않고 있음. **exemplar 기반 metric↔trace 조인은 이 버전(2026.9.5)에서 사실상 작동하지 않는 것으로 판단.**

### 9-3. 부가 발견 — `gen_ai.client.token.usage` 카운트 정체 (버그 의심)

`gen_ai.client.token.usage` 메트릭이 세션 내내 `Count: 1` (input Sum 94925, output Sum 572 — 첫 번째 테스트 메시지분으로 추정)에서 전혀 갱신되지 않음. 두 번째 테스트 메시지(input 96950 / output 540, 스팬에는 정상 기록됨)가 이 메트릭에는 전혀 반영되지 않았음. exemplar 미연결과는 별개로, 메트릭 기록 경로 자체에 누락/버그가 있을 가능성.

## 10. 최종 판단 (업데이트)

| 항목 | 결과 |
|---|---|
| 웹챗 컨트롤 UI 안정성 | 이번 세션에서는 프리징 재현 안 됨(9/21 이슈와 별개로 안정적으로 동작) |
| 스팬 트레이스 연결(model.call/tool.execution/model.usage 등) | **정상** — 동일 턴 내 동일 TraceID로 정상 연결 확인 |
| exemplar 연결 여부(마일스톤 0 본 질문) | **미연결 확인** — 로그 전체에서 Exemplar 0건. metric↔trace 조인에 exemplar를 못 씀 |
| `gen_ai.client.token.usage` 메트릭 갱신 | **정체 의심** — 두 번째 턴 이후 값이 갱신 안 됨, 별도 원인 조사 필요 |

## 11. 다음 단계 제안 (업데이트)

1. exemplar 기반 조인은 폐기하고, 개발계획서 2.2절의 타임스탬프/속성 기반 수동 조인(순차 구간 diff 근사) 경로로 설계 확정.
2. `gen_ai.client.token.usage` 카운트 정체 현상은 별도로 재현/원인 조사 — 세션당 1회만 기록되는 것인지, 특정 조건에서 누락되는 버그인지 확인 필요.
3. 웹챗 로그인 시 `openclaw.json`의 `gateway.token` 필드를 그대로 신뢰하지 말고, 항상 `openclaw gateway auth-token --show`로 받은 현재 값을 사용하도록 팀 내 공유(문서화).
4. 콜렉터 콘솔은 verbosity=detailed + 짧은 flush interval 조합에서 사람이 육안으로 스크롤하며 보기 어려우므로, 앞으로는 처음부터 `Tee-Object`(또는 동급 리다이렉트)로 파일 캡처하며 진행.
