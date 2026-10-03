# usagereport — 토큰·비용 귀속 결과 → usage.json 어댑터

PR #1 통합 스키마(`docs/schema-design-draft.md`, 0.6.0-draft) **14절 UsageReport 계약**에 맞춰,
도구 호출 단위 사용량 기록(`usage.json`)을 만든다. 대시보드는 이 파일로 사용량을 자산 화면에 붙이고,
QA는 이 파일로 귀속·매핑 결과를 검증한다.

```
OpenClaw ─OTLP─▶ otelcol-agentscope ─┬─ tokenattribution 커넥터 ─▶ Prometheus 메트릭(누적, 실시간)
                                     └─ file/traces 익스포터 ─▶ agentscope-traces.jsonl(원본 스팬)
                                                                      │
                     snapshot.json(스캐너, 선택) ──┐                  ▼
                                                   └──▶ agentscope-usage ─▶ usage.json
```

메트릭은 누적값이라 호출별 기록을 되살릴 수 없다(스키마 14.2-6). 그래서 Collector가 원본 스팬을
파일로도 남기고, 어댑터가 그 파일을 다시 읽어 커넥터와 **같은 판정 로직**(`attribution.Classify`)으로
레코드를 만든다.

## 실행

```powershell
# 1) Collector 설정(otelcol-agentscope-config.yaml)에 file/traces가 들어 있으면
#    .openclaw 폴더에 agentscope-traces.jsonl이 쌓인다.
# 2) usage.json 생성
.\agentscope-usage.exe --env env-test-01 --profile profile-test-01 `
  --input .\agentscope-traces.jsonl `
  --inventory .\snapshot.json `
  --openclaw-config .\openclaw.json `
  --from 2026-10-02T00:00:00Z --to 2026-10-03T00:00:00Z `
  --out .\usage.json
```

- 선택 옵션: `--inventory`(스캐너 스냅샷, 없으면 전부 unmatched), `--openclaw-config`(모델 단가),
  `--from`/`--to`(도구 시작 시각 기준 [from, to), 없으면 데이터 범위를 초 단위로 잡음),
  `--include-cache-in-prompt`(커넥터 옵션과 같게), `--reference-pricing=false`(참고 정가 끄기).
- `--input`은 여러 번 줄 수 있다(로테이션된 이전 파일 포함). Collector file 익스포터 출력(OTLP JSON 줄)과
  `export_fixtures.py` 픽스처 배열 둘 다 읽는다.
- `--env`, `--profile`은 필수다. 텔레메트리에는 host 수준 속성뿐이라 환경·프로필 ID를 주입한다.
- 출력에는 입력 파일의 **파일 이름만** 남는다(사용자 이름이 든 전체 경로, openclaw.json의 키 값은 안 남김).

빌드: `go build ./cmd/agentscope-usage` (Windows용은 `GOOS=windows GOARCH=amd64 go build ...`). 표준 라이브러리만 사용.

## 필드 대응 (attribution.Result → UsageRecord)

| UsageRecord | 값 |
|---|---|
| `usage_id` | `use-` + sha256(environment_id, profile_id, trace_id, tool_span_id) 앞 32자. 재전송돼도 같음 |
| `trace_id` / `run_id` / `tool_span_id` / `tool_call_id` | Result 그대로(tool_call_id 없으면 null) |
| `tool_name` / `tool_source` | OpenClaw 노출 이름(`<server>__<tool>` 또는 내장 도구 이름) / `mcp`, `core` 등 원본 값 |
| `pattern` | sequential / parallel / batch / unattributed |
| `duration_ms` | 도구 실행 시간, 시각이 없으면 null |
| `approx_input_tokens` | **sequential이고 토큰이 있을 때만** 값, 그 외 null(균등 배분 안 함) |
| `estimated_cost_usd` | 토큰 × 입력 단가. 토큰이 null이거나 단가를 모르면 null(0으로 안 바꿈) |
| `pricing` | `source`: config / reference_list_price / unavailable, `version`, `currency: USD`, `input_per_million`, `source_ref` |
| `negative_delta` / `missing_timestamps` / `note` | 판정 경고 그대로 |
| `model` / `provider` / `closing_model_span_id` | 닫는 model.call 기준(없으면 null) |
| `attribution_method` / `attribution_version` | `sequential-input-delta` / `attribution-go/0.2.0` |
| `include_cache_in_prompt` | 계산 옵션(커넥터와 같게 줄 것) |
| `estimated` | 항상 true |
| `evidence_source_refs` | `otlp-json:<파일 이름>#trace=<id>&span=<id>` |

