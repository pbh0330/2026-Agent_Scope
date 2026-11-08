# AgentScope Dashboard

AI 에이전트 환경(OpenClaw + MCP)의 자산을 식별·가시화하는 대시보드입니다.
팀 브랜치의 산출물을 공통 스키마 v0.6.0-draft 형식으로 묶어 한 화면에서 봅니다.

```text
feature/scanner-config      자산 스캐너 ──┐
feature/testbed-threat-s1   테스트베드 원본·정답·S1 구성·승인 목록 ─┤
docs/threat-scenarios       S1~S5 규칙 v2.1 (카탈로그·S2 정책) ─┼─▶ pipeline/build_data.py ─▶ public/data/*.json ─▶ 대시보드
docs/mcp-attack-surface     공통 스키마 v0.6 ─┤
feature/token-collector     usage.json ──┘
```

## 화면

| 화면 | 내용 | 읽는 파일 |
|---|---|---|
| 개요 | 상태 단계(선언→발견→노출→…) 사다리, S1~S5 평가 요약, 자산 구성, 수집 상태, 정답 비교, OpenClaw 내장 감사 | snapshot, detections, qa, audit |
| 자산 지도 | 호스트(tb-gw / tb-node)별 서버·플러그인·스킬. 도구 하나가 눈금 하나(채움=노출, 테두리=필터로 미노출, 빗금=확인 못함) | snapshot |
| 자산 목록 | 유형·확인된 상태·보안 판정·시나리오 필터와 검색 | snapshot, detections |
| 보안 경고 | 규칙별 평가 행렬, 경고마다 관련 자산·관계·근거·기준 정책, 전체 평가 기록(조건 ID와 이름) | detections |
| 변경 비교 | P0→P1→P2, P2→각 위험 구성의 자산·관계·경고 변화 | diffs |
| 수집과 검증 | 수집 작업별 성공·부분·미수행, 정답 목록 수집률 | snapshot, qa |
| 토큰 사용 | 도구 호출별 추정 입력 토큰·비용·자산 연결 | usage |

자산을 누르면 오른쪽에 상세(식별 키, 6단계 상태와 사유, 보안 평가, 자격증명 참조, 서버 정의, 설정 값, 관계, 근거)가 열립니다.
위쪽 타임라인에서 스냅샷을 바꾸고, 왼쪽 아래 버튼으로 테마(시스템/밝게/어둡게)를 바꿉니다.

## 실행

```powershell
cd dashboard
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/
```

`public/data`에 생성된 데이터가 들어 있으므로 바로 실행됩니다.

## 데이터 다시 만들기

develop에 팀원 작업이 합쳐지면 저장소 구조는 아래와 같습니다. `dashboard/` 폴더에서 스캐너의 가상환경 Python으로 실행합니다.
스캐너를 실제로 실행하므로 스캐너의 `requirements.txt`(json5)가 설치된 Python이어야 합니다.

