# AI Agent Threat Scenario Specification

> AI 에이전트 위협 시나리오 작성 및 검증 규격

**문서 버전:** v1.0
**작성 기준:** 2026-10-01
**프로젝트:** AI 에이전트 보안을 위한 자산 식별 및 가시화 도구 개발
**적용 범위:** MCP/OpenClaw 기반 AI 에이전트 환경의 정적 보안 분석

---

## 1. 문서 목적

본 문서는 AI 에이전트 보안을 위한 자산 식별 및 가시화 도구 개발 과정에서 사용하는 **위협 시나리오의 작성, 분석, 검증 및 대시보드 연계 기준**을 정의한다.

위협 시나리오는 단순한 공격 사례의 나열이 아니라 다음의 흐름을 기준으로 작성한다.

```text
공격표면
    ↓
자산 및 관계
    ↓
정상 상태
    ↓
위험 상태
    ↓
위협 시나리오
    ↓
정적 탐지 조건
    ↓
검증 방법
    ↓
보안 경고
    ↓
대시보드 표현
```

본 규격을 통해 각 시나리오가 동일한 구조와 기준으로 작성되도록 하며, 이후 개발되는 **자산 스캐너 및 대시보드와 직접 연결될 수 있는 형태**로 관리한다.

---

# 2. 적용 범위

## 2.1 분석 대상

본 문서에서 정의하는 위협 시나리오는 다음 환경을 대상으로 한다.

- AI Agent
- MCP Gateway
- MCP Node
- MCP Server
- Tool
- Resource
- Prompt
- Skill
- Plugin
- Server 연결 정보
- 인증·자격증명 관련 설정
- 서버 간 통신 관계

현재 구현 단계에서는 **정적 분석을 우선 적용**한다.

따라서 실제 런타임 호출 행위나 실시간 사용자 행동 자체를 탐지 대상으로 정의하지 않는다.

---

## 2.2 공격표면 분류

위협 시나리오는 다음 세 가지 공격표면을 기준으로 분류한다.

| 코드 | 공격표면             | 설명                                     |
| -- | ---------------- | -------------------------------------- |
| A  | 통신 경계            | Gateway, Node, MCP Server 간 연결 및 통신 경계 |
| B  | Skill/Plugin 공급망 | Tool, Skill, Plugin 등 기능 공급 및 호출 경계    |
| C  | 권한·자격증명          | 인증정보, 권한 범위, Credential 공유 및 접근 범위     |

---

# 3. 위협 시나리오 ID 규칙

모든 위협 시나리오는 고유 ID를 사용한다.

## 3.1 기본 ID

```text
S1
S2
S3
...
```

예:

```text
S1: 비인가 서버 등록 및 노출
S2: 악성 또는 과도한 권한의 도구 광고
```

---

## 3.2 세부 검증 항목

필요한 경우 다음과 같이 세분화한다.

```text
S1-C1
S1-C2
S1-T1
S1-R1
```

| ID 형식 | 의미                  |
| ----- | ------------------- |
| S1    | 위협 시나리오             |
| S1-C1 | Detection Condition |
| S1-T1 | Test Case           |
| S1-R1 | Result              |

예:

```text
S1
 ├── S1-C1
 ├── S1-T1
 └── S1-R1
```

---

# 4. 위협 시나리오 작성 표준 구조

모든 시나리오는 다음 순서로 작성한다.

```text
1. 기본 정보
2. 공격표면
3. 관련 자산
4. 정상 상태
5. 위험 상태
6. 위협 시나리오
7. 정적 탐지 조건
8. 탐지 근거
9. 검증 방법
10. 평가 지표
11. 대시보드 표현
```

---

# 5. 기본 정보 작성 규칙

각 시나리오의 첫 부분에는 다음 정보를 반드시 포함한다.

| 항목             | 작성 내용                          |
| -------------- | ------------------------------ |
| Scenario ID    | S1, S2 등                       |
| Scenario Name  | 위협 내용을 간결하게 표현                 |
| Attack Surface | A/B/C                          |
| Risk Category  | 해당 위험 유형                       |
| Priority       | 시나리오 우선순위                      |
| Status         | Draft / Implemented / Verified |

예:

```yaml
scenario_id: S1
scenario_name: 비인가 서버 등록 및 노출
attack_surface: A
risk_category: Unauthorized Server Exposure
priority: High
status: Draft
```