단가 버전: 참고 정가는 `anthropic-list-price@2026-09-28`, openclaw.json 단가는 원천에 버전이 없어서
모델별 단가표 내용의 해시(`openclaw-config-sha256:xxxxxxxxxxxx`)를 버전으로 쓴다(단가 값만 해시, 키 등 다른 값은 미포함).

## 자산 매핑 규칙 (asset_ref / mapping_status)

OpenClaw는 MCP 도구를 모델에 `안전한서버이름__안전한도구이름`으로 노출한다
(`src/agents/agent-bundle-mcp-names.ts`: 허용 밖 문자 → `-`, 서버 30자·전체 64자 제한, 영문자로 시작 안 하면 접두).
어댑터는 스냅샷의 각 Tool 자산(소속 서버의 설정 키 + 공식 도구 이름)으로 **같은 규칙을 재현**해서 노출 이름과 비교한다.

| 상황 | 결과 |
|---|---|
| 재현한 이름이 노출 이름과 같은 Tool이 정확히 1개, 근거(evidence_refs) 있음 | `matched`, `asset_ref` = 그 Tool ID, 근거 = 그 Tool의 evidence_refs |
| 같은 노출 이름이 나오는 Tool이 2개 이상(예: 같은 서버 키가 Gateway·Node 양쪽에 선언) | `ambiguous` — OpenClaw가 실행 시점에 붙이는 `-2` 접미사 순서는 스냅샷에 없음 |
| `tool_source`가 mcp가 아님(내장 도구 exec, ls 등) | `unmatched` — 가짜 MCP 자산을 만들지 않음 |
| 후보 없음 / `__` 구분자 없음 / 스냅샷 없음 | `unmatched` + 사유 |

서로 다른 서버의 동명 Tool은 서버 부분까지 비교하므로 섞이지 않는다(S3). 이름 규칙은 OpenClaw 소스의
함수를 그대로 실행한 결과와 무작위 이름 10만 건에서 일치함을 확인했다(공백·BOM·한글·이모지 포함).

서버 키는 서버 자산의 `product.config_path`에서 `servers.` 뒤를 쓰고, 없으면 `name`을 쓴다. 스캐너 출력 형식이
확정되면(스키마 12.1) 이 부분을 맞춰야 한다.

## 테스트

```bash
go test ./...
```

- 실제 로그 3개(순차·배치·병렬): 레코드의 판정·토큰·시간이 파이썬 기준 결과와 일치
- 병렬·배치·귀속불가는 토큰·비용 null, 단가 출처 3종(config/참고 정가/unavailable→비용 null)
- 같은 스팬 재전송 → 레코드·리포트 ID 동일(토큰 합계 668 유지)
- 집계 구간 [start, end), 시작 시각 없는 도구는 제외 + 사유 기록
- OTLP JSON 줄(BOM 포함)과 픽스처 입력 결과 동일
- 매핑: 동명 Tool 서버별 분리, Gateway·Node 키 충돌 ambiguous, 내장 도구 unmatched, 근거 없는 후보 거부
- CLI: 출력에 로컬 경로·openclaw.json 키 값이 안 남음

## 검증 기록 (2026-10-02)

빌드한 `otelcol-agentscope`에 `file/traces`를 켜고 실제 로그 3개를 OTLP로 보낸 뒤 순차·배치 로그를 한 번 더 재전송.
어댑터 출력 18건(1+13+4, 재전송 중복 0): exec 8건 649토큰·ls 1건 19토큰(core, unmatched),
`fs__list_directory_with_sizes` 264토큰·`fs__read_text_file` batch 4건·parallel 4건(테스트 스냅샷 Tool에 matched).
기존 메트릭 검증값과 같다.

## 아직 정해지지 않은 것

- UsageReport의 `schema_version`은 통합 스키마 문서 버전(0.6.0-draft)을 그대로 쓴다. 팀 합의로 별도 버전을 둘지 결정 필요.
- 실시간 집계 API(대시보드가 파일 대신 조회)는 스키마 14.2-6에 따라 별도 계약이 필요하다.
- 플러그인이 등록한 도구의 `tool_source` 값과 소속 기준(자산 분류 협의안)이 정해지면 매핑 규칙을 추가한다.
