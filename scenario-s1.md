# S1. 비인가 MCP Server 등록 및 노출

> Scenario ID: `S1`  
> Scenario Name: 비인가 MCP Server 등록 및 노출  
> Priority: `P1`  
> Attack Surface: `A — MCP 통신 경계`  
> 문서 기준: 2026-10-06  
> 적용 Spec: `threat-scenario-spec.md v2.0`

---

## 1. Basic Information

| 항목 | 내용 |
|---|---|
| Scenario ID | `S1` |
| Scenario Name | 비인가 MCP Server 등록 및 노출 |
| Priority | P1 |
| Attack Surface | A — MCP 통신 경계 |
| Related Assets | Gateway, Node, MCP Server, Skill, Plugin |
| Related Relations | `DECLARES`, `CONNECTS_TO`, `REFERENCES` 등 |

### 시나리오 목적

Gateway 또는 Node의 설정에서 **승인되지 않은 MCP Server가 등록·노출되어 있는지 식별**한다.

본 시나리오는 현재 프로젝트의 정적 분석 범위에 맞춰 실제 서버 연결이나 Tool 호출 성공 여부가 아니라, **MCP Server 선언 정보, 서버 식별자, Endpoint, 출처 및 관련 Skill·Plugin 정보를 기반으로 비인가 등록 가능성을 탐지**하는 것을 목표로 한다.

---

## 2. Related Assets

### 2.1 Gateway

MCP Server가 등록되는 Agent 환경의 Gateway 구성 요소이다.

```text
Gateway
   │
DECLARES
   │
   ▼
MCP Server
```

Gateway는 설치된 인스턴스를 기준으로 식별하며, 반복 스캔에서도 동일한 Gateway를 식별할 수 있도록 안정적인 Asset ID를 사용한다.

### 2.2 Node

분산 실행 환경에서 MCP Server가 선언될 수 있는 실행 노드이다.

```text
Node
  │
DECLARES
  │
  ▼
MCP Server
```

Server의 선언 위치와 실제 실행 위치는 구분하여 기록한다.

### 2.3 MCP Server

S1의 핵심 탐지 대상이다.

다음 정보를 확인한다.

- Server Identifier
- Declaration Source
- Endpoint
- 등록 위치
- 출처
- 버전
- 무결성 관련 정보

### 2.4 Skill / Plugin

Skill 또는 Plugin을 통해 새로운 MCP Server가 추가되거나 연결될 수 있으므로 관련 자산으로 식별한다.

```text
Skill / Plugin
      │
 REFERENCES
      │
      ▼
 MCP Server
```

---

## 3. Normal State

정상 상태에서는 Agent 환경에 **승인된 MCP Server만 선언되어 있어야 한다.**

### 정상 구성 기준

- 승인된 MCP Server 목록이 존재한다.
- Gateway 또는 Node의 Server 선언 정보가 승인 목록과 일치한다.
- Server Identifier가 승인된 식별자와 일치한다.
- Endpoint가 승인된 주소와 일치한다.
- Server의 선언 위치를 확인할 수 있다.
- Skill / Plugin을 통해 등록되는 경우 해당 출처를 확인할 수 있다.
- 필요한 경우 Server의 출처 및 무결성 정보를 확인할 수 있다.

### 테스트베드 정상 기준

S1의 정상 구성에서는 **승인 서버 목록을 문서화**하고, Scanner가 실제 선언 정보와 승인 목록을 비교한다.

---

## 4. Risk State

다음 조건 중 하나 이상이 확인되면 S1 위험 후보로 판단한다.

| 위험 조건 | 판단 내용 |
|---|---|
| 신규 Server 선언 | 기존 승인 목록에 없는 MCP Server가 선언됨 |
| 승인되지 않은 Server | Server Identifier가 승인 목록과 일치하지 않음 |
| Endpoint 불일치 | 승인된 주소와 다른 Endpoint가 확인됨 |
| 출처 이상 | 예상하지 않은 Skill / Plugin 또는 설치 경로를 통해 Server가 등록됨 |
| 무결성 이상 | 버전·파일·설정 등에서 예상하지 않은 변경이 확인됨 |
| 선언 위치 이상 | 예상하지 않은 Gateway 또는 Node에서 Server가 선언됨 |

