# 실제 MCP 서버 목록 조회·연결 (`live_discovery`, 내부 개발용 초안)

> 상태: 스캐너 내부 초안 `0.1.0-draft` · 작성일 2026-11-12
> 구현은 `asset_scanner/live_discovery.py`, 로컬 시험 서버는 `asset_scanner/dev_lists_server.py`입니다. 팀 공통 스키마·공통 ID는 반영하지 않았습니다.
> **이 명령은 서버 프로세스를 실행하거나 네트워크에 접속합니다.** 검증한 대상은 **프로젝트에 포함된 로컬 시험 서버뿐**이며 팀 테스트베드 검증이 아닙니다.

## 1. 구현 범위

| 항목 | 내용 |
|---|---|
| 조회하는 것 | `tools/list`, `resources/list`, `resources/templates/list`, `prompts/list` (페이지 끝까지) |
| 조회하지 않는 것 | `tools/call`, `resources/read`, `prompts/get`, `resources/subscribe`, 자동완성 등. 코드의 허용 목록(`ALLOWED_LIST_METHODS`)이 **보내기 전에** 막고 테스트가 이를 검증함 |
| 대상 | **명시적으로 고른 서버 하나**. ① 내장 시험 서버의 stdio(`--demo-stdio`), ② 내장 시험 서버의 로컬 HTTP + 가짜 인증(`--demo-http`), ③ 설정에 선언된 서버를 키로 지정(`--config --server KEY`) |
| 연결 | 공식 MCP Python SDK(`mcp 2.3.0`) 클라이언트. 버전 협상은 SDK 기본 흐름(`auto`: `server/discover` 우선, 구형 서버는 `initialize`)이며 `--client-mode legacy`로 `initialize` 흐름을 고를 수 있음 |
| 해석 | 응답 해석·가림·상태 구분은 저장된 응답 읽기와 같은 코드를 재사용: Tool은 `tools_catalog`, 나머지는 `resources_prompts` |

```powershell
# 내장 시험 서버 (stdio / 로컬 HTTP + 가짜 Bearer 인증)
.\.venv\Scripts\python.exe -m asset_scanner.live_discovery --demo-stdio --output output\live.result.json
.\.venv\Scripts\python.exe -m asset_scanner.live_discovery --demo-http --demo-auth fake --output output\live-http.result.json

# 설정에 선언된 서버 하나를 지정 (실행·접속은 명시적으로 허용해야 함)
.\.venv\Scripts\python.exe -m asset_scanner.live_discovery --config C:\path\openclaw.json5 --server my-server --allow-launch --output output\live-config.result.json
.\.venv\Scripts\python.exe -m asset_scanner.live_discovery --config C:\path\openclaw.json5 --server web --allow-connect --bearer-env MY_TOKEN_VAR --output output\live-web.result.json
```

`--catalog-output FILE`을 주면 Tool 카탈로그 형식의 결과도 저장하며 기존 `linking`의 입력으로 쓸 수 있습니다. 종료 코드: 0 완전 · 1 부분 · 2 인자 오류 · 3 실패(읽은 목록 없음 또는 대상 거부) · 4 저장 실패.

## 2. 대상 선택과 안전 장치

- **설정의 서버를 자동으로 고르거나 모두 실행하지 않습니다.** `--server`로 등록키 하나를 지정해야 하고(없으면 인자 오류) 실행은 `--allow-launch`, HTTP 접속은 `--allow-connect`를 줘야 합니다. 허용 플래그가 없으면 프로세스를 만들거나 소켓에 접속하지 않고 `target_refused`로 끝납니다.
- 선언에 해석하지 않는 참조(`${VAR}`, SecretRef, `$include`)가 있으면 실행·접속에 쓸 수 없어 `unresolved_reference`로 거부합니다(환경변수·SecretRef를 해석하지 않으므로).
- HTTP는 **루프백(`127.0.0.1`·`::1`·`localhost`)만** 기본 허용합니다. 다른 호스트는 `--allow-host`로 정확히 그 호스트를 적어야 하며 그렇지 않으면 `host_not_allowed`입니다. `streamable-http`만 지원합니다(`sse` 거부). URL 안의 사용자정보와 OAuth(`auth: oauth`·`oauth` 블록)는 지원하지 않아 거부합니다.
- **인증 토큰**: 내장 HTTP 시험 서버는 실행 때 임의로 만든 가짜 Bearer 토큰을 환경변수와 요청 헤더로만 씁니다. 설정 서버는 `--bearer-env 환경변수이름`으로 토큰을 **실행 시점에 환경에서 읽으며**, 결과에는 환경변수 **이름**과 헤더 **이름**만 기록합니다. 토큰은 결과·로그·표준출력·카탈로그 파일 어디에도 남기지 않습니다(테스트가 검증).
- 선언과의 연결: 결과의 `source.declaration_link`가 지정한 키의 선언 위치(`declaration_path`)를 가집니다(`basis: operator_selected_declaration`, `name_matching_used: false`). 기존 `linking`과 이어 쓰려면 `--config-scan-ref 라벨`을 줘야 카탈로그에 `config_link`(등록키·등록 영역·라벨)가 들어가고, 없으면 같은 이름이어도 자동으로 합치지 않습니다.

