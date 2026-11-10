# 위협 구성 S1-T5 — 선언 위치 이상 (선택, 설정 사본)

> 기준: `SNAP-2-P2`. 기대 경고: PR #7 `expected-results.md` 3절 (v2.1, S1-C4)
> 정답 목록: [../../ground-truth/S1-T5.json](../../ground-truth/S1-T5.json)
> 상태: **설정 사본만으로 정적 검증**한다(VM 스냅샷 없음). S1 프로파일(`SNAP-3-S1`)의 Case 2와 겹치지 않게 별도 사본으로 둔다.

## 1. 위험 구성 (P2 대비 변경)

승인 목록의 `inventory-remote`는 이름·Endpoint가 그대로지만 **선언 위치**가 바뀐다.

| 변경 | 내용 |
|---|---|
| tb-gw `mcp.servers.inventory-remote` | **제거** |
| tb-node `nodeHost.mcp.servers.inventory-remote` | **추가** (url `https://tb-node:8443/mcp`, `sslVerify: true`, 같은 Bearer 헤더 — 내용 동일) |

결과: 자산 키가 `tb-gw/mcp_server/inventory-remote` → `tb-node/mcp_server/inventory-remote`로 이동(정답 목록의 `removed_assets`/`added_assets`).

| 테스트 | 조건 ID | target | severity |
|---|---|---|---|
| S1-T5 | S1-C4 (선언 위치 이상) | `tb-node/mcp_server/inventory-remote` | medium |

- **S1-C1(미승인 서버)로 내면 오답이다.** 이름·Endpoint는 승인 목록과 같고, 선언 위치만 다르다.
- 승인 목록 `approved-servers.json`의 `inventory-remote`는 `declared_at_vm: tb-gw`, `registered_by: tb-gw:config`다. 이 사본은 그 선언 위치를 tb-node로 옮겨 "승인된 서버가 다른 위치에서 선언됨"을 만든다.

## 2. 확인 필요 (VM 반영 시)

`nodeHost.mcp.servers`가 **원격 url 서버**를 받는지는 미확인이다(#7). 받지 않으면 VM에는 반영하지 않고 이 설정 사본으로 정적 검증만 한다. 받으면 다음으로 반영한다.

```bash
# tb-gw: inventory-remote 제거
openclaw mcp remove inventory-remote
# tb-node: nodeHost에 동일 내용으로 추가 (단, 원격 url 수용 여부 확인 후)
openclaw config set nodeHost.mcp.servers.inventory-remote \
  '{"url":"https://tb-node:8443/mcp","transport":"streamable-http","headers":{"Authorization":"Bearer ${INVENTORY_MCP_TOKEN}"},"sslVerify":true,"enabled":true}' --strict-json
openclaw node restart
```

## 3. 정답 목록 재생성

```bash
python testbed/tools/build_ground_truth.py S1-T5
```

생성기는 `inventory-remote`의 광고본으로 `raw/P2`를 대신 쓰고(같은 서버·내용), 선언 위치 이동만 `removed_assets`/`added_assets`와 관계 이동(`removed_relations`/`added_relations`)으로 기록한다. 워크스페이스 스킬 `inventory-owner-report`의 연관 대상도 tb-node의 `inventory-remote`로 따라 옮겨진다.
