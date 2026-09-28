# 토큰 사용량 수집 · 비용 모니터링 — 진행 상황 종합 정리 (2026-09-28)

담당: 정철(`dlwjdcjf0`) · 저장소: `pbh0330/2026-Agent_Scope` · 브랜치: `feature/token-collector`
(develop에서 분기, PR 생성 완료 · 이 문서 작업분까지 반영해서 push 예정)

이 문서는 1~3주차 동안 한 작업, 발견한 것, 겪은 문제와 해결 방법을 한 곳에 모은 요약본이다.
개별 자세한 내용은 `docs/` 폴더의 각 문서를 참고.

---

## 1주차 — 실측 검증 (2026-09-22)

실제 OTel Collector debug 로그(28만 줄 이상)를 캡처해서 개발계획서의 가정을 검증했다.

- **exemplar 연결 불가능함을 확인.** 캡처 로그에 `Exemplar` 필드가 0건 — 메트릭↔트레이스
  자동 연결(exemplar)에 의존한 설계는 이 환경에서 애초에 성립하지 않음.
- **traceId 기반 스팬 연결은 정상 동작.** `openclaw.model.call` / `openclaw.tool.execution`
  스팬이 같은 traceId로 정상적으로 묶임.
- **중요한 단순화 발견**: `openclaw.model.call` 스팬 자체에 input/output 토큰 수가 이미
  속성으로 들어있어서, 메트릭 조인 없이 스팬만으로 귀속 계산이 가능함. 원래 계획서가
  가정한 "exemplar로 메트릭과 스팬을 연결"하는 단계 자체가 불필요해짐.
- `openclaw.cost.usd` 메트릭은 캡처에 안 보임 — 토큰 수 × 단가로 직접 계산하는 근사치로
  대체하기로 함.

자세한 내용: `docs/0921-diagnostics-otel-verification-log.md`

## 2주차 — 귀속 알고리즘 + 모니터링 파이프라인

- **traceId+타임스탬프 기반 도구별 토큰/비용 귀속 알고리즘**(Python, `attribution.py`)을
  구현. 핵심 로직:
  1. `group_runs()` — model.call/tool.execution 스팬을 부모(run) 단위로 묶음
  2. `classify_segments()` — 순차/병렬/배치 패턴 판별 (tool.execution 스팬끼리 시간이
     겹치면 병렬, 안 겹치면서 model.call 사이에 1개면 순차, 2개 이상이면 배치)
  3. 순차 구간은 `next.input_tokens - prev.input_tokens - prev.output_tokens` 공식으로
     귀속 (직전 모델 자신의 응답이 히스토리로 재편입되는 몫을 빼서 과대추정 방지)
  4. 병렬/배치 구간은 도구별 정밀 토큰 귀속을 포기하고 duration_ms만 대리 지표로 기록
- **OTel Collector + Prometheus + Grafana 모니터링 파이프라인** 구축 (docker-compose).
  실제 확인된 스팬/메트릭 구조(`openclaw.tokens`, `gen_ai.client.operation.duration` 등)를
  그대로 사용. 이 샌드박스는 docker 데몬을 못 띄우는 제약이 있어서 YAML/JSON 문법
  검증만 하고 실제 기동 테스트는 못 함 — 사용자 쪽에서 최초 기동 시 로그 한 번 확인 필요.

자세한 내용: `docs/token-usage-cost-monitoring-devplan-v2.md`, `pipeline/README.md`

## 3주차 — 정확도 검증 (착수, 2026-09-28)

**문제 인식**: 도구별 토큰 귀속치는 비교할 독립적인 정답(ground truth)이 없어서
"정확도 검증"이 원칙적으로 성립하지 않는다. 그래서 검증을 두 갈래로 나눴다 — 패턴
판별(순차/병렬/배치)은 스팬 타임스탬프가 실제로 겹치는지 여부라는 객관적 사실이라서
검증 가능하고, 순차 구간의 토큰 귀속 공식은 근사식 자체의 정답이 없어서 논리적
정합성 확인 + 엣지케이스 테스트로 접근했다.

- **`audit_attribution.py` 신규 작성**: 각 run의 model.call/tool.execution 원본
  타임스탬프를 나란히 출력해서, 패턴 판정 근거를 사람이 직접 감사(audit)할 수 있게 함.
