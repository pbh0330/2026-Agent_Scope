# Dashboard Design

# 1. 문서 개요

본 문서는 AI 에이전트 보안을 위한 자산 식별 및 가시화 기술 개발 프로젝트의 대시보드 설계 초안을 정의한다.
대시보드는 MCP 기반 AI 에이전트 환경에서 수집된 자산 정보를 시각화하고, 자산 간 관계와 자산 구성의 변화를 확인할 수 있도록 설계한다.

프로젝트의 최종 산출물은 다음 두 기능을 하나의 파이프라인으로 연결하는 것을 목표로 한다.
- MCP 자산 인벤토리 스캐너
- 자산 그래프 기반 대시보드

현재 대시보드 설계는 정적 자산 식별 결과의 가시화를 중심으로 하며, Token/Cost 정보는 별도 수집 모듈과의 연계를 고려한다.

---

# 2. 대시보드 설계 목표

대시보드는 다음 질문에 답할 수 있도록 설계한다.

1. 현재 어떤 자산이 존재하는가?
2. 자산들은 서로 어떻게 연결되어 있는가?
3. 어떤 자산이 Agent 환경에 노출되어 있는가?
4. 자산 구성에 어떤 변화가 발생했는가?
5. 어떤 권한 및 인증 정보가 연결되어 있는가?
6. Skill·Plugin 등 공급망 관련 자산의 상태는 어떠한가?
7. Token 사용량과 비용은 어떻게 발생하고 있는가?
8. 특정 자산의 상세 정보와 식별 근거는 무엇인가?

---

# 3. B-01. 대시보드가 답해야 할 질문

## Q1. 현재 어떤 자산이 존재하는가?
현재 AI Agent 환경에서 확인된 자산을 유형별로 확인할 수 있어야 한다.
현재 스캐너의 수집 대상은 다음 7종이다.

| 자산 유형 |
|---|
| MCP Server 
| MCP Tool 
| Resource / Template / Prompt 
| Skill 
| Plugin 
| Permission / Authentication 
| Node 


## Q2. 자산들은 서로 어떻게 연결되어 있는가?
AI Agent와 MCP 구성요소 사이의 관계를 확인할 수 있어야 한다.

예시:
Agent
  │
  ▼
MCP Host
  │
  ▼
MCP Client
  │
  ▼
MCP Server
  ├── Tool
  ├── Resource
  └── Prompt
  

## Q3. 어떤 자산이 Agent 환경에 노출되어 있는가?
현재 구성과 정책을 기준으로 Agent 또는 Host에 어떤 자산이 노출되는지 확인할 수 있어야 한다.
공격 표면 정의에서는 자산 상태를 다음과 같이 구분한다.

DECLARED
    ↓
DISCOVERED
    ↓
EXPOSED
    ↓
POTENTIALLY_CALLABLE
    ↓
CALLABLE
    ↓
USED

현재 프로젝트의 정적 분석 범위에서는 주로 선언·발견 및 정적으로 확인 가능한 노출 상태를 대상으로 한다.
실제 호출 및 사용 여부는 런타임 검증 범위로 구분한다.


## Q4. 자산 구성에 어떤 변화가 발생했는가?
이전 Snapshot과 현재 Snapshot을 비교하여 자산의 추가·삭제·변경 여부를 확인할 수 있어야 한다.

예시:
[ADDED]
Skill: example-skill

[REMOVED]
Plugin: example-plugin

[MODIFIED]
MCP Server
└── Tool 목록 변경

## Q5. 어떤 권한 및 인증 정보가 연결되어 있는가?
자산에 적용된 권한 및 인증 관련 설정을 확인할 수 있어야 한다.
확인 대상의 예시는 다음과 같다.

OAuth
Header
Environment Variable
API Key
mTLS
파일시스템 접근 권한
네트워크 접근 권한
프로세스 권한
데이터 접근 권한
Tool Filter
사용자 승인 정책
Node 차단 정책

실제 Secret, Token, API Key 등의 민감한 값 자체는 대시보드에 표시하지 않는다.