## 3. 통신 지원 버전과 파서 지원 버전

| 구분 | 버전 | 근거 |
|---|---|---|
| **SDK가 통신(협상)할 수 있는 버전** | `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`, `2026-07-28` | 설치된 `mcp_types.version.SUPPORTED_PROTOCOL_VERSIONS` (핸드셰이크 4종 + 모던 `2026-07-28`) |
| **스캐너가 목록 응답을 읽을 수 있는 버전(파서)** | `2025-11-25`, `2026-07-28` | `tools_catalog.SUPPORTED_PROTOCOL_VERSIONS`, 4장 규격 근거 |

결과의 `protocol`에 `negotiated_protocol_version`, `negotiated_supported_by_sdk`, `negotiated_readable_by_parser`와 두 목록을 함께 기록합니다. SDK는 통신할 수 있어도 파서가 읽지 못하는 버전(`2025-06-18` 등)으로 협상되면 **목록을 요청하지 않고** 모든 목록을 `not_performed`(`protocol_version_not_readable_by_parser`), 전체 `failed`로 둡니다. 응답 모양으로 버전을 추측하지 않습니다.

## 4. 상태 구분

목록마다 `lists.<tools|resources|resource_templates|prompts>`에 따로 기록합니다(`resources_prompts`와 같은 규칙).

| 상태 | 실제 통신에서의 근거 |
|---|---|
| `complete` (`items_listed`/`empty_list`/`tools_listed`) | 마지막 페이지까지 받음. 빈 목록은 서버가 0개를 응답한 경우 |
| `partial` | 뒤 페이지 오류, 최대 페이지·항목 수 한도, 반복 커서, 시간 초과로 일부만 받음 |
| `failed` | 오류 응답, SDK 응답 검증 거부, 시간 초과, 연결 끊김. **0개가 아님** |
| `unsupported` | 첫 응답이 JSON-RPC `-32601`. 서버가 메서드를 지원하지 않는다고 응답한 근거(`evidence`) |
| `not_performed` | 요청을 보내지 않음. 사유: `capability_not_declared`(서버가 해당 능력을 선언하지 않음), `session_ended`(앞선 요청에서 연결이 끊김), `total_timeout`, `protocol_version_not_readable_by_parser`, 연결 실패(`connect_rejected` 등), `target_refused` |

- **능력 선언**: 서버가 `tools`/`resources`/`prompts` 능력을 선언하지 않은 목록은 요청하지 않습니다(`resources` 능력이 resources와 resource_templates를 함께 포괄). `--request-undeclared`를 주면 요청해 보고, 서버가 `-32601`로 답하면 `unsupported`로 기록합니다.
- 연결·협상 전에 끝난 경우(인증 거부, 서버 미기동, 대상 거부) 요청을 보내지 않은 목록은 `failed/no_response`가 아니라 `not_performed`입니다. 없는 응답을 만들어 상태를 바꾸지 않습니다.
- **인증 거부**: SDK는 HTTP 401을 일반 서버 오류(`-32603`)로 감싸 예외만으로는 구분할 수 없어, HTTP 응답 **상태 코드 숫자만**(`http.status_code_counts`) 기록해 401·403이면 `connect_rejected`로 분류합니다. 응답 본문·헤더는 보지 않습니다.
- 서버 전체 상태: 모든 목록이 `complete`/`unsupported`이면 `complete`, 모두 `failed`/`not_performed`이면 `failed`, 그 밖에는 `partial`. `not_performed`가 있으면 `partial`입니다.

## 5. 한도와 정리

