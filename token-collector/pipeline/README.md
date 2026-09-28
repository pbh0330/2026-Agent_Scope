# OpenClaw 토큰/비용 파이프라인 (2주차 산출물)

1주차 마일스톤 0(`otel-debug-log.txt`)에서 확인한 실제 스팬/메트릭 구조를 바탕으로 만든
OTel Collector + Prometheus + Grafana 파이프라인. `debug` 익스포터로 눈으로만 보던 걸
Prometheus에 실제로 쌓고 Grafana로 보이게 만드는 단계.

## 구성

```
otel-collector-config.yaml   OTel Collector 설정 (OTLP 수신 → Prometheus 노출 + 파일 저장 + debug 콘솔)
docker-compose.yml           3개 서비스(otel-collector, prometheus, grafana) 한 번에 기동
prometheus/prometheus.yml    Prometheus가 Collector를 긁어가는 설정
prometheus/rules.yml         근사 비용 recording rule (⚠ 단가 placeholder — 아래 참고)
grafana/provisioning/...     Grafana가 켜지자마자 Prometheus 데이터소스 + 대시보드를 자동으로 불러오게 하는 설정
```

## 실행 방법

이 폴더 전체를 OTel Collector를 돌릴 머신(테스트베드와 같은 네트워크)으로 옮긴 뒤:

```bash
docker compose up -d
```

- Grafana: http://localhost:3000 (admin / admin — 최초 로그인 후 비밀번호 바꾸라고 뜰 수 있음)
- Prometheus: http://localhost:9090 (쿼리 직접 날려보고 싶을 때)
- OTel Collector OTLP 수신 주소: `http://<이 머신 주소>:4318`

그 다음 `openclaw-diagnostics-snippet.json`(1주차에 이미 전달한 파일)의 `diagnostics.otel.endpoint`가
이 Collector 주소를 가리키게 맞추고 OpenClaw gateway를 재시작하면 데이터가 흐르기 시작함.

## ⚠️ 지금 당장 확인/교체가 필요한 것

1. **`prometheus/rules.yml`의 단가가 placeholder임.** `attribution.py`에 썼던 것과 같은 임시값
   (input $1.00 / output $5.00, per 1M tokens)이 들어가 있음. 실제 `openclaw.json`의
   `models.providers.<provider>.models[].cost` 값을 받으면 이 파일의 두 상수를 바로 교체해야
   비용 패널 숫자가 의미 있어짐.
2. **`openclaw.cost.usd` 메트릭이 1주차 캡처 로그엔 안 보였음.** 개발계획서 1.1절엔 공식
   텔레메트리가 비용까지 분해해서 낸다고 돼 있는데, 실제 캡처에선 `openclaw.tokens`
   (input/output/prompt/total)만 있고 `cost`라는 문자열이 로그 전체에 한 번도 안 나옴.
   그래서 이 대시보드의 비용 패널은 OpenClaw가 직접 낸 비용이 아니라 **토큰 수 × 단가로
   우리가 계산한 근사치**(recording rule)임. 나중에 실제 `openclaw.cost.usd`가 어떤
   조건에서 나오는지(설정 플래그가 따로 있는지) 확인이 필요하면 알려주세요.
3. 이 샌드박스는 docker 데몬을 못 띄우는 제약이 있어서(rootless 환경), 모든 YAML/JSON은
   문법 검증만 했고 실제 기동 테스트는 못 해봤음. 처음 `docker compose up` 할 때 Collector
   로그(`docker compose logs otel-collector`)를 한 번 확인해서 프로세서/익스포터 이름이
   실제 이미지(otel/opentelemetry-collector-**contrib**)에 다 존재하는지 봐주세요
   (Collector core 이미지엔 `prometheus`/`file` 익스포터가 없어서 반드시 contrib 이미지여야 함 —
   docker-compose.yml에 이미 그렇게 지정해뒀음).

## 대시보드 패널 (openclaw-tokens.json)

| 패널 | 쿼리 | 비고 |
|---|---|---|
| 누적 토큰 총량 | `openclaw_tokens_total{openclaw_token="total"}` | |
| 근사 누적 비용 | `openclaw:cost_usd:total` | recording rule, 단가는 위 1번 참고 |
| 토큰 사용량 (input/output) | `sum by (openclaw_token) (openclaw_tokens_total{...})` | |
| model.call 응답시간 p95 | `histogram_quantile(0.95, ...gen_ai_client_operation_duration_bucket...)` | |

도구별(tool) 귀속은 이 대시보드에 없음 — 그건 Prometheus 메트릭에 애초에 없는 정보라서
(1.1절에서 확인한 그 간극), `attribution.py`가 별도로 처리하는 영역. 다음 단계에서
`attribution.py` 결과물을 Grafana에서 보이게 연결하는 방법(예: 작은 exporter를 만들어서
Prometheus에 커스텀 게이지로 올리기)을 정할 수 있음.