- **버그 발견·수정**: model.call이 하나도 없는 run(도구 실행 후 모델을 재호출하지 않고
  끝난 경우)의 도구 호출이 결과에서 조용히 누락되던 버그 → `"unattributed"`로 명시
  기록하도록 수정.
- **리스크 발견·완화**: tool.execution 스팬 타임스탬프가 하나라도 누락되면 실제로는
  병렬인데 batch로 오분류될 수 있는 문제 → note에 경고 남기도록 수정.
- **회귀 테스트 3건 추가** (경계값 겹침 테스트, unattributed 테스트, 타임스탬프 누락
  테스트) — 총 7건 전부 통과.
- **단가 이슈 발견**: 실제 `openclaw.json`(school-gateway 프로바이더)의 모델 단가가
  input/output/cacheRead/cacheWrite 전부 0으로 설정돼 있음 — 학교 게이트웨이가 학생에게
  종량제 과금을 안 하기 때문. Anthropic 공식 API 정가(2026-09-28 기준, 1M 토큰당
  input $1.00 / output $5.00 / cacheRead $0.10 / cacheWrite $2.00)를 참고용으로 자동
  대체하도록 `attribution.py` 수정 — 출력에 "참고용, 실제 청구액 아님" 명시.
- **실제 batch 사례 확보·검증**: 웹챗에 "파일 4개를 각각 읽어서 요약" 프롬프트를
  보내 새 캡처 로그를 만들었고, `fs__read_text_file` 4회 호출이 batch로 정확히
  분류되는 것을 원본 타임스탬프와 대조해 확인함. 순차 diff 공식도 실사례 9건으로
  추가 확인(전부 정상 범위).
- **병렬이 안 나온 원인 확인**: OpenClaw(pi-agent-core)는 기본이 병렬 실행이지만,
  MCP 서버 도구는 서버 설정에 `supportsParallelToolCalls: true`가 있을 때만 병렬로
  등록되고 없으면 순차로 등록된다(OpenClaw 소스 `agent-bundle-mcp-materialize.ts`).
  우리 `fs` 서버엔 이 옵션이 없어서 순차로 강제됐던 것 — parallel 판정 로직은
  아직 실사례 미검증.

자세한 내용: `docs/week3-accuracy-validation.md`

## 작업 중 겪은 이슈와 정리된 규칙

브랜치/저장소 세팅 과정에서 생긴 문제들과, 그 결과로 정리된 규칙만 남긴다 (문제
해결의 세부 과정은 생략).

- `feature/token-collector` 브랜치에 다른 작업분과의 충돌이 있었는데, 기존 내용이
  이미 별도 PR로 정상 제출돼 있는 걸 확인하고 안전하게 정리함.
- 저장소 구조를 정리하는 과정에서 실수가 두 차례 있었음 — 지금은 계획대로
  `token-collector/{docs,pipeline,scripts,README.md,.gitignore}` 구조로 정리됐고,
  저장소 최상위 `README.md`(팀 브랜치 전략 문서)는 원본 그대로 보존돼 있음.
- **규칙으로 정함: 이 저장소에 추가하는 파일명은 한글 대신 영문(ASCII)을 사용한다.**
  한글 파일명이 Windows에서 압축 파일을 통해 전달될 때 깨지는 호환성 문제가 있었음.

## 현재 상태 (2026-09-28 기준)

- `feature/token-collector` → `develop` PR 생성 완료, 3주차 작업분까지 push 완료.
- 저장소 구조: `token-collector/{docs,pipeline,scripts,README.md,.gitignore}` —
  저장소 최상위 `README.md`(팀 브랜치 전략)는 원본 그대로 보존됨.

## 다음 단계 후보

1. `fs` MCP 서버에 `"supportsParallelToolCalls": true` 설정 후 같은 프롬프트로 재캡처 →
   parallel 실사례 검증 (3주차 마무리)
2. `attribution.py` 결과를 Grafana에 연결 (커스텀 exporter 설계 필요)
3. `pipeline/prometheus/rules.yml`의 단가 placeholder 처리 방식 결정 (Prometheus
   recording rule은 정적 상수라서 attribution.py처럼 런타임 자동 대체가 안 됨)
4. PR 리뷰/머지 진행 상황 확인