## Q6. Skill·Plugin 공급망 관련 자산의 상태는 어떠한가?
Skill 및 Plugin과 관련된 공급망 정보를 확인할 수 있어야 한다.
주요 확인 대상은 다음과 같다.

이름
공급 출처
버전
Commit / 배포 식별자
Hash
Manifest
의존성
활성 상태
설치 위치
변경 여부


## Q7. Token 사용량과 비용은 어떻게 발생하고 있는가?
Token/Cost 수집 모듈에서 제공되는 데이터를 대시보드에서 확인할 수 있도록 한다.

예상 데이터:
Agent
Provider
Model
Input Token
Output Token
Total Token
Cost
Timestamp

실제 제공 데이터와 MCP Tool 단위의 비용 귀속 가능 여부는 Token/Cost 모듈 확인 후 확정한다.


## Q8. 특정 자산의 상세 정보와 근거는 무엇인가?
특정 자산을 선택했을 때 해당 자산의 상세 정보와 자산 간 관계, 수집 근거를 확인할 수 있어야 한다.


# 4. B-02. 필요한 데이터 목록

대시보드에 필요한 데이터는 다음과 같이 구분한다.

## 4.1 Asset Data
Asset ID	자산 고유 식별자
Asset Type	자산 유형
Name	자산 이름
Description	자산 설명
Source	자산이 확인된 출처
Status	자산 상태
Version	버전 정보
First Seen	최초 확인 시점
Last Seen	최근 확인 시점
Hash	변경 및 무결성 확인 정보
Evidence	자산 식별 근거

## 4.2 Relationship Data
자산 그래프를 구성하기 위해 자산 간 관계 정보를 사용한다.

Source Asset	관계의 출발 자산
Relation	관계 유형
Target Asset	관계의 대상 자산
Evidence	관계를 판단한 근거
Confidence	관계에 대한 신뢰도
Observed At	관계가 확인된 시점

주요 관계의 예시는 다음과 같다.
HOSTS_CLIENT
CONNECTS_TO
ADVERTISES
EXPOSES_TO
MAY_CALL
CAN_CALL
REQUESTS_INPUT_FROM
INSTALLS
DEPENDS_ON
REGISTERS
USES_CREDENTIAL
GRANTS_ACCESS_TO
ACCESSES
SENDS_TO
CAN_CHAIN_TO

관계는 단순한 이름 일치만으로 임의 생성하지 않고, 확인 가능한 근거를 기준으로 구성한다.

## 4.3 Snapshot / Diff Data
자산 구성의 변경 사항을 확인하기 위한 데이터이다.

Snapshot ID	Snapshot 식별자
Previous Snapshot	이전 비교 대상
Current Snapshot	현재 Snapshot
Change Type	Added / Removed / Modified
Asset ID	변경된 자산
Changed Field	변경된 필드
Changed At	변경 시점

## 4.4 Permission / Authentication Data
권한 및 인증 관련 정보를 확인하기 위한 데이터이다.

Permission/Auth ID	권한 또는 인증 식별자
Policy	적용 정책
Target	정책 적용 대상
Credential Reference	자격증명 참조 정보
Access Scope	접근 범위
Status	상태

실제 Credential 값이나 Secret은 저장하거나 표시하지 않는다.

## 4.5 Skill / Plugin Data
ID	Skill/Plugin 식별자
Name	이름
Provider	공급자
Version	버전
Source	설치 출처
Commit / Release	배포 식별자
Hash	무결성 확인 정보
Manifest	Manifest 정보
Dependency	의존 관계
Active	활성 여부
Install Path	설치 위치
Update Info	업데이트 정보

## 4.6 Token / Cost Data
Token/Cost 수집 모듈과 연계하기 위해 다음 데이터를 고려한다.

Timestamp	수집 시점
Agent	Agent 식별 정보
Provider	모델 제공자
Model	사용 모델
Input Tokens	입력 토큰
Output Tokens	출력 토큰
Total Tokens	총 토큰
Cost	비용
Attribution Status	실제값 / 추정값 구분

