# 정답 목록 (Ground Truth) 형식

> 상태: 초안 (6주차 SNAP-2 구성 시 프로파일별 파일 작성)

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
