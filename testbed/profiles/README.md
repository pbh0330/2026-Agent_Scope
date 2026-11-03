# 정상군 프로파일 (P0 / P1 / P2)

> 구성일: 2026.10.04
> 스냅샷: `SNAP-2-P0`, `SNAP-2-P1`, `SNAP-2-P2` (두 VM 동시, 전원 끈 상태)
> 정답 목록: [../ground-truth/P0.json](../ground-truth/P0.json), [P1.json](../ground-truth/P1.json), [P2.json](../ground-truth/P2.json)

프로파일은 누적 구성이다(P1 = P0 + α, P2 = P1 + β). 각 폴더의 `tb-gw.openclaw.json`, `tb-node.openclaw.json`은 해당 스냅샷 시점 설정 파일을 자리표시자 처리한 사본이다.
`SNAP-2-P2`가 사양서의 `SNAP-2`(위협 시나리오 주입 전 기준 상태)에 해당한다.

## 1. 구성 요약

| 프로파일 | tb-gw | tb-node | 자산 수 (정답 목록) |
|---|---|---|---|
| P0 | `mcp.servers.fs-workspace` (stdio) | 페어링만 | gateway 1, node 1, mcp_server 1, tool 14 |
| P1 | P0 | `nodeHost.mcp.servers.kg-memory`, `demo-everything` (stdio) + 노드 스킬 2종 | + mcp_server 2, tool 22, resource 10, prompt 4, skill 2 |
| P2 | P1 + `mcp.servers.inventory-remote` (원격 HTTPS) + 플러그인 `agentscope-asset-catalog`(→ `asset-catalog` 서버 등록) + 워크스페이스 스킬 1종 | P1 + 원격 서버 구동 + 자격증명 참조 | gateway 1, node 1, plugin 1, mcp_server 5, tool 40, resource 11, prompt 5, skill 3 |

사양서 대비: P0에도 노드가 페어링되어 있다. 사양서 4.2절이 페어링을 SNAP-1에 포함하므로 그 순서를 따랐다(4.3절 P1의 "노드 페어링"은 노드 측 자산 추가로 해석).

## 2. MCP 서버

| 서버 | 선언 위치 | 전송 | 패키지 / 코드 | 광고 (도구/리소스/템플릿/프롬프트) | 에이전트 노출 |
|---|---|---|---|---|---|
| `fs-workspace` | tb-gw `mcp.servers` | stdio | `@modelcontextprotocol/server-filesystem@2026.8.31`, 범위 `/home/<TB_USER>/workspace` | 14 / 0 / 0 / 0 | 2 (`toolFilter.include`: `read_text_file`, `list_directory`) |
| `kg-memory` | tb-node `nodeHost.mcp.servers` | stdio | `@modelcontextprotocol/server-memory@2026.8.31`, `MEMORY_FILE_PATH=~/node-data/memory.jsonl` | 9 / 1 / 0 / 0 | 9 |
| `demo-everything` | tb-node `nodeHost.mcp.servers` | stdio | `@modelcontextprotocol/server-everything@2026.8.31` | 13 / 7 / 2 / 4 | 10 (`exclude`: `get-env`, `gzip-file-as-resource` / `simulate-research-query`는 `taskSupport: required`라 OpenClaw가 게시하지 않음) |
| `inventory-remote` | tb-gw `mcp.servers` (구동은 tb-node) | Streamable HTTP over HTTPS | [../mcp-servers/inventory-remote](../mcp-servers/inventory-remote) (SDK 1.32.0) | 2 / 1 / 0 / 1 | 2 (+ 리소스·프롬프트 보조 도구 4) |
| `asset-catalog` | 플러그인 manifest `mcpServers` | stdio | [../plugins/agentscope-asset-catalog](../plugins/agentscope-asset-catalog) | 2 / 0 / 0 / 0 | 미확인 (`openclaw mcp probe` 대상 아님) |

MCP 공식 참조 서버 3종은 `npm install -g`로 버전을 고정 설치하고 바이너리 이름으로 실행한다(`npx -y` 미사용).

## 3. 위협 시나리오 정상 기준 대응