---

# 6. 관련 자산 정의

각 위협 시나리오는 반드시 관련 자산과 연결한다.

현재 정적 분석에서 우선적으로 사용하는 자산 유형은 다음과 같다.

| Asset Type | 설명                      |
| ---------- | ----------------------- |
| Gateway    | AI Agent와 MCP 환경의 연결 관문 |
| Node       | AI Agent 실행 및 연결 환경     |
| MCP Server | MCP 기능을 제공하는 서버         |
| Tool       | Agent가 호출할 수 있는 기능      |
| Resource   | Agent가 접근할 수 있는 데이터 자원  |
| Prompt     | 사전에 정의된 Prompt          |
| Skill      | Agent 기능을 확장하는 Skill    |
| Plugin     | 외부 기능 또는 확장 기능          |

시나리오 작성 시 다음과 같이 연결 관계를 기록한다.

```text
Scenario
 ├── Asset
 ├── Relation
 └── Evidence
```

---

# 7. 정상 상태 정의

위협을 판단하기 위해서는 먼저 정상 상태를 정의해야 한다.

정상 상태에는 다음 내용을 포함한다.

- 정상적인 구성
- 허용된 서버
- 허용된 Tool
- 정상적인 Credential 범위
- 정상적인 통신 방식
- 허용된 접근 범위

예:

```text
정상 상태

Gateway에 등록된 MCP Server가 사전에 승인된 서버 목록에 포함되어 있으며,
해당 서버의 연결 정보와 설정이 정의된 정책 범위 내에 존재한다.
```

---

# 8. 위험 상태 정의

정상 상태와 비교하여 보안상 문제가 발생하는 상태를 정의한다.

위험 상태는 가능한 한 **관찰 가능한 구성 정보**를 기준으로 작성한다.

예:

```text
위험 상태

Gateway에 등록된 MCP Server가 승인된 서버 목록에 존재하지 않으며,
Agent가 해당 서버를 사용할 수 있는 연결 관계가 구성되어 있다.
```

---

# 9. 위협 시나리오 작성 규칙

위협 시나리오는 다음 구조로 작성한다.

```text
[공격자 또는 위험 요인]
        ↓
[공격 대상 자산]
        ↓
[악용되는 관계 또는 설정]
        ↓
[발생 가능한 보안 영향]
```

시나리오에는 다음 내용을 포함한다.

1. 어떤 자산이 대상인지
2. 어떤 설정 또는 관계가 문제인지
3. 어떤 조건에서 위험이 발생하는지
4. 정적 분석으로 무엇을 확인할 수 있는지
5. 탐지 결과가 어떤 보안 경고로 표현되는지

---

# 10. 정적 탐지 조건

현재 프로젝트는 정적 분석을 우선하므로 시나리오마다 **정적 탐지 조건**을 명확하게 정의한다.

탐지 조건은 가능한 한 Boolean 또는 규칙 형태로 표현한다.

예:

```text
IF
  MCP Server ∉ Approved Server List
AND
  Gateway → MCP Server 관계 존재
THEN
  S1 Warning 발생
```

또는:

```yaml
condition:
  - server_registered: true
  - server_approved: false
result:
  alert: true
```

---

# 11. 탐지 근거(Evidence)

탐지 결과에는 반드시 근거를 연결한다.

근거에는 다음 정보를 포함할 수 있다.

- 설정 파일
- 서버 등록 정보
- Tool 목록
- Skill 목록
- Plugin 목록
- 연결 정보
- Credential reference
- 서버 간 관계
- 파일 경로
- 설정 항목
- 스캐너가 확인한 메타데이터

단, 실제 비밀번호·API Key·Token 등의 민감정보는 수집하거나 표시하지 않는다.

예:

```yaml
evidence:
  source: config
  type: server_registration
  reference: server_config.json
  field: server_list
```

---

# 12. Confidence 규칙

정적 분석 결과는 탐지 근거의 명확성에 따라 Confidence를 기록할 수 있다.

| Confidence | 의미                      |
| ---------- | ----------------------- |
| High       | 설정 또는 관계가 직접 확인됨        |
| Medium     | 여러 정보의 조합으로 위험 가능성이 확인됨 |
| Low        | 제한적인 정보로 위험 가능성을 추정함    |

예:

```yaml
confidence: High
```

Confidence는 실제 공격 성공 가능성을 의미하지 않는다.

