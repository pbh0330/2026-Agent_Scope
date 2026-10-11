# S3. Tool 이름 충돌을 이용한 호출 대상 위장

## 1. Basic Information

- **Scenario ID:** S3
- **Title:** Tool 이름 충돌을 이용한 호출 대상 위장
- **Priority:** P3
- **Attack Surface:** A. MCP 통신 경계
- **Analysis Type:** Static Analysis
- **Status:** Defined

### 목적

서로 다른 MCP Server가 동일한 Tool 이름을 제공하는 상황을 식별하고,
서버별 Tool 정보와 권한 차이를 비교하여 호출 대상 혼동 가능성을 탐지한다.

정적 분석을 통해 Tool 이름 충돌과 관련된 구성 정보를 확인하며,
실제 Tool 호출이나 공격 성공 여부는 판단하지 않는다.

---

## 2. Related Assets

| Asset Type | 설명 |
|---|---|
| Gateway | MCP Server 등록 및 Tool 연결 구조 확인 |
| Node | MCP Server가 선언된 실행 환경 확인 |
| MCP Server | Tool을 제공하는 서버 식별 |
| Tool | 이름, 입력 스키마, 설명 및 권한 정보 비교 |

### 주요 관계

    Gateway
       │
       ├── DECLARES ──> MCP Server A
       │                    │
       │                    └── PROVIDES ──> Tool: search
       │
       └── DECLARES ──> MCP Server B
                            │
                            └── PROVIDES ──> Tool: search

서로 다른 MCP Server가 동일한 이름의 Tool을 제공하는지 확인한다.

단, Tool 이름이 같다는 이유만으로 두 Tool을 동일한 자산으로 취급하지 않는다.

---

## 3. Normal State

정상 상태에서는 각 MCP Server가 제공하는 Tool을 서버별로 구분할 수 있어야 한다.

### 정상 조건

- 테스트 환경에서 서로 다른 MCP Server 간 Tool 이름이 중복되지 않음
- 각 Tool의 제공 서버를 식별할 수 있음
- Tool의 식별자와 제공 서버 간 관계가 유지됨
- Tool의 입력 스키마 및 권한 정보를 확인할 수 있음

### 예시

    MCP Server A
      └── PROVIDES ──> search

    MCP Server B
      └── PROVIDES ──> read_file

서버별 Tool 이름이 구분되므로 이름 충돌에 따른 혼동 가능성이 낮은 상태다.

---

## 4. Risk State

위험 상태에서는 서로 다른 MCP Server가 동일한 Tool 이름을 제공한다.

### 위험 조건

- 서로 다른 MCP Server에서 동일한 Tool 이름이 발견됨
- 동일한 이름을 가진 Tool의 제공 서버가 서로 다름
- 서버별 Endpoint, 입력 스키마, 권한 또는 설명에 차이가 존재함
- Tool 이름만으로는 제공 서버와 실제 기능을 구분하기 어려울 가능성이 있음

### 예시

    MCP Server A
      └── PROVIDES ──> search
                         ├── 입력: 검색어
                         └── 권한: 제한된 검색

    MCP Server B
      └── PROVIDES ──> search
                         ├── 입력: URL
                         └── 권한: 외부 네트워크 접근

두 Tool의 이름은 같지만 제공 서버와 기능, 권한이 다르다.

이 경우 호출 대상이 혼동될 가능성을 검토해야 한다.

> 동일한 Tool 이름이 존재한다는 사실만으로 실제 호출 대상이 위장되었거나 공격에 성공했다고 판단하지 않는다.

---

## 5. Threat Scenario

AI Agent 환경에서 서로 다른 MCP Server가 동일한 Tool 이름을 제공할 수 있다.

이때 Tool 이름만으로 기능을 구분하거나 제공 서버를 명확하게 식별하지 못하면,
사용자 또는 시스템이 의도한 Tool과 실제로 선택되는 Tool 사이에 혼동이 발생할 가능성이 있다.

특히 동일한 이름을 가진 Tool의 Endpoint, 입력 스키마, 설명 또는 권한이 서로 다른 경우,
이름 충돌로 인한 호출 대상 혼동 위험을 검토할 필요가 있다.

본 시나리오에서는 정적 구성 정보를 분석하여 중복된 Tool 이름과 서버별 차이를 식별한다.

---

## 6. Static Detection

### 탐지 조건

서로 다른 MCP Server가 동일한 Tool 이름을 제공하고,
서버별 주요 정보에 차이가 있는 경우 S3 Alert를 생성한다.

### 탐지 로직

    IF
        Tool이 서로 다른 MCP Server에 의해 제공되고
        AND
        Tool Name이 동일하며
        AND
        Provider / Endpoint / Permission / Input Schema 중
        하나 이상의 차이가 확인되면

    THEN
        S3 Alert 생성

### 탐지 예시

    Tool Name: search

    Server A:
      Endpoint: server-a.example
      Permission: restricted

    Server B:
      Endpoint: server-b.example
      Permission: broad

### 주의 사항

