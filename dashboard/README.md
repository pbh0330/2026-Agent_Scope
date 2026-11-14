# AgentScope Dashboard

AI 에이전트 환경(OpenClaw + MCP)의 자산을 식별·가시화하는 대시보드입니다.
팀 브랜치의 산출물을 공통 스키마 v0.6.0-draft 형식으로 묶어 한 화면에서 봅니다.

```text
feature/scanner-config      자산 스캐너 ──┐
develop + PR #24           테스트베드 P0~P2·S1~S5 구성·VM 수집본·정답·승인 목록 ─┤
docs/threat-scenarios       S1~S5 규칙 v2.1 (카탈로그·S2 정책) ─┼─▶ pipeline/build_data.py ─▶ public/data/*.json ─▶ 대시보드
docs/mcp-attack-surface     공통 스키마 v0.6 ─┤
feature/token-collector     사용 현황 API(usageapi) ──┘
```

## 화면

| 화면 | 내용 | 읽는 파일 |
|---|---|---|
| 개요 | 상태 단계(선언→발견→노출→…) 사다리, S1~S5 평가 요약, 자산 구성, 수집 상태, 정답 비교, OpenClaw 내장 감사 | snapshot, detections, qa, audit |
| 자산 지도 | 호스트(tb-gw / tb-node)별 서버·플러그인·스킬. 도구 하나가 눈금 하나(채움=노출, 테두리=필터로 미노출, 빗금=확인 못함) | snapshot |
| 자산 목록 | 유형·확인된 상태·보안 판정·시나리오 필터와 검색 | snapshot, detections |
| 보안 경고 | 규칙별 평가 행렬, 경고마다 관련 자산·관계·근거·기준 정책, 전체 평가 기록(조건 ID와 이름) | detections |
| 기대 결과 비교 | 위협 시나리오 기대 결과(나와야 할 경고·동반 경고·판단 불가·나오면 안 되는 경고)와 탐지 결과 대조. 구성별 요약과 항목별 근거 | expected |
| 변경 비교 | P0→P1→P2, P2→각 위험 구성의 자산·관계·경고 변화 | diffs |
| 수집과 검증 | 수집 작업별 성공·부분·미수행, 정답 목록 수집률 | snapshot, qa |
| 토큰 사용 | 호출 수·귀속 토큰·추정 비용, 시간대별 토큰, 계산 방식(순차/배분), 도구·서버·구간별 사용량, 소비 브레이크 기록, 호출 기록 | 사용 현황 API 또는 `usage-api/` 사본 |

자산을 누르면 오른쪽에 상세(식별 키, 6단계 상태와 사유, 보안 평가, 자격증명 참조, 서버 정의, 설정 값, 관계, 근거)가 열립니다.
위쪽 타임라인에서 스냅샷을 바꾸고, 왼쪽 아래 버튼으로 테마(시스템/밝게/어둡게)를 바꿉니다.

## 실행

```powershell
cd dashboard
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/
```

### 토큰 사용 화면을 실시간 API로 보기

정철님 토큰 수집기의 사용 현황 API를 띄우면 개발 서버가 `/api`를 그쪽으로 넘깁니다(`vite.config.ts` 프록시). API가 꺼져 있으면 `public/data/usage-api`의 저장된 응답을 보여 줍니다.

```bash
# token-collector/backend/usageapi (Go 1.24 이상) — 대시보드 스냅샷에 연결해 띄우기
go run ./cmd/agentscope-usage-api --env agentscope-testbed --profile tb-openclaw \
  --inventory ../../../dashboard/public/data/snapshots/P2/snapshot.json \
  --input testdata/pc-1029.traces.jsonl
# 테스트베드(tb-gw): --live --addr 0.0.0.0:8088 --input '~/agentscope/data/agentscope-traces*.jsonl'
#                    --tool-results ~/.openclaw/agentscope/agentscope-tool-results.jsonl (+ 같은 --env/--profile/--inventory)
```

