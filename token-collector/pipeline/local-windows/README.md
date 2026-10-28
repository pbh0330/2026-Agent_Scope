# Docker 없이 Windows에서 실행 (Prometheus + Grafana)

Docker Desktop이 없는 PC용 구성이다. 이미 켜 두는 `otelcol-agentscope.exe`(로컬 Collector) 옆에
Windows용 Prometheus와 Grafana만 직접 띄워서, 도구별 토큰 패널과 점(exemplar, trace_id)까지 확인한다.

| 항목 | docker 구성(`../docker-compose.yml`) | 이 구성 |
|---|---|---|
| Collector | 컨테이너 | 기존 `otelcol-agentscope.exe` 그대로 |
| Prometheus(exemplar 저장) | O | O |
| Grafana 대시보드 | O | O (같은 대시보드 JSON 사용) |
| 점 클릭 → Tempo 실행 기록 | O | **X** (Tempo는 Windows용 공식 빌드가 없음. 점의 trace_id는 보임) |
| usage.json 원본 스팬 파일 | `./data/` | `.openclaw\agentscope-traces.jsonl` |

## 1. Collector를 최신 실행 파일로 교체

`.openclaw\otelcol-agentscope-windows.zip`에 exemplar 유지 수정이 들어간 실행 파일이 있다. 켜져 있는 Collector를
끄고(Ctrl+C) 압축을 덮어써서 푼 뒤 다시 켠다.

```powershell
cd C:\Users\ssesa\.openclaw
Expand-Archive .\otelcol-agentscope-windows.zip -DestinationPath . -Force
.\otelcol-agentscope.exe --config .\otelcol-agentscope-config.yaml
```

## 2. Prometheus·Grafana 내려받기 (최초 1회)

`C:\Users\ssesa\agentscope-tools` 폴더를 만들고 두 zip을 그 안에 푼다(폴더 이름은 그대로 둬도 된다).

| 프로그램 | 받는 곳 | 파일 |
|---|---|---|
| Prometheus | https://prometheus.io/download/ | `prometheus-3.15.0.windows-amd64.zip` (Windows, amd64) |
| Grafana | https://grafana.com/grafana/download?platform=windows | Standalone Windows Binaries의 zip |

풀고 나면 이런 모양이면 된다.

```
C:\Users\ssesa\agentscope-tools\
  prometheus-3.15.0.windows-amd64\prometheus.exe
  grafana-…\bin\grafana.exe (또는 grafana-server.exe)
```

## 3. 실행

```powershell
cd C:\Users\ssesa\2026-Agent_Scope\token-collector\pipeline\local-windows
.\start-local.cmd
```

- 새 창 두 개(Prometheus, Grafana)가 뜬다. 끌 때는 그 창을 닫는다.
- `.cmd` 파일이라 PowerShell 실행 정책에 막히지 않는다. 탐색기에서 더블클릭해도 된다.
- 도구 폴더를 다른 곳에 뒀다면 먼저 `set AGENTSCOPE_TOOLS=D:\tools`(cmd) 후 실행.
- 두 프로그램 모두 이 PC(127.0.0.1)에서만 접속되게 띄운다. 데이터는 `agentscope-tools\data\`에 쌓인다.

## 4. 확인

1. http://localhost:9090/targets 에서 `otel-collector`가 **UP**인지 확인.
2. OpenClaw 웹챗에서 도구를 쓰는 요청(예: 폴더 목록 조회)을 보낸다.
3. http://localhost:3000 (admin / admin, 처음에 비밀번호 변경 화면이 뜰 수 있음) →
   대시보드 "OpenClaw 토큰/비용 메트릭"의 아래쪽 두 패널에 선과 점이 30초~1분 안에 나타나는지 확인.
4. 점에 마우스를 올리면 `trace_id`가 보이면 exemplar 연결까지 정상이다.
   (점을 눌러 실행 기록으로 이동하는 기능은 Tempo가 있는 docker 구성에서 동작)

## 파일

| 파일 | 내용 |
|---|---|
| `start-local.cmd` | Prometheus(`--enable-feature=exemplar-storage`)와 Grafana를 이 폴더 설정으로 실행 |
| `prometheus.yml` | `localhost:9464`(로컬 Collector) 15초 스크랩, 비용 rule은 `../prometheus/rules.yml` 공용 |
| `grafana/provisioning/` | Prometheus 데이터소스(localhost:9090), 대시보드는 `../grafana/provisioning/dashboards/*.json` 공용 |
