# OpenClaw 토큰/비용 파이프라인 (docker-compose)

OpenClaw 텔레메트리를 받아 **도구별 토큰·비용 메트릭**을 만들고, 그래프의 점(exemplar)을 누르면
그 값을 만든 요청의 **실행 기록(트레이스)** 으로 바로 넘어가게 하는 구성.

> ✅ **실기동 확인(2026-10-04)**: 작성자 PC(Windows, Docker Desktop)에서 4개 서비스를 띄우고 실제 OpenClaw 요청으로
> 대시보드 표시, 점 → Tempo 이동, 원본 스팬 파일 생성까지 확인했다. 아래 "검증 기록" 참고.

```
OpenClaw ─OTLP(4318)→ otel-collector ─┬─ tokenattribution 커넥터 → /metrics(9464) ← prometheus(9090, exemplar 저장)
   (커스텀 Collector, ../collector)    ├─ 트레이스 원본 → tempo(3200, traceId로 조회)
                                       └─ 원본 스팬 파일 → ./data/agentscope-traces.jsonl (usage.json 입력)
grafana(3000): Prometheus 패널의 점을 누르면 trace_id로 Tempo 화면이 열림
```

## 구성

| 파일 | 내용 |
|---|---|
| `docker-compose.yml` | 4개 서비스(otel-collector, tempo, prometheus, grafana) |
| `../collector/Dockerfile` | 커스텀 Collector 이미지(OCB로 소스에서 빌드). compose가 자동으로 빌드 |
| `docker-compose.prebuilt.yml`, `../collector/Dockerfile.prebuilt` | 소스 빌드 대신 미리 빌드한 Linux 실행 파일을 복사만 하는 이미지(디스크 부족 PC용) |
| `otel-collector-config.yaml` | OTLP 수신 → 귀속 커넥터·Tempo·원본 스팬 파일로 분기 |
| `tempo/tempo.yaml` | Tempo 단일 실행 설정(Tempo 3.0 공식 예제 기반, 로컬 디스크 저장) |
| `prometheus/prometheus.yml`, `rules.yml` | Collector 스크랩(15초), 근사 비용 recording rule(단가 placeholder) |
| `grafana/provisioning/datasources/datasource.yml` | Prometheus(uid `Prometheus`) + Tempo(uid `Tempo`), exemplar `trace_id` → Tempo 연결 |
| `grafana/provisioning/dashboards/openclaw-tokens.json` | 코어 토큰 패널 4개 + 도구별 귀속 패널 2개(exemplar 표시) |

버전: Collector v0.161.0(OCB), Tempo 3.0.0, Prometheus v3.15.0, Grafana 13.1.3.

## 실행 방법

Docker(Windows는 Docker Desktop)가 필요하다. 이 폴더에서:

```bash
docker compose up -d --build
```

- 처음에는 Collector 이미지를 소스에서 빌드하므로 몇 분 걸린다(Go 모듈 다운로드 포함).
- 빌드 중 Docker 엔진이 멈추거나(디스크 여유 공간 부족 시 발생 확인) 빌드가 너무 오래 걸리면, 미리 빌드한 실행 파일을 쓴다.
  `../collector/otelcol-agentscope-linux`를 준비한 뒤(만드는 법은 `../collector/README.md`):

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml up -d --build
  ```
- **로컬 단독 실행 Collector(`.openclaw\otelcol-agentscope.exe`)와 같은 4318·9464 포트를 쓰므로 그쪽을 먼저 끈다.**
- OpenClaw의 `diagnostics.otel.endpoint`는 지금처럼 `http://localhost:4318` 그대로 두면 된다(같은 PC일 때).

| 주소 | 용도 |
|---|---|
| http://localhost:3000 | Grafana (admin / admin) → 대시보드 "OpenClaw 토큰/비용 메트릭" |
| http://localhost:9090 | Prometheus (조회식 직접 실행) |
| http://localhost:9464/metrics | Collector 메트릭 원본 |
| http://localhost:3200/api/traces/&lt;traceId&gt; | Tempo 트레이스 조회 |

## 동작 확인 순서

1. `docker compose ps`로 4개 서비스가 모두 running인지 확인.
2. OpenClaw 웹챗에서 도구를 쓰는 요청(예: 폴더 목록 조회)을 한 번 보낸다.
3. 30초쯤 뒤 Grafana 대시보드의 "도구별 귀속 토큰 증가량" 패널에 선과 점이 나타나는지 확인.
4. 점에 마우스를 올려 `trace_id`를 확인하고, 링크를 누르면 Tempo 화면에서 그 요청의
   model.call → tool.execution → model.call 순서가 보이면 연결 완료.