| 제한 | 기본값 | 동작 |
|---|---|---|
| 전체 시간 `--timeout` | 60초 | 지나면 중단. 응답을 받지 못한 요청 중인 목록은 `failed/total_timeout`, 시작하지 않은 목록은 `not_performed/total_timeout` |
| 요청 시간 `--request-timeout` | 15초 | 요청 하나의 응답 대기. 초과 시 그 목록 `failed/request_timeout`, 나머지 목록은 계속 |
| 연결 대기 `--connect-timeout` | 20초 | 시험 HTTP 서버가 포트를 열 때까지 |
| 페이지 `--max-pages` | 50(목록당) | 도달하면 더 요청하지 않고 `partial` |
| 항목 `--max-items` | 5000(목록당, 1~5000) | 한도를 넘는 항목은 **보존하지 않고** 페이지별 건수만 `limit_exclusions`에 기록, `partial`. 정확히 한도만큼이면 `complete` |
| 반복 커서 | — | 이미 쓴 커서가 다시 오면 중단, `partial` |

제한값은 서버를 실행·접속하기 **전에** 검사합니다(NaN·Infinity·0·음수·범위 밖은 오류, 프로세스 미생성). 내장 HTTP 시험 서버는 자식 프로세스로 띄우고 끝나면 종료한 뒤 **포트가 닫혔는지 확인**하며, Windows의 가상환경 `python.exe`가 실제 서버를 자식으로 띄우는 런처일 수 있어 포트가 남으면 프로세스 트리를 강제 종료합니다(`source.child_process`에 `terminated`, `port_closed_after_cleanup`, `process_tree_killed` 기록). SDK가 응답을 받아 파싱하는 메모리는 제한하지 못합니다(보존만 제한).

## 6. 규격 근거

