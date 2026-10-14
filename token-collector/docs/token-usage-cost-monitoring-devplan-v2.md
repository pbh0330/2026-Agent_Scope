# 토큰 사용량 수집·비용 모니터링 개발계획서

**프로젝트**: AI 에이전트 보안 자산 식별·가시화 기술 개발
**담당 파트**: 토큰 사용량 수집 · 비용 모니터링
**작성자**: 정철
**작성일**: 2026-09-20 (11월 중순 완성으로 일정 재조정)
**최종 수정**: 2026-09-21 (1주차 마일스톤 0 중간 점검 결과 반영 — 3.1절)
**목표 완성 시점**: 2026-11-15

---

## 1. 접근 방식

### 1.1 문제 정의

OpenClaw 공식 텔레메트리는 토큰(`openclaw.tokens`, `gen_ai.client.token.usage`)과 비용(`openclaw.cost.usd`)을 채널·프로바이더·모델·에이전트 단위까지만 분해하고, **도구·MCP 서버 단위로는 분해하지 않는다.** 도구 실행 자체는 `openclaw.tool.execution` 스팬으로 기록되지만 여기엔 토큰/비용이 없고 소요 시간·차단 여부만 있다. 이 간극 — "얼마나 썼는지는 알아도 무엇 때문에 썼는지는 모른다" — 를 메우는 것이 이번 파트의 목표다.

생태계 조사 결과 SigNoz, ClawHosters, henrikrexed 관측 플러그인 등 어디에도 이 간극을 메운 사례가 없다(4절 참고). ClawHosters 가이드는 "토큰·비용은 개별 호출이 아니라 턴 단위로 집계된다"고 한계를 그대로 인정하고 있다. 즉 이건 미해결 문제이고, 우리 프로젝트의 실질적 차별화 지점이다.

### 1.2 기본 방향: 하이브리드 귀속

풀 방법을 하나로 정하지 않는다. **같은 run(트레이스) 안에서도 구간에 따라 귀속 가능 여부가 다르기 때문에, 구간 단위로 판별해서 두 방법을 섞어 쓴다.**

- **순차 구간** (도구 호출 → 결과 → 모델 호출이 한 줄로 이어지는 경우): 모델 호출 스팬의 토큰 증분을 직전 도구 실행의 기여분으로 근사 귀속한다 (기존 "대안 B: 스팬 계층 근사").
- **병렬/배치 구간** (도구 호출 여러 개가 겹치거나 몰려 있는 경우): 어느 도구 때문에 토큰이 늘었는지 순서로 가를 수 없으므로, `duration_ms`·`blocked`·`loop` 같은 대리 지표로 "얼마나 쓰였는가"만 표시한다 (기존 "대안 A: 대리 지표").

정밀 귀속과 대리 지표를 프로젝트 시작 시점에 양자택일하는 게 아니라, **파이프라인이 매 run/매 구간마다 자동으로 판별해서 둘 중 맞는 걸 적용**하는 게 이번 설계의 핵심이다 (2절 참고).

### 1.3 검증 우선

위 설계가 실제로 구현 가능한지는 전제 하나에 달려 있다 — 토큰 메트릭이 트레이스(스팬)와 exemplar로 연결되는지, 이게 공식 문서에 명시되어 있지 않다. 그래서 설계를 확정하기 전에 **1주차에 직접 검증(마일스톤 0)** 부터 한다. 검증 결과에 따라 1.2절의 구현 난이도가 달라진다(3절).

---

## 2. 최종 진행 로직

### 2.1 파이프라인 개요

```
OpenClaw Gateway (diagnostics-otel 플러그인)
        │  OTLP/HTTP protobuf
        ▼
   OTel Collector
   ├─▶ Prometheus 익스포트 (9464) ──▶ Grafana 대시보드 (코어 메트릭, 예산 알림)
   └─▶ 커스텀 프로세서 (이번 파트가 만드는 부분)
           1) 같은 traceId 내 스팬 나열 (tool.execution / model.call)
           2) 패턴 판별: 순차 / 병렬 / 배치
           3) 순차 구간 → diff 기반 근사 귀속
              병렬·배치 구간 → 대리 지표 폴백
           4) 단가표(models.providers.<provider>.models[].cost) 적용해 근사 비용 환산
           5) "근사 귀속(추정)" 지표로 별도 저장/노출
```

### 2.2 단계별 로직

