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
- HTTP는 **루프백(`127.0.0.1`·`::1`·`localhost`)만** 기본 허용합니다. 다른 호스트는 `--allow-host`로 정확히 그 호스트를 적어야 하며(그렇지 않으면 `host_not_allowed`) **https만** 허용합니다(10장). `streamable-http`만 지원합니다(`sse` 거부, 후속 작업). URL 안의 사용자정보와 OAuth(`auth: oauth`·`oauth` 블록)는 지원하지 않아 거부합니다(후속 작업).
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
| **아직 확인하지 못한 환경** | 팀 테스트베드 서버(stdio·원격), 실제 OpenClaw가 등록한 서버, **실제 원격 서버의 HTTPS**(공인 CA 인증서·실제 도메인·프록시 환경, 10장), OAuth 서버(지원하지 않음), SSE 전송(지원하지 않음), `2024-11-05`~`2025-06-18`로 협상되는 서버(SDK는 통신하지만 파서가 읽지 못해 요청하지 않음), 대용량 응답에서의 SDK 메모리 사용. 테스트베드 사양 정정본을 받기 전에는 정답 대조·수집률·누락 계산을 하지 않았고, 시험 서버 결과를 팀 테스트베드 검증으로 쓰지 않습니다. |

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

## 10. 원격 HTTPS (Streamable HTTP) 연결 (2026-11-13 추가)

범위: **Streamable HTTP의 HTTPS 연결과 Bearer·인증 헤더 전달.** OAuth 로그인과 SSE는 지원하지 않으며 후속 작업으로 남깁니다(`scope.support_status`, 거부 시 `target_refused.followup`: `oauth_login`/`sse_transport`).

