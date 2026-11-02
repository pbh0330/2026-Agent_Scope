# SNAP-1 설정 검증 결과 (스캐너 V3)

검증일: 2026-10-05 · 대상: 자산 스캐너 V3 (기준 커밋 `0c9a230a5db6cd39ed9143f2e4c2e5440d5bedd5`)

이 문서는 팀 테스트베드 SNAP-1의 Gateway·Node 설정 두 개를 현재 스캐너(코드 변경 없음)로 읽어 본 결과다. 새 수집 기능이나 공통 스키마는 구현하지 않았다. 출력은 여전히 스캐너 내부 협의용 초안이다.

## 1. 사용한 입력

팀 저장소 `pbh0330/2026-Agent_Scope`의 PR 커밋에서 `git show`로 읽어 로컬 사본(`asset-scanner/output/snap1/inputs/`, Git 제외 경로)에 보관했다. 다른 팀원 브랜치는 병합·체크아웃하지 않았다.

| 용도 | 저장소 경로 | 커밋 |
| --- | --- | --- |
| 스캐너 입력 (Gateway) | `testbed/baseline/SNAP-1/tb-gw.openclaw.json` | `3a5e7e833d9ba0b61a1a1d4706fb01d729073440` (PR #9) |
| 스캐너 입력 (Node) | `testbed/baseline/SNAP-1/tb-node.openclaw.json` | 위와 동일 |
| 대조 근거 | `testbed/baseline/SNAP-1/tb-gw.mcp-list.txt` | 위와 동일 |
| 대조 근거 | `testbed/README.md`, `testbed/docs/build-log-snap0-snap1.md` | 위와 동일 |
| QA 기준 | `QA/README.md`, `QA_테스트계획.md`, `QA_테스트케이스.md`, `QA_GroundTruth.md` | `762ca44390f0eb017845f0d94fb01a83c49408af` (PR #8) |

## 2. 환경 구분

| 구분 | 내용 |
| --- | --- |
| 테스트베드 (문서 기록) | OpenClaw 2026.9.6 (eb377ac), Ubuntu 24.04.5 LTS, Node.js v24.21.0. 스캐너는 이 VM에서 실행하지 않았다. |
| 스캐너 실행 PC (이번 실행) | Windows 10, Python 3.14.4, pytest 9.1.1, 콘솔 코드페이지 cp949 |

스캐너 실행 PC에는 OpenClaw를 설치하지 않았고 테스트베드 VM에도 접속하지 않았다. 입력은 문서 저장소에 올라온 설정 사본뿐이다.

## 3. 현재 V3의 읽기 범위

V3는 설정 파일의 **`mcp.servers`만** 읽는다. `nodeHost.mcp.servers`, 플러그인, 스킬, 내장 도구는 읽지 않는다. 따라서 이번 결과를 "Gateway·Node와 내장 Skill·Plugin까지 자산이 0개"라고 해석하면 안 된다.

## 4. 실행 명령과 결과

모든 명령은 `asset-scanner/`에서 실행했다 (`.venv`의 Python 사용).

| 단계 | 명령 | 종료 코드 | 결과 |
| --- | --- | --- | --- |
| 기존 테스트 | `python -m pytest -q -p no:cacheprovider` | 0 | **69개 통과, 0개 실패** (9.87초), stderr 비어 있음 |
| Gateway | `python -m asset_scanner --config <tb-gw.openclaw.json> --output output/snap1/tb-gw.result.json` | **1** | 결과 JSON 저장됨, stderr에 예외 (아래 결함 D1) |
| Node | `python -m asset_scanner --config <tb-node.openclaw.json> --output output/snap1/tb-node.result.json` | **1** | 위와 동일 |
| Gateway (참고) | 위 명령 앞에 `PYTHONUTF8=1` | 0 | stderr 비어 있음 |
| Node (참고) | 위 명령 앞에 `PYTHONUTF8=1` | 0 | stderr 비어 있음 |

`PYTHONUTF8=1` 실행은 결함 D1의 원인을 좁히기 위한 참고 실행이다. 공식 검증 결과는 환경변수 없이 실행한 두 줄이다.

## 5. 예상 결과와 실제 결과

두 설정 모두 최상위에 `mcp` 영역이 없다. 예상은 아래와 같고, 결과 JSON은 두 설정 모두 예상과 일치했다.

| 필드 | 예상 | Gateway 실제 | Node 실제 |
| --- | --- | --- | --- |
| `collection.status` | `complete` | `complete` | `complete` |
| `collection.outcome` | `registry_absent` | `registry_absent` | `registry_absent` |
| `collection.server_count` | `null` | `null` | `null` |
| `servers` | 빈 배열 | 빈 배열 | 빈 배열 |
| `collection.unresolved` | 비어 있음 | 비어 있음 | 비어 있음 |

- 이 값은 "해당 설정에 `mcp.servers` 등록 영역이 없다"는 뜻이다. `empty_registry` 또는 `server_count: 0`이 아니다.
- 테스트베드 대조 근거: `tb-gw.mcp-list.txt`는 OpenClaw CLI가 `mcp` 경로 미설정과 "등록된 MCP 서버 없음"을 출력했다고 기록한다. 이 CLI는 `mcp.servers`만 보여 주며 mcporter 서버는 포함하지 않는다고 같은 파일에 적혀 있다. 스캐너의 `registry_absent`와 방향이 일치하지만, 서로 다른 도구의 출력이다.
- Node 설정도 같은 결과가 나왔지만, 이것은 Node 설정에 `mcp.servers`가 없다는 사실만 보여 준다. `nodeHost.mcp.servers` 수집 기능이 검증된 것이 아니다 (V3에는 그 기능이 없다).

## 6. 추가 확인

| 확인 항목 | 결과 |
| --- | --- |
| 입력 파일 내용·수정 시각의 실행 전후 동일 여부 | 9개 입력 사본 모두 SHA-256과 수정 시각이 동일 |
| 인증값 출력 여부 | 입력에 있던 토큰 자리표시자 문자열이 결과 JSON 4개, stdout·stderr 파일, pytest 출력에 나타나지 않았다 (검색 0건). 이 검사의 범위는 여기까지다. 스캐너가 `gateway.auth`를 수집하지 않으므로, 해당 인증값에 대한 **가림 기능이 동작한 것을 검증한 것은 아니다**. |
| 프로그램 실행·서버 접속 | 소스에서 `subprocess`·`os.system`·`socket`·`requests` 등 실행·네트워크 사용 코드를 검색해 찾지 못했다. 유일하게 일치한 것은 `urllib.parse` 문자열 파싱 import다. 코드 검색과 설정에 서버 항목이 없다는 사실에 근거한 확인이며, 네트워크·프로세스 감시로 확인한 것은 아니다. |
| 환경변수 설정 여부에 따른 결과 JSON | `PYTHONUTF8` 유무와 관계없이 `generated_at`을 제외하고 동일 |

입력에는 Gateway 인증 토큰 필드가 있으나 값은 자리표시자였다. 스캐너가 `gateway.auth`를 읽지 않으므로 결과에 해당 영역이 애초에 나타나지 않는다. 비밀값 가림 규칙의 검증은 기존 단위·회귀 테스트(`mcp.servers` 안의 env·headers·args·URL 등)의 범위이며, 이번 SNAP-1 실행으로 새로 검증한 것이 아니다.

## 7. 발견한 결함

### D1. Windows cp949 콘솔에서 요약 출력 중 예외로 종료 코드가 1이 된다

- 기대: `status: complete`이면 종료 코드 0, 오류 출력 없음 (README의 종료 코드 표).
- 실제: 결과 JSON은 정상 저장되지만, 수집 사유를 출력하는 문장에서 유니코드 줄표(U+2014)를 cp949 인코딩으로 쓰지 못해 `UnicodeEncodeError`가 발생하고 프로세스가 종료 코드 1로 끝난다. 이 코드 1은 "부분 수집"이 아니라 처리되지 않은 예외다. stdout에는 첫 줄(수집 상태)만 출력된다.
- 재현: cp949 코드페이지의 Windows에서 `PYTHONUTF8` 없이 `python -m asset_scanner --config <설정> --output <결과>`를 stdout을 파일로 리다이렉트해 실행한다. 설정은 `mcp`가 없는 최소 JSON이면 충분하다 (사유가 1건 이상 출력되는 모든 경우에 해당할 가능성이 있다).
- 확인하지 못한 것: 리다이렉트 없이 콘솔에 직접 출력할 때의 동작. 사유가 없는 정상 수집의 동작.
- 기존 69개 테스트는 이 경로를 잡지 못했다 (테스트 실행 환경에서는 통과).
- (최초 기록) 이 검증 단계에서는 수정하지 않았다. 판정 규칙(`complete`/`registry_absent`)과는 무관한 출력 인코딩 문제다. 수정은 아래 10장에 기록했다.

## 8. 확인한 범위와 확인하지 못한 범위

확인한 것
- SNAP-1 Gateway·Node 설정 사본 두 개에 대해 V3가 `registry_absent` / `complete` / `server_count: null` / 빈 `servers`를 반환한다.
- 입력 변경 없음, 인증값 비노출, 코드 검색 기준 실행·접속 코드 없음.
- 기존 69개 단위 테스트가 이 PC에서 통과한다.

확인하지 못한 것
- **QA 문서의 32개 검증 항목**(S1~S5 10, COL 8, REL 2, SCHEMA 4, SEC 2, UI 4, NFR 2)은 pytest 테스트와 별개의 목록이며, 이번 실행으로 어느 항목도 합격 판정하지 않았다. `registry_absent`는 "설정에 등록 영역이 없다"는 설정 파일 상태이고, MCP 서버에 `tools/list`를 요청해 성공한 뒤 목록이 비어 있는 상황(QA-COL-06이 다루는 정상 빈 목록)과는 다른 상황이다. 이번에는 `tools/list`를 실행하지 않았으므로 QA-COL-06의 근거로 쓰지 않는다. QA-COL-02(Gateway·Node 분산 설정)도 `nodeHost.mcp.servers`를 읽지 못하므로 판정하지 않는다.
- `nodeHost.mcp.servers`, 플러그인·스킬·내장 도구 수집은 V3 범위 밖이다.
- 실제 SNAP-1 VM에서의 스캐너 실행, 실제 `~/.openclaw/openclaw.json` 원본 읽기. 이번 입력은 문서 저장소에 올라온 사본이다.
- MCP 서버가 실제로 있는 설정에서의 동작. SNAP-1에는 서버가 없다.
- 대조 근거인 CLI 출력은 Gateway 쪽만 있다. Node 쪽 `openclaw mcp list` 출력은 제공된 자료에 없다.

## 9. 다음 개발 항목

순서: D1 수정(완료, 10장) → `nodeHost.mcp.servers` 수집 지원 → 서버가 등록된 SNAP-2 설정 검증.

1. ~~D1 수정과 회귀 테스트 (cp949 환경 포함)~~ — 완료, 10장 참조.
2. **`nodeHost.mcp.servers` 수집 지원**: 테스트베드 문서가 노드 측 MCP 서버 위치로 기록한 경로이며, V3는 읽지 않는다. 등록 영역 위치를 `mcp.servers`·`nodeHost.mcp.servers`로 구분해 출처(`registry_path`)에 남긴다. 구현 전에 이 경로가 2026.9.6 문서에서도 유효한지 확인한다.
3. 서버가 하나 이상 등록된 SNAP-2 설정으로 필드별 수집 여부 대조.

## 10. D1 수정과 재검증

위 4~9장의 결과는 수정 전 최초 실행 기록이며 그대로 보존했다.

### 수정 전 재현 (회귀 테스트 `tests/test_console_encoding.py`)

PYTHONUTF8·PYTHONIOENCODING을 제거하고 `PYTHONIOENCODING=cp949`로 별도 프로세스를 실행해 stdout·stderr를 바이트로 캡처하고 종료 코드를 검사한다. 기존 `run_cli` 헬퍼는 `PYTHONIOENCODING=utf-8`을 강제해 D1을 가리고 있었다.

수정 전 실행(로그 `d1-before-fix.pytest.log`, 종료 코드 1): 4개 실패.
- 줄표 사유 출력, 이모지 서버 이름 출력, `failed` 수집의 종료 코드(기대 3, 실제 1)는 D1이 원인이었다. 따라서 D1은 `complete`뿐 아니라 `partial`·`failed` 종료 코드도 1로 바꿀 수 있다 (`partial`은 원래 1이라 구분되지 않는다).
- 한글 서버 이름 테스트의 실패는 D1이 아니라 테스트의 기대 문자열 오류였다 (실제 출력은 `mcp.servers["이름"]` 형태, 한글은 정상 출력, 종료 코드 0). 기대값만 고쳤다.

### 수정 방식

`asset_scanner/cli.py`의 `main` 시작에서 표준출력·표준오류를 `errors="backslashreplace"`로 재설정한다. 표현 가능한 문자는 그대로 출력하고, 표현할 수 없는 문자만 `\uXXXX`·`\UXXXXXXXX`로 표시한다. 오류를 삼키거나 종료 코드를 고정하지 않는다. 수집 판정, 결과 JSON 구조, 종료 코드 규칙, 결과 파일 인코딩(UTF-8)은 바꾸지 않았다. 단, 콘솔에 표시된 이스케이프 문자열은 원문이 아니므로 정확한 값은 결과 JSON에서 확인해야 한다.

### 수정 후 재검증

| 항목 | 명령 | 종료 코드 | 결과 |
| --- | --- | --- | --- |
| D1 회귀 테스트 | `python -m pytest -v -p no:cacheprovider tests/test_console_encoding.py` | 0 | 4개 통과 |
| 전체 테스트 | `python -m pytest -v -p no:cacheprovider` | 0 | **73개 통과, 0개 실패** (기존 69 + 신규 4, 16.82초) |
| Gateway (UTF-8 설정 없음) | `python -m asset_scanner --config <tb-gw.openclaw.json> --output output/snap1/tb-gw.fixed.result.json` | 0 | stderr 0바이트 |
| Node (UTF-8 설정 없음) | 위와 동일 (tb-node) | 0 | stderr 0바이트 |

- 두 설정 모두 `complete` / `registry_absent` / `server_count: null` / `servers: []`.
- 입력 9개의 SHA-256과 수정 시각이 재실행 후에도 동일했다.
- 수정 후 결과 JSON은 수정 전 결과와 `generated_at`·`source_path`를 제외하고 동일했다.
- 입력의 토큰 자리표시자 문자열은 수정 후 결과·stdout·stderr에도 없었다 (6.장의 범위 한계 동일).

### 남은 한계

- `PYTHONIOENCODING=cp949`로 재현했다. 실제 Windows 콘솔(리다이렉트 없이 직접 출력)에서의 동작은 직접 확인하지 못했다.
- 이스케이프된 표시는 사람이 읽기 어려울 수 있다. 정확한 이름은 결과 JSON을 본다.
- 표준출력·표준오류 외의 출력 경로(예: 파일)는 이 수정의 대상이 아니다. 결과 파일은 원래 UTF-8이다.

## 11. Node 등록 영역 선택 지원 후 재검증 (`--registry-path nodeHost.mcp.servers`)

10장까지는 `mcp.servers`만 읽는 V3 기준이다. 이후 `--registry-path` 옵션을 추가했다 (기본값 `mcp.servers` 유지).

### 경로 근거 (2026-10-06 확인)

- 팀 테스트베드 문서의 `nodeHost.mcp.servers`는 팀의 09.15 조사 기록이다. 이번에 OpenClaw **2026.9.6** npm 패키지(`npm pack`으로 tarball만 내려받음, 설치·실행 없음, 레지스트리 무결성값은 실행 로그에 보관)의 `docs/nodes/mcp-and-skills.md`를 직접 읽어 같은 경로가 문서화돼 있음을 확인했다.
- 현행 공개 문서(docs.openclaw.ai/nodes/mcp-and-skills)도 같은 경로를 보여 준다. 공개 문서에는 버전 표기가 없어 이것만으로는 2026.9.6과의 일치를 확정할 수 없고, 위 패키지 문서가 버전 근거다.
- 확인하지 못한 것: 설정 스키마(`openclaw config schema`)·소스. Node 서버 항목의 허용 필드와 `enabled` 지원 여부는 문서에 나오지 않는다. 따라서 "문서로 확인된 경로"이며 스키마로 검증된 것은 아니다.

### 가상 설정 검증 (자동 테스트)

`tests/test_registry_path.py` 26개와 가상 예제 `examples/node-and-gateway.json5`로 확인했다. 실제 팀 설정이 아니다.

- Node 서버 2개 수집, 비활성 서버 보존, 출처·선언 위치가 `nodeHost.mcp.servers`로 기록됨
- 파일 전체를 파싱하되 선택한 영역만 수집·보고 (같은 파일에 두 영역이 있어도 고르지 않은 영역의 중복·include·가린 키가 결과에 나타나지 않음)
- 영역 없음 / 빈 목록(`server_count: 0`) / 잘못된 구조(`failed`) 구분
- 잘못된 서버 하나가 있어도 정상 서버 보존, 중복 키·미해석 참조·비밀값 가림·이름 충돌 처리 유지
- 기본 경로 동작과 기존 실패 코드(`mcp_not_object`, `servers_not_object`) 유지, 지원하지 않는 경로는 종료 코드 2

### 테스트 실행 결과

| 명령 | 종료 코드 | 결과 |
| --- | --- | --- |
| `python -m pytest -v -p no:cacheprovider tests/test_registry_path.py` | 0 | 26개 통과 |
| `python -m pytest -v -p no:cacheprovider` (전체) | 0 | **99개 통과, 0개 실패** (기존 73 + 신규 26) |

로그: `output/snap1/node-new-tests.pytest.log`, `output/snap1/full-with-node.pytest.log`, 종료 코드는 각 `.exit.txt`.

### 테스트베드 설정 사본 검증 (SNAP-1, UTF-8 설정 없이 실행)

| 입력 | 선택한 영역 | 종료 코드 | 결과 |
| --- | --- | --- | --- |
| `tb-node.openclaw.json` | `nodeHost.mcp.servers` | 0 | `complete` / `registry_absent` / `server_count: null` / `servers: []`, 사유 `field_path: nodeHost.mcp` |
| `tb-gw.openclaw.json` | `nodeHost.mcp.servers` | 0 | 같은 결과 (`nodeHost` 자체가 없어 사유 `field_path: nodeHost`) |
| `tb-gw.openclaw.json` | `mcp.servers` | 0 | `registry_absent` (10장과 동일) |

- 입력 9개의 SHA-256과 수정 시각은 실행 전후 동일했고, 입력의 토큰 자리표시자는 결과·stdout·stderr에 없었다 (범위는 6장과 동일).
- SNAP-1 Node 설정에는 `nodeHost.autoUpdate`만 있고 `nodeHost.mcp`가 없다. 테스트베드 문서의 "노드 측 MCP 서버 0건"은 "등록 영역이 선언되지 않음"이며, 스캐너 결과도 같은 의미(`registry_absent`)이다.
- **이 실행만으로 실제 Node 서버 수집이 검증된 것이 아니다.** SNAP-1에는 서버가 없어 서버 항목 추출은 가상 설정 테스트로만 확인했다.

### 남은 한계

- 서버가 실제로 등록된 Node 설정(SNAP-2 이후)과 스키마·소스 대조는 아직 하지 않았다.
- `nodeHost.mcp.servers` 항목에 `enabled`가 문서화돼 있지 않다. 설정에 적힌 값만 기록하며 기본 동작을 추측하지 않는다.
- 한 번의 실행은 한 영역만 읽는다. Gateway와 Node를 합친 결과, 공통 ID, 공통 스키마는 만들지 않았다.
- `collection.key_redactions`는 선택한 영역 안의 키로 범위를 좁혔다 (이전에는 파일 전체). 기존 테스트는 영향을 받지 않았다.
- 내장 Skill·Plugin, `tools/list`, MCP 서버 실행·접속은 이번 범위가 아니다.