```text
2026-Agent_Scope/
├── asset-scanner/            feature/scanner-config
├── testbed/                  feature/testbed-threat-s1 (P0~P2 + S1, approved-servers.json)
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

- `--scenarios`를 생략하면 `pipeline/policies`의 사본(카탈로그·S2 정책)을 씁니다.
- `--testbed`에 `profiles/S1`이 없으면(예: feature/testbed-profiles) S1 스냅샷을 건너뛰고, `ground-truth/approved-servers.json`이 없으면 `pipeline/policies` 사본을 씁니다.
- `--usage`(선택): 토큰 수집기가 웹 API(`backend/usageapi`)로 바뀌어 지금은 넘길 파일이 없습니다. `public/data/usage.json`은 이전 형식 검증 로그이며, API 연동은 다음 작업입니다.

브랜치가 아직 합쳐지지 않았다면 각 브랜치를 따로 받아 둔 폴더 경로를 넘기면 됩니다.

출력 (`public/data/`)

| 파일 | 스키마 절 | 생성 |
|---|---|---|
| `manifest.json` | — | 스냅샷 목록, 비교 쌍, 출처 |
| `snapshots/<P>/snapshot.json` | 2~7 InventorySnapshot | 스캐너 출력 + 테스트베드 원본 → 어댑터 |
| `snapshots/<P>/detections.json` | 13 DetectionReport | S1~S5 정적 탐지 (규칙 세트 = 시나리오 카탈로그 v2.1) |
| `scenario-catalog.json` | 13 ScenarioDefinition | docs/threat-scenarios 카탈로그 사본 |
| `snapshots/<P>/qa.json` | 16.2 QAResult | 정상군만, 정답 목록 비교 |
| `snapshots/<P>/scanner/*.json` | — | 스캐너 원본 출력(참고용) |
| `diffs/<A>__<B>.json` | 12.5·12.9 SnapshotDiff | 자산·관계·경고 변화 |
| `usage.json` | 14 UsageReport | 토큰 수집기 출력 그대로 |

### 스냅샷 구성

- **P0, P1, P2**: 테스트베드 정상군. 설정 사본에 스캐너를 실행하고 `ground-truth/raw`의 서버 광고·노출 원본을 붙였습니다. 정답 목록과 비교해 선언·광고 자산 수집률 100%, 관계 일치율 P1·P2 100%(P0는 페어링 원본이 없어 15/16).
- **위험 구성**: `docs/threat-scenarios/expected-results.md`의 테스트 케이스를 그대로 옮겼고, 탭 순서는 구현 우선순위(S1 → S2 → S4 → S3 → S5)입니다.

| 탭 | 테스트 | 출처 |
|---|---|---|
| S1 | S1-T1~T4 (S4-T3 동반) | **테스트베드 구성 사본** `testbed/profiles/S1` + `raw/S1` 광고 원본. 플러그인 점검 원본이 없으면 저장소 manifest로 대신 읽고, 노출 목록은 S1에서 다시 수집하기 전까지 미확인 |
| S1-T5 | 선언 위치 이상 | 합성 (P2 설정 변경) |
| S2 | S2-T1, T2 | 합성 |
| S4 | S4-T1, T2 | 합성 |
| S3 | S3-T1, T2 | 합성 (inventory-remote 광고 원본에 도구 2개 추가) |
| S5-T1~T3 | 평문 전송, 인증서 검증 끔, sslVerify 없음 | 합성 |

합성 구성은 화면에 "P2 기반 합성 위험 구성"으로 표시됩니다. 테스트베드에 실제 위험 스냅샷이 생기면 S1처럼 `profiles/<키>`를 읽도록 추가하면 됩니다.

### 다른 팀원 결과 바로 보기

`snapshot.json`(필수)과 `detections.json`(선택)을 화면에 끌어다 놓거나 왼쪽 아래 폴더 버튼으로 열면 "불러옴" 스냅샷으로 추가됩니다.
스캐너 내부 형식(`agent-scope.scanner.*`)은 먼저 파이프라인으로 변환해야 합니다.

## 어댑터가 한 일과 남은 차이

- **자산 ID**: ID 규칙 협의안 B안(canonical key + SHA-256 앞 16자리). canonical key는 정답 목록의 `asset_key` 형식(`tb-gw/mcp_server/fs-workspace`)을 그대로 써서 QA 매핑이 이름이 아닌 키로 됩니다. 규칙 확정 시 `pipeline/agentscope_pipeline/ids.py`만 바꾸면 됩니다.
- **8종 분류**: 8종 협의안에 따라 Gateway를 자산으로 두고 `context.gateway_ref`도 채웠습니다(스키마 v0.6 본문은 7종 + Gateway 문맥).
- **스캐너 보강**: 스캐너 0.1.0은 `sslVerify`, `toolFilter`의 키 이름만 남깁니다. S2·S5 판정에 값이 필요해 어댑터가 설정에서 비밀이 아닌 두 값만 보강하고, 수집 작업 `adapter_supplement`와 자산의 `normalizations`에 기록했습니다. **스캐너에서 값을 수집하도록 바뀌면 이 보강은 지워도 됩니다.**
- **MCP 버전**: 테스트베드 실제 협상 버전은 `2025-11-25`라 스캐너의 tools_catalog(2026-07-28 전용)를 쓰지 않고 `*.advertised.json`을 직접 읽었습니다. 근거에 버전 차이를 표시합니다.
- **탐지기**: 팀 탐지 모듈이 아직 없어 위협 시나리오 v2.1(부록 A, `scenario-catalog.json`)을 옮긴 구현(`detector.py`)을 넣었습니다. 조건 ID(`S1-C1` 등)와 기본 심각도·신뢰도는 카탈로그에서 읽고, 판정 기준은 S1·S4-C3 `approved-servers.json`, S2 `expected-tool-policy.json`입니다. 모든 위험 구성에서 `expected-results.md`의 필수 경고·비경고·판단 불가와 일치하는 것을 확인했습니다. 평가를 항상 함께 출력해 "이상 없음"과 "판단 불가"를 구분하며, 탐지 모듈이 생기면 같은 `detections.json` 형식으로 교체하면 화면은 그대로입니다.
- **토큰 사용**: 현재 usage.json은 토큰 수집기 검증 로그(`env-test-01`)라 테스트베드 스냅샷과 연결되지 않습니다. 테스트베드에서 텔레메트리를 수집하면 자산별로 이어집니다.

## 구조

```text
pipeline/
  build_data.py                  실행 진입점, 위험 구성 정의 (expected-results.md 기준)
  agentscope_pipeline/
    adapter.py                   스캐너 출력 + 테스트베드 원본 → InventorySnapshot (+ 수용 검증)
    detector.py                  S1~S5 v2.1 조건 → DetectionReport
    compare.py                   SnapshotDiff, QAResult
    ids.py                       자산·관계 ID
  policies/                      카탈로그·S2 정책·승인 서버 목록 사본 (원본: docs/threat-scenarios, testbed)
src/
  types/contracts.ts             공통 스키마 타입
  data/load.ts, model.ts         로딩, 색인, 보안 판정 요약
  pages/                         화면 7개
  components/                    상세 패널, 공통 표시 요소
  styles.css                     디자인 토큰(밝게/어둡게)
public/data/                     파이프라인 출력
```

## 표시 원칙

- 실제 비밀값은 수집·표시하지 않습니다. 자격증명은 참조 이름·저장 위치·설정 경로만 보입니다.
- 서버가 보낸 설명·스키마는 신뢰하지 않는 데이터로만 표시합니다.
- 확인하지 못한 상태는 "확인 못함"과 사유로 표시하고, 미평가를 정상으로 표시하지 않습니다.
- 호출 가능·사용됨은 정적 분석으로 판정하지 않습니다.
