# usageapi — 토큰 사용 현황 API (`agentscope-usage-api`)

대시보드 UI(PR #13)의 Token Usage 화면과 자산 그래프·상세의 사용량 표시에 쓰는 읽기 전용 HTTP API.
계산은 usage.json과 같다(`usagereport.Build`). 메트릭(Prometheus)에는 호출 단위 기록과 자산 ID가 없어서
원본 스팬 파일에서 다시 계산한다.

| 모드 | 언제 | 동작 |
|---|---|---|
| 고정 응답(기본) | 개발·UI 연동 확인 | 시작할 때 스팬 파일을 한 번 읽고 그 구간의 기록으로 답한다. range 기준 시각 = 데이터 구간 끝 |
| 실시간(`--live`) | 테스트베드(tb-gw) | 입력 파일(로테이션 포함)이 바뀌면 다시 계산한다(기본 15초마다 확인, 최근 7일). range 기준 시각 = 현재 |

- 실시간 모드에서 다시 읽기가 실패하면 이전 데이터로 계속 답하고 health가 `degraded`와 `last_error`를 보여 준다.
- Collector가 쓰는 중인 마지막 줄(줄바꿈 전)은 건너뛰고 다음 확인 때 읽는다.
- 남은 일: 스캐너 InventorySnapshot으로 자산 ID 연결 확인(테스트베드 데이터), UI 타입(PR #13 src)에 필드 맞추기.

## 실행

```bash
cd token-collector/backend/usageapi
go run ./cmd/agentscope-usage-api --env env-pc --profile profile-pc \
  --input testdata/pc-1029.traces.jsonl
# 고정 응답 모드: 기록 16건, 구간 2026-10-29T05:24:02Z ~ 2026-10-29T05:29:03Z, http://127.0.0.1:8088/api/v1/usage/health

# 테스트베드(실시간): deploy/testbed/agentscope-usage-api.service가 이렇게 띄운다
agentscope-usage-api --live --env env-testbed --profile profile-snap2-p2t \
  --input '~/agentscope/data/agentscope-traces*.jsonl' \
  --tool-results ~/.openclaw/agentscope/agentscope-tool-results.jsonl --addr 0.0.0.0:8088
```

| 옵션 | 설명 |
|---|---|
| `--input` | 스팬 파일(OTLP JSON 줄 단위). 여러 번 지정 가능, `*` 패턴 가능(로테이션된 파일 포함) |
| `--env`, `--profile` | environment_id, profile_id(필수, 스냅샷과 같아야 매핑됨) |
| `--tool-results` | 결과 기록 플러그인 JSONL(선택). 토큰 수(스팬 파일 안의 값보다 우선)와 소비 브레이크 기록을 읽음 |
| `--inventory` | InventorySnapshot(선택). 없으면 전부 unmatched |
| `--openclaw-config` | 단가를 읽을 openclaw.json(선택). 단가가 0이거나 없으면 공식 정가(참고용) |
| `--from`, `--to` | 고정 모드의 데이터 구간(선택). 없으면 데이터에서 잡음 |
| `--live` | 실시간 모드. 입력 파일이 아직 없어도 시작(0건) |
| `--reload-interval` | 실시간: 변경 확인 주기(기본 `15s`) |
| `--retain` | 실시간: 현재 기준 계산 범위(기본 `7d`, 최대 7d) |
| `--default-range` | 실시간: 인자 없는 요청의 조회 구간(기본 `1h`) |
| `--addr` | 기본 `127.0.0.1:8088`(그 PC 안에서만). 테스트베드는 `0.0.0.0:8088`(NAT 안이라 호스트 PC에서만 접속) |

UI(Vite 개발 서버)에서는 프록시로 붙인다.

```ts
// vite.config.ts
export default defineConfig({
  server: { proxy: { '/api': 'http://127.0.0.1:8088' } },
})
```

## API

모두 GET, JSON. 다른 메서드는 405, 잘못된 인자는 400(`{"error": "..."}`).

| 경로 | 화면 | 내용 |
|---|---|---|
| `/api/v1/usage/summary` | Token Usage 상단 카드, Overview | 호출 수, 귀속 토큰, 추정 비용, 순차 실측/병렬 배분/계산 못 함, 자산 연결 상태, 데이터 품질 |
| `/api/v1/usage/by-asset` | 자산별 사용량, Asset Graph 노드 크기 | 묶음별 합계, 점유율(share), 상대값(relative, 최대 = 1), 마지막 사용 시각·trace_id |
| `/api/v1/usage/records` | 최근 호출 목록 | 호출 단위 기록(최신순), trace_id(실행 기록 이동), 근거 |
| `/api/v1/usage/timeseries` | 시간대 차트 | 구간(step)별 토큰·호출 수, 묶음별 시리즈 + 합계 |
| `/api/v1/usage/assets/{asset_id}` | Asset Detail | 자산 하나의 사용량, runtime(사용 여부·마지막 사용), 최근 호출 10건 |
| `/api/v1/usage/brake-events` | 실행 제한 기록 | 소비 브레이크 경고·승인 요청·차단, 승인 응답, trace_id |
| `/api/v1/usage/health` | 상태 표시 | 모드, 상태(ok / degraded / loading), 데이터 구간, 입력 파일 이름, 배분 근거 누락 수, 마지막 오류 |

### 공통 인자

| 인자 | 예 | 설명 |
|---|---|---|
| `range` | `15m`, `1h`, `24h`, `7d` | 기준 시각부터 거꾸로. 기준 시각: 고정 모드는 데이터 구간 끝, 실시간 모드는 현재 |
| `from`, `to` | `2026-10-29T05:26:00Z` | RFC3339. 도구 시작 시각 기준 [from, to). `range`와 함께 못 씀 |
| (없음) | | 고정 모드: 데이터 구간 전체 / 실시간 모드: 최근 `--default-range`(기본 1시간) |

조회 구간은 최대 7일. 모든 응답에 `window`와 `estimated: true`가 들어간다.

### summary

```json
{ "window": {"start": "2026-10-29T05:24:02.000Z", "end": "2026-10-29T05:29:03.000Z"},
  "estimated": true, "calls": 16, "attributed_tokens": 15769, "estimated_cost_usd": 0.015769,
  "pricing": {"currency": "USD", "sources": ["reference_list_price"]},
  "by_method": { "sequential":   {"calls": 3,  "tokens": 2268},
                 "allocated":    {"calls": 13, "tokens": 13501},
                 "not_computed": {"calls": 0} },
  "by_mapping": {"matched": 0, "ambiguous": 0, "unmatched": 16},
  "data_quality": {"missing_counts": 0, "not_computed": 0, "negative_delta": 0,
                   "calls_without_cost": 0, "inventory_snapshot_id": null} }
```

- `sequential`: 순차 구간 실측(앞뒤 모델 호출 입력 차이). `allocated`: 병렬·배치 구간 증가분을 나눈 값(결과마다 고정분 k를 먼저 주고 나머지를 결과별 토큰 수 비율로, 구간 합계 보존)
- `not_computed`: 토큰을 계산하지 못한 호출(배분 근거 없음 등). 0으로 채우지 않고 따로 센다. 그중 병렬·배치는 `missing_counts`
- 비용은 단가가 있는 기록만 더한다. 하나도 없으면 `null`(0과 구분)

### by-asset

`group`: `asset`(기본), `tool`, `server`, `pattern`

| group | key | 설명 |
|---|---|---|
| asset | Tool asset_id 또는 `tool:<도구 이름>` | 스냅샷에서 Tool 하나와만 맞으면 asset_id(matched), 아니면 도구 이름으로 묶음 |
| tool | `tool:<도구 이름>` | 도구 이름 |
| server | MCP 서버 asset_id, `mcp:<서버 이름>`, `source:<출처>` | 매핑된 Tool의 소속 서버, 못 찾으면 노출 이름의 서버 부분, 내장 도구는 출처(core 등) |
| pattern | `pattern:<구간 유형>` | sequential, parallel, batch, unattributed |

```json
{ "group": "asset", "total_tokens": 15769, "inventory_snapshot_id": null,
  "items": [
    { "key": "tool:read", "label": "read", "asset_id": null, "asset_type": null,
      "mapping_status": "unmatched", "tool_source": "core",
      "calls": 13, "calls_not_computed": 0, "tokens": 11790,
      "tokens_sequential": 2268, "tokens_allocated": 9522, "estimated_cost_usd": 0.01179,
      "share": 0.7477, "relative": 1, "last_used_at": "2026-10-29T05:29:02.132Z",
      "last_trace_id": "78f1519286fc431fe44ec8345e5d3e79" },
    { "key": "tool:fs__read_text_file", "label": "fs__read_text_file", "mcp_server": "fs",
      "tool_source": "mcp", "mapping_status": "unmatched", "tokens": 3920, "relative": 0.3325, "...": "..." } ] }
```

- 스냅샷을 주면 MCP 도구는 `"key": "tool-fs-read", "asset_id": "tool-fs-read", "asset_type": "tool", "mapping_status": "matched"`처럼 나온다
- `asset_type`은 스캐너 스냅샷 값(`tool`, `mcp_server`)을 그대로 쓴다. 대시보드 규격(PR #6)의 `MCP_SERVER` 표기와는 UI에서 맞춘다
- 정렬: 토큰 많은 순

### records

`limit`(기본 50, 최대 500), `cursor`(이전 응답의 `next_cursor`). 최신순. 아래는 `?limit=3`.

```json
{ "total": 16, "next_cursor": "3",
  "items": [ { "usage_id": "use-952ec048...", "time": "2026-10-29T05:29:02.132Z",
               "tool_name": "read", "tool_source": "core", "mcp_server": null, "asset_id": null,
               "mapping_status": "unmatched", "pattern": "sequential", "method": "sequential",
               "attribution_method": "sequential-input-delta", "tokens": 286, "estimated_cost_usd": 0.000286,
               "duration_ms": 35, "model": "claude-haiku-4-5-20251001",
               "trace_id": "78f1519286fc431fe44ec8345e5d3e79", "tool_span_id": "74c2875025776c0e",
               "tool_call_id": "toolu_...", "evidence_source_refs": ["otlp-json:pc-1029.traces.jsonl#trace=...&span=..."] } ] }
```

`trace_id`는 OpenClaw 실행 기록(요청 1건)의 ID다. 같은 trace_id의 스팬을 모으면 모델 호출 → 도구 실행 순서와 병렬 여부를 다시 볼 수 있다.

### timeseries

`step`(기본: 구간이 120개 이하가 되는 가장 작은 값, 1m·5m·15m·30m·1h·6h·1d 중), `group`(기본 `tool`), `top`(기본 8, 나머지는 `other`로 합침).
구간 시작은 한국 시간 기준 step 단위로 맞추고(예: `step=1d`는 한국 자정 = 전날 15:00Z, 시각 표기는 UTC) 기록이 없는 구간도 0으로 채운다. 플러그인의 일 단위 누적과 하루 경계가 같다. 구간이 1,000개를 넘으면 400.

```json
{ "group": "tool", "step": "1m0s",
  "total":  { "key": "total", "tokens": 15769, "points": [ {"t": "2026-10-29T05:24:00.000Z", "tokens": 3752, "calls": 4}, ... ] },
  "series": [ { "key": "tool:read", "label": "read", "tokens": 11790, "points": [ ... ] },
              { "key": "tool:fs__read_text_file", "label": "fs__read_text_file", "tokens": 3920, "points": [ ... ] }, ... ] }
```

### assets/{asset_id}

`asset_id`는 by-asset(group=asset)의 `key`: 연결된 Tool은 asset_id, 연결 안 된 도구는 `tool:<이름>`(URL에서는 `tool%3Aread`도 됨).
기록이 없으면 404가 아니라 `used: false, calls: 0, usage: null`.

```json
{ "key": "tool-fs-read",
  "usage": { "asset_id": "tool-fs-read", "asset_type": "tool", "mapping_status": "matched", "calls": 2, "tokens": 3920, ... },
  "runtime": { "used": true, "calls": 2, "last_used_at": "2026-10-29T05:26:56.716Z", "last_trace_id": "abd2a05c..." },
  "recent": [ { "usage_id": "...", "time": "...", "tokens": 3306, "trace_id": "...", ... } ],
  "brake_events": null }
```

- `runtime`은 스캐너의 state(선언·노출 등)를 바꾸지 않고 따로 붙이는 실제 사용 정보다(스키마 14.2-8, "사용됨"은 여기서 판단).
- `brake_events`: 이 도구 이름에 걸린 브레이크 수. 플러그인 기록을 안 줬으면 `null`.

### brake-events

`level`(warn / approve / block, 선택), `limit`, `cursor`. 최신순. 플러그인 기록(`--tool-results`)이 없으면 `available: false`.

```json
{ "available": true, "by_level": {"warn": 1, "approve": 1, "block": 1}, "total": 3,
  "items": [ { "time": "2026-10-29T05:28:40.288Z", "level": "block", "mode": "enforce", "enforced": true,
               "tool_name": "exec", "tool_call_id": "toolu_...", "run_id": "...",
               "reasons": [{"scope": "run", "metric": "toolCalls", "value": 5, "limit": 5}],
               "run_usage": {"result_bytes": 4, "counted_tokens": 8, "tool_calls": 4, "same_tool_streak": 5},
               "resolution": null, "trace_id": null },
             { "level": "approve", "resolution": {"decision": "allow-once", "time": "..."}, ... } ],
  "next_cursor": null }
```

- `trace_id`는 같은 도구 호출 ID의 사용 기록에서 찾는다(플러그인이 받은 trace id는 실행 기록 id와 다를 수 있어서). 차단된 호출처럼 사용 기록이 없으면 `null`.
- 브레이크는 위협 시나리오 경고(S1~S5)와 섞지 않고 Token Usage 화면의 실행 제한 기록으로 표시한다.

## 지키는 것

- 응답에 도구 결과 내용, 인자 값, API 키, 사용자 경로를 넣지 않는다. 입력 파일은 이름만 나간다
- 토큰을 계산 못 한 호출은 `null`로 두고 따로 센다(균등 배분·0 채우기 안 함)
- 모든 값은 추정치(`estimated: true`). 청구 금액이 아니며 모델 호출 단위 입력·출력 합계와 더하면 안 된다
- 기본 주소는 127.0.0.1(PC 안에서만). 인증이 없으므로 테스트베드처럼 NAT 안에서만 0.0.0.0으로 연다
- 브레이크 기록에서는 정해진 필드만 읽는다(도구 인자·결과 내용은 원래 기록에 없음)

## 테스트

```bash
go test ./...
```

`testdata/pc-1029.traces.jsonl`은 10.29 PC 재검증 원본 스팬에서 귀속에 필요한 스팬(모델 호출, 도구 실행,
결과별 토큰 수 등)만 남기고, 리소스 속성은 `service.name` 외에 지운 것이다(호스트 이름·경로 없음).
`testdata/inventory-pc-fs.json`은 매핑 확인용 가짜 스냅샷(fs 서버 Tool만).

| 테스트 | 확인 내용 |
|---|---|
| summary | 10.29 재검증 값(16건, 15,769토큰, 순차 3건 2,268 / 배분 13건 13,501, 누락 0)과 같음 |
| by-asset | 도구별 합계·상대값, 순차+배분 = 합계, 스냅샷이 있으면 Tool·서버 asset_id로 묶임 |
| records | 최신순, 쪽 나눔으로 16건 중복 없이 모두 나옴 |
| 구간 | range(데이터 끝 기준), from/to, 빈 구간이면 비용 null |
| 오류 | 잘못된 range·from/to·group·limit·cursor는 400, 7일 초과 400, POST 405 |
| 누락 | 토큰 수 스팬이 없으면 병렬 13건이 null + missing_counts 13 |
| 경로 | 입력 파일의 디렉터리가 응답에 안 나옴 |
| timeseries | 1분 구간 6개, 합계 = 15,769, top·other 합치기, 1d·6h 구간의 한국 시간 경계, step·top 오류 |
| assets | Tool asset_id·`tool:` 키, 최근 호출 최신순, 미사용 자산은 used=false |
| brake-events | 경고·승인 요청·차단, 승인 응답 짝짓기, trace_id 연결, level 필터, 기록 없으면 available=false |
| 실시간 | 파일 없음 → 0건, 파일이 늘면 다시 계산, 안 바뀌면 그대로, 반쯤 쓴 마지막 줄 무시, 패턴(로테이션), 깨진 줄이면 이전 데이터 유지 + degraded |
| 실행 | 고정·실시간 모드 기동 → health 응답 → 종료, `--live`와 `--from` 같이 쓰면 오류 |
