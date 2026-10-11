# S2. 악성 또는 과도한 권한의 도구 광고

> Scenario ID: `S2`  
> Scenario Name: 악성 또는 과도한 권한의 도구 광고  
> Priority: `P2`  
> Attack Surface: `A — MCP 통신 경계`, `C — 권한·자격증명`  
> 문서 기준: 2026-10-06  
> 적용 Spec: `threat-scenario-spec.md v2.0`

---

## 1. Basic Information

| 항목 | 내용 |
|---|---|
| Scenario ID | `S2` |
| Scenario Name | 악성 또는 과도한 권한의 도구 광고 |
| Priority | P2 |
| Attack Surface | A — MCP 통신 경계 / C — 권한·자격증명 |
| Related Assets | MCP Server, Tool, Permission/Auth, Resource / Template / Prompt |
| Related Relations | `PROVIDES`, `EXPOSES`, `APPLIES_TO`, `AUTHENTICATES`, `REFERENCES` 등 |

### 시나리오 목적

MCP Server가 Agent에게 제공하는 Tool 중 **고위험 입력 항목을 포함하거나 과도한 권한으로 사용될 수 있는 Tool**을 식별한다.

본 시나리오는 현재 프로젝트의 정적 분석 범위에 맞춰 실제 Tool 실행이나 공격 성공 여부가 아니라, **Tool의 입력 스키마, 권한 설정, 승인 정책 및 관련 Permission/Auth 정보를 기반으로 위험 가능성을 탐지**하는 것을 목표로 한다.

---

## 2. Related Assets

### 2.1 MCP Server

Tool을 제공·광고하는 서버이다.

```text
MCP Server
    │
  PROVIDES
    │
    ▼
  Tool
```

### 2.2 Tool

실제 위험 판단의 핵심 대상이다.

Tool 정의에서 다음과 같은 고위험 입력 항목을 확인한다.

- 경로(`path`)
- 명령(`command`)
- 주소(`address`)
- 토큰·자격증명(`token`, `credential`)
- 제한되지 않은 대상(`unrestricted destination`)

### 2.3 Permission/Auth

Tool이 사용할 수 있는 권한 또는 인증 설정을 식별한다.

```text
Permission/Auth
       │
   APPLIES_TO
       │
       ▼
      Tool
```

권한 범위가 Tool의 기능보다 과도하게 설정되었거나 승인 정책이 누락된 경우 S2 위험 후보로 판단한다.

### 2.4 Resource / Template / Prompt

Tool이 접근하거나 처리할 수 있는 Resource, Resource Template, Prompt가 존재하는 경우 관련 자산으로 연결한다.

---

## 3. Normal State

정상 상태에서는 Tool의 기능과 권한 범위가 필요한 수준으로 제한되어야 한다.

### 정상 구성 기준

- Tool Filter가 적용되어 필요한 Tool만 노출된다.
- 파일 관련 Tool은 필요한 작업 디렉터리로 범위가 제한된다.
- Tool의 입력 스키마를 확인할 수 있다.
- Tool 기능에 대응하는 Permission/Auth 범위를 확인할 수 있다.
- 승인 정책이 적용되는 경우 해당 정책과 Tool의 관계를 확인할 수 있다.
- 실제 필요한 범위를 넘어선 파일·명령·네트워크 접근 권한이 부여되지 않는다.

### 테스트베드 정상 기준

S2의 정상 구성에서는 **파일 서버의 작업 디렉터리를 한정하고 Tool Filter를 적용**한다.

또한 테스트베드의 자산 및 관계 Ground Truth를 사전에 작성하여 Scanner 결과와 비교한다.

---

## 4. Risk State

다음 조건 중 하나 이상이 확인되면 S2 위험 후보로 판단한다.

| 위험 조건 | 판단 내용 |
|---|---|
| 고위험 입력 | Tool 입력 스키마에 경로·명령·주소·토큰 등의 고위험 항목이 존재 |
| 권한 범위 과다 | Tool 기능에 비해 Permission/Auth의 권한 범위가 넓음 |
| 승인 정책 누락 | 필요한 Tool Filter 또는 승인 정책을 확인할 수 없음 |
| 파일 접근 범위 과다 | 작업 디렉터리 외부 또는 민감 경로 접근 가능성이 확인됨 |
| 네트워크 범위 과다 | 제한되지 않은 외부 또는 내부 목적지 입력이 가능함 |
| 인증정보 입력 | Tool 입력에 Token 또는 Credential 관련 항목이 포함됨 |

