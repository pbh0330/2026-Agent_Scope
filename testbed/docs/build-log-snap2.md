# SNAP-2 (정상군 P0/P1/P2) 구축 기록

> 작업일: 2026.10.04 (일)
> 작업자: 박병하
> 결과: 두 VM에 `SNAP-2-P0`, `SNAP-2-P1`, `SNAP-2-P2` 생성. 구성 설명은 [../profiles/README.md](../profiles/README.md)
> 민감정보: IP·사용자명·토큰은 자리표시자(`<TB_GW_IP>`, `<TB_NODE_IP>`, `<TB_USER>`, `<DUMMY_TOKEN>`)로 표기

---

## 1. 공통 준비 (양쪽 VM)

```bash
sudo npm install -g @modelcontextprotocol/server-filesystem@2026.8.31 \
  @modelcontextprotocol/server-memory@2026.8.31 @modelcontextprotocol/server-everything@2026.8.31
```

## 2. P0 (SNAP-1에서 시작)

```bash
# tb-gw
mkdir -p ~/workspace
openclaw mcp set fs-workspace '{"command":"mcp-server-filesystem","args":["/home/<TB_USER>/workspace"],
  "toolFilter":{"include":["read_text_file","list_directory"]},"enabled":true}'
openclaw mcp probe --json        # tools 2, filteredTools 12
```

사양서 5.2절 예시의 `read_file`은 이 버전에서 구 이름이며 현재 이름은 `read_text_file`이다.

## 3. P1 (SNAP-2-P0에서 시작)

```bash
# tb-node
openclaw config set nodeHost.mcp.servers.kg-memory \
  '{"command":"mcp-server-memory","env":{"MEMORY_FILE_PATH":"/home/<TB_USER>/node-data/memory.jsonl"}}' --strict-json
openclaw config set nodeHost.mcp.servers.demo-everything \
  '{"command":"mcp-server-everything","args":["stdio"],"toolFilter":{"exclude":["get-env","gzip-file-as-resource"]}}' --strict-json
# 노드 스킬 2종: profiles/P1/tb-node-skills/* → ~/.openclaw/skills/ (디렉터리명 = SKILL.md의 name)
openclaw node restart            # 노드는 MCP·스킬 설정 변경을 감시하지 않으므로 재시작 필요
```

게이트웨이에서 `openclaw nodes describe --node tb-node --json`의 `nodePluginTools`(kg-memory 9, demo-everything 10)와 `openclaw skills list`(source `openclaw-node`)로 게시를 확인했다.

## 4. P2 (SNAP-2-P1에서 시작)

### 4.1 실습용 CA와 원격 서버 (tb-node)

```bash
# CA·서버 인증서 (키는 VM에만 보관, 저장소에 올리지 않음)
openssl req -x509 -newkey rsa:3072 -nodes -days 825 -sha256 -keyout ca.key -out ca.crt \
  -subj "/O=Agent Scope Testbed/CN=Agent Scope Testbed CA" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
openssl req -newkey rsa:2048 -nodes -keyout tb-node.key -out tb-node.csr -subj "/O=Agent Scope Testbed/CN=tb-node"
# ext.cnf: subjectAltName=DNS:tb-node,IP:<TB_NODE_IP> / extendedKeyUsage=serverAuth / basicConstraints=CA:FALSE
openssl x509 -req -in tb-node.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 397 -sha256 -extfile ext.cnf -out tb-node.crt

# 원격 서버: testbed/mcp-servers/inventory-remote → ~/inventory-remote, npm install
# ~/inventory-remote/.env (600): INVENTORY_MCP_TOKEN=<DUMMY_TOKEN>, TLS_CERT, TLS_KEY, PORT=8443
# systemd 사용자 서비스 inventory-remote-mcp.service (EnvironmentFile=~/inventory-remote/.env)
```

확인: 토큰 없이 요청 → 401, CA 없이 Node.js 클라이언트 → TLS 실패, CA 지정 + 토큰 → 정상(도구 2, 리소스 1, 프롬프트 1).

