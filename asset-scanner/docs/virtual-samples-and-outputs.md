# 가상 자료 제작 방법·시험 조건·실제 출력 예시 (2026-11-18 재검증)

입력은 모두 **직접 작성한 가상 자료**다. 아래 JSON은 이 입력으로 스캐너 CLI를 실제 실행한 결과에서 필드를 발췌했다. 실제 OpenClaw·팀 테스트베드의 실행 결과가 아니다. 이전 판의 수작업 예시를 이번 실행 결과로 교체했다.

검토 ZIP의 `review/reproduce_examples.py`가 입력을 만들고 CLI를 실행한다. `review/synthetic-examples/inputs/`는 입력, `results/`는 원본 결과·stdout·stderr, `execution.json`은 명령·종료 코드·입력 SHA-256 기록이다. 스크립트는 지정한 **새 출력 폴더**만 만들며 실제 홈 설정·실제 자격증명을 읽지 않는다.

## 1. 자료 제작 조건과 실행

| 구분 | 조건 |
|---|---|
| 설정·설치 파일 | OpenClaw 2026.9.6 문서를 근거로 JSON/JSON5·SKILL.md를 직접 작성. 실제 팀 설정의 사본이 아님 |
| MCP 저장 응답 | `2025-11-25` 구조의 목록 응답을 코드에서 작성. 캡처의 요청 버전 `2026-07-28`은 제공된 메타데이터일 뿐 실제 협상을 수행한 증거가 아님 |
| 가짜 인증값 | `FAKE_` 표식만 사용. 토큰·명령 기록·Skill 본문 표식이 결과 JSON에 남지 않는지 검사 |
| 로컬 통신 | 마지막 한 번만 프로젝트의 `dev_lists_server`를 stdio로 실행. 4종 목록 조회만 수행. 실제 OpenClaw·원격 서버 조회가 아님 |
| 실행 환경 | Linux, Python 3.12.14, json5 0.15.0, mcp/mcp-types 2.3.0. Windows 최신 변경본은 별도 재검증 필요 |
| 원본 보존 | 입력 11개 파일의 실행 전후 SHA-256 일치. 7번 실행 모두 stderr 0바이트 |

프로젝트 의존성을 설치한 Python으로 실행한다. `<새 폴더>`는 기존 폴더와 겹치면 거부한다.

```text
python review/reproduce_examples.py --source asset-scanner --output <새 폴더>
```

| 실행 | 종료 코드 | 결과 |
|---|---:|---|
| Plugin·Skill | 0 | Plugin 1개·Skill 1개, complete |
| Permission/Auth·승인 문서 | 1 | 선언 17개 보존. SecretRef 미해석으로 partial |
| 저장 Tool 응답 | 0 | Tool 1개, 제공된 서버·클라이언트 능력 보존 |
| 저장 Resource·Template·Prompt 응답 | 0 | 각 목록이 비어 있음을 확인. 능력·서버 정보 보존 |
| Gateway 설정 + include | 0 | 서버 1개, 배열 순서·필드 출처 보존 |
| Node 설정 | 0 | 서버 1개, `enabled: false` 선언 보존 |
| 개발용 stdio 서버 | 0 | Tool·Resource·Template·Prompt 각 2개. 금지 요청 0개 |

## 2. Skill — YAML·설치 명세·설치 기록

입력은 `name: "demo" # 주석`, `description: >`의 여러 줄 설명, `requires.bins: [node, "a,b"]`, brew/download 설치 명세, `.clawhub/origin.json`의 가상 설치 기록이다. `sha256`에는 예시용 `1` 64자 문자열을 넣었다. 다운로드·설치·무결성 검증은 하지 않았다.

출력 경로: `skills[0]`의 다음 필드.

```json
{
  "frontmatter": {
    "name": "demo",
    "description": "First line second line\nNext paragraph\n"
  },
  "metadata_openclaw": {
    "openclaw_present": true,
    "requires": {
      "bins": [
        "node",
        "a,b"
      ]
    },
    "install_spec_count": 2,
    "install_specs": [
      {
        "id": "brew",
        "kind": "brew",
        "formula": "demo-cli",
        "kind_documented": true,
        "other_keys": []
      },
      {
        "id": "download",
        "kind": "download",
        "url": "https://example.invalid/demo.tar.gz",
        "kind_documented": true,
        "sha256_declared": true,
        "sha256_state": "valid_format",
        "other_keys": []
      }
    ],
    "other_keys": []
  },
  "install_origin": {
    "source": "clawhub_origin_json",
    "file": ".clawhub/origin.json",
    "verified_by_scanner": false,
    "verification": "not_performed",
    "basis": "OpenClaw 2026.9.6 docs/tools/skills.md, normalizeClawHubSkillOrigin",
    "status": "recorded",
    "version": 1,
    "installed_at_ms": 1700000000000,
    "registry": "https://registry.example.invalid",
    "slug": "demo",
    "installed_version": "1.2.3",
    "unknown_keys": []
  }
}
```

