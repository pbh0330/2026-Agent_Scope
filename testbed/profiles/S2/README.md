# 위협 구성 S2 — 악성 또는 과도한 권한의 도구 광고

> 기준: `SNAP-2-P2` → 결과 스냅샷 `SNAP-3-S2` (두 VM 동시, 전원 끈 상태)
> 시나리오 명세: PR #7 `scenario-s2.md`, 기대 경고: PR #7 `expected-results.md` 4절 (v2.1)
> 판정 기준 정책: [../../ground-truth/approved-servers.json](../../ground-truth/approved-servers.json), 도구 정책 PR #7 `policies/expected-tool-policy.json`
> 정답 목록: [../../ground-truth/S2.json](../../ground-truth/S2.json)
> 상태: 설정 사본은 **구축 전 예상본**. VM 구축 후 실제 파일·노출 수집본으로 교체한다.

## 1. 위험 구성 (P2 대비 변경)

서로 다른 서버의 변경 2건을 한 스냅샷에 함께 넣는다(판정이 섞이지 않는다).

| 테스트 | VM | 위치 | 변경 | 경고 대상 |
|---|---|---|---|---|
| S2-T1 | tb-gw | `mcp.servers.fs-workspace.args` | `["/home/<TB_USER>/workspace"]` → `["/home/<TB_USER>"]`. **toolFilter는 그대로 둔다** | `tb-gw/mcp_server/fs-workspace` (S2-C2, medium) |
| S2-T2 | tb-node | `nodeHost.mcp.servers.demo-everything.toolFilter` | 항목 삭제(`exclude: ["get-env", "gzip-file-as-resource"]` 제거) | `tb-node/mcp_server/demo-everything` (S2-C1, high) |

- S2-T1은 결정 사항 4(읽기 전용 Tool만 노출돼도 접근 범위가 넓어지면 탐지, medium)를 검증한다. toolFilter까지 지우면 high가 돼 이 케이스를 검증할 수 없다.
- S2-T2는 정책이 막던 `get-env`(서버 환경변수 반환)·`gzip-file-as-resource`(`readOnlyHint=false`)가 에이전트에 노출되게 한다.
- `fs-workspace`의 stdio 인자 변경은 승인 목록 `match_keys`(endpoint.args)와 어긋나므로 S1-C2 동반 경고가 날 수 있다. 정답에 `required: false`로 기록했다.
- S2-C3(명령·네트워크 입력)·S2-C4(인증정보 입력)는 테스트베드 서버에 해당 도구가 없어 이번 프로파일에서 검증하지 않는다.

## 2. 구축 절차

`SNAP-2-P2`로 되돌린 뒤 진행한다.

```bash
# tb-gw (S2-T1) — 범위만 확대, toolFilter 유지
openclaw mcp set fs-workspace \
  '{"command":"mcp-server-filesystem","args":["/home/<TB_USER>"],"toolFilter":{"include":["read_text_file","list_directory"]},"enabled":true}'

# tb-node (S2-T2) — toolFilter 제거
openclaw config set nodeHost.mcp.servers.demo-everything \
  '{"command":"mcp-server-everything","args":["stdio"],"env":{"EVERYTHING_DEMO_KEY":"${EVERYTHING_DEMO_KEY}"}}' --strict-json
openclaw node restart
```

### 확인

| 확인 | 기대 결과 |
|---|---|
| `openclaw mcp probe --json` | `fs-workspace`는 여전히 `read_text_file`·`list_directory` 2종만 노출(범위만 넓어짐) |
| `openclaw nodes describe --node tb-node --json` | `demo-everything`에 `get-env`·`gzip-file-as-resource`가 노출됨 |

확인 후 두 VM 전원을 끄고 `SNAP-3-S2` 스냅샷을 찍는다.

## 3. 정답 목록 재생성

```bash
python testbed/tools/build_ground_truth.py S2
```

설정 변경(범위·필터)은 선언 계층에서 바로 잡히므로 `changed_assets`에 반영된다.
다만 `get-env`·`gzip-file-as-resource`의 **에이전트 노출 여부**(`exposed_to_agent` false→true)는 VM 노출 수집(`raw/S2/`의 probe·nodes-describe) 전에는 미확인(`null`)이라 `changed_assets`에 포함되지 않는다. VM 수집 후 다시 생성하면 채워진다. 경고(S2-C1·S2-C2)는 설정만으로 확정되므로 그대로 둔다.