**스캐너가 확보한 근거의 명확성**을 표현하는 값으로 사용한다.

---

# 13. 자산 상태와 시나리오 연결

자산 상태는 다음 순서로 관리한다.

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

현재 정적 분석 단계에서는 다음 상태를 중심으로 판단한다.

```text
선언
발견
노출
```

`잠재 호출 가능`은 정적 구성 및 관계 정보를 기반으로 추론할 수 있으며, 이 경우 Evidence와 Confidence를 함께 기록한다.

실제 `호출됨`, `사용됨` 여부는 런타임 분석 영역으로 분리한다.

---

# 14. 검증 방법 작성 규칙

각 시나리오에는 최소 하나의 검증 방법을 정의한다.

검증 방법은 다음 구조를 따른다.

```text
1. 정상 상태 구성
2. 스냅샷 생성
3. 위협 조건 적용
4. 스캐너 실행
5. 탐지 결과 확인
6. 정상/위험 상태 비교
7. 결과 기록
```

예:

```text
SNAP-2 정상 환경
        ↓
위협 조건 적용
        ↓
SNAP-S1 생성
        ↓
Asset Scanner 실행
        ↓
S1 Detection 확인
        ↓
정상 상태와 비교
```

---

# 15. 테스트 케이스 작성 규칙

테스트 케이스는 다음 형식으로 작성한다.

```markdown
### S1-T1

- 목적:
- 사전 조건:
- 정상 상태:
- 위협 조건:
- 실행 방법:
- 기대 결과:
- 실제 결과:
- 판정:
```

판정 값은 다음과 같이 관리한다.

```text
PASS
FAIL
PARTIAL
```

---

# 16. 평가 지표

각 시나리오는 가능한 범위에서 정량적인 검증 지표를 사용한다.

예:

| 지표               | 설명              |
| ---------------- | --------------- |
| Detection        | 위협 조건을 탐지했는가    |
| Evidence         | 탐지 근거가 연결되었는가   |
| Asset Linkage    | 관련 자산이 연결되었는가   |
| Relation Linkage | 관련 관계가 연결되었는가   |
| Alert            | 대시보드 경고로 전달되었는가 |

기본적인 시나리오 검증 목표는 다음과 같다.

```text
위협 조건 발생
→ 탐지
→ 근거 연결
→ 자산 연결
→ 보안 경고 생성
```

---

# 17. 대시보드 연계 규칙

위협 시나리오의 탐지 결과는 대시보드에서 확인할 수 있어야 한다.

최소 다음 정보가 연결되어야 한다.

```text
Scenario
 ├── Alert
 ├── Asset
 ├── Relation
 └── Evidence
```

예:

```yaml
alert:
  scenario_id: S1
  severity: High
  asset_ids:
    - server-01
  relation_ids:
    - gateway-server-01
  evidence:
    - server_registration
```

---

# 18. 현재 위협 시나리오 목록

현재 프로젝트에서 우선 작성하는 시나리오는 다음과 같다.

| ID | 시나리오                     | 공격표면 | 우선순위 |
| -- | ------------------------ | ---- | ---- |
| S1 | 비인가 서버 등록 및 노출           | A    | 1    |
| S2 | 악성 또는 과도한 권한의 도구 광고      | B    | 2    |
| S3 | 도구 이름 충돌을 이용한 호출 대상 위장   | B    | 3    |
| S4 | 과도한 자격증명 공유로 인한 피해 범위 확대 | C    | 4    |
| S5 | 보안이 약한 연결을 통한 서버 위장 가능성  | A    | 5    |

---

# 19. S1 — 비인가 서버 등록 및 노출

## 19.1 기본 정보

```yaml
scenario_id: S1
scenario_name: 비인가 서버 등록 및 노출
attack_surface: A
priority: 1
```

## 19.2 정상 상태

Gateway에 등록된 MCP Server가 사전에 승인된 서버 목록에 포함되어 있다.

## 19.3 위험 상태

승인되지 않은 MCP Server가 Gateway에 등록되어 있으며 Agent가 해당 서버와 연결 가능한 상태이다.

## 19.4 정적 탐지 조건

```text
IF
  Server Registered = TRUE
AND
  Server Approved = FALSE
THEN
  S1 = DETECTED
```

## 19.5 기대 경고

```text
비인가 MCP Server가 등록되어 있습니다.
```