- Tool 이름이 같더라도 서로 다른 자산으로 유지한다.
- Tool ID와 제공 서버 정보를 함께 관리한다.
- 이름 충돌과 실제 호출 대상 위장은 구분한다.
- 정적 분석만으로 실제 호출 경로나 공격 성공을 단정하지 않는다.
- 비교에 필요한 정보가 부족하면 미확인 항목으로 기록한다.

---

## 7. Evidence

S3 탐지 결과에는 Tool 이름 충돌과 서버별 차이를 확인할 수 있는 근거를 포함한다.

### Evidence 항목

| 항목 | 설명 |
|---|---|
| `tool_name` | 중복된 Tool 이름 |
| `tool_identifier` | 개별 Tool 식별자 |
| `server_identifier` | Tool을 제공하는 MCP Server 식별자 |
| `endpoint` | MCP Server Endpoint 정보 |
| `input_schema` | Tool 입력 스키마 |
| `permission_auth` | 관련 권한 또는 인증 설정 참조 |
| `description` | Tool 설명 |
| `comparison_result` | 서버별 비교 결과 |
| `related_assets` | 관련 자산 목록 |

### Evidence 예시

    {
      "scenario_id": "S3",
      "tool_name": "search",
      "comparison_result": {
        "duplicate_name": true,
        "provider_differs": true,
        "endpoint_differs": true,
        "permission_differs": true
      },
      "related_assets": [
        "mcp_server:server-a",
        "mcp_server:server-b",
        "tool:server-a.search",
        "tool:server-b.search"
      ]
    }

위 예시는 데이터 구조를 설명하기 위한 예시이며,
실제 탐지 결과는 Scanner가 수집한 정보를 기준으로 생성한다.

실제 Secret 값은 Evidence에 포함하지 않는다.

---

## 8. Confidence

Confidence는 탐지 근거가 얼마나 충분한지를 나타낸다.

| Level | 기준 |
|---|---|
| High | 서로 다른 MCP Server의 동일 Tool 이름과 주요 정보 차이가 명확하게 확인됨 |
| Medium | Tool 이름 중복은 확인되지만 일부 비교 정보가 부족함 |
| Low | 제한된 정보만 확인되어 충돌 여부 또는 위험 조건을 판단하기 어려움 |

Confidence는 위험도와 별개로 관리한다.

Tool 이름이 중복되었다는 사실만으로 실제 공격 가능성이 확정되는 것은 아니다.

---

## 9. Validation

정상 환경과 위험 환경을 구성하여 S3 탐지 결과를 검증한다.

### 9.1 정상 환경

- 서로 다른 MCP Server 간 Tool 이름이 중복되지 않도록 구성
- 각 Tool의 제공 서버 및 식별자 확인
- Scanner 실행 후 S3 Alert 발생 여부 확인

### 9.2 위험 환경

- 서로 다른 MCP Server에 동일한 Tool 이름을 등록
- 필요에 따라 Endpoint, 입력 스키마 또는 권한 정보를 다르게 구성
- Scanner 실행 후 중복 이름 및 정보 차이 탐지 여부 확인

### 검증 절차

    Normal Snapshot
          ↓
    동일 Tool 이름 추가
          ↓
    필요 시 Endpoint / Schema / Permission 변경
          ↓
    Risk Snapshot
          ↓
    Scanner 실행
          ↓
    탐지 결과 확인
          ↓
    Ground Truth와 비교

---

## 10. Ground Truth

Ground Truth는 테스트 환경에서 의도적으로 구성한 Tool 이름 및 서버별 차이의 기준값이다.

### 정상 상태

- 서로 다른 MCP Server 간 Tool 이름 중복 없음
- 각 Tool의 제공 서버 식별 가능

### 위험 상태

- 서로 다른 MCP Server에서 동일한 Tool 이름 발견
- 구성에 따라 Endpoint, 입력 스키마 또는 권한 차이 존재

Scanner 결과를 Ground Truth와 비교하여 중복 탐지 및 관련 자산 식별이 정확한지 평가한다.

---

## 11. Metrics

S3는 다음 지표를 기준으로 평가한다.

### 11.1 Duplicate Tool Name Detection

서로 다른 MCP Server 간 중복 Tool 이름을 정확하게 탐지했는지 평가한다.

### 11.2 Asset Identification

중복된 Tool과 이를 제공하는 MCP Server를 정확하게 식별했는지 평가한다.

### 11.3 Relation Identification

MCP Server와 Tool 사이의 `PROVIDES` 관계를 정확하게 구성했는지 평가한다.

### 11.4 Difference Identification

서버별 Endpoint, 입력 스키마, 권한 및 설명의 차이를 정확하게 식별했는지 평가한다.

### 11.5 False Positive

정상적인 구성이나 의도된 이름 중복을 위험으로 잘못 판단한 사례를 확인한다.

### 11.6 Evidence Completeness

탐지 결과에 중복 Tool 이름, 제공 서버 및 비교 근거가 포함되어 있는지 평가한다.

---

## 12. Dashboard Linkage

