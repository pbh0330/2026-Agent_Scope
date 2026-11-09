# AI Agent Asset Visualization Dashboard Specification

> AI 에이전트 자산 가시화 대시보드 설계 및 구현 규격

**문서 버전:** v1.0
**작성 기준:** 2026-10.01
**프로젝트:** AI 에이전트 보안을 위한 자산 식별 및 가시화 도구 개발
**적용 범위:** MCP/OpenClaw 기반 AI 에이전트 환경의 정적 자산 분석 및 보안 상태 가시화

---

# 1. 문서 목적

본 문서는 AI 에이전트 보안을 위한 자산 식별 및 가시화 도구에서 사용하는 **자산 가시화 대시보드의 데이터 구조, 화면 구성, 기능 및 구현 순서**를 정의한다.

대시보드는 단순한 자산 목록을 제공하는 것이 아니라 자산 간 관계와 보안 상태를 함께 표현하는 것을 목적으로 한다.

전체 데이터 흐름은 다음과 같다.

```text
AI Agent Environment
        ↓
Asset Scanner
        ↓
Asset / Relation / Evidence
        ↓
Threat Detection
        ↓
Dashboard Data
        ↓
Asset Graph
        ↓
Security Status / Alert
```

---

# 2. 적용 범위

현재 구현 단계에서는 **정적 자산 분석 결과의 가시화**를 우선한다.

따라서 대시보드의 주요 대상은 다음과 같다.

- AI Agent 관련 자산
- MCP Gateway
- MCP Node
- MCP Server
- Tool
- Resource
- Prompt
- Skill
- Plugin
- 자산 간 관계
- 자산 상태
- 탐지된 보안 경고
- 탐지 근거

런타임 기반의 실시간 행동 분석 및 실시간 이벤트 모니터링은 현재 구현 범위에서 제외하고 추후 확장 영역으로 관리한다.

---

# 3. 핵심 설계 원칙

## 3.1 Graph-Centered

대시보드의 핵심 화면은 **자산 그래프(Asset Graph)**&#xB85C; 구성한다.

```text
Node = Asset
Edge = Relation
Metadata = Evidence / State / Security
```

이를 통해 개별 자산뿐만 아니라 자산 간 연결 관계를 확인할 수 있도록 한다.

---

## 3.2 Evidence-Based

대시보드에서 보안 경고를 표시할 경우 가능한 한 탐지 근거를 함께 제공한다.

```text
Alert
 ├── Asset
 ├── Relation
 └── Evidence
```

단순히 `위험`이라고 표시하는 것이 아니라 어떤 설정이나 관계를 기반으로 판단했는지 확인할 수 있어야 한다.

---

## 3.3 Static-First

현재 프로젝트의 스캐너는 정적 분석을 우선 수행한다.

따라서 대시보드 역시 다음 정보를 우선적으로 표현한다.

```text
구성
자산
관계
노출
설정
보안 상태
```

실제 런타임 사용 여부는 정적 분석 결과와 혼동하지 않는다.

---

# 4. 데이터 흐름

대시보드 데이터는 다음 단계로 전달된다.

```text
[환경]

AI Agent
Gateway
Node
MCP Server
Tool
Resource
Prompt
Skill
Plugin

        ↓

[Asset Scanner]

        ↓

[Asset Data]
[Relation Data]
[Evidence Data]

        ↓

[Threat Detection]

        ↓

[Security Alert]

        ↓

[Dashboard]

Asset Graph
Asset Detail
Security Status
Alert
```

---

# 5. 자산 유형 규격

현재 대시보드에서 우선적으로 표현하는 자산 유형은 7개이다.

| Asset Type | 설명                      |
| ---------- | ----------------------- |
| Gateway    | AI Agent 환경과 MCP 연결의 관문 |
| Node       | AI Agent 실행 및 연결 환경     |
| MCP Server | MCP 기능을 제공하는 서버         |
| Tool       | Agent가 호출할 수 있는 기능      |
| Resource   | Agent가 접근할 수 있는 데이터 자원  |
| Skill      | Agent 기능을 확장하는 기능       |
| Plugin     | 외부 기능 또는 확장 기능          |

