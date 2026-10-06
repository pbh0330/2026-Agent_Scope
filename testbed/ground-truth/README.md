# 정답 목록 (Ground Truth) 형식

> 상태: P0/P1/P2 작성 완료(2026.10.04, `tools/build_ground_truth.py`로 생성). 공통 스키마(PR #1)의 자산 분류·ID 규칙 확정 시 생성기만 수정해 재생성

프로파일(P0/P1/P2)과 위협 구성(S1~S5)마다 **테스트베드에 실제로 구성한 자산과 관계**를 수작업으로 기록한다.
스캐너 출력과 비교하여 수집률(S1 선언 계층, S2 광고 계층)과 오탐을 산출하는 기준으로 쓴다.

## 파일 규칙

```text
testbed/ground-truth/
├── README.md
├── P0.json
├── P1.json
├── P2.json
└── S1.json ...        # 위협 구성은 기준 프로파일 대비 추가·변경 자산만 기록
```

## 필드

| 필드 | 필수 | 설명 |
|---|---|---|
| `profile` | O | `P0` / `P1` / `P2` / `S1`~`S5` |
| `snapshot` | O | 대응 스냅샷 이름 (예: `SNAP-2`) |
| `environment.openclaw_version` | O | `2026.9.6` |
| `environment.mcp_spec_version` | O | `2026-07-28` |
| `assets[].asset_key` | O | 복합 식별 키. 생성 규칙은 공통 스키마 합의 결과를 따름 |
| `assets[].asset_type` | O | `gateway` / `node` / `mcp_server` / `tool` / `resource` / `prompt` / `skill` / `plugin` |
| `assets[].declared_at` | O | 선언 위치 (VM + 파일 + 키 경로) |
| `assets[].layer` | O | `declared`(설정 선언) / `advertised`(서버 광고) |
| `relations[].type` | O | `DECLARES` / `ASSOCIATED_WITH` / `MAY_EXPOSE_TO` / `MAY_ACCESS` / `MAY_SEND_TO` |
| `relations[].source`, `target` | O | `asset_key` 참조 |
| `expected_alerts` | 위협 구성만 | 스캐너가 내야 할 경고 |

비밀값은 기록하지 않는다. 자격증명은 참조 이름(`env:FS_TOKEN` 등)만 적는다.

## 예시 (P0, 가상 값)

```json
{
  "profile": "P0",
  "snapshot": "SNAP-2",
  "environment": { "openclaw_version": "2026.9.6", "mcp_spec_version": "2026-07-28" },
  "assets": [
    { "asset_key": "tb-gw/gateway", "asset_type": "gateway",
      "declared_at": "tb-gw:~/.openclaw/openclaw.json", "layer": "declared" },
    { "asset_key": "tb-gw/mcp_server/fs-workspace", "asset_type": "mcp_server",
      "declared_at": "tb-gw:~/.openclaw/openclaw.json#mcp.servers.fs-workspace", "layer": "declared" },
    { "asset_key": "fs-workspace/tool/read_file", "asset_type": "tool",
      "declared_at": "fs-workspace:tools/list", "layer": "advertised" }
  ],
  "relations": [
    { "type": "DECLARES", "source": "tb-gw/gateway", "target": "tb-gw/mcp_server/fs-workspace" }
  ]
}
```

## 현행 작성본 보충 (2026.10.04)

P0/P1/P2는 위 형식을 따르되, 공통 스키마 합의 전이라 아래 항목을 잠정 추가했다.

| 항목 | 내용 | 비고 |
|---|---|---|
| `relations[].type: PAIRED_WITH` | 게이트웨이 → 노드. 근거: `openclaw devices list --json`의 페어링 기록 | PR #1 의견으로 제안된 관계명 |
| `relations[].type: ADVERTISES` | MCP 서버 → 도구·리소스·프롬프트. 근거: 서버의 `tools/list` 등 | PR #1 8종 협의안 예시의 관계명 |
| `relations[].evidence_refs`, `confidence` | 모든 관계에 근거와 신뢰도 기록 | v2.0 원칙 |
| `assets[].attributes.device_id` | 게이트웨이·노드의 암호학적 device ID | ID 규칙이 device ID 기준으로 확정되면 `asset_key` 생성에 사용 |
| `assets[].attributes.exposed_to_agent` | 광고된 도구가 에이전트에 실제 투영되는지(`true`/`false`/`null`=미확인)와 사유 | 광고 계층과 노출(`MAY_EXPOSE_TO`)을 구분하기 위함 |
| `resource` + `attributes.subtype: template` | 리소스 템플릿 | 8종 분류의 `resource_prompt` 하위 유형으로 변환 가능 |

- 범위: 테스트베드가 추가한 자산만 포함. 내장(stock) 플러그인 63종·스킬 57종은 제외([../baseline/SNAP-1](../baseline/SNAP-1/)).
- 원본: `raw/<P>/` — 서버 광고 원본(`*.advertised.json`, [../tools/mcp-advertised.mjs](../tools/mcp-advertised.mjs)로 서버에 직접 수집)과 OpenClaw CLI 출력.
- 생성: `python testbed/tools/build_ground_truth.py` (S3 정상 기준인 "서버 간 원래 도구 이름 중복 없음"을 생성 시 검사).