S3 탐지 결과는 Asset Graph와 Security Alert에 연결한다.

### 12.1 Asset Graph

동일한 Tool 이름을 가진 자산을 그룹화하거나 비교할 수 있도록 표현한다.

    MCP Server A
       │
       └── PROVIDES ──> search
                              │
                              └── 동일 이름 비교
                                      │
    MCP Server B                       │
       │                               │
       └── PROVIDES ──> search <───────┘

각 Tool은 별도의 Asset ID를 유지하며,
제공 서버와의 관계를 통해 구분한다.

### 12.2 Security Alert

Alert에는 다음 정보를 포함한다.

- Scenario ID
- 중복 Tool 이름
- 관련 MCP Server
- 관련 Tool Asset
- 서버별 차이
- Evidence
- Confidence

사용자가 Alert를 선택하면 관련 Tool과 MCP Server를 Asset Graph에서 확인할 수 있도록 연결한다.

---

## 13. Expected Alert

### Alert Title

**동일한 Tool 이름을 사용하는 MCP Server 발견**

### Alert 내용 예시

    Scenario: S3
    Title: 동일한 Tool 이름을 사용하는 MCP Server 발견
    Tool Name: search
    Related Servers:
      - server-a
      - server-b

    Differences:
      - Endpoint 차이
      - Permission 차이

    Confidence: High

Alert는 이름 충돌과 확인된 차이를 안내한다.
실제 호출 대상 위장 여부는 별도 검증 없이는 확정하지 않는다.

---

## 14. Implementation Tasks

### S3-01. Tool 식별 정보 정의

- Tool 이름 및 고유 식별자 기준 정의
- 제공 서버 식별 정보 정의

### S3-02. MCP Server와 Tool 관계 수집

- MCP Server 정보 수집
- Tool 제공 정보 수집
- `PROVIDES` 관계 생성

### S3-03. Tool 이름 비교 로직 구현

- 서로 다른 MCP Server에서 제공하는 Tool 이름 비교
- 중복 이름 식별

### S3-04. Tool 정보 비교 로직 구현

- Endpoint 비교
- 입력 스키마 비교
- 권한 정보 비교
- 설명 비교

### S3-05. 중복 Tool 탐지 규칙 구현

- 동일 Tool 이름과 제공 서버 차이 확인
- 시나리오 조건에 따른 Alert 생성

### S3-06. Evidence 생성

- 중복 이름 기록
- 제공 서버 및 Tool 식별자 기록
- 비교 결과 기록

### S3-07. Confidence 산정

- 수집 정보의 충분성에 따른 Confidence 기준 적용
- 미확인 정보 구분

### S3-08. Dashboard 연계

- 중복 Tool 및 제공 서버 표시
- 관련 Asset Graph 연결
- Security Alert 표시

### S3-09. 정상 / 위험 환경 검증

- 정상 환경에서 불필요한 Alert 발생 여부 확인
- 중복 Tool 이름 환경에서 탐지 여부 확인
- Ground Truth와 비교

### S3-10. 결과 및 완료 기준 정리

- 탐지 결과 기록
- 평가 지표 확인
- 미탐지 및 오탐 사례 정리

---

## 15. Completion Criteria

다음 조건을 충족하면 S3 구현을 완료한 것으로 본다.

- [ ] 서로 다른 MCP Server에서 제공하는 Tool 이름을 비교할 수 있음
- [ ] 동일한 Tool 이름을 가진 Tool을 식별할 수 있음
- [ ] 각 Tool의 고유 식별자를 유지할 수 있음
- [ ] Tool과 MCP Server 사이의 `PROVIDES` 관계를 구성할 수 있음
- [ ] 서버별 주요 정보 차이를 비교할 수 있음
- [ ] 탐지 근거를 Evidence로 저장할 수 있음
- [ ] Confidence 기준을 적용할 수 있음
- [ ] Security Alert를 생성할 수 있음
- [ ] Dashboard Asset Graph에서 관련 자산을 확인할 수 있음
- [ ] 정상 / 위험 환경을 이용해 탐지 결과를 검증할 수 있음

---

## 16. Current Scope / Future Expansion

### Current Scope

현재는 Static Analysis를 통해 다음 항목을 확인한다.

- Tool 이름 중복
- Tool 제공 서버 식별
- Endpoint 및 입력 스키마 차이
- 확인 가능한 권한 정보 차이
- MCP Server와 Tool 간 관계

### Future Expansion

향후 Runtime Analysis를 통해 다음 항목을 추가로 검증할 수 있다.

- 실제 Tool 선택 및 호출 대상
- 호출 과정에서의 이름 해석 방식
- 실제 호출 대상과 의도한 대상의 일치 여부
- 호출 시 적용되는 권한
- 실제 호출 결과 및 실행 이력

현재 정적 분석만으로 실제 호출 대상 위장이나 공격 성공을 확정하지 않는다.

---

## 17. References

- Threat Scenario Specification v2.0
- MCP 관련 보안 및 구성 기준
- OpenClaw 환경 구성 및 테스트베드 정의