## 19.6 검증

- 승인 서버 목록을 기준으로 정상 환경 구성
- 승인되지 않은 서버 등록
- 스캐너 실행
- 서버 등록 상태 확인
- 승인 목록과 비교
- S1 탐지 여부 확인

---

# 20. S2 — 악성 또는 과도한 권한의 도구 광고

## 20.1 기본 정보

```yaml
scenario_id: S2
scenario_name: 악성 또는 과도한 권한의 도구 광고
attack_surface: B
priority: 2
```

## 20.2 정상 상태

Tool이 허용된 범위의 기능과 접근 경로를 가지고 있으며, Agent가 사용할 수 있는 Tool 목록이 정책 범위 내에 존재한다.

## 20.3 위험 상태

Tool이 필요 이상의 접근 범위 또는 위험한 기능을 광고하고 있으며 Agent가 해당 Tool을 사용할 수 있는 구조이다.

## 20.4 정적 탐지 조건

```text
IF
  Tool Advertised = TRUE
AND
  Tool Permission Scope > Expected Scope
THEN
  S2 = DETECTED
```

## 20.5 검증

- 정상 Tool 목록 구성
- 위험한 Tool 추가
- Tool 권한 및 접근 범위 설정
- 스캐너 실행
- Tool 정보 및 관계 확인
- S2 탐지 여부 확인

---

# 21. S3 — 도구 이름 충돌을 이용한 호출 대상 위장

## 21.1 기본 정보

```yaml
scenario_id: S3
scenario_name: 도구 이름 충돌을 이용한 호출 대상 위장
attack_surface: B
priority: 3
```

## 21.2 정상 상태

서로 다른 MCP Server에 동일한 Tool 이름이 존재하지 않는다.

## 21.3 위험 상태

서로 다른 서버에서 동일하거나 혼동 가능한 Tool 이름이 등록되어 호출 대상 식별에 혼란을 발생시킬 수 있다.

## 21.4 정적 탐지 조건

```text
IF
  Tool Name A == Tool Name B
AND
  Server A != Server B
THEN
  S3 = DETECTED
```

## 21.5 검증

- 서버별 Tool 목록 생성
- 중복되지 않은 정상 상태 확인
- 동일 Tool 이름 등록
- 스캐너 실행
- Tool 이름 중복 여부 확인
- S3 탐지 여부 확인

---

# 22. S4 — 과도한 자격증명 공유로 인한 피해 범위 확대

## 22.1 기본 정보

```yaml
scenario_id: S4
scenario_name: 과도한 자격증명 공유로 인한 피해 범위 확대
attack_surface: C
priority: 4
```

## 22.2 정상 상태

각 MCP Server 또는 서비스에 필요한 자격증명을 분리하여 사용한다.

## 22.3 위험 상태

하나의 자격증명이 여러 서버 또는 서비스에 공유되어 하나의 자격증명 노출이 여러 자산에 영향을 미칠 수 있다.

## 22.4 정적 탐지 조건

```text
IF
  Credential A
    → Server A
    → Server B
AND
  Credential Scope is Shared
THEN
  S4 = DETECTED
```

실제 Credential 값은 수집하지 않고 다음 정보만 확인한다.

```text
Credential 존재 여부
Credential 유형
Credential Reference
Credential Scope
```

## 22.5 검증

- 서버별 개별 Credential 구성
- 정상 상태 확인
- 동일 Credential Reference를 여러 서버에 연결
- 스캐너 실행
- Credential 관계 확인
- S4 탐지 여부 확인

---

# 23. S5 — 보안이 약한 연결을 통한 서버 위장 가능성

## 23.1 기본 정보

```yaml
scenario_id: S5
scenario_name: 보안이 약한 연결을 통한 서버 위장 가능성
attack_surface: A
priority: 5
```

## 23.2 정상 상태

서버 연결 과정에서 TLS 및 인증서 검증이 적용된다.

## 23.3 위험 상태

암호화되지 않았거나 서버 인증 검증이 충분하지 않은 연결 설정이 존재한다.

## 23.4 정적 탐지 조건

```text
IF
  Server Connection Exists
AND
  TLS Validation = FALSE
THEN
  S5 = DETECTED
```

## 23.5 검증

- TLS 및 인증서 검증이 적용된 정상 서버 구성
- 보안 검증 조건 변경
- 스캐너 실행
- 연결 설정 확인
- S5 탐지 여부 확인