| 항목 | 내용 |
|---|---|
| 대상 선택 | 기존과 같음: `--config --server KEY --allow-connect`로 키 하나를 명시. 루프백이 아닌 호스트는 `--allow-host`로 정확히 그 호스트를 적어야 함(`host_not_allowed`). **루프백이 아닌 호스트는 https만**(평문 http는 `insecure_remote_http`로 거부: 인증정보가 평문으로 가지 않도록) |
| TLS 검증 | **항상 켜짐.** 인증서 체인과 호스트 이름(IP 포함) 검증, 최소 TLS 1.2. 끄는 옵션·인자가 없고 코드가 기본값 변경을 감지하면 접속하지 않음(`build_ssl_context`). 테스트도 검증을 끄지 않음 |
| 사설 CA | `--ca-bundle 파일.pem`은 시스템 신뢰 저장소에 CA를 **추가**로 신뢰할 뿐 검증은 그대로(`tls.trust: system_default+custom_ca_bundle`). 없는 파일·인증서가 아닌 파일·http 대상은 접속 전에 거부(`ca_bundle_not_found`/`ca_bundle_invalid`/`ca_bundle_requires_https`). CA 파일 경로는 결과에 기록하지 않음 |
| 인증값 | `--bearer-env 환경변수이름`(`Authorization: Bearer`)과 `--auth-header-env 헤더이름=환경변수이름`(여러 번 가능)으로 **실행 중에만 환경에서 읽음.** 결과·카탈로그·로그에는 헤더 **이름**과 환경변수 **이름**만 기록하고 값·해시는 남기지 않음. `Host`·`Content-Length`·`Transfer-Encoding`·`Mcp-Session-Id` 등 프로토콜 헤더, 중복 헤더, 비어 있는 환경변수는 접속 전에 거부. 환경의 토큰이 설정에 적힌 같은 이름 헤더를 대체(헤더가 둘로 나가지 않음) |
| 리다이렉트 | 따라가지 않음(`follow_redirects=False`, SDK도 같은 출처의 안전한 리다이렉트만 따름). 다른 호스트로의 리다이렉트는 `redirect_not_followed`로 끝나며 **리다이렉트 대상 서버는 어떤 요청도 받지 않음**(테스트로 확인). 추가로 요청 이벤트 훅이 엔드포인트와 출처(스킴·호스트·포트)가 다른 요청을 헤더를 보내기 전에 막음(`cross_origin_request_blocked`) |
| 환경변수 | 프록시·인증서 관련 환경변수(`HTTPS_PROXY`, `ALL_PROXY`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` 등)를 **읽지 않음**(`trust_env=False`, `tls.env_proxy_and_cert_variables_read: false`). 읽었다면 실패했을 값을 넣어 두고 조회가 성공함을 테스트로 확인 |
| 요청·한도·정리 | 기존 요청 허용 목록(목록 4종만), 페이지·항목·요청·전체 시간 제한, 시험 서버 정리 동작은 그대로 |

연결 실패는 원인별로 구분합니다(`connect_failure`와 `lists.*.outcome`, 요청을 보내지 못한 목록은 `not_performed`):

| `outcome` | 의미 | 근거 |
|---|---|---|
| `tls_certificate_untrusted` | 신뢰하지 않는 CA·자체 서명·발급자 불명 | OpenSSL 검증 코드 2·18·19·20·21 |
| `tls_hostname_mismatch` | 인증서가 접속한 호스트 이름·IP와 맞지 않음 | 코드 62·64 |
| `tls_certificate_expired` / `tls_certificate_not_yet_valid` | 유효 기간 밖 | 코드 10 / 9 |
| `tls_certificate_invalid` · `tls_error` | 그 밖의 인증서 검증 오류 · TLS 핸드셰이크 오류(예: TLS가 아닌 서버) | 예외 종류 |
| `connect_refused` · `dns_failure` · `network_connect_timeout` · `network_error` | 연결 거부 · 이름 해석 실패 · 연결 시간 초과 · 그 밖의 네트워크 오류 | 예외 종류 |
| `connect_rejected` | TLS는 성공했고 서버가 HTTP 401·403으로 인증 거부 | 상태 코드 숫자 |
| `redirect_not_followed` · `cross_origin_request_blocked` | 3xx 응답을 따르지 않음 · 다른 출처 요청 차단 | 상태 코드·훅 |

SDK는 연결 예외를 일반 서버 오류로 감싸 원인을 잃으므로, 전송 계층 래퍼가 TLS·연결 예외를 **범주·검증 코드·예외 종류 이름만** 기록합니다(메시지·인증서 내용·호스트 이름 원문은 저장하지 않음). 결과의 `tls` 블록에 검증 설정, 신뢰 저장소 구성, 오류 범주, 차단한 교차 출처 요청 수, 본 리다이렉트 수, 따라간 리다이렉트 수(항상 0)가 있습니다.

### 검증 수준 구분 (원격 HTTPS)

| 구분 | 내용 |
|---|---|
| **개발용 서버의 실제 TLS 통신 검증** | 테스트가 만든 임시 CA와 `127.0.0.1`의 로컬 HTTPS 시험 서버(`dev_lists_server --tls-cert/--tls-key`, 필요 시 `--require-bearer`·`--require-api-key-header`·`--redirect-to`)로 실제 핸드셰이크: ① 신뢰하는 사설 CA + 호스트 일치 + Bearer 인증으로 4개 목록 수집, 협상 버전 기록 ② 신뢰 목록에 CA를 더하지 않은 경우 `tls_certificate_untrusted` ③ 다른 CA가 서명한 인증서 ④ 호스트 이름 불일치(`localhost` 이름·`127.0.0.1` IP 두 경우) ⑤ 만료 인증서 ⑥ TLS 없는 서버에 https 접속 ⑦ 연결 거부 ⑧ 인증 성공·거부(토큰 없음·틀림, 사용자 정의 헤더) ⑨ 다른 호스트로의 307 리다이렉트에서 토큰이 대상 서버에 도달하지 않음 ⑩ 프록시·인증서 환경변수 무시. TLS 실패는 모두 핸드셰이크 단계에서 끝나 서버에 **HTTP 요청도 인증 헤더도 도달하지 않았음**을 서버 요청 기록으로 확인했고, 성공 경로에서는 서버가 받은 MCP 요청이 목록 요청뿐이고 `Host` 값이 접속한 이름임을 확인했습니다. 결과·카탈로그·서버 기록·표준출력에 토큰이 없음을 확인했습니다. |
| **가상 입력 검증** | 대상 선택 규칙(비루프백 http 거부, 정확한 `--allow-host`, 인증 헤더 옵션 형식·금지 이름·중복·미설정 환경변수, CA 번들 유효성, OAuth·SSE 거부)과 출처 차단 훅(5가지 다른 출처 차단·대소문자 차이 허용), DNS 실패 분류는 외부로 DNS 조회가 나가지 않도록 합성 예외로만 확인했습니다(`network_connect_timeout` 분류는 코드만 있고 테스트하지 않았습니다). |
| **아직 확인하지 못한 환경** | **실제 원격 서버**(공인 CA 인증서, 실제 도메인, 중간 CA 체인, OCSP·CRL), 팀 테스트베드, 사설망 프록시·TLS 가로채기 환경, 클라이언트 인증서(mTLS), 실제 서버가 보내는 리다이렉트 형태(307 외 301·302 등은 코드 분류만 있고 실통신 검증 없음), SDK가 사용하는 TLS 라이브러리의 인증서 폐기 처리, OAuth·SSE(지원하지 않음). 시스템 신뢰 저장소로만 검증하는 경로(`--ca-bundle` 없음)는 "신뢰하지 않음" 방향만 확인했고 공인 CA로 서명된 서버에 대한 성공 경로는 검증하지 못했습니다. |

## 11. 원격 HTTPS 검증 실행 기록 (2026-11-13)

로그는 `asset-scanner/output/review-resources-prompts/split/https-*.log`(`.exit.txt`)입니다. `output/`은 Git에서 제외되어 수치를 옮겨 적습니다. 이 PC는 RAM 8GB이고 다른 프로세스(주로 Claude 자체)가 메모리를 크게 써서 **실행 중 시스템 여유 메모리가 10~30MB까지 반복해서 떨어졌습니다.** 실행기는 120MB 미만이면 그 실행만 중단하도록 감시했고, 중단된 실행은 **기록으로 인정하지 않고** 메모리가 회복된 뒤 같은 대상을 다시 실행했습니다(python 프로세스는 최대 277MB).

| 실행 | 대상 | 결과 | pytest 종료 코드 |
|---|---|---|---|
| `https-a-happy` | 정상·인증 묶음 | 감시 중단(ABORTED, 여유 13MB) — 중단 전 3개 통과 표시, **기록 미인정** | 없음 |
| `https-b1`~`b4`, `b8`~`b9` | 정상 경로, 사용자 정의 헤더, 인증 거부 2종, 비신뢰 CA, TLS 없는 서버, 연결 거부 | 각 통과 | 모두 **0** |
| `https-b5`~`b7`(재시도 포함 중단) → `https-c5`~`c7` | 다른 CA, 호스트·IP 불일치, 만료 | b: ABORTED(여유 11~27MB) → c: 각 통과 | c: 모두 **0** |
| `https-d8`~`d11` | 분류, 검증 불가 옵션, 환경변수 무시, 리다이렉트 | 각 통과 | **0** |
| `https-d12` | 출처 차단 훅 | 1 failed: 테스트 입력 오류(`:8443.evil` 포트는 클라이언트가 요청을 만들기 전에 거부) → 입력 제거 | 1 |
| `https-e13`~`e16`, `https-g17`~`g18`, `https-g19b` | 출처 훅(수정 후), 대상 규칙, CA 번들, 헤더 옵션, 중복 헤더, OAuth·SSE, CLI | 각 통과(e17~e19·f17~f19·g19는 ABORTED 후 재실행) | 재실행 모두 **0** |
| **`https-final-all`** | **`tests/test_live_https.py` 전체** | **32 passed (106초)**, python 최대 277MB | **0** |
| `https-regression-live` | 기존 `tests/test_live_discovery.py` 전체(회귀) | 59 passed, 1 failed | 1 |
| `https-regression-timeout-fixed` | 실패한 기존 테스트 1개를 수정한 뒤 | 1 passed | **0** |

- **기존 테스트 1건의 실패는 이번 변경의 회귀가 아닙니다.** `test_total_timeout_marks_unfinished_lists_not_performed`는 총 제한 시간 3초에 의존했는데, 현재 느려진 PC(같은 60개가 90초 → 167초)에서 서버 시작+첫 목록이 3초를 넘어 요청 전에 시간이 끝나 `not_performed`가 됐습니다. **변경 전 `HEAD`(`d232cc8`)를 별도 폴더로 내보내 같은 테스트를 실행해도 동일하게 실패**함을 확인했습니다(2회). 테스트의 의도는 유지하고 총 제한을 12초로 늘려 안정화했고(요청 제한 60초) 이후 통과했습니다. 이 수정 후 `test_live_discovery.py` **파일 전체를 한 번에 다시 돌린 기록은 없습니다**(수정 전 실행에서 나머지 59개 통과, 수정한 1개는 단독 통과).
- 실행 뒤 남은 `dev_lists_server` 프로세스는 0개였고, 시험 서버를 띄운 테스트는 종료 시 프로세스 트리를 정리했습니다(`child_process.port_closed_after_cleanup` 확인은 이전 단계의 테스트가 계속 담당).
- 이 기록은 파일(또는 함수) 단위 실행이며 한 번의 전체 실행 기록이 아닙니다.