- **스냅샷 연결(`--inventory`)**: 자산 상세의 "실제 사용"과 토큰 화면의 자산 연결은 API를 대시보드 스냅샷 파일과 같은 `--env agentscope-testbed --profile tb-openclaw`로 띄웠을 때만 채워집니다. 값이 다르면 API가 시작을 거부합니다. 대시보드는 이름으로 추측해서 연결하지 않습니다. 위 예시의 PC 실측 데이터(16건)는 테스트베드 도구가 아니라서 연결 0건이 정상입니다.
- **API 주소(`USAGE_API_TARGET`)**: 기본은 같은 PC(`http://127.0.0.1:8088`)입니다. 테스트베드 tb-gw의 API에 붙이려면 주소를 바꿔 개발 서버를 띄웁니다. API가 CORS를 지원하지 않아 브라우저에서 직접 부를 수 없으므로 항상 이 프록시를 거칩니다.

```powershell
$env:USAGE_API_TARGET="http://<TB_GW_IP>:8088"; npm run dev      # PowerShell
USAGE_API_TARGET=http://<TB_GW_IP>:8088 npm run dev               # bash
# 또는 .env.example을 .env.local로 복사해 값을 고친 뒤 npm run dev
```

`public/data`에 생성된 데이터가 들어 있으므로 바로 실행됩니다.

## 데이터 다시 만들기

develop에 팀원 작업이 합쳐지면 저장소 구조는 아래와 같습니다. `dashboard/` 폴더에서 스캐너의 가상환경 Python으로 실행합니다.
스캐너를 실제로 실행하므로 스캐너의 `requirements.txt`(json5)가 설치된 Python이어야 합니다.

```text
2026-Agent_Scope/
├── asset-scanner/            feature/scanner-config
├── testbed/                  develop(P0~P2·S1~S5 구성) + PR #24 feature/testbed-threat-vm-capture(S1~S4 VM 수집본)
├── docs/threat-scenarios/    docs/threat-scenarios (v2.1)
├── token-collector/          feature/token-collector
└── dashboard/                이 폴더
```

```powershell
cd dashboard
..\asset-scanner\.venv\Scripts\python.exe pipeline\build_data.py `
  --scanner   ..\asset-scanner `
  --testbed   ..\testbed `
  --scenarios ..\docs\threat-scenarios
```

- `--scenarios`를 생략하면 `pipeline/policies`의 사본(카탈로그·S2 정책·기대 결과)을 씁니다.
- `--testbed`에 `profiles/S1`이 없으면(예: develop만 받은 경우) S1 스냅샷을 건너뛰고, `ground-truth/approved-servers.json`이 없으면 `pipeline/policies` 사본을 씁니다.
- `--usage-api http://127.0.0.1:8088`(선택): 실행 중인 사용 현황 API의 응답(summary, by-asset, records, timeseries, brake-events, health)을 `public/data/usage-api/`에 저장합니다. 지금 사본은 10/29 PC 실측 16건(고정 응답 모드)이고 플러그인 기록이 없어 브레이크는 비어 있습니다.
- `--usage`(선택, 이전 방식): usage.json 파일을 그대로 복사합니다(`token-collector/backend/usagereport/testdata/example.usage.json`). 화면은 API 형식만 읽습니다.

브랜치가 아직 합쳐지지 않았다면 각 브랜치를 따로 받아 둔 폴더 경로를 넘기면 됩니다.

출력 (`public/data/`)

| 파일 | 스키마 절 | 생성 |
|---|---|---|
| `manifest.json` | — | 스냅샷 목록, 비교 쌍, 출처 |
| `snapshots/<P>/snapshot.json` | 2~7 InventorySnapshot | 스캐너 출력 + 테스트베드 원본 → 어댑터 |
| `snapshots/<P>/detections.json` | 13 DetectionReport | S1~S5 정적 탐지 (규칙 세트 = 시나리오 카탈로그 v2.1) |
| `scenario-catalog.json` | 13 ScenarioDefinition | docs/threat-scenarios 카탈로그 사본 |
| `snapshots/<P>/expected.json` | 16.2 QAResult(checks) | expected-results.md(+ 테스트베드 S1.json)와 탐지 결과 대조. P2와 위험 구성만 |
| `snapshots/<P>/qa.json` | 16.2 QAResult | 정상군만, 정답 목록 비교 |
| `snapshots/<P>/scanner/*.json` | — | 스캐너 원본 출력(참고용) |
| `diffs/<A>__<B>.json` | 12.5·12.9 SnapshotDiff | 자산·관계·경고 변화 |
| `usage-api/*.json` | 14 (API 응답) | 사용 현황 API 응답 사본 |
| `usage.json` | 14 UsageReport | `--usage`를 줬을 때만, 토큰 수집기 출력 그대로 |

