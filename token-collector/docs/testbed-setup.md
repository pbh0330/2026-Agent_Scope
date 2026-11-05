# 테스트베드 적용 가이드 — 토큰 사용량 수집

작성 11.02, 수정 11.05(Anthropic API 직접 연결) 이정철 · 대상 tb-gw(Ubuntu 24.04, OpenClaw 2026.9.6) · 10.31 회의 결정 반영

## 0. 무엇을 하나

tb-gw 안에서 도구 호출마다 토큰 사용량을 계산할 원본 기록을 남긴다. 대시보드(Grafana)는 쓰지 않는다.
남은 파일로 토큰 파트가 usage.json과 사용 현황 API(대시보드 백엔드) 데이터를 만든다.

```
tb-gw (VM 하나 안에서 동작. 밖으로 여는 포트는 사용 현황 API 8088 하나, NAT 안)
  OpenClaw 게이트웨이 ── diagnostics-otel ──┐
        │                                     ├─→ Collector(127.0.0.1:4318) → ~/agentscope/data/agentscope-traces.jsonl
        └ token-guard 플러그인 ── 결과별 토큰 수 ┘
                    └─→ ~/.openclaw/agentscope/agentscope-tool-results.jsonl
  사용 현황 API(:8088, 실시간 모드) ← 위 두 파일을 읽어 계산 ← 대시보드 UI(호스트 PC에서 http://<TB_GW_IP>:8088)
  Anthropic API(claude-haiku-5-5) ← 에이전트 모델 호출 + 플러그인 토큰 세기(무료 count_tokens, 같은 공용 키)
```

| 회의 결정(10.31) | 이 가이드에서 |
|---|---|
| 모델 Claude Haiku 5.5 | 에이전트 모델과 플러그인 토큰 계산 모델 모두 `claude-haiku-5-5` |
| 공용 키, tb-gw 환경 변수로만 | 공용 Claude Max 계정의 API 크레딧으로 만든 **Anthropic API 키**. 환경 변수 `ANTHROPIC_API_KEY`에 실행할 때마다 메모리로만 넣음(4절). 설정 파일에는 키가 없음 |
| 분기 스냅샷 SNAP-2-P2-T | SNAP-2-P2는 그대로 두고 분기에서만 작업. 플러그인 2개가 늘어나므로 정답 목록 따로 관리 |
| Collector 위치 | tb-gw 안. OpenTelemetry 공식 Collector(otelcol, 버전 고정)를 설치 스크립트로 내려받음. Docker 없음 |
| 소비 브레이크 | `warn`(기록만). 에이전트 동작은 바뀌지 않음 |

## 1. 준비물

| 항목 | 받는 곳 | 비고 |
|---|---|---|
| Anthropic API 키 | 공용 계정(Claude Max) | claude.ai Settings → Billing에서 API 크레딧(월 100달러)을 Console 조직에 연결한 뒤 Console에서 만든 키. 테스트베드 전용 키·워크스페이스를 권장(지출 한도 설정 가능). 메시지·문서·저장소에 붙이지 않음 |
| 저장소 | GitHub | `feature/token-collector` 브랜치(플러그인, 설치 스크립트·설정) |
| 사용 현황 API 실행 파일 `agentscope-usage-api-linux-amd64.zip` | 정철 | 실행 파일 + `.sha256`. `deploy/build.sh`로 만든 linux/amd64 파일(약 7MB). 저장소에는 없음 |

tb-gw에서 쓰는 사용자는 아래에서 `<TB_USER>`로 적는다. 명령은 전부 이 사용자로(sudo 없이) 실행한다.

## 2. 스냅샷 분기

1. tb-gw를 끈 상태에서 SNAP-2-P2로 되돌린 뒤 켠다.
2. 이 가이드를 끝까지 진행하고 동작 확인(8절)까지 마친 뒤, **11절 체크리스트를 거쳐** 끈 상태에서 SNAP-2-P2-T를 만든다.
3. SNAP-2-P2-T의 정답 목록에는 플러그인 `diagnostics-otel`, `agentscope-token-guard`가 추가된다(SNAP-2-P2와 따로 관리).

## 3. 모델 설정(Anthropic API, 키는 설정 파일에 넣지 않음)

```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-$(date +%m%d)
openclaw config set agents.entries.main.model anthropic/claude-haiku-5-5
```