> 위 조건은 정적 분석 단계의 **위험 후보**이다. 실제 서버 연결 성공이나 실제 Tool 호출을 의미하지 않는다.

---

## 5. Threat Scenario

비인가 MCP Server가 Gateway 또는 Node의 설정에 등록되면 Agent가 해당 Server를 인식하거나 이후 호출 가능한 대상으로 취급할 가능성이 발생한다.

따라서 정적 분석 단계에서 **어떤 MCP Server가 어디에 선언되어 있으며, 해당 Server가 승인된 대상인지**를 확인한다.

또한 Skill 또는 Plugin이 Server 등록에 영향을 주는 경우 해당 관계를 함께 분석한다.

전체 구조는 다음과 같다.

```text
Gateway / Node
      │
   DECLARES
      │
      ▼
 MCP Server
      ▲
      │
 REFERENCES
      │
Skill / Plugin
```

단, `DECLARES`는 설정상 Server가 선언되어 있다는 의미이며, **실제 연결 성공을 의미하지 않는다.**

---

## 6. Static Detection

### 6.1 기본 탐지 조건

```text
IF
  Gateway 또는 Node에서 MCP Server 선언이 확인되고
  AND
  해당 Server가 승인 목록에 존재하지 않거나
  Identifier / Endpoint가 승인 정보와 일치하지 않음
THEN
  S1 Alert 생성
```

### 6.2 추가 탐지 조건

다음 정보를 함께 확인한다.

```text
MCP Server
    │
    ├── Server Identifier
    ├── Endpoint
    ├── Declaration Source
    ├── Version
    ├── Integrity
    │
    └── Related Skill / Plugin
```

### 6.3 승인 목록 비교

```text
실제 선언 정보
      │
      ▼
승인 Server 목록과 비교
      │
      ├── 일치 ──▶ Normal
      │
      └── 불일치 ─▶ S1 Finding
```

비교 대상은 최소 다음 항목을 포함한다.

- Server Identifier
- Endpoint
- 등록 위치
- 승인 여부

### 6.4 관련 관계

정적 분석 결과에서 다음 관계를 생성할 수 있다.

```text
Gateway ── DECLARES ──▶ MCP Server

Node ── DECLARES ──▶ MCP Server

Skill / Plugin ── REFERENCES ──▶ MCP Server
```

`DECLARES`는 설정상 등록 관계이며, 연결 성공이나 실행 성공을 의미하지 않는다.

---

## 7. Evidence

S1 탐지 결과에는 비인가 Server 여부를 판단한 근거를 포함한다.

### 7.1 Evidence 항목

| Evidence | 설명 |
|---|---|
| `server_identifier` | MCP Server 식별 정보 |
| `declaration_source` | Server 선언이 확인된 설정 위치 |
| `endpoint` | Server Endpoint |
| `approval_status` | 승인 목록과의 일치 여부 |
| `source` | Server 설치·등록 출처 |
| `version` | 확인된 Server 버전 |
| `integrity` | 무결성 관련 정보 |
| `related_assets` | 관련 Gateway / Node / Skill / Plugin |

### 7.2 Evidence 예시

```json
{
  "evidence_type": "server_declaration",
  "source": "gateway_config",
  "asset_id": "mcp-server-001",
  "server_identifier": "unknown-server",
  "endpoint": "https://example.invalid/mcp",
  "approval_status": "unapproved",
  "declaration_source": "gateway-config.json"
}
```

> 실제 Token, API Key, Password 등의 Secret 값은 Evidence에 저장하지 않는다.

---

## 8. Confidence

Confidence는 S1 탐지 판단의 **근거 수준**을 의미한다.

| 수준 | 기준 |
|---|---|
| High | Server 선언, Identifier, Endpoint 및 승인 목록을 직접 비교하여 비인가 여부를 명확히 판단 |
| Medium | Server 선언과 일부 식별 정보는 확인했으나 승인 또는 출처 정보가 일부 부족 |
| Low | Server에 대한 간접 정보만 확인되어 비인가 여부를 확정하기 어려움 |

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