Prompt는 Resource와 함께 관리되는 구성 요소로 포함할 수 있으며, 데이터 모델에서 별도 타입이 필요한 경우 확장한다.

---

# 6. 자산 상태 표현

자산 상태는 다음 단계로 관리한다.

```text
선언
 ↓
발견
 ↓
노출
 ↓
잠재 호출 가능
 ↓
호출 가능
 ↓
사용됨
```

현재 정적 분석에서는 다음 상태를 중심으로 표현한다.

```text
선언
발견
노출
```

`잠재 호출 가능`은 정적 구성과 관계 정보를 통해 추론할 수 있다.

이 경우 다음 정보를 함께 제공한다.

```text
State
Evidence
Confidence
```

실제 `호출됨`, `사용됨` 상태는 런타임 분석이 구현된 이후 확장한다.

---

# 7. 데이터 모델

대시보드는 최소 다음 세 가지 데이터 구조를 사용한다.

```text
Asset
Relation
Security Alert
```

---

# 8. Asset 데이터 규격

기본 Asset 데이터 구조는 다음과 같다.

```json
{
  "asset_id": "server-001",
  "asset_type": "MCP_SERVER",
  "name": "filesystem",
  "state": "EXPOSED",
  "source": "scanner",
  "confidence": "HIGH"
}
```

## 필드 정의

| 필드         | 타입     | 설명          |
| ---------- | ------ | ----------- |
| asset_id   | String | 자산 고유 ID    |
| asset_type | String | 자산 유형       |
| name       | String | 표시 이름       |
| state      | String | 자산 상태       |
| source     | String | 자산 발견 출처    |
| confidence | String | 탐지 근거 신뢰 수준 |

---

# 9. Relation 데이터 규격

자산 간 연결 관계는 Relation으로 표현한다.

```json
{
  "relation_id": "rel-001",
  "source": "gateway-001",
  "target": "server-001",
  "relation_type": "CONNECTS_TO"
}
```

## 필드 정의

| 필드            | 타입     | 설명       |
| ------------- | ------ | -------- |
| relation_id   | String | 관계 고유 ID |
| source        | String | 출발 자산 ID |
| target        | String | 대상 자산 ID |
| relation_type | String | 관계 유형    |

---

# 10. Security Alert 데이터 규격

보안 경고는 위협 시나리오와 자산을 연결한다.

```json
{
  "alert_id": "alert-001",
  "scenario_id": "S1",
  "severity": "HIGH",
  "message": "비인가 MCP Server가 등록되어 있습니다.",
  "asset_ids": [
    "server-001"
  ],
  "relation_ids": [
    "rel-001"
  ],
  "confidence": "HIGH"
}
```

## 필드 정의

| 필드           | 설명         |
| ------------ | ---------- |
| alert_id     | 경고 고유 ID   |
| scenario_id  | 관련 위협 시나리오 |
| severity     | 위험 수준      |
| message      | 경고 메시지     |
| asset_ids    | 관련 자산      |
| relation_ids | 관련 관계      |
| confidence   | 탐지 근거의 명확성 |

---

# 11. 그래프 구조

대시보드의 기본 그래프는 다음과 같이 구성한다.

```text
             ┌─────────────┐
             │   Gateway   │
             └──────┬──────┘
                    │
              CONNECTS_TO
                    │
             ┌──────▼──────┐
             │ MCP Server  │
             └──────┬──────┘
                    │
                PROVIDES
                    │
             ┌──────▼──────┐
             │    Tool     │
             └─────────────┘
```

그래프에서는 다음 정보를 확인할 수 있어야 한다.

- 어떤 자산이 존재하는가
- 자산이 어떤 서버에 연결되는가
- 어떤 Tool을 제공하는가
- 어떤 자산이 위험 상태인가
- 어떤 경고가 특정 자산과 연결되는가

---

# 12. Relation 규격

프로젝트에서 사용하는 관계 유형은 자산 간 구조를 표현하기 위한 기준으로 관리한다.

예:

```text
CONNECTS_TO
PROVIDES
EXPOSES
USES
CONTAINS
REFERENCES
AUTHENTICATES
```

실제 구현에서는 현재 정의된 Relation Type 목록을 기준으로 사용하며, 새로운 관계가 필요한 경우 데이터 모델을 먼저 확정한 후 추가한다.