저장된 응답 읽기와 같은 규격 근거를 씁니다: Tool은 [field-mapping 6장·8장](field-mapping.md), Resource·ResourceTemplate·Prompt는 [field-mapping 10장](field-mapping.md#10-resourceresourcetemplateprompt-목록-수집-resources_prompts--내부-개발용-초안)(고정 커밋 `c4c367f9…`·`271ecc9a…`). 라이브 조회는 SDK가 협상한 버전의 스키마로 응답을 검증한 **result dict 그대로**를 저장된 응답과 같은 파서에 넘깁니다(SDK의 모델 변환·기본값 보충을 거치지 않음). 따라서 JSON 파싱을 SDK가 했으므로 전송 계층의 중복 키·NaN 토큰 원문은 확인하지 못합니다(`wire_level_raw_json`).

## 7. 검증 수준 구분

| 구분 | 내용 |
|---|---|
| **가상 입력 검증** | 저장된 응답 파서는 `tests/test_resources_prompts.py`(53개)와 기존 Tool 카탈로그 테스트로 가상 응답을 검증했습니다. 설정 서버 거부 사유 14종은 가상 설정으로 검증했습니다(`tests/test_live_discovery.py`). |
| **개발용 서버의 실제 통신 검증** | 프로젝트에 포함된 시험 서버(`dev_lists_server`)에 stdio와 `127.0.0.1` HTTP(가짜 Bearer 인증)로 실제 연결해 확인: 4개 목록 수집, 정상 빈 목록·미지원(-32601)·미수행(능력 미선언)·실패·부분 수집, 페이지·항목 한도, 요청·전체 시간 초과, 서버 종료 중 연결 끊김, 인증 누락/오류 거부, `2025-11-25`(legacy)·`2026-07-28` 협상, 같은 이름의 서로 다른 유형·서버를 합치지 않음, 가짜 비밀값 가림, 프로세스·포트 정리. **허용하지 않은 호출이 없었는지는 시험 서버가 받은 요청의 메서드 이름 기록으로 검증**했습니다(`tools/call`·`resources/read`·`prompts/get` 없음, 스캐너가 센 요청 수와 서버가 받은 목록 요청 수 일치). |
| **아직 확인하지 못한 환경** | 팀 테스트베드 서버(stdio·원격), 실제 OpenClaw가 등록한 서버, 원격 HTTPS·실제 인증서, OAuth 서버(지원하지 않음), SSE 전송(지원하지 않음), `2024-11-05`~`2025-06-18`로 협상되는 서버(SDK는 통신하지만 파서가 읽지 못해 요청하지 않음), 대용량 응답에서의 SDK 메모리 사용. 테스트베드 사양 정정본을 받기 전에는 정답 대조·수집률·누락 계산을 하지 않았고, 시험 서버 결과를 팀 테스트베드 검증으로 쓰지 않습니다. |

## 8. 시험 서버 (`dev_lists_server`)

`python -m asset_scanner.dev_lists_server [--scenario NAME] [--transport stdio|http --port N [--require-bearer]]`. 시나리오 12종(`full`, `empty-all`, `no-prompts`, `only-tools`, `resources-error`, `templates-mnf`, `fail-second`, `many`, `secrets`, `slow-resources`, `exit-resources`, `same-names`)은 파일 상단 설명에 있습니다. `tools/call`·`resources/read`·`prompts/get` 핸들러가 없고, 환경변수 `DEV_MCP_SERVER_LOG` 파일에 요청의 메서드 이름·커서 상태(없음/빈 문자열/있음)·HTTP 인증 결과(ok/missing/bad)만 남깁니다(응답 내용·커서 값·토큰은 기록하지 않음). 기존 `dev_mcp_server`(Tool 2개)와 그 정답 목록(`examples/dev-server-ground-truth.json`)은 바꾸지 않았습니다.

## 9. 검증 실행 기록 (2026-11-12)

로그는 `asset-scanner/output/review-resources-prompts/split/`(`live-*.log`, `.exit.txt`)에 있습니다(`output/`은 `.gitignore` 대상이라 수치를 옮겨 적습니다). 순차로 실행했고, 실행기가 시스템 여유 메모리 120MB 미만이면 해당 실행만 중단하도록 감시하면서 python 프로세스의 최대 메모리와 pytest 종료 코드를 기록했습니다.

| 실행 | 대상 | 결과 | pytest 종료 코드 | python 최대 메모리 | 시스템 최소 여유 |
|---|---|---|---|---|---|
| `live-a-stdio-basic` | stdio 기본·상태 구분 | 8 passed, 1 failed | 1 | 171MB | 359MB |
| `live-b-limits-timeouts` | 한도·시간 초과·정리·가림·버전 | 14 passed, 2 failed | 1 | 171MB | 423MB |
| `live-b2-limits-legacy` | 한도·legacy 재확인 | 3 passed | **0** | 168MB | 478MB |
| `live-c-http` | HTTP·가짜 인증 | 3 passed, 3 failed | 1 | 176MB | 541MB |
| `live-c2-http` / `live-c3-http` | HTTP 재확인 | 4 passed·2 failed / 6 passed | 1 / **0** | 176 / 174MB | 601 / 318MB |
| `live-d-config` / `live-d2-config` | 설정 대상 선택·거부·연결 | 18 passed·1 failed / 2 passed | 1 / **0** | 164 / 168MB | 418 / 441MB |
| `live-e-guards-cli` | 제한값·요청 허용 목록·CLI | 10 passed | **0** | 246MB | 407MB |
| **`live-final-all`** | **`tests/test_live_discovery.py` 전체** | **60 passed (90초)** | **0** | **255MB** | **275MB** |

- 최종 통과(`live-final-all`)는 모든 코드 수정 이후에 실행했고 소스·테스트의 마지막 수정 시각보다 로그가 나중임을 확인했습니다. 실행 뒤 남은 `dev_lists_server` 프로세스는 0개였습니다.
- 개발 중 발견해 고친 문제: ① SDK가 HTTP 401을 일반 서버 오류(`-32603`)로 감싸 인증 거부와 일반 연결 실패를 구분하지 못했습니다 → HTTP 응답 상태 코드 숫자만 기록하는 훅을 추가해 401·403이면 `connect_rejected`로 분류. ② 연결 전에 끝난 경우 요청하지 않은 목록이 `failed/no_response`로 나왔습니다 → `not_performed`(사유 기록)로 바로잡음. ③ 테스트 기대 오류 세 건(내부 참조 접두어, 핸드셰이크 통지 `notifications/initialized`, 두 한도가 동시에 걸릴 때의 보고 코드)과 `linking` 결과 구조 가정을 실제 구조에 맞췄습니다. 토큰 누출로 보였던 실패 하나는 조사 결과 누출이 아니라 테스트가 헤더 이름(`Authorization`)까지 금지한 오류였습니다(결과·카탈로그·서버 로그를 모두 검색해 토큰 0건 확인).
- Windows에서 가상환경 `python.exe`가 실제 서버의 런처일 수 있어 서버 요청 기록의 pid와 제가 띄운 자식의 pid가 달랐습니다. 이 환경에서는 런처 종료로 서버까지 종료됐지만 그 동작에 기대지 않도록 정리 후 포트 확인과 프로세스 트리 강제 종료 안전장치를 넣었습니다(`port_closed_after_cleanup: true`를 테스트가 확인).
- 이 기록은 `tests/test_live_discovery.py`의 파일 단위 기록이며 한 번의 전체 실행 기록이 아닙니다. 기존 `tests/test_live_tools.py`(개발용 서버 stdio, 34개)는 이번에 수정하지 않아 다시 실행하지 않았습니다.
