# agentscope-token-guard — OpenClaw 플러그인

토큰 파트의 OpenClaw 플러그인. 두 가지를 한다.

| 기능 | 훅 | 내용 |
|---|---|---|
| 결과 기록 + 토큰 계산 | `tool_result_persist` | 도구 결과의 크기·특징값을 기록하고, 토큰 계산 API로 결과마다 토큰 수를 센다. `agentscope-usage --tool-results`가 이 값으로 병렬·배치 구간 증가분을 나눈다(정확도 개선 방안 B) |
| 소비 브레이크 | `before_tool_call` | run·일 단위 누적 소비(결과 바이트, 센 토큰 수, 도구 호출 수, 같은 도구 연속 호출)를 기준과 비교해 경고 기록 / 승인 요구 / 차단 |

- **결과 내용은 저장하지 않는다.** 크기·글자 수·비ASCII 비율·이미지 픽셀 크기만 남긴다. 토큰 계산 시에는 결과 내용을
  토큰 계산 API로 보내지만(계산 후 버림) 기록하지 않는다.
- 결과 메시지는 바꾸지 않는다(`tool_result_persist`에서 아무것도 반환하지 않음).
- 기본값은 토큰 계산 꺼짐, 브레이크 `warn`(기록만)이라 설치만 해서는 에이전트 동작이 바뀌지 않는다.

## 설치 (테스트베드)

```bash
openclaw plugins install --link ./token-collector/plugin --force
openclaw plugins enable agentscope-token-guard
openclaw plugins inspect agentscope-token-guard --runtime --json   # 훅 등록 확인
```

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

기준값은 예시다. 테스트베드 정상 사용 데이터로 기준선을 만든 뒤 정하고, 처음에는 `warn`으로 오탐 수준을 확인한다.

## 기록 형식 (JSONL, `v:1`)

| kind | 언제 | 주요 필드 |
|---|---|---|
| `tool_result` | 결과 저장 직전 | `toolCallId`, `runId`, `toolName`, `textBytes`, `textChars`, `nonAsciiRatio`, `images[{mimeType,bytes,width,height}]`, `isError`, `isSynthetic` |
| `token_count` | 토큰 계산 완료 | `toolCallId`, `countedTokens`(= T_i − T_0), `probeTotal`, `probeBaseline`, `model`, `durationMs` |
| `token_count_error` | 토큰 계산 실패 | `toolCallId`, `error`(200자 이내) |
| `brake` | 기준 초과 | `level`(warn/approve/block), `mode`, `enforced`, `reasons[{scope,metric,value,limit}]`, `run` 누적값 |
| `brake_resolution` | 승인 요구 응답 | `decision`(allow-once/allow-always/deny/timeout/cancelled) |

토큰 계산 방식: 결과 하나만 담은 최소 요청(`user` → `assistant tool_use` → `user tool_result`)의 입력 토큰 수 T_i에서
결과 내용을 비운 같은 요청의 T_0(모델별 1회)을 뺀다. tool_result 형식 토큰까지 포함한 결과 몫이다.

## 테스트

```bash
node --test test/*.test.ts      # Node 22.18 이상(TypeScript 타입 제거 실행)
```

가짜 토큰 계산 서버로 요청 형식·기준값 재사용·실패 처리, 크기 측정(PNG·JPEG·GIF·WebP 헤더), 결과 내용 미기록,
브레이크 단계(warn은 개입 안 함, 승인 후 같은 run 재질문 안 함, 차단 유지, 일 단위 누적)를 확인한다.

## 테스트베드에서 확인할 것

- 토큰 계산 API에 접근 가능한지(엔드포인트·키). 학교 게이트웨이 같은 중계 서버는 지원하지 않을 수 있다.
- `tool_result_persist`가 다음 model.call 전에 호출되는지, 병렬 실행 시 결과마다 호출되는지.
- OpenClaw는 이 훅 뒤에 결과 길이 제한(cap)을 적용한다. 제한에 걸리는 큰 결과는 `maxResultChars`를 같은 값으로 맞춘다.
- 웹채팅에서 승인 요구 화면이 표시·처리되는지(`requireApproval`은 응답이 없으면 거부).