1. **스팬 수집**: OTel Collector가 `openclaw.harness.run → openclaw.run → {openclaw.model.call, openclaw.tool.execution}` 계층의 스팬을 traceId 기준으로 모은다.
2. **패턴 판별** (이번 개발의 핵심 로직):
   - **시간 겹침 체크**: 같은 부모(`openclaw.run`) 아래 `tool.execution` 스팬들의 [시작, 종료] 구간이 겹치는가? → 겹치면 **병렬**.
   - **모델 호출 사이 도구 개수 체크**: 연속된 두 `model.call` 스팬 사이에 `tool.execution`이 몇 개인가? 1개 → **순차**, 2개 이상 → **배치**.
   - 판정 결과(순차/병렬/배치)를 태그로 남겨, 이후 정확도 검증(마일스톤 3)에서 패턴별로 나눠 평가할 수 있게 한다.
3. **귀속 계산**:
   - 순차로 판정된 구간: 해당 `model.call`의 입력 토큰에서 직전 `model.call` 대비 증분을 계산 → 그 사이에 끝난 `tool.execution`의 근사 소비량으로 기록.
   - 병렬·배치로 판정된 구간: 토큰/비용은 에이전트·모델 단위로만 표시하고, 도구별로는 `duration_ms`/`blocked`/`loop` 카운트만 표시.
4. **연결 방식** (마일스톤 0 결과에 따라 분기):
   - exemplar가 확인되면: 메트릭 데이터포인트의 exemplar(traceId/spanId)로 직접 스팬과 조인.
   - exemplar가 안 되면: `logging.file`의 타임스탬프 + traceId로 수동 조인(정확도는 떨어지지만 구현 가능).
5. **비용 환산**: 근사 토큰 수치에 `models.providers.<provider>.models[].cost`(입력/출력/캐시 단가, USD/1M 토큰)를 그대로 곱해 근사 비용을 낸다 — 별도 가격 정책을 만들지 않고 기존 설정을 재사용.
6. **표시**: Grafana 대시보드에 "근사 귀속(추정)"과 "실측 귀속(에이전트/모델 단위)"을 시각적으로 구분해서 표시. 근사치를 실측처럼 보여주지 않는다.
7. **자산 그래프 통합**: 위 결과를 자산 인벤토리(도구/MCP 서버 정점)의 "사용" 축 속성으로 연결해, 다른 파트(박병하 2.2/2.3절)의 자산 그래프에서 바로 조회 가능하게 한다.

---

## 3. 문제점