> 위 조건은 정적 분석 단계의 **위험 후보**이다. 실제 악성 실행 또는 실제 권한 사용을 의미하지 않는다.

---

## 5. Threat Scenario

MCP Server가 Agent에게 파일시스템, 명령 실행, 네트워크 또는 인증정보와 연결될 수 있는 Tool을 광고한다.

Tool의 입력 범위가 넓거나 Permission/Auth가 충분히 제한되지 않은 경우, 해당 Tool이 접근할 수 있는 자원 및 기능의 범위가 필요 이상으로 확대될 수 있다.

예를 들어 파일 작업 Tool에 제한된 작업 디렉터리가 적용되지 않거나, 명령 실행 Tool에 별도의 승인 정책이 적용되지 않는 경우를 위험 후보로 판단할 수 있다.

본 프로젝트에서는 다음과 같은 구조를 정적으로 확인한다.

```text
MCP Server
    │
  PROVIDES
    │
    ▼
   Tool
    │
    ├── 입력 스키마
    │
    └── Permission/Auth
              │
          APPLIES_TO
```

---

## 6. Static Detection

### 6.1 기본 탐지 조건

```text
IF
  MCP Server가 Tool을 제공하고
  AND
  Tool 입력 스키마에 고위험 항목이 존재하며
  AND
  해당 Tool에 적용되는 Permission/Auth 범위가 과도하거나
  필요한 승인 정책 / Tool Filter가 확인되지 않음
THEN
  S2 Alert 생성
```

### 6.2 고위험 입력 항목

다음 입력 항목을 주요 탐지 대상으로 한다.

| 유형 | 예시 |
|---|---|
| 경로 | `path`, `file_path`, `directory` |
| 명령 | `command`, `exec`, `shell` |
| 네트워크 주소 | `url`, `host`, `address`, `destination` |
| 인증정보 | `token`, `credential`, `api_key` |
| 제한 없는 대상 | unrestricted destination / wildcard target |

단, 입력 필드 이름만으로 실제 위험성을 확정하지 않고 **Tool의 기능과 Permission/Auth 설정을 함께 확인**한다.

### 6.3 권한 범위 탐지

다음 항목을 확인한다.

```text
Tool 기능
    │
    └── 비교
          │
          ▼
Permission/Auth 범위
```

예:

- Tool은 특정 workspace 파일만 다루면 되는데 외부 경로까지 접근 가능
- Tool은 제한된 네트워크 대상만 필요하지만 광범위한 목적지 접근 가능
- Tool 기능에 비해 과도한 실행 권한이 부여됨
- 필요한 사용자 승인 또는 Tool Filter가 누락됨

### 6.4 관련 관계

가능한 경우 다음 관계를 생성한다.

```text
MCP Server ── PROVIDES ──▶ Tool

Permission/Auth ── APPLIES_TO ──▶ Tool
```

인증 설정이 별도로 식별되는 경우:

```text
Tool / MCP Server
       ▲
       │ AUTHENTICATES
       │
Permission/Auth
```

실제 관계 명칭은 공통 스키마에서 확정한 명칭을 우선한다.

---

## 7. Evidence

S2 탐지 결과에는 Tool의 위험 가능성을 판단한 근거를 포함한다.

### 7.1 Evidence 항목

| Evidence | 설명 |
|---|---|
| `tool_identifier` | Tool 식별 정보 |
| `server_identifier` | Tool을 제공하는 MCP Server |
| `input_schema` | Tool 입력 스키마 |
| `high_risk_fields` | 확인된 고위험 입력 항목 |
| `permission_policy` | 관련 Permission/Auth 정책 |
| `approval_policy` | Tool Filter 또는 승인 정책 |
| `scope` | 확인된 접근·권한 범위 |
| `related_assets` | 관련 Resource / Prompt / Permission/Auth 등 |

### 7.2 Evidence 예시

```json
{
  "evidence_type": "tool_definition",
  "source": "mcp_server_catalog",
  "asset_id": "tool-001",
  "server_id": "mcp-server-001",
  "high_risk_fields": [
    "path",
    "command"
  ],
  "permission_auth_id": "permission-001",
  "approval_policy": "missing"
}
```

