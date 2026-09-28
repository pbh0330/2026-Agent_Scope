# 3주차 — 정확도 검증 (2026-09-28 착수)

## 왜 이게 어려운 문제인가

정확도를 "검증"하려면 원래 비교할 정답(ground truth)이 있어야 하는데, 이 프로젝트엔
그게 애초에 없다. OpenClaw 공식 텔레메트리가 도구별 토큰 소비량을 따로 재지 않기
때문에(1주차 milestone 0에서 확인함), `attribution.py`가 만드는 "도구별 토큰 귀속치"
자체가 근사 공식으로 만든 추정값이다. 그 추정값이 맞는지 비교할 독립적인 실측값이
없다는 뜻이다. 그래서 검증을 두 갈래로 나눠서 접근했다.

1. **패턴 판별(순차/병렬/배치)** — 이건 사실 검증 가능하다. tool.execution 스팬의
   시작/종료 시각이 실제로 겹치는지는 로그에 그대로 찍혀 있는 객관적 사실이라서,
   `classify_segments()`의 판정을 원본 타임스탬프와 나란히 놓고 사람이 눈으로 확인할
   수 있다.
2. **순차 구간의 토큰 귀속 공식(diff 근사)** — 이건 근사식 자체의 정답이 없어서
   "검증"이 아니라 "논리적 정합성 확인 + 엣지케이스 테스트"로 접근했다.

## 이번에 한 것

### 1) `audit_attribution.py` 추가 — 패턴 판별 근거를 사람이 감사할 수 있게 출력

`scripts/traceid_attribution/audit_attribution.py`. 각 run의 model.call/tool.execution
원본 타임스탬프를 나란히 보여줘서, "왜 이걸 sequential/parallel/batch로 판정했는지"를
사람이 바로 확인할 수 있음. 실제 캡처 로그(1주차 것)로 돌려보면:

```
[model.call] 05:46:04.143 ~ 05:46:08.222  in=48292 out=102
[model.call] 05:46:08.388 ~ 05:46:12.442  in=48658 out=438
[tool.exec ] 05:46:08.286 ~ 05:46:08.330  fs__list_directory_with_sizes
→ [sequential] fs__list_directory_with_sizes  tokens=264
```

도구 실행이 첫 model.call이 끝난 뒤(08.222) 시작해서(08.286) 두 번째 model.call이
시작하기 전(08.388)에 끝났다(08.330) — 겹치는 구간이 없으므로 sequential 판정이
원본 데이터와 맞다는 걸 확인함.

### 2) 코드 감사 중 발견한 버그/리스크 2건 (수정 완료)

- **버그: model.call이 하나도 없는 run은 결과에서 조용히 사라졌음.** 도구 실행 후
  모델을 다시 안 부르고 끝난 run이나, model.call 스팬 캡처가 누락된 run은
  `classify_segments()`의 k-루프가 아예 안 돌아서 결과 리스트에서 빠짐 —
  `ToolAttribution.pattern`에 애초에 `"unattributed"`라는 값이 정의돼 있었는데
  실제로는 한 번도 안 쓰이고 있었다. 지금은 이런 도구 호출을 `"unattributed"`로
  명시적으로 남기도록 고쳐서, 나중에 "비용 합계에서 왜 이 도구가 빠졌는지" 감사 가능.
- **리스크: 타임스탬프 누락 시 병렬이 배치로 오분류될 수 있음.** `_overlaps()`는
  두 스팬의 시작/종료 시각이 하나라도 없으면 무조건 "안 겹침"으로 처리한다. 즉
  실제로는 병렬 호출인데 한쪽 스팬의 타임스탬프 파싱이 실패하면 batch로 잘못
  분류될 수 있다. 지금은 이 경우 note에 경고를 남기도록 고쳐서, "자신있게 batch"와
  "타임스탬프가 없어서 batch로 보이는 것"을 구분할 수 있게 함.
- 두 가지 다 `test_attribution.py`에 회귀 테스트 추가함 (`test_no_model_call_marked_unattributed`,
  `test_missing_timestamp_flags_batch_confidence`). 경계값 테스트(`test_boundary_touch_is_not_parallel`
  — 두 도구 호출이 맞닿기만 하고 안 겹치는 경우가 병렬로 잘못 잡히지 않는지)도 추가.
  총 7개 테스트 전부 통과.

### 3) 별개로 발견한 것: 비용 단가가 사실상 0으로 설정돼 있음

`openclaw.json`(school-gateway 프로바이더)의 `claude-haiku-4-5-20251001` cost 필드가
input/output/cacheRead/cacheWrite **전부 0**으로 돼 있다. 즉 "실제 단가표"를 정상적으로
로딩해도 비용 계산 결과가 항상 $0.00이 나온다 — 코드 버그가 아니라, 학교 게이트웨이가
학생에게 종량제로 과금하지 않기 때문에 생기는 데이터 자체의 한계다.

"비용 모니터링" 파트의 숫자가 의미를 가지려면 참고용 정가가 필요해서, Anthropic
공식 API 정가(2026-09-28 기준, platform.claude.com/docs/en/about-claude/pricing —
input $1.00 / output $5.00 / cacheRead $0.10 / cacheWrite(1시간 TTL) $2.00, 전부
1M 토큰당)를 참고용으로 병행 사용하도록 `attribution.py`를 고쳤다. 단가가 0인 모델을
만나면 자동으로 이 참고 정가로 대체하고, 출력에 "참고용, 실제 청구액 아님"이라고
명시한다. (공교롭게도 기존에 쓰던 `PRICING_PLACEHOLDER` 값이 이 공식 정가와 우연히
같았다.)

## 실제 병렬/배치 사례 확보 및 검증 (2026-09-28)