실제 제공 가능한 필드는 Token/Cost 모듈 확인 후 확정한다.

# 5. B-05. 대시보드 정보 구조

대시보드는 다음과 같은 화면 구조를 기본안으로 한다.
Dashboard
│
├── Overview
├── Asset Graph
├── Security / Change
├── Usage / Cost
└── Asset Detail

## 5.1 Overview
AI Agent 환경의 전체적인 자산 상태를 한눈에 확인한다.

주요 정보
전체 자산 수
자산 유형별 수
최근 변경 사항
주요 상태 정보
Token / Cost 요약
마지막 수집 시점

## 5.2 Asset Graph
자산과 자산 간 관계를 그래프로 확인한다.

주요 정보
Agent
MCP Host
MCP Client
MCP Server
Tool
Resource
Prompt
Skill / Plugin
Permission / Authentication
Node
Backend Resource
External System
자산 간 관계

## 5.3 Security / Change
자산 구성의 변화와 보안 관련 정보를 확인한다.

주요 정보
신규 자산
삭제 자산
변경 자산
Permission / Authentication 정보
Skill / Plugin 변경
Snapshot Diff
변경 시점
관련 Evidence

## 5.4 Usage / Cost
AI Agent의 Token 사용량과 비용 정보를 확인한다.

주요 정보
Token 사용량
Input / Output Token
Model
Provider
Agent
Cost
시간별 사용량

## 5.5 Asset Detail
개별 자산의 상세 정보와 관계를 확인한다.

주요 정보
Asset ID
Asset Type
Name
Description
Status
Source
Version
First Seen
Last Seen
Relations
Evidence
관련 Permission / Authentication
변경 이력


# 6. B-06. Overview 화면 와이어프레임
Overview 화면은 전체 자산 현황, 자산 유형별 분포, 최근 변경 사항, Token/Cost 정보를 한 화면에서 확인할 수 있도록 구성한다.

┌──────────────────────────────────────────────────────────────┐
│ AI Agent Security Dashboard                 Last Scan: --    │
├──────────────┬───────────────────────────────────────────────┤
│              │                                               │
│  Overview    │  Security Overview                            │
│              │                                               │
│  Asset Graph │  ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│              │  │  Assets  │ │  Active  │ │ Changes  │       │
│  Security    │  │    --    │ │    --    │ │    --    │       │
│  / Change    │  └──────────┘ └──────────┘ └──────────┘       │
│              │                                               │
│  Usage/Cost  │  Asset Distribution                           │
│              │  ┌─────────────────────────────────────────┐  │
│  Asset Detail│  │ MCP Server                    --        │  │
│              │  │ MCP Tool                      --        │  │
│              │  │ Resource / Template / Prompt  --        │  │
│              │  │ Skill                         --        │  │
│              │  │ Plugin                        --        │  │
│              │  │ Permission / Authentication   --        │  │
│              │  │ Node                          --        │  │
│              │  └─────────────────────────────────────────┘  │
│              │                                               │
│              │  Recent Changes                               │
│              │  ┌─────────────────────────────────────────┐  │
│              │  │ Added      --                           │  │
│              │  │ Removed    --                           │  │
│              │  │ Modified   --                           │  │
│              │  └─────────────────────────────────────────┘  │
│              │                                               │
│              │  Usage / Cost                                 │
│              │  ┌─────────────────────┐ ┌────────────────┐   │
│              │  │ Token Usage         │ │ Cost           │   │
│              │  │ --                  │ │ --             │   │
│              │  └─────────────────────┘ └────────────────┘   │
│              │                                               │
└──────────────┴───────────────────────────────────────────────┘

# 7. Overview 화면 구성 요소
영역	표시 정보	데이터 출처
Summary	전체 자산 / 활성 자산 / 변경 수	Asset / Diff
Asset Distribution	7종 자산별 수	Scanner
Recent Changes	추가 / 삭제 / 변경	Snapshot / Diff



Usage / Cost	Token / Cost	Token/Cost Module
Last Scan	마지막 수집 시점	Scanner