- OpenClaw의 Anthropic 플러그인(번들)이 환경 변수 `ANTHROPIC_API_KEY`를 읽는다. `models.providers`나 `env.vars`에 키를 적지 않는다.
- 4절에서 키를 넣고 재시작한 뒤 `openclaw models list --provider anthropic`에 `claude-haiku-5-5`가 보이는지 확인한다.
- 비용은 크레딧에서 빠진다. Haiku 5.5는 입력 100만 토큰당 0.10달러(프롬프트 10만 토큰 이하, 넘으면 0.50달러), 10.29 PC 테스트 1시간 분량(입력 약 79만 토큰)이 약 0.08달러.
- 크레딧을 다 쓰면 API가 `credit balance is too low` 오류를 돌려주고 다음 달까지 멈춘다(12절).

## 4. 키 넣기(실행할 때마다, 디스크에 안 남김)

게이트웨이는 systemd 사용자 서비스로 돈다. 서비스 이름을 먼저 확인한다.

```bash
systemctl --user list-units 'openclaw*'      # 예: openclaw-gateway.service
```

키를 systemd 사용자 관리자 메모리에만 넣고 게이트웨이를 다시 시작한다.

```bash
read -rs -p "Anthropic API 키: " K && systemctl --user set-environment ANTHROPIC_API_KEY="$K"; unset K; echo
systemctl --user restart openclaw-gateway     # 위에서 확인한 이름
systemctl --user show-environment | grep -c '^ANTHROPIC_API_KEY='   # 1이면 들어감(값은 출력하지 않음)
```

- `read -s`라 화면과 셸 기록(history)에 키가 남지 않는다. `set-environment`는 파일에 저장하지 않는다.
- VM을 껐다 켜면 사라지므로 다시 넣는다. 스냅샷은 전원을 끈 상태로 만들므로 키가 들어가지 않는다.
- `openclaw gateway restart`는 실행 중인 프로세스 안에서 다시 시작해 새 환경 변수를 못 받을 수 있다. 키를 넣은 뒤에는 `systemctl --user restart`를 쓴다.
- `~/.openclaw/.env`나 서비스 환경 파일에는 넣지 않는다(파일이라 스냅샷·OVA에 남음).

## 5. Collector 설치

```bash
git clone -b feature/token-collector https://github.com/pbh0330/2026-Agent_Scope.git ~/agentscope/repo
~/agentscope/repo/token-collector/deploy/testbed/install-collector.sh
```

스크립트가 하는 일:

1. OpenTelemetry 공식 Collector(`otelcol` 0.161.0, core 배포판)를 GitHub 릴리스에서 내려받고 SHA-256을 확인한다.
2. `~/agentscope/bin/otelcol`, `~/agentscope/otelcol-testbed.yaml`로 설치하고 설정을 검사한다.
3. systemd 사용자 서비스 `agentscope-collector`를 등록·시작한다. 마지막에 `active`가 나오면 정상.

- 127.0.0.1:4318에서만 받는다. tb-node나 바깥에서 접속할 수 없다.
- 결과 파일은 `~/agentscope/data/agentscope-traces.jsonl`(50MB마다 나뉘고 최대 20개 보관).
- 로그: `journalctl --user -u agentscope-collector -n 50`
- 다시 실행해도 된다(덮어쓰고 재시작).

## 6. OpenClaw 텔레메트리(diagnostics-otel)

```bash
openclaw plugins install @openclaw/diagnostics-otel
openclaw config get plugins.allow --json     # 결과에 따라 아래 주의 참고

openclaw config set plugins.entries.diagnostics-otel '{"enabled": true}' --strict-json --merge
openclaw config set diagnostics '{"enabled": true, "otel": {
  "enabled": true, "endpoint": "http://127.0.0.1:4318", "protocol": "http/protobuf",
  "traces": true, "metrics": false, "logs": false,
  "sampleRate": 1, "flushIntervalMs": 5000, "captureContent": false }}' --strict-json --merge
```

- `sampleRate: 1` 필수(일부만 남기면 도구별 계산이 빠짐). `captureContent: false`로 대화 내용은 내보내지 않는다.
- `metrics: false`: Collector가 트레이스만 받는다(메트릭을 켜면 404 오류 로그가 계속 남음).
- **`plugins.allow` 주의**: `allow`는 "추가 허용"이 아니라 허용 목록이다. 값이 이미 있으면 거기에 `diagnostics-otel`, `agentscope-token-guard`를
  **추가**하고, 기존 항목(P2 플러그인 포함)을 빼지 않는다. 비어 있으면(unset) 그대로 두고 `openclaw plugins list`로 두 플러그인이 로드되는지만 본다.
  (09.21 학교 게이트웨이에서 allow에 하나만 넣었다가 번들 플러그인이 전부 빠진 적 있음)

## 7. token-guard 플러그인