### 스냅샷 구성

- **P0, P1, P2**: 테스트베드 정상군. 설정 사본에 스캐너를 실행하고 `ground-truth/raw`의 서버 광고·노출 원본을 붙였습니다. 정답 목록과 비교해 선언·광고 자산 수집률 100%, 관계 일치율 P1·P2 100%(P0는 페어링 원본이 없어 15/16).
- **위험 구성**: 테스트베드 `profiles/<키>` 설정과 `ground-truth/raw/<키>` VM 수집본을 그대로 씁니다. 탭 순서는 구현 우선순위(S1 → S2 → S4 → S3 → S5)이고, 기대 결과는 테스트베드 정답 파일(`ground-truth/<키>.json`의 `expected_*`)과 대조합니다.

| 탭 | 테스트 | 출처 |
|---|---|---|
| S1 | S1-T1~T4 (S4-T3 동반) | **VM 수집** SNAP-3-S1 (PR #24) |
| S2 | S2-T1, T2 | **VM 수집** SNAP-3-S2 |
| S4 | S4-T1, T2 | **VM 수집** SNAP-3-S4 |
| S3 | S3-T1, T2 | **VM 수집** SNAP-3-S3 (inventory-remote 실제 광고본) |
| S1-T5 | 선언 위치 이상 | 설정 사본(VM 미구축) — 수집본은 P2 기준, 바뀐 서버의 노출은 미확인 |
| S5-T1~T3 | 평문 전송, 인증서 검증 끔, sslVerify 없음 | 설정 사본(VM 미구축) |

화면에는 "VM 수집"과 "설정 사본"으로 구분해 표시합니다. 이제 대시보드가 직접 만든 합성 구성은 없습니다.

### 다른 팀원 결과 바로 보기

`snapshot.json`(필수)과 `detections.json`(선택)을 화면에 끌어다 놓거나 왼쪽 아래 폴더 버튼으로 열면 "불러옴" 스냅샷으로 추가됩니다.
스캐너 내부 형식(`agent-scope.scanner.*`)은 먼저 파이프라인으로 변환해야 합니다.

## 어댑터가 한 일과 남은 차이

- **자산 ID**: ID 규칙 협의안 B안(canonical key + SHA-256 앞 16자리). canonical key는 정답 목록의 `asset_key` 형식(`tb-gw/mcp_server/fs-workspace`)을 그대로 써서 QA 매핑이 이름이 아닌 키로 됩니다. 규칙 확정 시 `pipeline/agentscope_pipeline/ids.py`만 바꾸면 됩니다.
- **8종 분류**: 8종 협의안에 따라 Gateway를 자산으로 두고, 모든 자산의 `context.gateway_ref`는 같은 스냅샷의 Gateway `asset_id`를 가리킵니다(QA-INT-01).
- **스캐너 값 우선**: 최신 스캐너(11/13)가 `sslVerify`·`toolFilter` 선언값을 직접 수집하므로 그 값을 그대로 씁니다. 예전 스캐너처럼 키 이름만 있을 때에만 어댑터가 설정에서 보강하고 `adapter_supplement`로 기록합니다. 최신 수집값을 덮어쓰지 않습니다(QA-INT-02). 플러그인이 등록한 서버도 스캐너 `--plugin-manifest` 결과(비밀값 가림 적용)를 우선 씁니다.
- **MCP 버전**: 스캐너 tools_catalog가 `2025-11-25`·`2026-07-28`을 모두 지원하게 되어, 저장된 `*.advertised.json`을 스캐너가 읽은 결과로 Tool 자산을 만듭니다(수집 작업 `details.parsed_by`). 스캐너가 읽지 못한 경우에만 원본을 직접 읽고 사유를 남깁니다.
- **탐지기**: 팀 탐지 모듈이 아직 없어 위협 시나리오 v2.1(부록 A, `scenario-catalog.json`)을 옮긴 구현(`detector.py`)을 넣었습니다. 조건 ID(`S1-C1` 등)와 기본 심각도·신뢰도는 카탈로그에서 읽고, 판정 기준은 S1·S4-C3 `approved-servers.json`, S2 `expected-tool-policy.json`입니다. 모든 위험 구성에서 `expected-results.md`의 필수 경고·비경고·판단 불가와 일치하는 것을 확인했습니다. 평가를 항상 함께 출력해 "이상 없음"과 "판단 불가"를 구분하며, 탐지 모듈이 생기면 같은 `detections.json` 형식으로 교체하면 화면은 그대로입니다.
- **토큰 사용**: 사용 현황 API 응답 필드를 그대로 씁니다(`src/types/contracts.ts`의 Usage* 타입, `src/data/usage.ts`). 지금 사본은 PC 실측 데이터(`env-pc`)라 테스트베드 스냅샷과 자산 연결이 0건입니다. 테스트베드 실시간 모드에서 `--inventory`로 띄우면 이어집니다. 사용 기록은 자산의 "사용됨" 상태를 바꾸지 않고 따로 표시합니다(스키마 14.2).

## QA 첫 통합 실행(QA-INT-01) 대조표

P0 기준으로 대시보드 출력과 테스트베드 정답(`ground-truth/P0.json`)의 차이와 이유입니다.

| 구분 | 정답 | 대시보드 | 차이 이유 |
|---|---|---|---|
| Gateway · Node · MCP Server · Tool | 1 · 1 · 1 · 14 | 1 · 1 · 1 · 14 | 일치 |
| Permission/Auth | — (정답 범위 밖) | 3 | `Gateway 접속 인증`(gateway.auth), `에이전트 도구 정책`(tools.profile), `fs-workspace · toolFilter`. 별도 대조 대상 |
| **자산 합계** | **17** | **20** | 위 Permission/Auth 3개 |
| DECLARES · ADVERTISES | 1 · 14 | 1 · 14 | 일치 |
| PAIRED_WITH | 1 | 0 | 페어링 원본(`devices list`)이 P0 수집본에 없어 만들지 않음 |
| APPLIES_TO | — | 3 | 위 Permission/Auth 3개가 적용 대상(Gateway 2, fs-workspace 1)을 가리킴 |
| **관계 합계** | **16** | **18** | +3(APPLIES_TO) −1(PAIRED_WITH) |

- `gateway_ref`는 모든 자산에서 같은 스냅샷의 Gateway `asset_id`입니다.
- 실행 commit·스냅샷 ID는 `public/data/manifest.json`의 `generated_at`, `sources`와 `snapshots/P0/snapshot.json`의 `snapshot_id`로 고정합니다.

## 구조

```text
pipeline/
  build_data.py                  실행 진입점, 위험 구성 정의 (expected-results.md 기준)
  agentscope_pipeline/
    adapter.py                   스캐너 출력 + 테스트베드 원본 → InventorySnapshot (+ 수용 검증)
    detector.py                  S1~S5 v2.1 조건 → DetectionReport
    compare.py                   SnapshotDiff, QAResult
    expected.py                  기대 결과 ↔ 탐지 결과 대조
    ids.py                       자산·관계 ID
  policies/                      카탈로그·S2 정책·승인 서버 목록 사본 (원본: docs/threat-scenarios, testbed)
src/
  types/contracts.ts             공통 스키마 타입
  data/load.ts, model.ts         로딩, 색인, 보안 판정 요약
  data/usage.ts                  사용 현황 API 연결(실시간 → 저장 사본)
  pages/                         화면 8개
  components/                    상세 패널, 공통 표시 요소
  styles.css                     디자인 토큰(밝게/어둡게)
public/data/                     파이프라인 출력
```

## 표시 원칙

- 실제 비밀값은 수집·표시하지 않습니다. 자격증명은 참조 이름·저장 위치·설정 경로만 보입니다.
- 서버가 보낸 설명·스키마는 신뢰하지 않는 데이터로만 표시합니다.
- 확인하지 못한 상태는 "확인 못함"과 사유로 표시하고, 미평가를 정상으로 표시하지 않습니다.
- 호출 가능·사용됨은 정적 분석으로 판정하지 않습니다.