> 실제 Token, API Key, Password 등의 값은 저장하지 않는다.

---

## 8. Confidence

Confidence는 S2 탐지 판단의 **근거 수준**을 의미한다.

| 수준 | 기준 |
|---|---|
| High | Tool 정의, 입력 스키마, 관련 Permission/Auth 및 정책 정보를 직접 확인하여 위험 조건을 명확히 판단 |
| Medium | Tool의 고위험 입력 또는 권한 범위는 확인했으나 일부 정책 정보가 부족 |
| Low | Tool 또는 권한에 대한 간접 정보만 확인되어 위험 범위를 확정하기 어려움 |

### Confidence와 Severity

```text
Confidence
= 위험 판단 근거의 확실성

Severity
= 위험의 영향 및 대응 우선순위
```

두 값은 독립적으로 기록한다.

---

## 9. Validation

### 9.1 검증 목적

정상 구성과 위험 구성을 각각 준비하고 Scanner가 Tool의 고위험 입력 및 권한 조건을 구분하여 S2 Alert를 생성하는지 확인한다.

### 9.2 정상 구성

```text
MCP Server
    │
  PROVIDES
    │
    ▼
   Tool
    │
    ▼
제한된 Permission/Auth
    │
    ▼
제한된 작업 디렉터리 / Tool Filter
```

정상 구성 기준:

- 파일 서버 작업 디렉터리 제한
- Tool Filter 적용
- 필요한 범위의 권한만 부여
- 승인 정책이 필요한 경우 정책 적용

### 9.3 위험 구성

다음과 같은 변경을 적용한다.

#### Case 1. 파일 접근 범위 확대

```text
정상
Tool ──▶ workspace/

위험
Tool ──▶ workspace/ + 외부 경로
```

#### Case 2. Tool Filter 제거

```text
정상
필요한 Tool만 노출

위험
불필요한 고위험 Tool까지 노출
```

#### Case 3. 과도한 Permission/Auth

```text
Tool
  │
  └── APPLIES_TO
        │
        ▼
광범위한 파일 / 명령 / 네트워크 권한
```

### 9.4 검증 절차

1. 정상 Snapshot 생성
2. Tool 및 Permission/Auth Ground Truth 작성
3. Scanner 실행
4. 정상 구성에서 S2 오탐 여부 확인
5. 위험 Snapshot 생성
6. 위험 Tool 및 권한 상태 Ground Truth 작성
7. Scanner 실행
8. S2 탐지 결과와 Ground Truth 비교
9. Evidence / Confidence 확인

---

## 10. Ground Truth

S2 검증을 위한 Ground Truth에는 최소 다음 정보를 포함한다.

| 항목 | 내용 |
|---|---|
| Asset ID | Tool의 고유 식별자 |
| Asset Type | `tool` |
| Server ID | Tool을 제공하는 MCP Server |
| Input Schema | 입력 항목 |
| High-Risk Fields | 고위험 입력 항목 |
| Permission/Auth ID | 적용되는 권한·인증 자산 |
| Scope | 권한 범위 |
| Approval Policy | Tool Filter / 승인 정책 |
| Expected Relations | `PROVIDES`, `APPLIES_TO` 등 |
| Expected Finding | S2 탐지 여부 |

---

## 11. Metrics

S2는 다음 지표를 기준으로 평가한다.

### 11.1 위험 Tool 탐지 여부

고위험 입력 또는 과도한 권한을 가진 Tool이 존재할 때 S2 Alert가 생성되는지 확인한다.

### 11.2 Tool 식별 정확도

탐지된 Tool이 실제 위험 구성의 Tool과 일치하는지 확인한다.

### 11.3 고위험 입력 식별 정확도

다음 항목을 정확히 식별하는지 확인한다.

```text
path
command
address
token / credential
unrestricted destination
```

### 11.4 Permission/Auth 관계 식별 정확도

Tool에 적용되는 Permission/Auth를 정확히 식별하고 `APPLIES_TO` 관계를 생성하는지 확인한다.

### 11.5 정상 구성 오탐 여부

정상적인 Tool Filter 및 권한 제한이 적용된 환경에서 S2 Alert가 발생하지 않는지 확인한다.

---

## 12. Dashboard Linkage

### 12.1 Asset Graph

S2 관련 자산은 다음 구조로 표현할 수 있다.