---

# 13. 화면 구성

대시보드는 다음 네 영역을 기본 구성으로 한다.

```text
Dashboard
│
├── Overview
├── Asset Graph
├── Asset Detail
└── Security Status
```

---

# 14. Overview

Overview는 현재 분석 환경의 전체 상태를 빠르게 파악하기 위한 화면이다.

## 표시 정보

```text
Total Assets
Total Relations
Detected Alerts
High Risk Assets
Asset Type Distribution
```

예:

```text
┌─────────────────────────────────────┐
│ AI Agent Security Dashboard         │
├──────────┬──────────┬───────────────┤
│ Assets   │ Relations│   Alerts      │
│   25     │    31    │      4        │
└──────────┴──────────┴───────────────┘
```

---

# 15. Asset Graph

Asset Graph는 대시보드의 핵심 화면이다.

## 주요 기능

- 자산 그래프 표시
- 자산 선택
- 관계 강조
- 자산 유형 필터
- 상태 필터
- 검색
- 위험 자산 식별
- 자산 상세 화면 연결

---

# 16. Asset Graph 표시 규칙

## 16.1 Node

Node는 Asset을 나타낸다.

```text
Asset Type
Name
State
Security Status
```

---

## 16.2 Edge

Edge는 Relation을 나타낸다.

```text
Source
Target
Relation Type
```

---

## 16.3 선택 상태

사용자가 자산을 선택하면 다음 정보를 강조한다.

```text
Selected Asset
    ↓
Connected Assets
    ↓
Connected Relations
    ↓
Related Alerts
```

---

# 17. Asset Detail

자산을 선택하면 상세 정보를 확인할 수 있어야 한다.

## 기본 정보

```text
Asset ID
Asset Type
Name
State
Confidence
Source
```

## 관계 정보

```text
Incoming Relations
Outgoing Relations
Connected Assets
```

## 보안 정보

```text
Related Alerts
Scenario ID
Evidence
```

---

# 18. Security Status

Security Status에서는 탐지된 위협 시나리오를 확인한다.

기본 구조:

```text
Alert
 ├── Scenario
 ├── Severity
 ├── Asset
 ├── Relation
 └── Evidence
```

예:

```text
[HIGH]

S1
비인가 MCP Server 등록

Asset:
server-001

Evidence:
server_registration

Confidence:
HIGH
```

---

# 19. 시나리오-대시보드 연결

각 위협 시나리오는 대시보드의 Security Alert와 연결한다.

| Scenario | Dashboard 표현        |
| -------- | ------------------- |
| S1       | 비인가 Server Alert    |
| S2       | Tool 권한 범위 Alert    |
| S3       | Tool 이름 충돌 Alert    |
| S4       | Credential 공유 Alert |
| S5       | 연결 보안 Alert         |

---

# 20. S1 대시보드 표현

```text
Scenario: S1
Severity: HIGH

Message:
비인가 MCP Server가 등록되어 있습니다.

Related Asset:
MCP Server

Evidence:
Server Registration

Confidence:
HIGH
```

그래프에서는 해당 MCP Server와 연결된 Gateway 관계를 확인할 수 있어야 한다.

---

# 21. S2 대시보드 표현

```text
Scenario: S2
Severity: HIGH

Message:
Tool의 권한 또는 접근 범위가 기준을 초과합니다.

Related Asset:
Tool

Evidence:
Tool Permission Scope
```

---

# 22. S3 대시보드 표현

```text
Scenario: S3
Severity: MEDIUM

Message:
서로 다른 MCP Server에서 동일한 Tool 이름이 확인되었습니다.

Related Assets:
Tool A
Tool B

Evidence:
Tool Name Collision
```

그래프에서 두 Tool과 각각의 MCP Server 간 관계를 확인할 수 있어야 한다.

---

# 23. S4 대시보드 표현

```text
Scenario: S4
Severity: HIGH

Message:
하나의 Credential이 여러 Server에서 공유되고 있습니다.

Related Assets:
Server A
Server B

Evidence:
Credential Reference
Credential Scope
```

실제 Credential 값은 표시하지 않는다.

---

# 24. S5 대시보드 표현