### 4.2 게이트웨이 (tb-gw)

```bash
# CA 신뢰: 시스템 저장소 + Node.js(시스템 저장소를 쓰지 않음)
sudo cp ca.crt /usr/local/share/ca-certificates/agentscope-testbed-ca.crt && sudo update-ca-certificates
# systemd drop-in: Environment=NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/agentscope-testbed-ca.crt
echo 'INVENTORY_MCP_TOKEN=<DUMMY_TOKEN>' >> ~/.openclaw/.env   # 600

openclaw mcp set inventory-remote '{"url":"https://tb-node:8443/mcp","transport":"streamable-http",
  "headers":{"Authorization":"Bearer ${INVENTORY_MCP_TOKEN}"},"sslVerify":true,"enabled":true}'

# 플러그인: 복사 설치(~/.openclaw/extensions/에 위치하도록 --link 미사용)
openclaw plugins install ./agentscope-asset-catalog --force

# 워크스페이스 스킬: profiles/P2/tb-gw-workspace-skills/* → ~/workspace/skills/
```

### 4.3 노드 자격증명 참조 (tb-node)

```bash
echo 'EVERYTHING_DEMO_KEY=<DUMMY_TOKEN>' >> ~/.openclaw/.env   # 600
openclaw config set nodeHost.mcp.servers.demo-everything '{"command":"mcp-server-everything","args":["stdio"],
  "env":{"EVERYTHING_DEMO_KEY":"${EVERYTHING_DEMO_KEY}"},"toolFilter":{"exclude":["get-env","gzip-file-as-resource"]}}' --strict-json
openclaw node restart
```

## 5. 정답 목록 생성

```bash
# 광고 계층: 각 서버에 직접 붙어 수집 (OpenClaw 필터 적용 전 원본)
node testbed/tools/mcp-advertised.mjs -- mcp-server-filesystem /home/<TB_USER>/workspace > fs-workspace.advertised.json
NODE_EXTRA_CA_CERTS=... node testbed/tools/mcp-advertised.mjs --url https://tb-node:8443/mcp \
  --header "Authorization: Bearer $INVENTORY_MCP_TOKEN" > inventory-remote.advertised.json
# 투영 결과·식별 정보: openclaw mcp probe --json, openclaw nodes describe --json, openclaw devices list --json,
#   openclaw gateway call gateway.identity.get --json, openclaw node identity --json
python testbed/tools/build_ground_truth.py     # → testbed/ground-truth/P0.json, P1.json, P2.json
```

원본은 `testbed/ground-truth/raw/<P>/`에 있다.

## 6. 실측으로 확인한 사항

| 항목 | 내용 |
|---|---|
| MCP 프로토콜 버전 | 클라이언트가 `2026-07-28`을 요청해도 모든 서버가 `2025-11-25`로 협상. 최신 SDK 1.32.0과 OpenClaw 내장 SDK 1.30.0의 최신 지원 버전이 `2025-11-25` |
| 플러그인 등록 서버 | manifest `mcpServers`로 등록된 서버는 `openclaw mcp list`·`probe`에 나오지 않음. 설치 시 `install.acceptedSurface.mcpServers`로 명시 승인됨 |
| 도구 이름 투영 | 게이트웨이 `<server>__<tool>`, 노드 `<server>_<tool>` |
| 비게시 도구 | `taskSupport: "required"` 도구는 노드 호스트가 게시하지 않음(`demo-everything`의 `simulate-research-query`) |
| 자격증명 표시 | `openclaw mcp show`는 `${ENV}` 참조를 실제 값으로 풀어 출력, `openclaw config get`은 `env` 값을 가림 |
| 노드 설정 반영 | 노드 MCP·스킬 변경은 `openclaw node restart` 후 반영(감시 안 함). 게이트웨이 `mcp.servers` 변경은 즉시 반영 |
| 내장 감사 (P2) | critical 1, warn 3, info 1. 플러그인 추가로 `plugins.extensions_no_allowlist`, `plugins.tools_reachable_permissive_policy` 경고 추가 |
