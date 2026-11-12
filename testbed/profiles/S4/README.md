# 위협 구성 S4 — 과도한 자격증명 공유

> 기준: `SNAP-2-P2` → 결과 스냅샷 `SNAP-3-S4` (두 VM 동시, 전원 끈 상태)
> 시나리오 명세: PR #7 `scenario-s4.md`, 기대 경고: PR #7 `expected-results.md` 5절 (v2.1)
> 정답 목록: [../../ground-truth/S4.json](../../ground-truth/S4.json)
> 상태: **VM 구축 완료(2026.11.12, `SNAP-3-S4`)**. 설정 사본은 VM 실측본(자리표시자 처리). 실제 비밀값은 어디에도 적지 않는다(참조 이름·저장 위치만).

## 1. 위험 구성 (P2 대비 변경)

| 테스트 | VM | 위치 | 변경 | 판정 |
|---|---|---|---|---|
| S4-T1 | tb-gw | `mcp.servers.fs-workspace.env` | `{"FS_SYNC_TOKEN": "${INVENTORY_MCP_TOKEN}"}` 추가 | `fs-workspace` (S4-C1, medium) — `inventory-remote`와 같은 저장소(tb-gw `.env`)의 `INVENTORY_MCP_TOKEN` 공유 |
| S4-T2 | tb-node | `nodeHost.mcp.servers.demo-everything.env.EVERYTHING_DEMO_KEY` | `"${EVERYTHING_DEMO_KEY}"` → `"${INVENTORY_MCP_TOKEN}"` | `demo-everything` (S4-C2, **unknown**) — 참조 이름은 같아도 저장소가 tb-node `.env`로 달라 확정 불가 |
| S4-T3 | — | S1 프로파일 Case 2 재사용 | `inventory-remote` url 변경 + Bearer `${INVENTORY_MCP_TOKEN}` 헤더 유지 | S1.json의 S4-C3(`required: false`, high). S4 채점에선 `required: true`로 센다 |

- **S4-C2는 경고가 아니다.** `unknown`으로 평가돼야 하며, `detected`/`not_detected`로 나오면 FAIL이다([../../ground-truth/S4.json](../../ground-truth/S4.json)의 `expected_unknown`).
- S4-T2를 VM에 반영하려면 tb-node `~/.openclaw/.env`에 `INVENTORY_MCP_TOKEN`이라는 이름의 **가짜 값**을 넣어 서버가 뜨게 한다. tb-gw 값과 같게 넣지 않는다(같은지 다른지 탐지기가 알 수 없어야 하는 케이스).
- S4-T1은 env 추가라 S1 Endpoint 비교(`match_keys`)에 영향이 없다.

## 2. 구축 절차

```bash
# tb-gw (S4-T1)
openclaw mcp set fs-workspace \
  '{"command":"mcp-server-filesystem","args":["/home/<TB_USER>/workspace"],"env":{"FS_SYNC_TOKEN":"${INVENTORY_MCP_TOKEN}"},"toolFilter":{"include":["read_text_file","list_directory"]},"enabled":true}'

# tb-node (S4-T2): .env에 가짜 INVENTORY_MCP_TOKEN 추가 후 참조 변경
printf 'INVENTORY_MCP_TOKEN=dummy-not-same-as-gw\n' >> ~/.openclaw/.env
openclaw config set nodeHost.mcp.servers.demo-everything.env.EVERYTHING_DEMO_KEY '"${INVENTORY_MCP_TOKEN}"' --strict-json   # --strict-json은 JSON 문자열(따옴표 포함)만 받는다
openclaw node restart
```

확인 후 두 VM 전원을 끄고 `SNAP-3-S4` 스냅샷을 찍는다. S4-T3은 `SNAP-3-S1`을 그대로 쓴다.

## 3. 정답 목록 재생성

```bash
python testbed/tools/build_ground_truth.py S4
```

자격증명 참조는 설정의 `${ENV}`에서 도출한다(값 미기록). 저장소는 선언 VM의 `~/.openclaw/.env`로 잡아 S4-C1(같은 저장소)·S4-C2(다른 저장소)를 구분한다. 수집 원본에 토큰 값이 들어가지 않았는지 커밋 전에 확인한다.