```text
Scenario: S5
Severity: HIGH

Message:
서버 연결의 보안 검증 설정을 확인해야 합니다.

Related Asset:
MCP Server

Evidence:
Connection Security Configuration
```

---

# 25. 검색 및 필터 규칙

대시보드는 최소 다음 필터를 제공한다.

## Asset Type

```text
Gateway
Node
MCP Server
Tool
Resource
Skill
Plugin
```

## State

```text
DECLARED
DISCOVERED
EXPOSED
POTENTIALLY_CALLABLE
CALLABLE
USED
```

현재 정적 분석에서는 실제 확인 가능한 상태를 중심으로 제공한다.

## Security Status

```text
Normal
Warning
High
```

## Scenario

```text
S1
S2
S3
S4
S5
```

---

# 26. 검색 규칙

검색은 최소 다음 값을 대상으로 한다.

```text
Asset ID
Asset Name
Asset Type
Scenario ID
```

검색 결과를 선택하면 해당 자산이 Asset Graph에서 강조되어야 한다.

---

# 27. Snapshot 비교

스캐너 결과는 Snapshot 단위로 관리할 수 있다.

예:

```text
SNAP-0
SNAP-1
SNAP-2
```

두 Snapshot을 비교하여 다음 변화를 확인할 수 있도록 한다.

```text
Added Asset
Removed Asset
Changed Asset
Added Relation
Removed Relation
Changed Security Status
```

예:

```text
SNAP-2 → SNAP-S1

+ MCP Server: server-unauthorized
+ Relation: Gateway → server-unauthorized
+ Alert: S1
```

---

# 28. 스캐너 연계 규칙

대시보드 입력 데이터는 Asset Scanner가 생성하는 결과를 기준으로 한다.

```text
Scanner
   ↓
Asset JSON
   +
Relation JSON
   +
Evidence JSON
   ↓
Dashboard Parser
   ↓
Graph
```

대시보드는 스캐너 내부의 탐지 로직과 직접 결합하지 않는다.

탐지 결과가 정의된 데이터 구조를 통해 전달되도록 구성한다.

---

# 29. 데이터 처리 원칙

## 29.1 실제 Secret 미수집

다음 정보는 수집하거나 화면에 표시하지 않는다.

```text
Password
API Key
Access Token
Private Key
Secret Value
```

대신 다음과 같이 표현한다.

```text
Credential Exists
Credential Type
Credential Reference
Credential Scope
```

---

## 29.2 Evidence 보존

탐지 결과는 가능한 한 원본 근거를 추적할 수 있도록 한다.

예:

```text
Alert
 ↓
Evidence
 ↓
Source
 ↓
Configuration Field
```

---

# 30. 구현 작업 순서

대시보드 개발은 다음 순서로 진행한다.

```text
D1. 데이터 구조 확정
        ↓
D2. Scanner Output 연계
        ↓
D3. Asset Graph 구현
        ↓
D4. Asset Detail 구현
        ↓
D5. Security Alert 구현
        ↓
D6. Snapshot / Filter / Search 구현
        ↓
D7. 시나리오 기반 통합 검증
```

---

# 31. 소과제 단위 작업 목록

## D-01. Dashboard Data Schema 확정

### 작업

- Asset Schema 확정
- Relation Schema 확정
- Evidence Schema 확정
- Alert Schema 확정
- ID 규칙 확정

### 산출물

```text
Dashboard Data Schema
```

---

## D-02. Scanner Output 연계

### 작업

- Scanner Output 구조 확인
- JSON 데이터 파싱
- Asset 데이터 변환
- Relation 데이터 변환
- Evidence 데이터 연결

### 산출물

```text
Scanner → Dashboard Data Pipeline
```

---

## D-03. Asset Graph 구현

### 작업

- Node 렌더링
- Edge 렌더링
- Asset Type 표현
- State 표현
- 관계 표시
- Node 선택 기능

### 산출물

```text
Asset Graph UI
```

---

## D-04. Asset Detail 구현

### 작업

- Asset 기본정보 표시
- Asset 상태 표시
- 관계 정보 표시
- Evidence 표시
- 관련 Alert 표시

### 산출물

```text
Asset Detail UI
```

---

## D-05. Security Alert 구현

### 작업