정상 구성과 위험 구성을 각각 준비하고 Scanner가 승인된 Server와 비인가 Server 선언을 구분하여 S1 Alert를 생성하는지 확인한다.

### 9.2 정상 구성

```text
Gateway / Node
      │
   DECLARES
      │
      ▼
승인된 MCP Server
      │
      ▼
승인 목록과 일치
```

정상 구성 기준:

- 승인된 MCP Server만 선언
- Server Identifier 일치
- Endpoint 일치
- 선언 위치 확인 가능
- 관련 출처 정보 확인 가능

### 9.3 위험 구성

다음과 같은 변경을 적용한다.

#### Case 1. 비인가 Server 추가

```text
정상
Gateway
   │
DECLARES
   │
   ▼
Approved Server

위험
Gateway
   │
DECLARES
   ├──▶ Approved Server
   │
   └──▶ Unapproved Server
```

#### Case 2. Endpoint 변경

```text
정상
Server A ──▶ 승인된 Endpoint

위험
Server A ──▶ 승인되지 않은 Endpoint
```

#### Case 3. Skill / Plugin을 통한 예상하지 않은 Server 등록

```text
Skill / Plugin
      │
 REFERENCES
      │
      ▼
비인가 MCP Server
```

### 9.4 검증 절차

1. 정상 Snapshot 생성
2. 승인 MCP Server 목록 작성
3. Server Asset 및 Relation Ground Truth 작성
4. Scanner 실행
5. 정상 구성에서 S1 오탐 여부 확인
6. 위험 Snapshot 생성
7. 비인가 Server 또는 Endpoint 추가
8. Scanner 실행
9. S1 탐지 결과와 Ground Truth 비교
10. Evidence / Confidence 확인

---

## 10. Ground Truth

S1 검증을 위한 Ground Truth에는 최소 다음 정보를 포함한다.

| 항목 | 내용 |
|---|---|
| Asset ID | MCP Server의 고유 식별자 |
| Asset Type | `mcp_server` |
| Server Identifier | Server 식별 정보 |
| Declaration Source | Server 선언 위치 |
| Endpoint | Server Endpoint |
| Approval Status | 승인 / 비승인 |
| Source | 설치·등록 출처 |
| Related Assets | Gateway / Node / Skill / Plugin |
| Expected Relations | `DECLARES`, `REFERENCES` 등 |
| Expected Finding | S1 탐지 여부 |

---

## 11. Metrics

S1은 다음 지표를 기준으로 평가한다.

### 11.1 비인가 Server 탐지 여부

승인 목록에 없는 MCP Server가 선언된 경우 S1 Alert가 생성되는지 확인한다.

### 11.2 Server 식별 정확도

탐지된 MCP Server가 실제 위험 구성의 Server와 일치하는지 확인한다.

### 11.3 Declaration Source 식별 정확도

Server가 어느 Gateway 또는 Node 설정에서 선언되었는지 정확히 식별하는지 확인한다.

### 11.4 Endpoint 식별 정확도

Server의 Endpoint를 정확히 수집하고 승인 정보와 비교하는지 확인한다.

### 11.5 관계 식별 정확도

다음 관계가 실제 구성과 일치하는지 확인한다.

```text
Gateway ── DECLARES ──▶ MCP Server

Node ── DECLARES ──▶ MCP Server

Skill / Plugin ── REFERENCES ──▶ MCP Server
```

### 11.6 정상 구성 오탐 여부

승인된 Server만 존재하는 정상 환경에서 S1 Alert가 발생하지 않는지 확인한다.

---

## 12. Dashboard Linkage

### 12.1 Asset Graph

S1 관련 자산은 다음과 같이 표현할 수 있다.

```text
Gateway A
    │
  DECLARES
    │
    ▼
MCP Server B
    ▲
    │
 REFERENCES
    │
Skill / Plugin C
```

Node가 Server를 선언하는 경우:

