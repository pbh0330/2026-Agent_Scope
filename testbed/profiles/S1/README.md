# 위협 구성 S1 — 비인가 MCP Server 등록 및 노출

> 기준: `SNAP-2-P2` → 결과 스냅샷 `SNAP-3-S1` (두 VM 동시, 전원 끈 상태)
> 시나리오 명세: PR #7 `scenario-s1.md` (9.3절 위험 구성 Case 1~3)
> 승인 서버 목록: [../../ground-truth/approved-servers.json](../../ground-truth/approved-servers.json)
> 정답 목록: [../../ground-truth/S1.json](../../ground-truth/S1.json) (P2 대비 변경분 + `expected_alerts`)
> 상태: **VM 구축 완료(2026.11.12, `SNAP-3-S1`)**. 설정 사본은 VM 실제 파일을 자리표시자 처리한 실측본이며 구축 전 예상본과 내용이 같았다.

## 1. 위험 구성

P2의 승인 서버 5종은 그대로 두고(오탐 확인용), 아래 4건을 한 스냅샷에 함께 넣는다. 서버마다 경고 대상이 달라 서로 섞이지 않는다.

| Case | 명세 위험 조건 | 변경 | 경고 대상 |
|---|---|---|---|
| 1-gw | 신규 Server 선언 | tb-gw `mcp.servers.shadow-notes` 추가 (stdio, [../../mcp-servers/notes-stub](../../mcp-servers/notes-stub)) | `tb-gw/mcp_server/shadow-notes` |
| 1-node | 신규 Server 선언 | tb-node `nodeHost.mcp.servers.node-helper` 추가 (같은 코드, 이름만 다름) | `tb-node/mcp_server/node-helper` |
| 2 | Endpoint 불일치 | `inventory-remote` url `https://tb-node:8443/mcp` → `https://tb-node:9443/mcp` (tb-node에 같은 서버를 9443으로 하나 더 띄움) | `tb-gw/mcp_server/inventory-remote` |
| 3 | 출처 이상 | 승인 목록에 없는 플러그인 `agentscope-notes-sync` 설치 → manifest `mcpServers`로 `notes-sync` 등록 ([../../plugins/agentscope-notes-sync](../../plugins/agentscope-notes-sync)) | `tb-gw/mcp_server/notes-sync` (+ 플러그인, 선택) |

설계상 다른 시나리오에 영향을 주지 않게 한 점:

- 비인가 서버 3종의 도구는 읽기 전용 2종씩이고 가상 데이터만 다룬다(S2 무관). 도구 이름에 서버 이름 접두어가 붙어 기존 40종과 겹치지 않는다(S3 무관, 생성기에서 검사).
- Case 2의 9443 endpoint도 실습용 CA 인증서와 `sslVerify: true`를 그대로 쓴다(S5 무관).
- Case 2는 기존 토큰이 바뀐 endpoint로 전송되므로 **S4 동반 경고가 날 수 있다.** 정답 목록에 `required: false`로 기록했다(내도 정답, 안 내도 S1 채점에 영향 없음).
- 명세 위험 조건 중 "무결성 이상"(버전·파일 변경)은 이번 구성에 넣지 않았다.

## 2. 구축 절차

`SNAP-2-P2`로 두 VM을 되돌린 뒤 진행한다. 저장소 파일은 VM에 복사해 둔다.

### 2.1 tb-node

```bash
# 비인가 서버 코드
mkdir -p ~/mcp-servers/notes-stub && cp notes-stub/server.mjs ~/mcp-servers/notes-stub/

# Case 1-node
openclaw config set nodeHost.mcp.servers.node-helper \
  '{"command":"node","args":["/home/<TB_USER>/mcp-servers/notes-stub/server.mjs","--name","node-helper"]}' --strict-json
openclaw node restart

# Case 2: 같은 inventory-remote를 9443으로 하나 더 구동 (8443 승인 인스턴스는 그대로 둠)
# EnvironmentFile 값이 Environment=보다 우선하므로 env 파일을 따로 만든다
sed 's/^PORT=.*/PORT=9443/' ~/inventory-remote/.env > ~/inventory-remote/.env.9443 && chmod 600 ~/inventory-remote/.env.9443
sed 's#\.env$#.env.9443#' ~/.config/systemd/user/inventory-remote-mcp.service \
  > ~/.config/systemd/user/inventory-remote-mcp-9443.service
systemctl --user daemon-reload && systemctl --user enable --now inventory-remote-mcp-9443.service
ss -ltnp | grep -E '8443|9443'     # 두 포트 모두 LISTEN
```