```bash
openclaw plugins install --link ~/agentscope/repo/token-collector/plugin --force --accept-capabilities
openclaw plugins enable agentscope-token-guard

openclaw config set plugins.entries.agentscope-token-guard.config '{
  "tokenCount": { "enabled": true, "api": "anthropic-count-tokens", "baseUrl": "https://api.anthropic.com",
                  "apiKeyEnv": "ANTHROPIC_API_KEY", "model": "claude-haiku-5-5" },
  "otlpEndpoint": "http://127.0.0.1:4318",
  "brake": { "mode": "warn",
             "run": { "warn": { "toolCalls": 20, "countedTokens": 30000, "sameToolStreak": 8 } },
             "day": { "warn": { "countedTokens": 1000000 } } }
}' --strict-json

systemctl --user restart openclaw-gateway
openclaw plugins inspect agentscope-token-guard --runtime --json   # before_tool_call, tool_result_persist 훅이 보여야 함
```

- 명령은 **한 줄씩** 붙여 넣는다(설치 중 질문에 다음 줄이 답으로 들어가 취소된 적 있음, 10.12).
- `apiKeyEnv`에는 환경 변수 **이름**만 적는다. 키는 4절에서 넣은 것을 같이 쓴다.
- 토큰 세기는 Anthropic 토큰 계산 API(`/v1/messages/count_tokens`)를 쓴다. 무료이고 메시지 요청과 한도가 따로다(기본 등급 분당 5,000회).
- 브레이크 값은 정상 사용 데이터를 보기 위한 관찰용이다. `warn`이라 기록만 남고 막지 않는다.
- 결과 내용은 기록하지 않는다(크기·토큰 수·도구 이름·호출 ID만).

## 8. 동작 확인

```bash
openclaw agent --agent main --message "워크스페이스에서 .md 파일 두 개를 골라 동시에(병렬로) 읽고 한 줄씩 요약해줘"

J=~/.openclaw/agentscope/agentscope-tool-results.jsonl
tail -n 20 $J | grep -o '"kind":"[a-z_]*"' | sort | uniq -c
grep -c 'agentscope.tool_result.count' ~/agentscope/data/agentscope-traces.jsonl
grep -c '"kind":"token_count_error"\|"kind":"count_export_error"' $J
```

| 확인 | 기대값 |
|---|---|
| JSONL의 `tool_result`, `token_count` | 도구 호출 수만큼씩(목록 조회 + 파일 읽기 2개면 3개씩) |
| 스팬 파일의 `agentscope.tool_result.count` | 0보다 큼 |
| 스팬 파일 크기 | 요청 뒤 5~10초 안에 늘어남(`ls -l ~/agentscope/data`) |
| `token_count_error`, `count_export_error` | 0 |

- `openclaw agent exec`는 게이트웨이를 거치지 않아 텔레메트리가 안 나온다. 위처럼 `openclaw agent`(게이트웨이 경유)를 쓴다.
- 확인 결과(위 명령 출력, `plugins inspect` 출력)를 정철에게 보내 주면 2026.9.6에서 훅 동작이 9.5와 같은지 함께 본다.
- Anthropic 직접 연결은 PC 실측(학교 게이트웨이)과 다르므로 아래 두 가지를 첫 데이터로 확인한다.
  - **프롬프트 캐시**: Anthropic은 캐시된 입력을 `input_tokens`에서 빼고 따로 보고한다. 사용 현황 API는 `--include-cache-in-prompt`로 캐시분까지 합쳐 계산하도록 서비스 파일에 넣어 두었다(9절). 스팬의 `gen_ai.usage.cache_read.input_tokens`가 0보다 큰지 본다.
  - **thinking**: Haiku 5.5는 기본으로 생각(thinking) 토큰을 쓴다. 순차 구간 공식(다음 입력 − 앞 입력 − 앞 출력)이 그대로 맞는지 같은 파일의 순차·병렬 비교를 한 번 돌려 본다. 어긋나면 에이전트 thinking을 `off`로 두고 다시 비교한다.

## 9. 사용 현황 API(대시보드 백엔드)

받은 zip을 tb-gw 홈에 둔 뒤(예: 병하 PC에서 `scp agentscope-usage-api-linux-amd64.zip <TB_USER>@<TB_GW_IP>:`):

```bash
mkdir -p ~/usage-api-dist && unzip -o ~/agentscope-usage-api-linux-amd64.zip -d ~/usage-api-dist
~/agentscope/repo/token-collector/deploy/testbed/install-usage-api.sh ~/usage-api-dist/agentscope-usage-api
```