1주차에 캡처한 로그(28만 줄)엔 tool.execution 스팬이 1건밖에 없어서, "병렬"/"배치"
판정 로직은 합성(synthetic) 테스트로만 검증된 상태였다. 그래서 OpenClaw 웹챗에
여러 도구를 한 번에 부를 수밖에 없는 프롬프트를 직접 보내서 새 캡처 로그
(`otel-debug-log-week3.txt`)를 만들고, 실제 사례를 확보했다.

**보낸 프롬프트 2개**:
1. "워크스페이스 최상위에 있는 AGENTS.md, IDENTITY.md, SOUL.md, USER.md 이 4개
   파일을 전부 읽어서 각각 한 줄로 요약해줘. 파일마다 따로따로 읽어서 확인해줘."
2. "이번엔 AGENTS.md랑 BOOTSTRAP.md 두 파일을 각각 열어서 줄 수를 세어줘."

**결과 — 실제 batch 사례 확보, 판정 정확함을 확인**:

```
[model.call] 13:56:20.719 ~ 13:56:25.134  in=49232 out=258
[model.call] 13:56:25.448 ~ 13:56:31.161  in=55237 out=339
[tool.exec ] 13:56:25.189 ~ 13:56:25.220  fs__read_text_file
[tool.exec ] 13:56:25.291 ~ 13:56:25.303  fs__read_text_file
[tool.exec ] 13:56:25.349 ~ 13:56:25.363  fs__read_text_file
[tool.exec ] 13:56:25.400 ~ 13:56:25.409  fs__read_text_file
→ [batch] fs__read_text_file × 4건
```

첫 프롬프트(파일 4개 동시 요약 요청)가 실제로 `fs__read_text_file` 4번 호출을
유발했다. 타임스탬프를 보면 네 호출이 서로 안 겹치고(각자 시작 전에 직전 게 끝남)
순서대로 실행됐다 — `classify_segments()`가 이걸 batch로 정확히 분류함, 원본
데이터와 일치.

**왜 병렬(parallel)이 안 나왔나 — 공식 문서·소스로 확인한 원인**:

한 응답 안의 도구 호출 4개가 겹치지 않고 하나씩 실행됐는데, 이건 OpenClaw가 원래
병렬 실행을 안 해서가 아니라 **우리 환경의 MCP 서버 설정 때문**이었다.

- OpenClaw가 쓰는 에이전트 루프(pi-agent-core)는 **기본이 병렬 실행**이다. 공식
  README 기준: 기본값 `"parallel"`은 도구 호출들의 사전 검사(preflight)를 순서대로
  끝낸 뒤 허용된 도구들을 동시에 실행한다. 단, 한 배치 안에 `executionMode:
  "sequential"`인 도구가 있으면 그 배치는 순차로 실행된다.
- OpenClaw 소스(`src/agents/agent-bundle-mcp-materialize.ts`)를 보면 MCP 서버에서
  가져온 도구는 서버 설정에 `supportsParallelToolCalls: true`가 **명시돼 있을 때만**
  `"parallel"`이고, 그 외에는 전부 `"sequential"`로 등록된다
  (`server?.supportsParallelToolCalls === true ? "parallel" : "sequential"`).
- 우리 `openclaw.json`의 `mcp.servers.fs`에는 이 옵션이 없다. 그래서 `fs__*` 도구는
  전부 sequential로 등록돼 있었고, 4개의 `fs__read_text_file` 호출이 순서대로
  실행된 것이다. 호출 사이 간격(약 40~70ms)도 이 설명과 맞는다.

즉 이번 결과는 "이 시스템엔 병렬이 없다"는 뜻이 아니다. **설정상 순차로 강제된
다중 호출을 batch로 정확히 분류했다**는 뜻이고, 병렬 판정 로직은 아직 실사례로
검증하지 못한 상태다. 병렬 설정이 켜진 MCP 서버나 기본값이 병렬인 내장 도구를
쓰면 실제 운영 환경에서도 병렬 호출이 충분히 나올 수 있으므로, 병렬 분류 검증은
생략하면 안 된다.

(근거: pi-agent-core README — github.com/earendil-works/pi/blob/main/packages/agent/README.md,
OpenClaw 설정 문서 — docs.openclaw.ai/gateway/config-extensions, OpenClaw 소스
`src/agents/agent-bundle-mcp-materialize.ts` 226~227행)

두 번째 프롬프트도 정상 처리됐고(`ls`×1, `exec`×8이 이미 첫 번째 run에서 sequential로
잡혔던 것 포함), 순차 diff 공식도 실사례 9건으로 추가 확인됨 — 전부 음수 없이
정상 범위의 토큰 수가 나왔다.

## 다음에 할 일

- [x] 실제 병렬/배치 캡처 로그 확보 → batch 사례 확보 및 검증 완료
- [ ] 병렬(parallel) 실사례 확보 — `openclaw.json`의 `mcp.servers.fs`에
      `"supportsParallelToolCalls": true`를 추가하고 게이트웨이 재시작 후 같은
      "파일 4개 읽기" 프롬프트를 다시 보내서, tool.execution 스팬이 실제로 겹치는지와
      parallel로 분류되는지 확인 (읽기 전용 호출이라 동시 실행해도 안전함)
- [ ] `pipeline/prometheus/rules.yml`의 단가 placeholder도 `attribution.py`와
      동일하게 "게이트웨이 단가 0 → Anthropic 공식 정가 대체" 로직 반영할지 결정
      (지금은 Prometheus recording rule이라 정적 상수라서 attribution.py처럼
      런타임에 자동 대체는 안 됨 — 상수 자체를 고정값으로 박아넣는 수밖에 없음)