5. `./data/agentscope-traces.jsonl`이 생겼는지 확인(usage.json 입력, `collector/usagereport` 참고).

문제가 있으면 `docker compose logs otel-collector tempo`를 먼저 본다.

## 유의 사항

- **exemplar는 표본**이다. 시리즈마다 최근 최대 5건을 유지하고, Prometheus는 스크랩할 때 그중 하나를 저장한다.
  모든 호출의 목록은 usage.json이나 Tempo 검색으로 본다.
- 컨테이너 Collector는 `openclaw.json`을 읽지 않는다(같은 파일에 API 키가 있음). 학교 게이트웨이 단가가 0이라
  비용은 Anthropic 공식 정가(참고용)로 계산되며 `pricing_source="reference_list_price"` 라벨로 구분된다.
- `prometheus/rules.yml`의 코어 비용 rule은 아직 placeholder 단가(input $1 / output $5 per 1M)다.
- `./data/`의 원본 스팬 파일에는 OpenClaw 스팬 속성이 그대로 들어가므로 저장소에 올리지 않는다(.gitignore 처리).
- Grafana 기본 계정(admin/admin)은 로컬 검증용이다. 다른 사람이 접속하는 환경이면 바꾼다.

## 검증 기록 (2026-10-04, 작성자 PC 실기동)

Windows + Docker Desktop, `docker-compose.prebuilt.yml` 사용. OpenClaw Gateway를 같은 PC에서 실행하고 웹챗으로
도구 요청 9건(순차·병렬·단일 호출, MCP `fs` 서버 도구와 코어 도구 `ls`·`exec`)을 보냈다.

- `docker compose ps`: 4개 서비스 모두 running.
- 대시보드: 코어 토큰 패널과 도구별 귀속 패널 모두 값 표시. 도구 6종이 각각 시리즈로 나타나고 결과 크기에 따라 값이 다름
  (같은 `fs__read_text_file`이 1.1KB 파일 608토큰, 6.2KB 파일 3,270토큰). 병렬 호출은 호출 수만 올라감.
- 점(exemplar) 툴팁에 trace_id·span_id·도구·서버·모델 라벨 표시, "Query with Tempo"로 해당 trace가 열리고
  model.call → tool.execution → model.call 순서 확인.
- `./data/agentscope-traces.jsonl` 생성 확인(약 1.1MB), 이 파일로 `agentscope-usage` 실행 → usage.json 12건
  (순차 8건 토큰·비용 있음, 병렬 4건 null). 스캐너 스냅샷을 넣지 않아 자산 매핑은 모두 unmatched.
- 남은 문제: 모델 호출 지연 p95 패널은 "No data"(참조 메트릭 이름 확인 필요), 코어 비용 rule은 placeholder 단가.

## 검증 기록 (2026-10-03, 클라우드 샌드박스)

샌드박스에서 Docker Hub 이미지를 받을 수 없어 `docker compose up` 자체는 실행하지 못했다. 대신 각 구성요소를
같은 설정으로 직접 실행해 확인했다.

- `docker compose config`로 compose 문법 확인, 각 이미지 태그가 Docker Hub에 있는지 확인.
- Collector 설정을 빌드한 `otelcol-agentscope`로 `validate` 통과. 실제 로그 3개 재전송 시 Tempo 쪽으로
  스팬 38개·트레이스 4개 전달, 원본 스팬 파일도 같은 수, 메트릭 값은 기존 검증값과 같음
  (exec 649, ls 19, fs__list_directory_with_sizes 264).
- Prometheus v3.15.0을 소스에서 빌드해 `--enable-feature=exemplar-storage`, 스크랩 15초로 실행 →
  `/api/v1/query_exemplars`로 8개 시리즈의 exemplar(trace_id) 조회 확인.
  이 과정에서 exemplar가 flush(5초)마다 비워져 15초 스크랩에 잘 안 걸리는 문제를 발견해 커넥터를 수정함
  (시리즈별 최근 exemplar 유지).
- Tempo·Grafana 실제 화면 연동(점 클릭 → Tempo)은 10.04 실기동에서 확인(위 기록).