| 문제 | 내용 | 대응 |
|---|---|---|
| exemplar 연결 여부 미확인 | 메트릭(토큰)과 스팬(트레이스)이 traceId로 실제 연결되는지 공식 문서에 명시 없음 | 마일스톤 0에서 OTel Collector debug 로그로 직접 검증 후 설계 분기 |
| CLI 백엔드 해상도 저하 | Claude Code CLI 계열은 턴을 단일 합성 스팬으로 내보내 내부 모델 요청을 숨김(`observation_unit=turn`) | 테스트베드를 임베디드(native) 모드로 고정, CLI 백엔드는 "턴 단위 근사까지만 지원"으로 범위 명시 |
| 병렬/배치 구간 근사 오차 | 시간 겹침·다중 도구 구간은 diff 근사가 부정확 | 판별 로직으로 미리 걸러내 대리 지표로 폴백, 근사치는 대시보드에서 "추정"으로 별도 표시 |
| Prometheus exemplar 노출 누락 | Collector까지는 exemplar가 도착해도 Prometheus `/metrics` 단에서 누락되는 사례가 다수 보고됨(미해결 이슈) | 1차 판정은 Prometheus가 아니라 Collector의 debug 익스포터 원시 로그로 수행 |
| 판별 로직 자체의 정확도 불확실 | 시간 겹침/도구 개수 체크가 실제 현장에서 얼마나 정확할지 검증 안 됨 | 마일스톤 3에서 ReAct 테스트베드로 오차율 실측, 정기 재검증 |
| **[9/21 신규]** `diagnostics-otel` 활성화 시 게이트웨이 이벤트 루프 블로킹 | 익스텐션을 켜면 게이트웨이가 시작 단계·실행 중 모두에서 수 분(최대 관측 366초)간 완전히 멈춤. OpenClaw 자체 미해결 이슈(#152981, #139583)와 동일 패턴 — 우리 환경 고유 문제가 아니라 2026.9.5 빌드의 알려진 버그로 추정 | 상시 운영 환경에는 비활성화 유지. 마일스톤 0 시나리오 테스트는 격리된 테스트베드에서 단발성으로만 재시도 (3.1절) |

### 3.1 마일스톤 0 중간 점검 (9/21)

1주차 마일스톤 0(exemplar 연결 여부 판정)을 위해 테스트베드에 `diagnostics.otel` 설정을 우선 반영해봤다. 결과는 절반의 검증 — **파이프라인 자체는 살아있음을 확인했지만, 핵심 시나리오("MCP 도구 1회 호출 → 모델 응답" 후 exemplar 확인)는 안정성 문제로 아직 실행하지 못함.**

**확인된 것**

- `diagnostics.otel` 설정 블록만으로는 동작하지 않는다. `diagnostics-otel`은 게이트웨이 코어 기능이 아니라 별도 익스텐션(플러그인)이라, `openclaw plugins install clawhub:@openclaw/diagnostics-otel` 설치와 `plugins.allow`/`plugins.entries` 등록이 별도로 필요했다 (출처: [Set up OpenTelemetry export](https://docs.openclaw.ai/gateway/opentelemetry/setup)).
- `plugins.allow`는 화이트리스트로 동작한다. 목록에 `diagnostics-otel` 하나만 넣으면 기존에 쓰던 anthropic/browser 등 번들 플러그인 전부가 함께 빠진다 — 새 플러그인을 추가할 때는 기존 플러그인을 전부 같이 나열해야 함 (출처: [Configuration — MCP, skills, and plugins](https://docs.openclaw.ai/gateway/config-extensions)).
- 설정을 바로잡은 뒤에는 콜렉터가 `ResourceSpans`/`ResourceMetrics`를 정상 수신했다. `service.name: openclaw`, 호스트/프로세스 리소스 속성, 실제 Trace ID·Span ID가 실린 스팬, `openclaw.tokens`류는 아니지만 `openclaw.telemetry.exporter.events`(exporter=diagnostics-otel, status=started, reason=configured) 등 진단 메트릭까지 확인 — **OpenClaw → Collector 전송 경로 자체는 정상 동작함이 검증됐다.**

**막힌 것**

- `diagnostics-otel`을 켠 상태에서 게이트웨이 시작 시 `sidecars.model-runtime` 단계가 멈추며 `prepared model runtime publication (workspace plugins; agent main) timed out` 에러로 실패하는 현상을 반복 재현했다. 이벤트 루프 지연이 168초, 이후 재시도에서는 실행 중에 366초(약 6분)까지 관측됨 — Ctrl+C 같은 신호 처리조차 지연될 정도로 게이트웨이 전체가 멈춘다.
- 동일 증상이 OpenClaw 저장소의 미해결 이슈로도 보고돼 있다(원인 미특정, 해결책 없음): [#152981](https://github.com/openclaw/openclaw/issues/152981), [#139583](https://github.com/openclaw/openclaw/issues/139583).
- 이 때문에 "도구 호출 → 모델 응답" 실제 시나리오까지는 안정적으로 못 갔고, exemplar Yes/No 판정은 다음 주로 이월.

**다음 주 진행 방향**

1. 학교 게이트웨이 상시 운영본에는 `diagnostics-otel`을 비활성화 상태로 되돌려 둔 채 유지 (완료).
2. 격리된 별도 테스트베드(또는 짧은 시간만 켰다 끄는 방식)에서 exemplar 확인용 최소 시나리오만 빠르게 실행해 마일스톤 0을 마저 완료.
3. `sampleRate`/`flushIntervalMs` 조정이나 플러그인 버전 고정이 블로킹 재현에 영향을 주는지 추가로 확인.
4. 안정화가 계속 안 되면, exemplar 판정용으로는 `diagnostics-otel` 대신 `logging.file` 기반 수동 조인 경로(2.2절 4단계 대안)로 먼저 넘어가는 것도 검토.

상세 트러블슈팅 로그는 별도 파일(`0921_diagnostics-otel_검증로그.md`) 참고.

---

## 4. 로직 근거

### 4.1 공식 텔레메트리 재검증

| 메트릭/스팬 | 종류 | 속성(attrs) | 도구/MCP 서버 귀속 |
|---|---|---|---|
| `openclaw.tokens` | 메트릭(counter) | `openclaw.token`, `openclaw.channel`, `openclaw.provider`, `openclaw.model`, `openclaw.agent` | 불가 |
| `gen_ai.client.token.usage` | 메트릭(histogram) | `gen_ai.token.type`, `gen_ai.provider.name`, `gen_ai.operation.name`, `gen_ai.request.model` | 불가 |
| `openclaw.cost.usd` | 메트릭(counter) | `openclaw.channel`, `openclaw.provider`, `openclaw.model` | 불가 |
| `openclaw.tool.execution` | 스팬 | `gen_ai.tool.name`, `openclaw.toolName`, `openclaw.tool.source`, `openclaw.tool.owner` | **가능** |

→ 메트릭에는 도구 정보가 없고 스팬에는 있다는 게 1.2절 하이브리드 설계의 출발점. (출처: [Model calls and exported metrics](https://docs.openclaw.ai/gateway/opentelemetry/model-calls-and-metrics), [Exported spans and diagnostic events](https://docs.openclaw.ai/gateway/opentelemetry/spans-and-events))

`openclaw.harness.run → openclaw.run → {model.call, tool.execution}`이 같은 traceId를 공유한다는 것도 공식 문서로 확인됨 — 2.2절의 "같은 trace 내 스팬 나열" 단계가 성립하는 근거. (출처: [OpenTelemetry export](https://docs.openclaw.ai/gateway/opentelemetry))

비용은 실측이 아니라 `models.providers.<provider>.models[].cost`(입력/출력/캐시 단가) 설정으로 추정되므로, 2.2절 5단계에서 이 단가표를 그대로 재사용하는 게 타당함. (출처: [Token use and costs](https://openclaw-docs.beaverslab.xyz/en/reference/token-use))

### 4.2 생태계 조사 — 아무도 안 풀었다

| 사례 | 제공 | 미제공 |
|---|---|---|
| ClawHosters (OTel+Prometheus+Grafana) | 코어 메트릭 대시보드, 예산 알림 | "토큰·비용은 턴 단위로만 집계"라고 명시 — 도구별 세분화 없음 |
| henrikrexed 관측 플러그인 | `openclaw.request → agent.turn → tool.Read` 트레이스 트리를 도구 단위까지 깊게 만듦 | 트레이스 트리와 토큰 메트릭을 잇는 대시보드/exemplar 상관관계 미구현 |
| SigNoz / Comet(Opik) | 트레이스 시각화, 세션 단위 모니터링 | 도구/자산 단위 비용 귀속 없음 |

→ 트레이스를 도구 단위로 쪼개는 것(플러그인)과 토큰/비용 메트릭(코어)은 각각 존재하지만, 둘을 잇는 작업이 없다는 게 확인됨. 1.1절의 "차별화 지점" 주장의 근거.

### 4.3 판별 로직(2.2절 2단계) 근거

같은 부모 스팬 아래 자식 스팬들은 Span ID/Parent Span ID로 부모-자식 관계가 재구성되고, 각 스팬은 시작·종료 시각을 갖는다(공식 문서 기준 스팬 구조). 따라서:

- 두 스팬의 [시작,종료] 구간이 겹치지 않고 시간순으로 이어지면 "동시에 실행되지 않았다"는 뜻이므로 순차로 판정하는 게 타당하다.
- 두 `model.call` 사이의 `tool.execution` 개수는 "이 모델 호출 직전에 도구가 몇 번 불렸는가"를 그대로 반영하므로, 1개면 명확히 그 도구 때문이라고 볼 근거가 되고 2개 이상이면 어느 것 때문인지 알 수 없다.

다만 이 판별 기준의 실제 정확도(오탐/누락률)는 검증된 바 없어 3절 리스크로 남겨두고, 마일스톤 3에서 실측 검증한다.

---

## 5. 주차별 진행 작업

목표 완성 시점을 11/30 → **11/15(중순)**로 앞당기면서, 원래 11주 계획을 8주로 압축했다. 순서는 그대로 두고 인접 단계를 묶어서 기간만 줄인 것 — 버퍼와 일부 정교화 작업이 줄어드는 대신 핵심 로직(마일스톤 0~순차 근사~정확도 검증)의 순서와 내용은 그대로 유지된다.

역할 분담: **테스트베드(OpenClaw 실행 환경) 구축은 팀원 담당**, 본 파트(정철)는 텔레메트리 설계·검증·파이프라인 구현 담당.

| 주차 | 기간 | 이번 주 할 일 | 체크포인트 |
|---|---|---|---|
| 1 | 9/20~9/26 | **[마일스톤 0]** 팀원에게 `diagnostics.otel` 설정값 전달, 검증용 OTel Collector debug 설정 준비, "MCP 도구 1회 호출→모델 응답" 최소 시나리오 요청 → 결과 로그에서 `gen_ai.client.token.usage`에 exemplar가 붙는지, Trace ID가 `model.call` 스팬과 일치하는지 판정. **(9/21 진행: 파이프라인 연결 자체는 검증 완료, 안정성 문제로 시나리오 테스트는 이월 — 3.1절 참고)** | exemplar 연결 Yes/No 판정 → 2.2절 4단계 분기 확정 |
| 2 | 9/27~10/3 | OTel Collector + Prometheus + Grafana 파이프라인 구축, `diagnostics.otel` 설정 확정(`sampleRate`/`flushIntervalMs`, `captureContent:false`) + 코어 메트릭(`openclaw.cost.usd`, `openclaw.tokens`, `openclaw.run.duration_ms`) 기본 대시보드까지 완성 | 파이프라인 기동 + 기본 대시보드 시연 |
| 3 | 10/4~10/10 | 같은 traceId 내 `tool.execution`/`model.call` 스팬 나열 스크립트(2.2절 1단계) + **패턴 판별 로직(2.2절 2단계: 시간 겹침 체크, 모델 호출 사이 도구 개수 체크)** 구현 | **중간 공유 1**: 파이프라인·대시보드·순차/병렬/배치 자동 태깅 팀 리뷰 |
| 4 | 10/11~10/17 | 순차 구간 diff 기반 근사 알고리즘 구현(2.2절 3단계) | 알고리즘 1차 버전 |
| 5 | 10/18~10/24 | ReAct 패턴 테스트베드(임베디드 모드 고정)에서 정확도 검증, 패턴 판별 로직의 오탐/누락률까지 함께 측정 | **중간 공유 2**: 근사 알고리즘 + 판별 로직 오차율 팀 리뷰 |
| 6 | 10/25~10/31 | 병렬/배치 구간 대리 지표 폴백 로직 구현, 하이브리드 귀속 통합(2.2절 전체) | 하이브리드 귀속 v1 완성 |
| 7 | 11/1~11/7 | 비용 대시보드(근사 vs 실측 구분 표시, 2.2절 6단계) + 예산 초과 알림 + 자산 그래프 "사용" 축 통합(2.2절 7단계) | 대시보드 데모 + 자산 그래프 연동 확인 |
| 8 | 11/8~11/15 | 전체 통합 테스트, 최종 보고서 작성, 팀 공유/발표 준비 | **최종 완료 (11/15)** |

※ 일정이 밀릴 경우: 귀속 로직 자체(1~5주차, 마일스톤 0~정확도 검증)는 프로젝트 핵심이므로 사수하고, 병렬 폴백 정교화·대시보드 UI(6~7주차)를 먼저 축소해 11/15을 맞춘다. 8주 압축안이라 버퍼가 거의 없으므로, 중간 공유 1·2에서 지연이 확인되면 그 시점에 바로 범위를 줄이는 판단이 필요하다.

---

## 출처

- [OpenTelemetry export · OpenClaw](https://docs.openclaw.ai/gateway/opentelemetry)
- [Model calls and exported metrics · OpenClaw](https://docs.openclaw.ai/gateway/opentelemetry/model-calls-and-metrics)
- [Exported spans and diagnostic events · OpenClaw](https://docs.openclaw.ai/gateway/opentelemetry/spans-and-events)
- [OpenTelemetry configuration · OpenClaw](https://docs.openclaw.ai/gateway/opentelemetry/configuration)
- [Configuration — audit, logging, diagnostics, and telemetry · OpenClaw](https://docs.openclaw.ai/gateway/config-observability)
- [Diagnostics export · OpenClaw](https://docs.openclaw.ai/gateway/diagnostics)
- [Token use and costs · OpenClaw Docs (beaverslab)](https://openclaw-docs.beaverslab.xyz/en/reference/token-use)
- [AI Observability for OpenClaw: OTel + Grafana · ClawHosters](https://clawhosters.com/blog/posts/openclaw-ai-observability-monitoring-guide)
- [LLM Observability for OpenClaw Monitoring · ClawHosters](https://clawhosters.com/blog/posts/openclaw-monitoring-opentelemetry-prometheus-grafana)
- [OpenClaw Observability Plugin (henrikrexed)](https://henrikrexed.github.io/openclaw-observability-plugin/getting-started/)
- [Set up OpenTelemetry export · OpenClaw](https://docs.openclaw.ai/gateway/opentelemetry/setup)
- [Configuration — MCP, skills, and plugins · OpenClaw](https://docs.openclaw.ai/gateway/config-extensions)
- [Gateway startup hangs at sidecars.model-runtime, "prepared model runtime publication timed out" · Issue #152981](https://github.com/openclaw/openclaw/issues/152981)
- [gateway startup fails with "prepared model runtime publication timed out" on large config · Issue #139583](https://github.com/openclaw/openclaw/issues/139583)
