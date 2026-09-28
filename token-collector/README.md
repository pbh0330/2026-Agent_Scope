# 토큰 사용량 수집 · 비용 모니터링

AI 에이전트 보안 자산 식별·가시화 기술 개발 프로젝트 — 토큰 사용량 수집·비용 모니터링 파트
(`feature/token-collector` 브랜치 작업물).

OpenClaw 공식 텔레메트리는 토큰·비용을 채널/프로바이더/모델/에이전트 단위까지만 분해하고
**도구·MCP 서버 단위로는 분해하지 않는다.** 이 폴더는 그 간극(“얼마나 썼는지는 알아도
무엇 때문에 썼는지는 모른다”)을 메우기 위한 검증 로그, 귀속(attribution) 알고리즘,
관측 파이프라인을 담고 있다.

담당: 정철 · 목표 완성 시점: 2026-11-15 (4주 압축 일정 적용, 2026-09-20 시작)

> 저장소 최상위 `README.md`(브랜치 전략)는 그대로 두고, 이 파트 작업은
> `token-collector/` 폴더 하나로 모아서 `feature/token-collector` 브랜치에
> 추가하는 방식으로 진행합니다.

## 폴더 구조

```
docs/       개발계획서, 마일스톤 0(exemplar 연결) 검증 로그, 3주차 정확도 검증 결과
scripts/    traceId+타임스탬프 기반 도구별 토큰/비용 귀속 알고리즘 (Python 프로토타입)
pipeline/   OTel Collector + Prometheus + Grafana 관측 파이프라인 (docker-compose)
```

## 지금까지 확인된 것 (마일스톤 0, 2026-09-22)

- **exemplar 연결 안 됨.** 실제 캡처 로그(28만 줄 이상)에 `Exemplar` 필드가 0건 —
  메트릭↔트레이스 자동 연결(exemplar)에 의존한 설계는 불가능함을 확인.
- **스팬 간 traceId 연결은 정상.** `openclaw.model.call` / `openclaw.tool.execution`
  스팬이 같은 traceId로 정상적으로 묶임. 게다가 `model.call` 스팬 자체에
  input/output 토큰 수가 이미 속성으로 들어 있어서, **메트릭 조인 없이 스팬만으로
  귀속 계산이 가능**하다는 걸 확인함 — 자세한 내용은 `docs/` 참고.
- `openclaw.cost.usd` 메트릭은 이번 캡처엔 안 보였음 — `scripts/`, `pipeline/`
  양쪽 다 토큰 수 × 단가로 직접 계산하는 근사치를 씀.

## 3주차: 정확도 검증 (2026-09-28)

- **패턴 판별(순차/병렬/배치)은 원본 타임스탬프로 감사(audit) 가능함을 확인.**
  `scripts/traceid_attribution/audit_attribution.py`로 판정 근거(스팬 시작/종료
  시각)를 사람이 직접 확인할 수 있게 함.
- **버그 발견·수정**: model.call 없이 끝난 run의 도구 호출이 결과에서 조용히
  누락되던 문제 → `"unattributed"`로 명시 기록하도록 수정.
- **리스크 발견·완화**: 도구 스팬 타임스탬프 누락 시 병렬이 배치로 오분류될 수
  있는 문제 → note에 경고 남기도록 수정. 회귀 테스트 3건 추가(총 7건 전부 통과).
- **단가 이슈 발견**: 실제 `openclaw.json`(school-gateway)의 모델 단가가
  input/output/cache 전부 0으로 설정돼 있음 — 학교 게이트웨이가 종량제 과금을
  안 하기 때문. Anthropic 공식 정가(참고용, 실제 청구액 아님)를 자동 대체하도록
  `attribution.py`를 고침.
- **아직 미해결**: 실제 캡처 로그에 병렬/배치 도구 호출 사례가 없어서 그 두 판정
  로직은 여전히 합성 테스트로만 검증됨. 실사례를 유도하는 테스트 프롬프트 제안함.

자세한 내용: `docs/3주차_정확도검증.md`

## 사용법

```bash
# 1) 캡처한 OTel Collector debug 로그로 도구별 토큰/비용 귀속 계산
cd scripts/traceid_attribution
python3 attribution.py <otel-debug-log.txt> [openclaw.json]   # 단가표 실제값은 openclaw.json에서 로드
python3 test_attribution.py                                    # 순차/병렬/배치 분류 로직 단위 테스트
python3 audit_attribution.py <otel-debug-log.txt>               # 패턴 판정 근거(원본 타임스탬프) 감사용 출력

# 2) Prometheus + Grafana로 코어 메트릭(토큰 총량/근사 비용/응답시간) 상시 모니터링
cd pipeline
docker compose up -d
# Grafana: http://localhost:3000 (admin/admin)
```

각 폴더 안의 README/코드 주석에 더 자세한 내용과 TODO가 있음.

## 아직 안 끝난 것

- `pipeline/prometheus/rules.yml`은 여전히 단가 placeholder임 — `attribution.py`처럼
  "게이트웨이 단가 0이면 Anthropic 공식 정가로 자동 대체"하는 로직을 Prometheus
  recording rule(정적 상수)에도 반영할지 결정 필요.
- 병렬/배치 구간 귀속 로직은 여전히 합성 테스트로만 검증됨 — `docs/3주차_정확도검증.md`의
  제안 프롬프트로 실제 병렬/배치 캡처 로그를 얻으면 실증 검증 필요.
- `attribution.py`의 도구별 귀속 결과를 Grafana 대시보드에서 보이게 잇는 작업(예:
  작은 exporter를 만들어 Prometheus 커스텀 게이지로 올리기)은 아직 설계 전.