```text
MCP Server A
    │
  PROVIDES
    │
    ▼
 Tool B
    ▲
    │
APPLIES_TO
    │
    │
Permission/Auth C
```

Tool의 위험 상태가 탐지된 경우 관련 Tool, MCP Server, Permission/Auth를 함께 확인할 수 있어야 한다.

### 12.2 Security Alert

S2 Alert에는 최소 다음 정보를 연결한다.

```text
Scenario ID
    └── S2

Related Assets
    ├── MCP Server
    ├── Tool
    └── Permission/Auth

Related Relations
    ├── PROVIDES
    └── APPLIES_TO

Evidence
    ├── input schema
    ├── high-risk fields
    ├── permission scope
    └── approval policy

Confidence
Snapshot ID
Alert Status
```

---

## 13. Expected Alert

### Alert 제목

```text
고위험 입력 또는 과도한 권한을 가진 Tool 발견
```

### Alert 내용 예시

```text
MCP Server가 제공하는 Tool에서 고위험 입력 항목과
과도한 권한 범위가 확인되었습니다.

- Server: mcp-server-001
- Tool: tool-001
- High-Risk Fields: path, command
- Permission/Auth: permission-001
- Approval Policy: missing
- Confidence: High
```

> 실제 인증정보나 Secret 값은 Alert에 표시하지 않는다.

---

## 14. 구현 작업

| ID | 작업 | 결과물 |
|---|---|---|
| S2-01 | Tool 정의 및 입력 스키마 수집 | Tool Asset |
| S2-02 | 고위험 입력 항목 판별 규칙 정의 | High-Risk Field Rule |
| S2-03 | Permission/Auth 정보 수집 | Permission/Auth Asset |
| S2-04 | Tool과 Permission/Auth 관계 생성 | `APPLIES_TO` Relation |
| S2-05 | Tool Filter / 승인 정책 확인 | Approval Policy Evidence |
| S2-06 | 권한 범위 비교 규칙 구현 | S2 Detection Rule |
| S2-07 | Evidence / Confidence 생성 | Security Finding |
| S2-08 | Dashboard Alert 연계 | S2 Security Alert |
| S2-09 | 정상 / 위험 Snapshot 검증 | Validation Result |

---

## 15. 완료 기준

- [ ] MCP Server가 제공하는 Tool을 식별할 수 있다.
- [ ] Tool의 입력 스키마를 수집할 수 있다.
- [ ] 경로·명령·주소·토큰 등의 고위험 입력 항목을 식별할 수 있다.
- [ ] 관련 Permission/Auth 자산을 식별할 수 있다.
- [ ] Tool과 Permission/Auth의 적용 관계를 표현할 수 있다.
- [ ] Tool Filter 또는 승인 정책의 적용 여부를 확인할 수 있다.
- [ ] 과도한 권한 또는 정책 누락을 위험 후보로 탐지할 수 있다.
- [ ] Evidence가 탐지 결과에 포함된다.
- [ ] Confidence가 탐지 결과에 포함된다.
- [ ] 정상 구성에서 오탐 여부를 검증할 수 있다.
- [ ] Dashboard Asset Graph 및 Security Alert에 연결할 수 있다.
- [ ] 실제 Tool 실행이나 공격 성공을 정적 탐지 결과로 확정하지 않는다.
- [ ] 실제 Token / API Key / Password / Secret 값을 수집·표시하지 않는다.

---

## 16. 현재 범위 및 후속 확장

### 현재 범위

- Tool 정의 및 입력 스키마 정적 분석
- 고위험 입력 항목 식별
- Permission/Auth 자산 및 적용 관계 분석
- Tool Filter / 승인 정책 확인
- 권한 범위 비교
- Evidence / Confidence
- Snapshot 기반 검증

### 후속 범위

다음 항목은 현재 S2 정적 탐지에서 확정하지 않고 후속 런타임 분석에서 검토한다.

- 실제 Tool 호출 여부
- 실제 명령 실행 결과
- 실제 파일 접근 여부
- 실제 네트워크 연결 및 외부 전송
- 실제 Token / Credential 사용 여부
- 실행 과정에서의 비정상 행위

---

## 17. References

- `threat-scenario-spec.md v2.0`
- `AI Agent MCP 공격표면 정의 v2.0`
- `프로젝트 세부수행 보고서 2026-09-30`
