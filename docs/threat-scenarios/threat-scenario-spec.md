# Threat Scenario Specification v2.1

> AI Agent 보안을 위한 자산 식별 및 가시화 도구의 위협 시나리오 작성·검증 공통 규격

- **Version:** v2.1 (v2.0: 2026-10-06)
- **작성일:** 2026-10-06 · **개정일:** 2026-11-08
- **v2.1 변경:** [부록 A](#부록-a-v21-변경-사항-2026-11-08) — 구현 우선순위, 조건 ID, 평가 결과, 카탈로그·기대 결과 문서, 관계 이름 대응
- **문서 유형:** Threat Scenario Specification
- **적용 범위:** AI Agent / MCP / OpenClaw 기반 환경
- **분석 방식:** Static Analysis 우선

---

## 1. 문서 목적

본 문서는 AI Agent 환경에서 발생할 수 있는 보안 위협을 일관된 기준으로 정의하고,
Asset Scanner 및 Dashboard 구현에 활용하기 위한 공통 위협 시나리오 작성·검증 규격을 정의한다.

개별 위협 시나리오(S1~S5)는 본 문서의 공통 규칙을 기반으로 별도 문서에서 정의한다.

### 주요 목적

- AI Agent 환경의 보안 자산 식별 기준 정의
- 공격표면 및 자산 상태 기준 정의
- 자산 간 관계(Relation) 정의
- 정적 분석 기반 위협 탐지 기준 정의
- Evidence 및 Confidence 기준 정의
- 정상/위험 환경을 이용한 검증 기준 정의
- Dashboard Security Alert 연계 기준 정의

---

## 2. 분석 범위

### 2.1 대상 환경

본 프로젝트의 분석 대상은 다음 환경을 기준으로 한다.

- AI Agent
- Gateway
- Node
- MCP Server
- Tool
- Resource / Template / Prompt
- Skill
- Plugin
- Permission / Authentication

주요 테스트 환경은 OpenClaw 기반 AI Agent 환경과 MCP 연동 구조를 대상으로 한다.

---

## 3. 공격표면 분류

AI Agent 환경의 공격표면은 다음 3개 영역으로 분류한다.

| 공격표면 | 설명 |
|---|---|
| A. MCP 통신 경계 | Gateway / Node와 MCP Server 사이의 연결 및 Tool 노출 영역 |
| B. Skill / Plugin 공급망 | Skill / Plugin 설치, 선언, 소스 및 확장 기능 영역 |
| C. 권한·자격증명 | Permission / Authentication 및 접근 범위와 관련된 영역 |

---

## 4. 자산 분류 기준

### 4.1 자산 유형

본 프로젝트에서는 자산을 다음 8개 유형으로 분류한다.

| Type | 명칭 | 설명 |
|---|---|---|
| `gateway` | Gateway | AI Agent Gateway 인스턴스 및 관련 설정 |
| `node` | Node | 분산 실행 Node의 식별 정보 및 설정 |
| `mcp_server` | MCP Server | MCP Server 선언, 연결 및 Discovery 정보 |
| `tool` | Tool | MCP Server가 제공하는 개별 Tool |
| `resource_prompt` | Resource / Template / Prompt | Resource, Resource Template, Prompt |
| `skill` | Skill | Skill 설치, 선언 및 소스 정보 |
| `plugin` | Plugin | Plugin 설치, 선언 및 확장 관계 |
| `permission_auth` | Permission / Authentication | 권한 정책 또는 인증 설정/참조 정보 |

> 위 8개는 자산의 **분류 유형**이며, 실제 자산 개수와 동일하지 않다.
> 실제 자산의 개수는 각 Asset의 고유한 `asset_id`를 기준으로 산정한다.

### 4.2 Subtype

필요한 경우 자산의 세부 유형을 `subtype`으로 구분한다.

예:

- `resource_prompt`
  - `resource`
  - `resource_template`
  - `prompt`

- `permission_auth`
  - `permission_policy`
  - `authentication_config`

---

## 5. Asset ID 기준

각 자산은 고유한 `asset_id`를 가진다.

예:

    gateway:gateway-01
    node:node-01
    mcp_server:filesystem
    tool:filesystem.read_file
    skill:skill-example
    plugin:plugin-example
    permission_auth:filesystem-policy

동일 환경을 반복적으로 Scan하더라도 동일한 자산을 식별할 수 있도록
가능한 경우 안정적인 식별자를 사용한다.

특히 Gateway는 설치된 인스턴스를 기준으로 독립적인 Asset으로 식별한다.

---

## 6. 자산 상태(State)

자산의 상태는 다음 단계로 구분한다.

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

### 6.1 선언

설정 파일이나 구성 정보에 자산이 명시되어 있는 상태.

예:

- Gateway 설정에 MCP Server가 등록됨
- Plugin 설정에 특정 Plugin이 선언됨

### 6.2 발견

Scanner가 실제 환경에서 자산의 존재를 확인한 상태.

### 6.3 노출

자산이 외부 또는 다른 구성요소에서 접근 가능한 구조로 확인된 상태.

### 6.4 잠재 호출 가능

현재 정적 분석 결과를 기준으로 호출 가능한 조건이 존재한다고 판단되는 상태.

> 정적 분석 단계에서는 실제 호출이 발생했다고 판단하지 않는다.

잠재 호출 가능 여부는 다음과 같은 근거를 통해 판단할 수 있다.

- Tool 제공 관계
- 접근 권한
- 연결 정보
- 호출 대상 식별 가능 여부
- 정책 및 설정 정보

### 6.5 호출 가능

실제 실행 조건이 충족되어 호출할 수 있는 상태.

현재 프로젝트의 Static Analysis 범위에서는 직접적인 실행 성공 여부를 기본적으로 검증하지 않는다.

### 6.6 사용됨

실제 실행 또는 사용 이력이 확인된 상태.

이는 향후 Runtime Analysis 범위에서 확장한다.

---

## 7. 자산 관계(Relation)

자산 간 관계는 Graph 기반 시각화를 위해 별도의 Relation으로 관리한다.

### 7.1 주요 Relation

| Relation | 의미 |
|---|---|
| `DECLARES` | Gateway / Node가 MCP Server를 선언 |
| `CONNECTS_TO` | 구성요소 간 연결 관계 |
| `PROVIDES` | MCP Server가 Tool 등을 제공 |
| `EXPOSES` | 자산이 다른 자산 또는 기능을 노출 |
| `USES` | 특정 자산을 사용하는 관계 |
| `CONTAINS` | 구성요소가 다른 자산을 포함 |
| `REFERENCES` | 설정 또는 구성에서 특정 자산을 참조 |
| `AUTHENTICATES` | 인증 구성과 대상 간 관계 |
| `APPLIES_TO` | Permission / Policy가 특정 자산에 적용 |

---

## 8. DECLARES 관계 기준

`DECLARES`는 설정 또는 구성에서 MCP Server가 등록되어 있음을 의미한다.

예:

    Gateway
       │
       └── DECLARES ──> MCP Server

단,

> `DECLARES` 관계는 MCP Server의 **선언 또는 등록 사실**을 의미하며,
> 실제 연결 성공이나 Tool 호출 성공을 의미하지 않는다.

---

## 9. Permission / Authentication Asset 기준

Permission / Authentication은 다른 자산의 속성으로만 처리하지 않고,
독립적으로 식별 가능한 경우 별도의 Asset으로 관리한다.

### 9.1 Permission Asset

예:

    permission_auth:filesystem-policy

다음과 같은 정보를 기반으로 식별할 수 있다.

- 권한 정책
- 접근 범위
- 허용된 Resource
- 허용된 Tool
- 파일 시스템 접근 범위
- 네트워크 접근 범위

### 9.2 Authentication Asset

인증 설정 또는 인증 참조가 독립적으로 식별 가능한 경우 별도 Asset으로 관리한다.

예:

    permission_auth:filesystem-auth

### 9.3 APPLIES_TO 관계

Permission / Authentication Asset은 대상 자산과의 관계를 통해 적용 범위를 표현한다.

예:

    Permission/Auth
          │
          └── APPLIES_TO ──> Tool

또는

    Permission/Auth
          │
          └── APPLIES_TO ──> MCP Server

---

## 10. Secret 보호 기준

실제 Secret 값은 수집하거나 Dashboard에 표시하지 않는다.

### 수집 가능한 정보

- Secret 존재 여부
- Secret 유형
- 환경변수 이름
- Secret 참조 위치
- 적용 범위

### 수집하지 않는 정보

- 실제 API Key
- Access Token
- Password
- Private Key
- 실제 Credential 값

예:

    {
      "secret_present": true,
      "secret_type": "api_key",
      "reference": "ENV_VAR_NAME"
    }

---

## 11. 환경변수 식별 기준

동일한 환경변수 이름이 존재한다는 사실만으로
동일한 Credential이라고 판단하지 않는다.

예:

    SERVER_A_API_KEY
    SERVER_B_API_KEY

각각의 Credential은 적용 범위와 참조 위치를 별도로 확인한다.

---

## 12. 위협 시나리오 문서 구조

개별 위협 시나리오는 다음 구조를 따른다.

    Basic Information
    Related Assets
    Normal State
    Risk State
    Threat Scenario
    Static Detection
    Evidence
    Confidence
    Validation
    Ground Truth
    Metrics
    Dashboard Linkage
    Expected Alert
    Implementation Tasks
    Completion Criteria
    Current Scope / Future Expansion
    References

---

## 13. Basic Information

각 시나리오는 다음 정보를 포함한다.

| 항목 | 설명 |
|---|---|
| Scenario ID | S1 ~ S5 |
| Title | 위협 시나리오 명칭 |
| Priority | 위험 등급 P1~P3 (v2.1: 구현 우선순위 1~5는 별도, 부록 A.1) |
| Attack Surface | A / B / C |
| Analysis Type | Static / Runtime |
| Status | Draft / Defined / Validated 등 |

---

## 14. Normal State

정상 상태에서는 테스트 환경에서 의도적으로 설정한 정상 구성과
보안 정책이 충족되어 있는지를 정의한다.

예:

- 승인된 MCP Server만 등록
- Tool Filter 적용
- 제한된 파일 시스템 접근 범위
- 서버별 Credential 분리
- TLS 및 인증서 검증

정상 상태는 Ground Truth와 비교하여 False Positive를 평가하는 기준으로 사용한다.

---

## 15. Risk State

위협 시나리오를 재현하기 위해 정상 환경에서 특정 보안 조건을 변경한다.

예:

- 승인되지 않은 MCP Server 등록
- 과도한 Tool 권한 부여
- 동일 Tool Name 등록
- Credential 공유
- 보안이 약한 연결 구성

Risk State는 공격 성공 자체보다
Scanner가 식별할 수 있는 구성상의 위험 조건을 중심으로 정의한다.

---

## 16. Static Detection 기준

Static Analysis에서는 구성 정보와 관계 정보를 기반으로 위협 조건을 판단한다.

일반적인 구조:

    IF
        특정 자산 또는 관계가 존재하고
        AND
        위험 조건이 확인되며
        AND
        관련 Evidence가 존재하는 경우

    THEN
        해당 Threat Scenario Alert 생성

정적 분석 결과만으로 실제 공격 성공이나 실제 Tool 실행을 주장하지 않는다.

---

## 17. Evidence 기준

각 Threat Alert는 탐지 근거가 되는 Evidence를 포함해야 한다.

예:

    {
      "asset_id": "tool:filesystem.read_file",
      "server_id": "mcp_server:filesystem",
      "evidence": {
        "config_source": "openclaw.json",
        "permission_scope": "workspace",
        "input_schema": {},
        "related_assets": []
      }
    }

Evidence는 가능한 경우 원본 구성 위치 또는 식별 가능한 정보를 포함한다.

---

## 18. Confidence 기준

탐지 결과는 Evidence의 충분성에 따라 Confidence를 부여한다.

| Level | 기준 |
|---|---|
| High | 핵심 조건과 관련 Evidence가 명확하게 확인됨 |
| Medium | 주요 조건은 확인되나 일부 정보가 부족함 |
| Low | 제한된 정보 또는 간접적인 근거만 확인됨 |

Confidence는 공격 위험도와 별개의 값이다.

---

## 19. Validation 기준

각 시나리오는 최소한 정상 환경과 위험 환경을 비교하여 검증한다.

    Normal Snapshot
          ↓
    Risk Modification
          ↓
    Risk Snapshot
          ↓
    Scanner 실행
          ↓
    Detection Result
          ↓
    Ground Truth 비교

---

## 20. Ground Truth

Ground Truth는 테스트 환경에서 실제로 의도한 상태를 기록한 기준값이다.

예:

    S1:
    - approved server = 정상
    - unapproved server = 위험

    S2:
    - restricted tool permission = 정상
    - excessive permission = 위험

Ground Truth와 Scanner 결과를 비교하여 탐지 성능을 평가한다.

---

## 21. 평가 지표

각 위협 시나리오는 다음 지표를 기준으로 평가한다.

### 21.1 Detection

위험 상태를 실제로 탐지했는지 평가한다.

    Detection Rate
    = 탐지한 위험 상태 수 / 전체 위험 상태 수

### 21.2 Asset Identification

위협과 관련된 자산을 정확하게 식별했는지 평가한다.

예:

- Gateway
- Node
- MCP Server
- Tool
- Permission/Auth

### 21.3 Relation Identification

위협과 관련된 자산 간 관계를 정확하게 식별했는지 평가한다.

예:

    Gateway
      └── DECLARES ──> MCP Server

### 21.4 Evidence Identification

탐지 결과에 필요한 근거 정보가 포함되어 있는지 평가한다.

### 21.5 False Positive

정상 상태를 위험 상태로 잘못 탐지한 경우를 측정한다.

---

## 22. Dashboard 연계

Threat Scenario 탐지 결과는 Dashboard의 다음 요소와 연결한다.

### 22.1 Asset Graph

자산 및 관계를 Graph 형태로 표현한다.

예:

    Gateway
       │
       └── DECLARES ──> MCP Server
                             │
                             └── PROVIDES ──> Tool

### 22.2 Security Alert

위협이 탐지되면 Security Alert를 생성한다.

예:

    {
      "alert_id": "S1-001",
      "scenario_id": "S1",
      "severity": "high",
      "title": "비인가 MCP Server 등록 및 노출",
      "confidence": "high",
      "related_assets": []
    }

---

## 23. Scanner Output

Asset Scanner는 최소한 다음 정보를 전달해야 한다.

    Assets
    Relations
    Evidence
    Security Alerts
    Scan Metadata

예:

    {
      "scan_id": "scan-001",
      "assets": [],
      "relations": [],
      "alerts": [],
      "metadata": {
        "timestamp": "",
        "environment": ""
      }
    }

---

## 24. Snapshot 기준

환경 상태는 Snapshot 단위로 관리한다.

예:

    SNAP-0
    └── Base Environment

    SNAP-1
    └── OpenClaw Installed / Paired

    SNAP-2
    └── Normal State

    SNAP-S1
    └── S1 Risk State

    SNAP-S2
    └── S2 Risk State

    ...

각 Snapshot은 Scanner 실행 및 결과 비교에 활용한다.

---

## 25. Testbed 기준

테스트베드는 다음 구조를 기준으로 한다.

    Gateway VM
        │
        └── Node VM
              │
              └── MCP Servers

MCP Reference Server 및 Custom Remote Server를 활용하여
정상/위험 상태를 구성한다.

테스트 환경에서는 실제 민감정보를 사용하지 않고,
Dummy Value 또는 Reference Name을 사용한다.

---

## 26. 시나리오별 문서 관리

개별 시나리오는 별도의 Markdown 파일로 관리한다.

    docs/
    └── threat-scenarios/
        ├── README.md                  목차·버전·상태 (v2.1 추가)
        ├── threat-scenario-spec.md
        ├── scenario-s1.md
        ├── scenario-s2.md
        ├── scenario-s3.md
        ├── scenario-s4.md
        ├── scenario-s5.md
        ├── scenario-catalog.json      ScenarioDefinition 카탈로그 (v2.1 추가)
        ├── expected-results.md        S1~S5 기대 결과 (v2.1 추가)
        └── policies/
            └── expected-tool-policy.json   S2 기준 정책 (v2.1 추가)

---

## 27. 구현 작업 목록

### TS-01. 공통 자산 분류 기준 확정

- 8개 Asset Type 확정
- Subtype 기준 확정
- Asset ID 기준 정의

### TS-02. 공격표면 기준 확정

- A. MCP 통신 경계
- B. Skill / Plugin 공급망
- C. 권한·자격증명

### TS-03. Asset State 정의

- 선언
- 발견
- 노출
- 잠재 호출 가능
- 호출 가능
- 사용됨

### TS-04. Relation 기준 확정

- DECLARES
- CONNECTS_TO
- PROVIDES
- EXPOSES
- USES
- CONTAINS
- REFERENCES
- AUTHENTICATES
- APPLIES_TO

### TS-05. Permission / Authentication 기준 확정

- Permission Asset
- Authentication Asset
- 적용 범위
- APPLIES_TO 관계

### TS-06. Evidence / Confidence 기준 확정

- Evidence 구조
- Confidence Level
- Evidence 기반 판단 기준

### TS-07. Scenario Validation 기준 확정

- Normal Snapshot
- Risk Snapshot
- Ground Truth
- Detection Result 비교

### TS-08. Dashboard 연계 기준 확정

- Asset Graph
- Relation Graph
- Security Alert
- Scenario ID 연계

### TS-09. Scanner Output 기준 확정

- Assets
- Relations
- Evidence
- Alerts
- Scan Metadata

### TS-10. 개별 시나리오 문서 작성

- S1 비인가 MCP Server 등록 및 노출
- S2 고위험 입력 또는 과도한 권한을 가진 Tool
- S3 Tool 이름 충돌을 이용한 호출 대상 위장
- S4 과도한 자격증명 공유
- S5 보안이 약한 연결을 통한 서버 위장 가능성

---

## 28. 완료 기준

다음 조건을 모두 충족하면 공통 Threat Scenario Specification 작성을 완료한 것으로 본다.

- [ ] Asset Type 8종 정의
- [ ] Asset ID 기준 정의
- [ ] Attack Surface A/B/C 정의
- [ ] Asset State 정의
- [ ] Relation 기준 정의
- [ ] Permission / Authentication 기준 정의
- [ ] Secret 보호 기준 정의
- [ ] Evidence 기준 정의
- [ ] Confidence 기준 정의
- [ ] Validation 기준 정의
- [ ] Ground Truth 기준 정의
- [ ] 평가 지표 정의
- [ ] Dashboard 연계 기준 정의
- [ ] Scanner Output 기준 정의
- [ ] Testbed 기준 정의
- [ ] S1~S5 개별 문서 구조 정의

---

## 29. 범위 및 향후 확장

### 현재 범위

현재 프로젝트에서는 Static Analysis를 우선 구현한다.

주요 확인 범위:

- 설정 파일
- 서버 선언
- Tool 정의
- Permission / Authentication 설정
- Skill / Plugin 정보
- 자산 간 관계
- 정적 구성상의 위험 조건

### 향후 확장

향후 Runtime Analysis를 추가하여 다음 정보를 확장할 수 있다.

- 실제 Tool 호출
- 실제 Resource 접근
- 실행 이력
- Runtime Permission 변화
- 실제 공격 수행 여부
- 사용된 자산 추적

현재 Static Analysis 결과만으로 Runtime 행동이나
실제 공격 성공을 의미한다고 해석하지 않는다.

---

## 30. 문서 구조

최종 GitHub 문서 구조는 다음과 같다.

    docs/
    ├── dashboard/
    │   └── dashboard-spec.md
    │
    └── threat-scenarios/
        ├── threat-scenario-spec.md
        ├── scenario-s1.md
        ├── scenario-s2.md
        ├── scenario-s3.md
        ├── scenario-s4.md
        └── scenario-s5.md

---

---

## 부록 A. v2.1 변경 사항 (2026-11-08)

2026-11-08 담당자 확정 사항이다. 본문과 다르면 이 부록이 우선한다.

### A.1 위험 등급과 구현 우선순위

v2.0의 `P1~P3`은 위험 등급으로 유지하고, 구현·검증 순서는 정수 우선순위로 따로 둔다. 순서는 테스트베드 PR #4의 S1 → S2 → S4 → S3 → S5를 따른다. 공통 스키마 0.7 13.3절의 미합의 항목을 이것으로 닫는다.

| 우선순위 | 시나리오 | 위험 등급 | 주요 공격 표면 | 문서 |
|---|---|---|---|---|
| 1 | S1 비인가 MCP Server 등록 및 노출 | P1 | A (관련 B) | [scenario-s1.md](scenario-s1.md) |
| 2 | S2 악성 또는 과도한 권한의 도구 광고 | P2 | A, C | [scenario-s2.md](scenario-s2.md) |
| 3 | S4 과도한 자격증명 공유 | P2 | C (관련 A, B) | [scenario-s4.md](scenario-s4.md) |
| 4 | S3 Tool 이름 충돌 | P3 | A | [scenario-s3.md](scenario-s3.md) |
| 5 | S5 보안이 약한 연결 | P3 | A (관련 C) | [scenario-s5.md](scenario-s5.md) |

S2 공격 표면은 원문대로 A·C다. 공통 스키마 0.7 13.3절의 "PR #7 기준 B"는 정정 대상이다.

### A.2 식별자 규칙

| 식별자 | 형식 | 예 | 쓰는 곳 |
|---|---|---|---|
| 시나리오 | `S1`~`S5` | `S1` | `scenario_id` |
| 조건 | `S<n>-C<m>` | `S1-C2` | 탐지 결과 `rule_id`, 기대 결과 `condition_id` |
| 판정 기준 없음·미수집 | `S<n>-C0` | `S2-C0` | `unknown` 평가 |
| 적용 제외 | `S<n>-NA` | `S5-NA` | `not_applicable` 평가 |
| 테스트 | `S<n>-T<k>` (`T0` = P2 정상) | `S1-T3` | 카탈로그 `test_case_ids` |
| QA 케이스 | `QA-S<n>-01` 위험, `QA-S<n>-02` 정상 | `QA-S4-01` | QA 테스트케이스 |

- 시나리오 문서 v2.0의 `S5-01`~`S5-05`는 `S5-C1`~`S5-C5`로 바꾼다.
- 구현 작업 번호(`S1-01`, `S3-01` 등)는 작업 목록 번호이며 조건 ID와 다르다.
- 규칙 버전(`rule_version`)은 카탈로그 버전 `2.1`이다.

### A.3 평가 결과

탐지 결과는 공통 스키마 0.7 13절 DetectionReport를 따른다. 경고 목록만으로 정상과 미평가를 구분할 수 없으므로 평가를 함께 낸다.

| 결과 | 기준 | 경고 |
|---|---|---|
| `detected` | 근거·기준 정책으로 위험 조건 확인 | 생성 |
| `not_detected` | 근거·기준 정책으로 위험 조건이 없음을 확인 | 없음 |
| `unknown` | 입력·근거 부족 | 없음. 정상으로 집계하지 않음 |
| `not_applicable` | 대상 아님 | 없음 |
| `not_evaluated` | 이번 버전에서 평가하지 않음 | 없음 |
| `error` | 평가 실행 오류 | 없음 |

v2.1에서 `unknown`으로 확정한 경우: 승인 목록 없음(S1-C0), 다른 저장소의 같은 참조 이름(S4-C2), https인데 sslVerify 항목 없음(S5-C3), 한쪽 Tool 정의 미수집(S3-C3).

severity(영향·대응 우선순위)와 confidence(근거의 확실성)는 따로 정한다. 조건별 기본값은 카탈로그에 있고 규칙 정책으로 조정한다. 18절 Confidence 기준은 그대로다.

### A.4 함께 관리하는 문서

| 문서 | 내용 | 주 독자 |
|---|---|---|
| [README.md](README.md) | 목차, 버전, 상태, 우선순위 | 전체 |
| [scenario-catalog.json](scenario-catalog.json) | 공통 스키마 13절 ScenarioDefinition. 조건·기본 severity/confidence·테스트·QA 대응 | 탐지 모듈, 대시보드 |
| [expected-results.md](expected-results.md) | S1~S5 기대 경고·비경고·판단 불가. 테스트베드 형식(P2 대비 변경분 + `expected_alerts`)과 16.1절 변환 규칙 | QA, 테스트베드 |
| [policies/expected-tool-policy.json](policies/expected-tool-policy.json) | S2 기준 정책 | 탐지 모듈 |

S1 기준 정책은 테스트베드의 `testbed/ground-truth/approved-servers.json`을 쓴다.

20절 Ground Truth는 테스트베드 정답 파일(`testbed/ground-truth/<profile>.json`)이 원본이고, 위협 시나리오 쪽은 그중 `expected_alerts`·`expected_no_alert`·`expected_unknown`을 정한다.

### A.5 관계 이름 대응 (공통 스키마 0.7)

7절 관계 이름은 v2.0 기준이다. 탐지 결과와 대시보드에서는 공통 스키마 0.7 이름을 쓴다(12.3·12.8절).

| v2.0 | 스키마 0.7 | 비고 |
|---|---|---|
| `DECLARES` | `DECLARES` | Gateway/Node/Plugin → Server |
| `PROVIDES` | `ADVERTISES` | 서버 목록 근거가 있을 때만 |
| `CONNECTS_TO` | `MAY_SEND_TO`, `PAIRED_WITH` | 선언을 연결 성공으로 바꾸지 않음 |
| `EXPOSES` | `MAY_EXPOSE_TO` / `EXPOSES_TO` | 노출 목록 근거가 있으면 `EXPOSES_TO` |
| `USES`, `REFERENCES`, `AUTHENTICATES`, `APPLIES_TO` | permission_auth 자산의 `target_refs` | 의미·방향 합의 전 확정 간선을 만들지 않음 |
| `CONTAINS` | `CONTAINS` 후보 | Plugin → Skill |
| (없음) | `ASSOCIATED_WITH` | Skill/Plugin → Server/Tool |