- `sha256_declared`는 키 존재, `sha256_state`는 값의 모양이다. `valid_format`은 해시 검증 성공이 아니다. 원문 다이제스트는 저장하지 않는다.
- `install_origin.installed_at_ms`는 설치 시각 기록이다. **최근 수정·업데이트 시각으로 대체하지 않는다.**
- `install_specs[].kind`는 설치 방식(brew·download 등)이다. 실제 실행물이 script인지 binary인지 판정한 값이 아니다.
- YAML은 부분집합이다. 따옴표 밖 주석·따옴표 안 쉼표·문단 줄바꿈을 처리하며, 깊이/노드/문자열 제한과 흐름 객체 중복 키를 검사한다. 앵커·별칭·태그, JSON과 호환되지 않는 큰따옴표 escape 등 미지원 문법은 추측하지 않는다. 전체 YAML 1.2 구현이 아니다.

## 3. Plugin — 공급자 힌트와 commit 선언

입력 package.json의 author·repository·homepage·gitHead를 읽은 결과다. author가 공통 자산 스키마의 provider라는 뜻은 아니며 commit의 실재·설치본 일치도 검증하지 않는다.

```json
{
  "package": {
    "name": "@demo/plugin",
    "version": "1.0.0",
    "declared_provider_hints": {
      "author_name": "Synthetic Author",
      "repository": "https://example.invalid/plugin.git",
      "homepage": "https://example.invalid/plugin"
    },
    "git_head": {
      "value": "1234567890abcdef1234567890abcdef12345678",
      "format": "sha1_hex40",
      "verified_by_scanner": false
    },
    "declared_keys": [
      "name",
      "version",
      "author",
      "homepage",
      "repository",
      "gitHead"
    ]
  }
}
```

## 4. Permission/Auth — 허용·차단·파일·네트워크 범위와 승인 문서

`permission.json`과 사용자가 명시한 `exec-approvals.json`만 읽었다. 모든 허용·차단 항목을 자동으로 찾는다는 의미는 아니며, 지원하는 경로의 선언을 보존한다. 최종 실효 권한은 계산하지 않는다.

| 실제 출력 경로 `items[].config_path` | 기록된 내용 |
|---|---|
| `tools.allow` | `["read"]` |
| `tools.deny` | `["browser"]` |
| `agents.defaults.sandbox.mode` | `"non-main"` |
| `agents.defaults.sandbox.workspaceAccess` | `"ro"` |
| `agents.defaults.sandbox.docker.network` | `"none"` |
| `agents.defaults.sandbox.docker.binds` | `["/srv/demo:/demo:ro"]` |
| `agents.defaults.sandbox.ssh.identityData` | `{"kind": "secret_ref", "ref": {"source": "env", "provider": "default", "id": "DEMO_SSH_IDENTITY"}}` |
| `tools.exec.mode` | `"allowlist"` |
| `tools.exec.host` | `"gateway"` |
| `tools.fs.workspaceOnly` | `true` |
| `browser.ssrfPolicy.dangerouslyAllowPrivateNetwork` | `false` |
| `browser.ssrfPolicy.allowedHostnames` | `["*.example.invalid"]` |
| `cron.webhookSsrfPolicy.allowedHostnames` | `["127.0.0.1"]` |
| `cron.webhookToken` | `{"kind": "literal_withheld"}` |
| `exec-approvals.socket.token` | `{"kind": "literal_withheld"}` |
| `exec-approvals.defaults.security` | `"deny"` |
| `exec-approvals.agents.main["allowlist[0]"]` | `{"pattern": "~/bin/rg", "arg_pattern_declared": true}` |

승인 항목의 `argPattern` 값·`lastUsedCommand`와 socket/webhook 토큰은 결과에 없다. SecretRef는 참조만 남기고 값을 해석하지 않아 종료 코드가 **1(partial)** 이다. 항목 17개는 결과에 보존된다.

## 5. 저장 캡처 — 서버와 클라이언트 능력의 출처

`tools_catalog`와 `resources_prompts` 모두 제공된 내용은 `*_as_provided`에 별도로 보존한다. 기존 `declared_capabilities`의 존재 요약도 유지한다. 이전 판의 "resources_prompts는 내용 미보존" 설명은 현재 코드와 달라 정정했다.

아래는 `resources_prompts` 결과 `servers[0]`의 실제 발췌다. 입력에 없는 값은 만들지 않으며, 제공값은 서버에서 직접 확인한 것으로 표시하지 않는다.