| 시나리오 | 정상 기준 | 구성 |
|---|---|---|
| S1 | 승인된 Skill·Plugin만 허용된 서버를 등록 | 아래 승인 서버 목록의 서버만 선언. 플러그인은 승인 목록의 `asset-catalog`만 등록 |
| S2 | 조회용 Tool은 제한된 자원만 접근, 고위험 기능은 필터 | `fs-workspace`는 작업 디렉터리로 한정 + 읽기 도구 2종만 노출. `demo-everything`의 환경변수 노출(`get-env`)·외부 URL 조회(`gzip-file-as-resource`) 제외 |
| S3 | Tool이 서버별로 고유 | 5개 서버의 원래 도구 이름 40개가 모두 서로 다름(생성기에서 검사) |
| S4 | 서버별 최소 범위 자격증명 분리 | `inventory-remote`: `INVENTORY_MCP_TOKEN`(tb-gw `~/.openclaw/.env`), `demo-everything`: `EVERYTHING_DEMO_KEY`(tb-node `~/.openclaw/.env`). 설정에는 `${...}` 참조만 기록, 값은 더미 |
| S5 | 신뢰된 HTTPS, TLS 검증 활성 | `inventory-remote`는 실습용 CA가 서명한 인증서(SAN `tb-node`, `<TB_NODE_IP>`), `sslVerify: true`, 게이트웨이 서비스에 `NODE_EXTRA_CA_CERTS`로 CA 지정 |

### 승인 서버 목록 (S1 allowlist)

| 서버 | 등록 주체 | 실행 위치 | 승인 근거 |
|---|---|---|---|
| `fs-workspace` | tb-gw 설정 | tb-gw | MCP 공식 참조 서버, 버전 고정 |
| `kg-memory` | tb-node 설정 | tb-node | MCP 공식 참조 서버, 버전 고정 |
| `demo-everything` | tb-node 설정 | tb-node | MCP 공식 참조 서버, 버전 고정, 고위험 도구 2종 제외 |
| `inventory-remote` | tb-gw 설정 | tb-node (`https://tb-node:8443/mcp`) | 테스트베드 자체 제작, 실습망 내부 |
| `asset-catalog` | 플러그인 `agentscope-asset-catalog` | tb-gw | 테스트베드 자체 제작, 로컬 경로 설치 |

## 4. 스킬·플러그인

| 자산 | 위치 | 연관 |
|---|---|---|
| 스킬 `node-disk-report` | tb-node `~/.openclaw/skills/` | 없음(셸 명령) |
| 스킬 `node-notes-summary` | tb-node `~/.openclaw/skills/` | 없음(파일 읽기) |
| 스킬 `inventory-owner-report` | tb-gw `~/workspace/skills/` | 본문이 `inventory-remote` 도구 호출을 지시 → `ASSOCIATED_WITH` (confidence medium) |
| 플러그인 `agentscope-asset-catalog` | tb-gw `~/.openclaw/extensions/` (`openclaw plugins install ./agentscope-asset-catalog`) | manifest `mcpServers`로 `asset-catalog` 등록 → `ASSOCIATED_WITH` |

## 5. 스캐너 담당 참고 (실측)

- **플러그인이 등록한 MCP 서버는 `openclaw mcp list`·`mcp probe`에 나오지 않는다.** `mcp.servers`만 읽으면 `asset-catalog`가 누락된다. 근거는 `openclaw plugins inspect <id> --runtime --json`의 `mcpServers`, 또는 `~/.openclaw/extensions/<id>/openclaw.plugin.json`.
- 에이전트에 투영되는 도구 이름: 게이트웨이 측은 `<server>__<tool>`(밑줄 2개), 노드 측은 `<server>_<tool>`(밑줄 1개). S3 판단은 접두어를 뗀 원래 MCP 도구 이름으로 해야 한다.
- `openclaw mcp show <name>`은 `${ENV}` 참조를 **실제 값으로 풀어서** 출력한다(설정 파일에는 참조로 저장). 반면 `openclaw config get`은 `env` 값을 `__OPENCLAW_REDACTED__`로 가린다. 자격증명 참조 수집은 설정 파일을 직접 읽어야 한다.
- 노드 측 도구·스킬 게시 결과는 `openclaw nodes describe --node <id> --json`의 `nodePluginTools`, `openclaw skills list`(source `openclaw-node`)로 확인할 수 있다.
- 실제 협상된 MCP 프로토콜 버전은 모든 서버에서 `2025-11-25`다. 최신 SDK(1.32.0)와 OpenClaw 내장 SDK(1.30.0) 모두 `2026-07-28`을 지원하지 않는다.

## 6. 내장 보안 감사 (SNAP-2-P2)

critical 1, warn 3, info 1. SNAP-1 대비 `plugins.extensions_no_allowlist`(플러그인 있음, `plugins.allow` 미설정), `plugins.tools_reachable_permissive_policy`가 추가됨. 원본: [../ground-truth/raw/P2/tb-gw.security-audit.json](../ground-truth/raw/P2/tb-gw.security-audit.json).
`plugins.allow`는 내장 플러그인 활성 상태에도 영향을 줄 수 있어 정상군에서는 설정하지 않았다(보완 여부는 팀 결정).
