# agentscope-token-guard — OpenClaw 플러그인

토큰 파트의 OpenClaw 플러그인. 세 가지를 한다.

| 기능 | 훅 | 내용 |
|---|---|---|
| 결과 기록 + 토큰 계산 | `tool_result_persist` | 도구 결과의 크기·특징값을 기록하고, 토큰 계산 API로 결과마다 토큰 수를 센다. `agentscope-usage --tool-results`가 이 값으로 병렬·배치 구간 증가분을 나눈다(정확도 개선 방안 B) |
| 실시간 반영 | (토큰 계산 완료 시) | `otlpEndpoint`를 주면 결과별 토큰 수를 OTLP 스팬(`agentscope.tool_result.count`)으로 Collector에 보내, 커넥터가 병렬·배치 구간 배분을 대시보드에 바로 반영한다(아래) |
| 소비 브레이크 | `before_tool_call` | run·일 단위 누적 소비(결과 바이트, 센 토큰 수, 도구 호출 수, 같은 도구 연속 호출)를 기준과 비교해 경고 기록 / 승인 요구 / 차단 |

- **결과 내용은 저장하지 않는다.** 크기·글자 수·비ASCII 비율·이미지 픽셀 크기만 남긴다. 토큰 계산 시에는 결과 내용을
  토큰 계산 API로 보내지만(계산 후 버림) 기록하지 않는다.
- 결과 메시지는 바꾸지 않는다(`tool_result_persist`에서 아무것도 반환하지 않음).
- 기본값은 토큰 계산 꺼짐, 브레이크 `warn`(기록만)이라 설치만 해서는 에이전트 동작이 바뀌지 않는다.

## 설치 (테스트베드)

```bash
openclaw plugins install --link ./token-collector/plugin --force --accept-capabilities
openclaw plugins enable agentscope-token-guard
openclaw plugins inspect agentscope-token-guard --runtime --json   # 훅 등록 확인
```

`--accept-capabilities`가 없으면 설치 중 기능 동의를 묻는다. 명령을 여러 줄 한꺼번에 붙여 넣으면 다음 줄이 그 질문의 답으로 들어가 설치가 취소되므로(10.12 확인) 한 줄씩 실행한다.

두 훅 모두 대화 내용 접근 권한(`allowConversationAccess`)이 필요한 훅이 아니다(OpenClaw `docs/plugins/hooks.md`).

## 설정 (`openclaw.json`)

```json5
{
  plugins: {
    entries: {
      "agentscope-token-guard": {
        enabled: true,
        config: {
          // 기본: ~/.openclaw/agentscope/agentscope-tool-results.jsonl
          outputPath: "~/.openclaw/agentscope/agentscope-tool-results.jsonl",
          tokenCount: {
            enabled: true,
            api: "anthropic-count-tokens",          // 또는 "openai-usage"(아래)
            baseUrl: "https://api.anthropic.com",   // 토큰 계산 엔드포인트(POST /v1/messages/count_tokens)
            apiKeyEnv: "ANTHROPIC_API_KEY",          // 키는 환경 변수 이름만 적는다
            model: "claude-haiku-4-5",               // 테스트베드 모델과 같게
            maxResultChars: 400000                    // (선택) OpenClaw 결과 길이 제한과 같게
          },
          brake: {
            mode: "warn",                             // off | warn(기록만) | enforce(승인 요구·차단)
            run: { warn: { countedTokens: 20000 }, approve: { countedTokens: 50000 }, block: { sameToolStreak: 20 } },
            day: { block: { countedTokens: 2000000 } }
          }
        }
      }
    }
  }
}
```

**OpenAI 호환 게이트웨이(학교 게이트웨이 등)를 쓰는 경우**: 토큰 계산 API(count_tokens)가 없으므로(10.12 확인: 404)
`api: "openai-usage"`로 둔다. 게이트웨이에 `max_tokens: 1` 요청을 보내 응답의 `usage.prompt_tokens`로 센다
(10.12 학교 게이트웨이 확인: 단어 200개 추가 시 차이 199토큰). 요청을 실제로 보내므로 게이트웨이 단가·호출 제한을 확인한다.
이 방식은 텍스트 결과만 세고 이미지 블록은 세지 않는다(`skippedBlocks`).