### 2.2 tb-gw

```bash
mkdir -p ~/mcp-servers/notes-stub && cp notes-stub/server.mjs ~/mcp-servers/notes-stub/

# Case 1-gw
openclaw mcp set shadow-notes \
  '{"command":"node","args":["/home/<TB_USER>/mcp-servers/notes-stub/server.mjs","--name","shadow-notes"],"enabled":true}'

# Case 2 (url만 바꾸고 나머지는 P2와 같게)
openclaw mcp set inventory-remote '{"url":"https://tb-node:9443/mcp","transport":"streamable-http",
  "headers":{"Authorization":"Bearer ${INVENTORY_MCP_TOKEN}"},"sslVerify":true,"enabled":true}'

# Case 3 (복사 설치, mcpServers 표면 승인 확인)
openclaw plugins install ./agentscope-notes-sync --force
```

### 2.3 확인

| 확인 | 기대 결과 |
|---|---|
| `openclaw mcp list` | `shadow-notes` 보임, `notes-sync`는 **안 보임**(플러그인 등록 서버) |
| `openclaw mcp probe --json` | `shadow-notes` 도구 2, `inventory-remote` 9443으로 정상 연결(도구 2) |
| `openclaw plugins inspect agentscope-notes-sync --runtime --json` | `mcpServers`에 `notes-sync` |
| `openclaw nodes describe --node tb-node --json` | `nodePluginTools`에 `node-helper` 도구 2 추가 |
| `openclaw security audit --json` | P2 대비 변화 기록(참고용) |

확인 후 두 VM 전원을 끄고 `SNAP-3-S1` 스냅샷을 찍는다.

## 3. 정답 목록 재생성

`ground-truth/raw/S1/`에는 비인가 서버 3종의 광고 원본과 VM 수집본(probe·nodes-describe·plugin inspect·security audit·9443 광고본)이 있다(2026.11.12 수집). `shadow-notes`·`node-helper` 도구 4종의 노출 여부는 `true`로 확정됐다. `notes-sync`(플러그인 등록 서버)는 `openclaw mcp probe` 대상이 아니라 P2의 `asset-catalog`와 같이 `null`(미확인)로 남는다. 수집 명령은 아래와 같다.

> SSH로 비대화형 실행할 때는 `bash -lc`로 로그인 셸을 써야 한다. 실습 CA(`NODE_EXTRA_CA_CERTS`)가 `~/.profile`에만 있어, 그렇지 않으면 `inventory-remote` probe가 `UNABLE_TO_VERIFY_LEAF_SIGNATURE`로 실패한다(게이트웨이 서비스는 drop-in으로 CA를 따로 받는다).

```bash
openclaw mcp probe --json > tb-gw.mcp-probe.json                         # tb-gw
openclaw nodes describe --node tb-node --json > tb-node.nodes-describe.json  # tb-gw
openclaw plugins inspect agentscope-notes-sync --runtime --json > tb-gw.plugin-inspect.agentscope-notes-sync.json
openclaw security audit --json > tb-gw.security-audit.json
NODE_EXTRA_CA_CERTS=... node testbed/tools/mcp-advertised.mjs --url https://tb-node:9443/mcp \
  --header "Authorization: Bearer $INVENTORY_MCP_TOKEN" > inventory-remote.advertised.json
python testbed/tools/build_ground_truth.py S1
```

수집 원본에 토큰 값이 들어가지 않았는지 커밋 전에 확인한다(`openclaw mcp show`는 `${ENV}`를 실제 값으로 풀어 출력하므로 쓰지 않는다).