- 체크섬 확인 → `~/agentscope/bin`에 설치 → systemd 사용자 서비스 `agentscope-usage-api` 등록·시작 → health 출력까지 한다.
- 실시간 모드로 돈다: Collector 스팬 파일(로테이션 포함)과 플러그인 기록이 바뀌면 15초 안에 다시 계산한다.
- `0.0.0.0:8088`로 열린다. VMware NAT 안이라 호스트 PC(대시보드 UI)에서 `http://<TB_GW_IP>:8088`로 접속된다.
- `environment_id`/`profile_id`는 서비스 파일의 `AS_ENV`, `AS_PROFILE`(기본 `env-testbed`, `profile-snap2-p2t`). 스캐너 스냅샷과 같은 값으로 맞춘다.
  바꾸려면 `systemctl --user edit agentscope-usage-api`로 `Environment=` 두 줄을 덮어쓴다.
- 스캐너 스냅샷을 연결할 때는 서비스 파일의 `--inventory` 주석 참고.

확인:

```bash
curl -s http://127.0.0.1:8088/api/v1/usage/health                  # "mode":"live", "status":"ok"
curl -s 'http://127.0.0.1:8088/api/v1/usage/summary?range=1h'      # 8절 요청이 calls에 잡힘
curl -s 'http://127.0.0.1:8088/api/v1/usage/brake-events?range=24h' # "available":true
```

API 명세: `token-collector/backend/usageapi/README.md`.

## 10. 기록 파일 전달

병하 PC에서(SSH 키로 tb-gw 접속되는 상태):

```bash
mkdir -p tb-token-$(date +%m%d) && cd tb-token-$(date +%m%d)
scp '<TB_USER>@<TB_GW_IP>:agentscope/data/agentscope-traces*.jsonl' .
scp '<TB_USER>@<TB_GW_IP>:.openclaw/agentscope/agentscope-tool-results.jsonl' .
```

- 두 파일을 묶어 정철에게 전달(팀 드라이브 등). `openclaw.json`은 보내지 않는다(게이트웨이 토큰이 들어 있음).
- 파일에는 도구 이름·실행 시각·모델 호출 토큰 수·결과 크기만 있고 대화·결과 내용은 없다. 저장소에는 올리지 않는다.
- 어느 실행이 어떤 시나리오인지 시각과 함께 메모해 주면 분석할 때 맞춰 본다.

## 11. 스냅샷 만들기 전 체크리스트

```bash
systemctl --user unset-environment ANTHROPIC_API_KEY
systemctl --user show-environment | grep -c '^ANTHROPIC_API_KEY='    # 0
grep -rl 'sk-ant-' ~/.openclaw ~/.config/systemd ~/.bashrc ~/.profile 2>/dev/null   # 아무것도 안 나와야 함(키는 sk-ant-로 시작)
```

- 그다음 VM을 **끈 상태**에서 SNAP-2-P2-T를 만든다.
- 위협 시나리오 스냅샷(SNAP-3~)과 OVA 내보내기 전에도 같은 확인을 한다. 키를 넣지 않은 상태에서는 에이전트가 모델을 못 불러 실행이 실패하는 것이 정상이다.
- 기록 파일(`~/agentscope/data`, `~/.openclaw/agentscope`)은 스냅샷에 남는다. 다음 실험과 섞이지 않게 하려면 전달 후 비운다.

## 12. 문제가 생기면

| 증상 | 확인 |
|---|---|
| 게이트웨이가 멈추거나 시작이 매우 느림 | diagnostics-otel 알려진 이슈(OpenClaw #152981, 09.21 재현). `openclaw config set diagnostics.otel.enabled false` 후 재시작해 비교 |
| 모델 호출 실패(401 등) | 4절 키 확인(`grep -c` 결과 1), `systemctl --user restart`로 다시 시작했는지 |
| `credit balance is too low` | 공용 계정 API 크레딧 소진. Console Billing에서 잔액 확인(다음 결제 주기에 새로 들어옴) |
| `token_count_error` | 키 미설정, `error`에 HTTP 상태 확인(401 키 / 429 한도). 에이전트는 계속 동작함(병렬 배분만 빠짐) |
| API health가 `degraded` | `last_error` 확인, `journalctl --user -u agentscope-usage-api -n 50`. 이전 데이터로는 계속 답함 |
| `count_export_error` | Collector가 꺼짐(`systemctl --user status agentscope-collector`, `journalctl --user -u agentscope-collector`) |
| 플러그인이 안 보임 | `plugins.allow` 목록(6절 주의), `openclaw plugins list` |
| 되돌리기 | SNAP-2-P2로 복귀(이 가이드의 변경은 전부 분기에서만) |