```json5
tokenCount: { enabled: true, api: "openai-usage", baseUrl: "https://<게이트웨이>/v1/gateway",
              apiKeyEnv: "AGENTSCOPE_COUNT_KEY", model: "claude-haiku-4-5-20251001" }
```

기준값은 예시다. 테스트베드 정상 사용 데이터로 기준선을 만든 뒤 정하고, 처음에는 `warn`으로 오탐 수준을 확인한다.

**실시간 대시보드 반영(10.28)**: `config`에 Collector OTLP/HTTP 주소를 넣는다(OpenClaw `diagnostics.otel.endpoint`와 같은 Collector).

```json5
otlpEndpoint: "http://localhost:4318",   // /v1/traces는 자동으로 붙음. 없으면 보내지 않음(JSONL만)
otlpTimeoutMs: 5000
```

토큰 계산이 끝날 때마다 짧은 스팬 하나를 보낸다. trace id는 `before_tool_call`의 `ctx.trace.traceId`(OpenClaw 진단 trace)를
그대로 써서 Tempo에서 같은 요청 아래에 보인다. 속성은 `gen_ai.tool.call.id`, `openclaw.toolName`, `agentscope.counted_tokens`,
`agentscope.count.skipped_blocks`, `agentscope.count.source`뿐이고 결과 내용은 없다. 전송 실패는 `count_export_error`로 기록만 하고
에이전트 실행에는 영향이 없다. 커넥터 쪽 설정은 `count_wait`(기본 15초, `../collector/README.md`).

## 기록 형식 (JSONL, `v:1`)

| kind | 언제 | 주요 필드 |
|---|---|---|
| `tool_result` | 결과 저장 직전 | `toolCallId`, `runId`, `traceId`, `toolName`, `textBytes`, `textChars`, `nonAsciiRatio`, `images[{mimeType,bytes,width,height}]`, `isError`, `isSynthetic` |
| `token_count` | 토큰 계산 완료 | `toolCallId`, `traceId`, `countedTokens`(= T_i − T_0), `probeTotal`, `probeBaseline`, `model`, `source`(계산 방식), `skippedBlocks`(세지 못한 블록 수. 0보다 크면 `agentscope-usage`가 배분에 쓰지 않음), `durationMs` |
| `token_count_error` | 토큰 계산 실패 | `toolCallId`, `error`(200자 이내) |
| `count_export_error` | Collector 전송 실패(`otlpEndpoint` 설정 시) | `toolCallId`, `traceId`, `error`(200자 이내) |
| `brake` | 기준 초과 | `level`(warn/approve/block), `mode`, `enforced`, `reasons[{scope,metric,value,limit}]`, `run` 누적값 |
| `brake_resolution` | 승인 요구 응답 | `decision`(allow-once/allow-always/deny/timeout/cancelled) |

토큰 계산 방식: 결과 하나만 담은 최소 요청(`user` → `assistant tool_use` → `user tool_result`)의 입력 토큰 수 T_i에서
결과 내용을 비운 같은 요청의 T_0(모델별 1회)을 뺀다. tool_result 형식 토큰까지 포함한 결과 몫이다.

## 테스트

```bash
node --test test/*.test.ts      # Node 22.18 이상(TypeScript 타입 제거 실행)
```

가짜 토큰 계산 서버로 요청 형식·기준값 재사용·실패 처리, 크기 측정(PNG·JPEG·GIF·WebP 헤더), 결과 내용 미기록,
브레이크 단계(warn은 개입 안 함, 승인 후 같은 run 재질문 안 함, 차단 유지, 일 단위 누적), 가짜 Collector로
OTLP 본문 형식(trace id 연결, 결과 내용 없음)과 전송 실패 처리를 확인한다.

## 테스트베드에서 확인할 것

- 모델 백엔드에 맞는 계산 방식(`api`)과 키. Anthropic 직접 연결이면 `anthropic-count-tokens`, 학교 게이트웨이 같은 OpenAI 호환 중계 서버면 `openai-usage`(10.12 PC에서 확인).
- `tool_result_persist`가 다음 model.call 전에 호출되는지, 병렬 실행 시 결과마다 호출되는지.
- OpenClaw는 이 훅 뒤에 결과 길이 제한(cap)을 적용한다. 제한에 걸리는 큰 결과는 `maxResultChars`를 같은 값으로 맞춘다.
- 웹채팅에서 승인 요구 화면이 표시·처리되는지(`requireApproval`은 응답이 없으면 거부).
