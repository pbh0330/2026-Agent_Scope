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

## 아직 검증 못 한 것 — 실제 병렬/배치 사례가 없음

1주차에 캡처한 로그(28만 줄)엔 tool.execution 스팬이 **1건**밖에 없다. 그래서
"병렬"/"배치" 판정 로직은 지금까지 전부 합성(synthetic) 테스트로만 검증된 상태고,
실제 OpenClaw 에이전트가 병렬/배치로 도구를 호출하는 진짜 사례로는 아직 한 번도
확인 못 했다.

### 제안: 병렬/배치를 유도하는 테스트 프롬프트

OpenClaw 웹챗에서 아래 같은 프롬프트를 던지면 에이전트가 서로 무관한 도구를
한 턴에 여러 번 호출할 가능성이 높다 (모델이 "동시에 처리해도 되는 독립적인 작업"으로
인식하면 병렬로, "순서대로 해야 하는 작업"으로 인식하면 배치로 부를 것으로 예상):

- **병렬 유도**: "지금 이 폴더(A), 저 폴더(B), 저기 폴더(C) 각각에 파일이 몇 개
  있는지 동시에 확인해줘" — 서로 의존관계 없는 3개의 디렉터리 조회를 한 번에 요청.
- **병렬 유도 2**: "이 세 개 URL(X, Y, Z)에서 각각 제목만 가져와서 비교해줘" —
  웹 조회 도구가 있다면 독립적인 fetch 3건.
- **배치(순차) 유도**: "이 폴더 안의 파일들을 하나씩 열어서 내용을 요약해줘" —
  파일 개수만큼 도구 호출이 필요하지만 서로 의존관계가 있을 수 있어서 모델이
  순서대로(하지만 model.call 재호출 없이 한 번에 여러 번) 부를 가능성.
- **배치 유도 2**: "폴더 안의 .txt 파일을 전부 찾아서 각각 줄 수를 세줘" — 파일
  개수만큼 반복되는 동일 패턴의 도구 호출.

실행 후 지난번과 같은 방식으로 OTel Collector debug 로그를 캡처해서
(`otelcol.exe ... | Tee-Object -FilePath otel-debug-log-2.txt`) 업로드해주면,
`audit_attribution.py otel-debug-log-2.txt`로 이번엔 진짜 병렬/배치 사례가
있는지, 있다면 판정이 맞는지 바로 확인할 수 있다.

## 다음에 할 일

- [ ] 위 테스트 프롬프트로 실제 병렬/배치 캡처 로그 확보 → `audit_attribution.py`로
      실사례 검증
- [ ] (검증되면) 이 문서에 실사례 결과 추가
- [ ] `pipeline/prometheus/rules.yml`의 단가 placeholder도 `attribution.py`와
      동일하게 "게이트웨이 단가 0 → Anthropic 공식 정가 대체" 로직 반영할지 결정
      (지금은 Prometheus recording rule이라 정적 상수라서 attribution.py처럼
      런타임에 자동 대체는 안 됨 — 상수 자체를 고정값으로 박아넣는 수밖에 없음)