```json
{
  "declared_capabilities": {
    "resources": "declared",
    "prompts": "declared",
    "source": "stored_in_input_not_verified"
  },
  "capabilities_as_provided": {
    "value": {
      "tools": {
        "listChanged": true
      },
      "resources": {
        "subscribe": true
      },
      "prompts": {},
      "extensions": {
        "demo/extension": {
          "level": 2
        }
      }
    },
    "verified_by_scanner": false,
    "origin": "stored_capture_field"
  },
  "server_info_as_provided": {
    "value": {
      "name": "demo-server",
      "version": "1"
    },
    "verified_by_scanner": false,
    "origin": "stored_capture_field"
  },
  "client_capabilities_as_provided": {
    "value": {
      "experimental": {
        "demo": true
      }
    },
    "verified_by_scanner": false,
    "origin": "stored_capture_field",
    "sender": "synthetic-client"
  },
  "client_info_as_provided": {
    "value": {
      "name": "synthetic-client",
      "version": "1"
    },
    "verified_by_scanner": false,
    "origin": "stored_capture_field",
    "sender": "synthetic-client"
  },
  "requested_protocol_version_as_provided": "2026-07-28"
}
```

Tool 정의의 `inputSchema.$schema`는 입력의 `http://json-schema.org/draft-07/schema#`를 그대로 유지했다.

## 6. `$include` — 배열 연결과 선언 위치

입력 `include/openclaw.json`의 Gateway 서버 영역에 `a.json5`·`b.json5`를 순서대로 include하고 형제 항목을 더했다. Node 영역도 같은 파일에 넣었다. 각 실행에서는 지정한 영역의 서버만 수집했다. 설정의 가상 command는 실행하지 않았다.

Gateway 결과 `servers[0]`:

```json
{
  "registration_key": "s",
  "declaration_path": "mcp.servers.s",
  "declared": {
    "command": "from-main",
    "args": [
      "--a1",
      "--a2",
      "--b1",
      "--main"
    ]
  },
  "include_origin": {
    "file": "a.json5",
    "include_chain": [
      "a.json5"
    ],
    "basis": "include_resolution (논리 경로는 declaration_path, 파일은 최상위 설정 폴더 기준 상대 경로)",
    "field_origin_overrides": [
      {
        "field_path": "mcp.servers.s.args[2]",
        "file": "b.json5"
      },
      {
        "field_path": "mcp.servers.s.args[3]",
        "file": "(top-level config)"
      },
      {
        "field_path": "mcp.servers.s.command",
        "file": "(top-level config)"
      }
    ]
  }
}
```

Node 결과 `servers[0]`:

```json
{
  "registration_key": "node-docs",
  "declaration_path": "nodeHost.mcp.servers.node-docs",
  "declared": {
    "command": "python",
    "args": [
      "-m",
      "synthetic_node_mcp"
    ],
    "enabled": false
  }
}
```

## 7. 개발용 stdio 서버 — 실제 전송 관측

프로젝트 내 개발용 서버를 새 프로세스로 실행한 결과다. 저장 응답을 읽는 시험과 구분한다. 전송 관측값은 SDK 쓰기 스트림이 전송을 받아들인 뒤에만 기록하며, 서버 수신 확인·OpenClaw의 전송값을 뜻하지 않는다. 실패한 send를 전송됨으로 기록하지 않는 회귀 테스트도 있다.

```json
{
  "collection": {
    "status": "complete",
    "outcome": "lists_collected",
    "reasons": [],
    "item_counts": {
      "tools": 2,
      "resources": 2,
      "resource_templates": 2,
      "prompts": 2
    }
  },
  "client_capabilities_sent": {
    "sender": "asset_scanner live_discovery (MCP Python SDK client)",
    "is_openclaw_client": false,
    "origin": "observed_outgoing_message",
    "note": "이 스캐너의 클라이언트가 서버로 실제 보낸 값이다. OpenClaw(Gateway·Node)가 서버에 보내는 client capabilities가 아니다.",
    "status": "observed",
    "mode": "per_request_meta",
    "observed_on_method": "server/discover",
    "protocol_version": "2026-07-28",
    "capabilities": {},
    "client_info": {
      "name": "mcp",
      "version": "0.1.0"
    }
  },
  "requests": {
    "by_method": {
      "tools/list": 1,
      "resources/list": 2,
      "resources/templates/list": 1,
      "prompts/list": 1
    },
    "allowed_list_methods": [
      "prompts/list",
      "resources/list",
      "resources/templates/list",
      "tools/list"
    ],
    "forbidden_requests_sent": 0,
    "forbidden_examples_never_sent": [
      "tools/call",
      "resources/read",
      "prompts/get",
      "resources/subscribe",
      "completion/complete"
    ],
    "request_undeclared": false
  }
}
```