---

# 24. 시나리오 작성 작업 순서

각 시나리오의 세부 작업은 다음 순서로 수행한다.

```text
Step 1. 공격표면 확인
        ↓
Step 2. 관련 자산 정의
        ↓
Step 3. 정상 상태 정의
        ↓
Step 4. 위험 상태 정의
        ↓
Step 5. 정적 탐지 조건 작성
        ↓
Step 6. 테스트 케이스 작성
        ↓
Step 7. 스캐너 검증
        ↓
Step 8. 대시보드 연계 정보 정의
        ↓
Step 9. 결과 기록
```

---

# 25. 소과제 단위 작업 목록

## S-01. 시나리오 기본 구조 확정

### 작업

- Scenario ID 규칙 확정
- 공격표면 분류 연결
- 시나리오 작성 템플릿 확정

### 산출물

```text
Threat Scenario Template
```

---

## S-02. S1 시나리오 작성

### 작업

- 정상 상태 정의
- 위험 상태 정의
- 탐지 조건 정의
- 테스트 케이스 작성

### 산출물

```text
S1 Scenario
S1 Detection Rule
S1 Test Case
```

---

## S-03. S2 시나리오 작성

### 작업

- Tool 권한 범위 정의
- 위험 Tool 조건 정의
- 탐지 조건 작성
- 테스트 케이스 작성

### 산출물

```text
S2 Scenario
S2 Detection Rule
S2 Test Case
```

---

## S-04. S3 시나리오 작성

### 작업

- Tool 이름 식별 기준 정의
- 서버 간 Tool 관계 정의
- 중복 탐지 조건 작성
- 테스트 케이스 작성

### 산출물

```text
S3 Scenario
S3 Detection Rule
S3 Test Case
```

---

## S-05. S4 시나리오 작성

### 작업

- Credential Reference 기준 정의
- Credential Scope 정의
- 공유 관계 탐지 조건 작성
- 테스트 케이스 작성

### 산출물

```text
S4 Scenario
S4 Detection Rule
S4 Test Case
```

---

## S-06. S5 시나리오 작성

### 작업

- 연결 보안 설정 기준 정의
- TLS 및 인증서 검증 조건 정의
- 탐지 조건 작성
- 테스트 케이스 작성

### 산출물

```text
S5 Scenario
S5 Detection Rule
S5 Test Case
```

---

## S-07. 시나리오 통합 검증

### 작업

- S1\~S5 탐지 조건 검토
- 중복 조건 검토
- Asset Linkage 검토
- Evidence Linkage 검토
- Dashboard Alert 구조 검토

### 산출물

```text
Threat Scenario Verification Report
```

---

# 26. 완료 기준

위협 시나리오는 다음 조건을 모두 만족할 경우 완료된 것으로 판단한다.

- [ ] Scenario ID가 정의되어 있다.
- [ ] 공격표면이 지정되어 있다.
- [ ] 관련 자산이 정의되어 있다.
- [ ] 정상 상태가 정의되어 있다.
- [ ] 위험 상태가 정의되어 있다.
- [ ] 정적 탐지 조건이 정의되어 있다.
- [ ] 탐지 근거가 정의되어 있다.
- [ ] 테스트 케이스가 작성되어 있다.
- [ ] 실제 테스트베드에서 검증할 수 있다.
- [ ] 탐지 결과를 Asset과 연결할 수 있다.
- [ ] 탐지 결과를 Dashboard Alert와 연결할 수 있다.

---

# 27. GitHub 문서 구조

권장 디렉터리 구조는 다음과 같다.

```text
docs/
└── threat-scenarios/
    ├── threat-scenario-spec.md
    ├── S1-unauthorized-server.md
    ├── S2-tool-permission.md
    ├── S3-tool-name-collision.md
    ├── S4-credential-sharing.md
    └── S5-weak-connection.md
```

본 문서는 전체 시나리오 작성 규격을 정의하는 기준 문서이며, 각 시나리오의 상세 내용은 개별 Markdown 문서로 분리할 수 있다.

---

# 28. 문서 변경 이력

| 버전   | 날짜         | 변경 내용                    |
| ---- | ---------- | ------------------------ |
| v1.0 | 2026-10-01 | 위협 시나리오 작성 및 검증 규격 초안 작성 |