- S1\~S5 Alert 연계
- Severity 표시
- Scenario ID 표시
- 관련 Asset 표시
- Evidence 표시
- Alert → Asset Graph 연결

### 산출물

```text
Security Alert UI
```

---

## D-06. 검색 및 필터 구현

### 작업

- Asset Type Filter
- State Filter
- Security Status Filter
- Scenario Filter
- Asset Search

### 산출물

```text
Dashboard Filter / Search
```

---

## D-07. Snapshot 비교 구현

### 작업

- Snapshot 데이터 저장
- Snapshot 선택
- Asset Diff
- Relation Diff
- Alert Diff

### 산출물

```text
Snapshot Comparison
```

---

## D-08. 통합 검증

### 작업

- S1\~S5 테스트 환경 연결
- Scanner 실행
- Dashboard 데이터 전달
- Graph 표시 확인
- Alert 표시 확인
- Evidence 연결 확인

### 산출물

```text
Dashboard Integration Test Report
```

---

# 32. 화면 간 데이터 연결

전체 화면은 동일한 Asset 데이터를 공유한다.

```text
Overview
   ↓
Asset Graph
   ↓
Asset Detail
   ↓
Security Alert
   ↓
Evidence
```

예:

```text
Overview에서 Alert 1개 확인
        ↓
Security Status 선택
        ↓
S1 Alert 선택
        ↓
server-001 선택
        ↓
Asset Graph에서 해당 Node 강조
        ↓
Asset Detail 표시
        ↓
Evidence 확인
```

---

# 33. 구현 우선순위

현재 프로젝트의 구현 우선순위는 다음과 같이 관리한다.

```text
1. Data Schema
2. Scanner Output 연결
3. Asset Graph
4. Asset Detail
5. Security Alert
6. Search / Filter
7. Snapshot Comparison
```

기본적인 Asset Graph와 Security Alert 연결을 우선 구현하고 이후 부가 기능을 확장한다.

---

# 34. 현재 구현 범위

## 포함

- 정적 Asset Discovery
- Asset Graph
- Asset Relation
- Asset State
- Evidence
- Confidence
- Security Alert
- S1\~S5 시나리오 연계
- Snapshot 기반 비교

## 추후 확장

- Runtime Monitoring
- 실제 Tool Call 추적
- Agent 행동 분석
- 실시간 Security Event
- Runtime Risk Scoring
- 장기적인 자산 변화 분석

---

# 35. 완료 기준

대시보드는 다음 조건을 모두 만족할 경우 기본 구현을 완료한 것으로 판단한다.

- [ ] Scanner Output을 입력받을 수 있다.
- [ ] 7개 주요 Asset Type을 표현할 수 있다.
- [ ] Asset 간 Relation을 표현할 수 있다.
- [ ] Asset State를 표현할 수 있다.
- [ ] Evidence를 확인할 수 있다.
- [ ] Confidence를 확인할 수 있다.
- [ ] S1\~S5 Security Alert를 표현할 수 있다.
- [ ] Alert에서 관련 Asset으로 이동할 수 있다.
- [ ] Asset에서 관련 Relation을 확인할 수 있다.
- [ ] 실제 Secret 값이 화면에 노출되지 않는다.
- [ ] Snapshot 간 변경사항을 확인할 수 있다.
- [ ] 테스트베드 기반 결과를 대시보드에서 확인할 수 있다.

---

# 36. GitHub 문서 구조

권장 디렉터리 구조는 다음과 같다.

```text
docs/
└── dashboard/
    ├── dashboard-spec.md
    ├── data-schema.md (예정)
    ├── asset-graph.md (예정)
    ├── security-alert.md (예정)
    └── snapshot-comparison.md (예정)
```

본 문서는 대시보드 전체 설계 및 구현 기준을 정의하는 기준 문서이다.

세부 구현이 진행될 경우 Data Schema, Asset Graph, Security Alert 등의 내용을 개별 문서로 분리할 수 있다.

---

# 37. 문서 변경 이력

| 버전   | 날짜         | 변경 내용                                 |
| ---- | ---------- | ------------------------------------- |
| v1.0 | 2026-10-01 | AI Agent 자산 가시화 대시보드 설계 및 구현 규격 초안 작성 |