```text
Node D
    │
  DECLARES
    │
    ▼
MCP Server B
```

### 12.2 Security Alert

S1 Alert에는 최소 다음 정보를 연결한다.

```text
Scenario ID
    └── S1

Related Assets
    ├── Gateway / Node
    ├── MCP Server
    └── Skill / Plugin

Related Relations
    ├── DECLARES
    └── REFERENCES

Evidence
    ├── server identifier
    ├── declaration source
    ├── endpoint
    ├── approval status
    ├── source
    └── integrity

Confidence
Snapshot ID
Alert Status
```

---

## 13. Expected Alert

### Alert 제목

```text
비인가 MCP Server 등록 및 노출
```

### Alert 내용 예시

```text
승인 목록에 존재하지 않는 MCP Server가
Gateway 또는 Node 설정에 선언되어 있습니다.

- Server: unknown-server
- Declaration Source: gateway-config.json
- Endpoint: https://example.invalid/mcp
- Approval Status: unapproved
- Confidence: High
```

> 실제 인증정보나 Secret 값은 Alert에 표시하지 않는다.

---

## 14. 구현 작업

| ID | 작업 | 결과물 |
|---|---|---|
| S1-01 | MCP Server 선언 정보 수집 | MCP Server Asset |
| S1-02 | Gateway / Node 선언 위치 식별 | Declaration Evidence |
| S1-03 | 승인 Server 목록 구성 | Approved Server List |
| S1-04 | Server Identifier / Endpoint 비교 | S1 Detection Rule |
| S1-05 | Skill / Plugin 연관 정보 수집 | Related Asset / Relation |
| S1-06 | 출처 / 버전 / 무결성 정보 확인 | Source Evidence |
| S1-07 | Evidence / Confidence 생성 | Security Finding |
| S1-08 | Dashboard Alert 연계 | S1 Security Alert |
| S1-09 | 정상 / 위험 Snapshot 검증 | Validation Result |

---

## 15. 완료 기준

- [ ] Gateway에서 선언된 MCP Server를 식별할 수 있다.
- [ ] Node에서 선언된 MCP Server를 식별할 수 있다.
- [ ] MCP Server의 Server Identifier를 수집할 수 있다.
- [ ] MCP Server의 Endpoint를 수집할 수 있다.
- [ ] Server의 Declaration Source를 식별할 수 있다.
- [ ] 승인된 Server 목록과 실제 선언 정보를 비교할 수 있다.
- [ ] 비인가 Server 또는 Endpoint 불일치를 위험 후보로 탐지할 수 있다.
- [ ] 관련 Skill / Plugin을 식별하고 관계를 표현할 수 있다.
- [ ] Evidence가 탐지 결과에 포함된다.
- [ ] Confidence가 탐지 결과에 포함된다.
- [ ] 정상 구성에서 오탐 여부를 검증할 수 있다.
- [ ] Dashboard Asset Graph 및 Security Alert에 연결할 수 있다.
- [ ] `DECLARES`를 실제 연결 성공으로 해석하지 않는다.
- [ ] 실제 Token / API Key / Password / Secret 값을 수집·표시하지 않는다.

---

## 16. 현재 범위 및 후속 확장

### 현재 범위

- Gateway / Node의 MCP Server 선언 정보 정적 분석
- 승인 Server 목록과 비교
- Server Identifier / Endpoint 확인
- Declaration Source 확인
- Skill / Plugin 연관 관계 분석
- 출처 / 버전 / 무결성 정보 확인
- Evidence / Confidence
- Snapshot 기반 검증

### 후속 범위

다음 항목은 현재 S1 정적 탐지에서 확정하지 않고 후속 런타임 분석에서 검토한다.

- 실제 MCP Server 연결 성공 여부
- 실제 Server Handshake 성공 여부
- 실제 Tool 호출 여부
- 실제 Server 응답 여부
- 실제 비인가 서버로의 통신 발생 여부

---

## 17. References

- `threat-scenario-spec.md v2.0`
- `AI Agent MCP 공격표면 정의 v2.0`
- `프로젝트 세부수행 보고서 2026-09-30`
