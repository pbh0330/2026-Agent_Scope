# AI 에이전트 MCP 공격 표면 정의 v2.0

> **문서 상태: 2026.09.22 회의 검토본**
>
> 본 문서는 MCP 통신 경계를 핵심 공격 표면으로 정의하고, Skill·Plugin 공급망과 권한·자격증명을 자산 분석 필드로 반영한다. 전체 공격 표면 개념 모델은 보안 관계를 설명하기 위한 논리 모델이며, 1차 스캐너는 회의에서 합의한 7종의 정적 자산만 직접 수집한다. 실제 호출과 데이터 흐름은 후속 런타임 분석 범위로 구분한다.
>
> 문서 범위: MCP 기반 AI 에이전트의 공격 표면 정의, 분석 경계, 정적 자산·관계 및 최소 수집 기준을 다룬다. 런타임 관찰은 후속 단계로 구분하며, 구체적인 공격 페이로드와 침투 테스트 절차는 제외한다.
>
> 기준 규격: Model Context Protocol `2026-07-28`
>
> 검증 기준일: 2026-09-22

## 1. 문서 목적

본 프로젝트는 AI 에이전트가 MCP(Model Context Protocol)를 통해 외부 기능과 데이터에 연결될 때 형성되는 공격 표면을 식별하고 가시화하는 것을 목표로 한다.

이 문서는 다음 사항을 명확히 한다.

1. 프로젝트에서 말하는 **MCP 공격 표면의 의미와 판정 기준**
2. 핵심 공격 표면인 **MCP 통신 경계와 신뢰 경계**
3. 공격 표면을 구성하는 **자산, 데이터 흐름 및 관계**
4. **공식 규격·제품 정보**와 **프로젝트 확장 정보**의 구분
5. 현재 수행할 **정적 자산 분석**과 추후 수행할 **런타임 분석**의 구분

---

## 2. MCP 공격 표면 정의

> **본 프로젝트에서 MCP 공격 표면은 MCP Host·Client·Server 사이의 통신 경계를 중심으로, 비신뢰 주체가 입력·변조하거나 악용할 수 있고 현재 구성과 정책상 Agent가 도달 가능한 JSON-RPC 인터페이스, MCP 기능 및 데이터 흐름의 집합이다.**

본 프로젝트의 핵심 공격 표면은 **A: MCP 통신 경계**이다. **B: Skill·Plugin 공급망**과 **C: 권한·자격증명**은 별도의 공격 표면으로 병렬 분석하지 않고, MCP Server·Tool·Skill·Plugin 등 자산의 출처·신뢰도·권한·영향 범위를 설명하는 **자산 분석 축과 필드**로 흡수한다.

공격 표면은 단순 자산 목록과 구분한다. 설정이나 카탈로그에서 발견된 모든 자산이 곧 활성 공격 표면인 것은 아니다. 다음 조건을 기준으로 공격 표면 여부와 상태를 판단한다.

| 판정 요소 | 확인 질문 |
|---|---|
| 신뢰 경계 | 데이터 또는 명령이 서로 다른 신뢰 수준의 구성요소 사이를 이동하는가? |
| 통제 가능성 | 외부 서버, 공급자, 사용자 입력 등 비신뢰 주체가 내용을 입력·변경할 수 있는가? |
| 도달 가능성 | 현재 설정·필터·정책·승인 조건에서 Agent 또는 MCP 구성요소가 해당 자산에 도달할 수 있는가? |
| 보안 영향 | 악용 시 기밀성·무결성·가용성, 코드 실행, 권한 또는 사용자 의사결정에 영향을 줄 수 있는가? |

전체 분석 체계에서는 다음 상태를 구분한다. 현재 정적 자산 단계는 `DECLARED`, `DISCOVERED`와 설정으로 판정 가능한 `EXPOSED`를 우선 다루며, 실제 호출을 확인해야 하는 `CALLABLE`과 `USED`는 후속 런타임 단계에서 검증한다.

```text
DECLARED    설정에 선언됨
    ↓
DISCOVERED  설치 파일 또는 런타임 응답에서 발견됨
    ↓
EXPOSED     특정 Agent/Host에 표시되거나 연결됨
    ↓
POTENTIALLY_CALLABLE  정적 조건상 호출 가능성이 있음
    ↓
CALLABLE    런타임 검증 결과 실제 호출 가능함
    ↓
USED        실행 로그에서 실제 사용이 관찰됨
```

`EXPOSED`와 `CALLABLE`은 같은 의미가 아니다. Agent에게 Tool이 표시되더라도 인증 실패, 사용자 승인, 정책 또는 sandbox 제한 때문에 실제 호출할 수 없을 수 있다. 정적 단계에서 호출 조건이 충족될 것으로 추정되는 상태는 `POTENTIALLY_CALLABLE`로 기록하고, 런타임에서 검증된 경우에만 `CALLABLE`로 확정한다.

---

## 3. 공격 표면과 자산 분석 축

본 프로젝트는 A를 핵심 공격 표면으로 분석하고, B와 C는 A에 포함된 자산을 설명하는 보조 분석 축으로 적용한다.

| ID | 분류 | 프로젝트 내 역할 | 핵심 질문 |
|---|---|---|---|
| A | **핵심 공격 표면** | MCP Client와 Server 사이의 JSON-RPC 메시지, 도구 호출 요청·응답 및 양방향 capability가 통과하는 경계 | 누가 어떤 서버와 통신하며, 어떤 입력·기능·데이터가 경계를 통과하는가? |
| B | **자산 축: 공급망** | Skill·Plugin 파일, manifest·설정, 설치·업데이트 출처 및 서드파티 MCP Server에 관한 자산 필드 | 해당 자산은 어디에서 왔으며 무결성과 변경 상태를 신뢰할 수 있는가? |
| C | **자산 축: 권한·자격증명** | OAuth 토큰, Header·환경변수, 인증서 및 파일시스템·네트워크·프로세스 권한에 관한 자산 필드 | 해당 자산이 어떤 권한을 사용하며 침해 시 영향 범위는 어디까지인가? |

A와 B·C의 관계는 다음과 같다.

```text
                    [A: 핵심 공격 표면]
Agent / MCP Host → MCP Client ⇄ MCP Server
                                    │
              Tool / Resource / Prompt / Extension
                                    │
                                    ▼
                    Backend / External System

각 자산의 분석 필드
├── [B: 공급망 축] 출처 · 버전 · 무결성 · 의존성 · 변경 상태
└── [C: 권한 축] 인증 · scope · secret · 파일 · 네트워크 · 실행 권한
```

### 3.1 단계별 분석 범위

핵심 공격 표면 A와 이를 설명하는 B·C 자산 필드는 다음 두 단계로 구현한다.

| 단계 | 현재 여부 | 분석 대상 | 제외되는 정보 |
|---|---|---|---|
| 1단계: 정적 자산 분석 | 현재 범위 | 설정·등록 정보·정의 파일·manifest·선언된 권한을 기반으로 한 자산과 잠재 접근 경로 | 실제 요청 내용, 호출 성공 여부, 실행 중 데이터 흐름 |
| 2단계: 런타임 분석 | 후속 범위 | JSON-RPC 요청·응답, Tool 호출, 인증 성공·실패, 실제 파일·네트워크 접근 및 데이터 흐름 | 현재 단계에서 구현하지 않음 |

본 문서에서 **정적 자산**은 파일에만 존재하는 정보를 뜻하지 않는다. 실행 이력과 무관하게 특정 시점의 구조와 기능을 설명하는 설정·등록·정의 metadata의 스냅샷을 의미한다. 현재 수집 범위에는 다음이 포함된다.

- MCP 설정 파일
- 등록된 MCP Server 목록과 연결 정의
- Tool 정의: 이름, description, 입력 스키마 및 기타 공식 metadata
- Skill·Plugin 파일과 manifest·설정
- 권한·자격증명 선언: OAuth scope, 환경변수·Header 사용 선언, 파일시스템·네트워크·프로세스 권한 및 승인 정책

등록 Server 목록이나 Tool 정의를 CLI 또는 MCP 조회로 가져오더라도, 실제 호출 이력이 아니라 구조·정의를 스냅샷으로 수집한 것이므로 본 프로젝트에서는 정적 자산으로 분류한다.

---

## 4. 아키텍처 및 신뢰 경계

MCP 공식 아키텍처의 Host, Client, Server를 구분한다. OpenClaw Gateway 또는 Agent runtime이 여러 역할을 구현하더라도 자산 모델에서는 논리적 역할을 분리한다.

| 구성요소 | 본 프로젝트에서의 역할 |
|---|---|
| User | Tool 실행, 데이터 제공 및 권한 위임의 최종 승인 주체 |
| Agent | 모델 판단을 바탕으로 MCP 기능 사용을 요청하는 실행 주체 |
| MCP Host | Client 생성, 연결 허용, 사용자 동의, 정책 및 서버 간 격리를 통제하는 주체 |
| MCP Client | 특정 MCP Server와 통신하며 요청·응답을 전달하는 논리적 연결 주체 |
| MCP Server | Tool·Resource·Prompt와 capability를 제공하는 로컬 또는 원격 서비스 |
| Skill·Plugin | Agent 또는 Host의 지침·기능·설정·코드를 확장하는 설치 가능 구성요소 |
| External System | MCP Tool이 접근하거나 데이터를 전송하는 파일, DB, API, SaaS 및 내부 시스템 |

주요 신뢰 경계는 다음과 같다.

1. **사용자–Agent/Host 경계**: 사용자의 의도, 동의 및 승인 정보가 전달되는 지점
2. **Host–MCP Server 경계**: JSON-RPC 메시지와 capability가 양방향으로 이동하는 지점
3. **설치 환경–공급자 경계**: 외부 Skill·Plugin·패키지·서버 코드가 유입되는 지점
4. **실행 주체–보호 자원 경계**: 자격증명, 파일시스템, 네트워크 및 외부 계정에 접근하는 지점
5. **서버–외부 시스템 경계**: Tool이 backend 또는 제3자 서비스와 데이터를 주고받는 지점

---

## 5. A — MCP 통신 경계

### 5.1 포함 범위

공격 표면 A의 전체 범위는 MCP Client와 Server 사이에서 교환되는 요청, 응답, 알림, 오류, capability 및 확장 메시지이다. 현재 정적 자산 단계에서는 실제 메시지 payload를 수집하지 않고, 설정과 공식 정의에서 확인되는 통신 구조·method·schema·capability를 수집한다.

| 세부 영역 | 분석 대상 |
|---|---|
| 연결·발견 | 서버 선언 위치, stdio/HTTP 연결, endpoint, `server/discover`, 프로토콜 버전 |
| JSON-RPC | 지원·노출된 method와 요청·응답 방향; 실제 메시지는 후속 런타임 범위 |
| Tool | `tools/list`로 확인한 Tool 이름·description·입출력 스키마·annotation |
| Resource | 등록·광고된 Resource의 URI·metadata와 지원 capability |
| Prompt | 등록·광고된 Prompt 이름·인자·metadata |
| Client 기능 | elicitation 등 서버가 클라이언트 또는 사용자에게 요구하는 입력 |
| Capability | 요청별 Client capability, Server capability 및 선택적 extension |
| 활성 Extension | Tasks, MCP Apps, Skills over MCP 등 실제 활성화된 확장 기능 |

MCP `2026-07-28`은 상태 비저장 요청과 요청별 버전·capability 전달을 기준으로 한다. 과거 세션 중심 필드와 최신 요청별 정보를 같은 의미로 취급하지 않으며, 이전 규격을 사용하는 연결은 `protocol_version`으로 구분한다.

### 5.2 핵심 확인 항목

- 어느 Host/Client가 어느 MCP Server와 통신하는가?
- 로컬 stdio 서버인가, 원격 HTTP 서버인가?
- endpoint와 TLS 검증 정책은 무엇인가?
- 설정·서버 정의에서 확인되는 MCP 규격 버전은 무엇인가?
- 서버가 광고하는 Tool·Resource·Prompt·extension은 무엇인가?
- 그중 특정 Agent에게 노출되고 정적 조건상 잠재적으로 호출 가능한 항목은 무엇인가?
- Tool 설명, annotation, Prompt 및 Resource 내용이 신뢰된 출처에서 왔는가?
- 서버가 클라이언트나 사용자에게 요청할 수 있는 입력 기능은 무엇인가?
- Tool 입력·출력 스키마상 민감정보가 전달될 수 있는 필드가 존재하는가?
- 서버 카탈로그와 capability의 정적 스냅샷은 무엇인가?

실제 JSON-RPC payload, Tool 호출 결과, 호출 성공 여부, 시간에 따른 카탈로그 변경 및 실행 중 민감정보 전달은 후속 런타임 분석에서 확인한다.

Tool 설명과 annotation을 포함한 서버 제공 메타데이터는 신뢰된 서버에서 제공되었다는 근거가 없는 한 비신뢰 입력으로 취급한다.

### 5.3 자원의 의미 구분

| 유형 | 의미 |
|---|---|
| MCP Resource | MCP 인터페이스를 통해 Client에 제공되는 context 또는 data |
| Backend Resource | Tool 구현이 내부적으로 접근하는 파일, DB, 저장소 또는 내부 API |
| External Destination | Tool이 데이터나 결과를 전송할 수 있는 외부 API·SaaS·네트워크 대상 |

Tool이 파일이나 DB에 접근한다고 해서 해당 대상이 반드시 MCP Resource로 광고되는 것은 아니다.

---

## 6. 자산 축 B — Skill·Plugin 공급망 필드

### 6.1 포함 범위

Skill·Plugin 공급망은 독립 공격 표면이 아니라 MCP 관련 자산의 출처와 신뢰도를 설명하는 필드로 수집한다. 모든 소스코드를 대상으로 정밀 취약점 분석을 수행하는 것이 아니라, **설치·변경·로딩·실행 및 MCP 연결에 영향을 주는 공급 경로**를 자산 속성으로 기록한다.

| 세부 영역 | 분석 대상 |
|---|---|
| 공급 출처 | 공식 marketplace, Git 저장소, URL, 로컬 경로, 조직 내부 배포처 |
| 식별·버전 | 이름, 공급자, 버전, commit 또는 배포 식별자 |
| 무결성 | hash, 서명, lock 정보, 검증 결과, 설치 후 변경 여부 |
| manifest·설정 | entry point, 권한 선언, hook, MCP Server 등록, 의존성 |
| 실행 코드 | 로딩되는 script/binary와 실행 위치 |
| 업데이트 경로 | 자동 업데이트 여부, update channel, 마지막 변경 시각 |
| 전이 의존성 | 패키지와 추가 Skill·Plugin·외부 서버 의존 관계 |
| 서드파티 서버 | Skill·Plugin이 설치·등록·실행하는 MCP Server |

### 6.2 핵심 확인 항목

- 누가 Skill·Plugin 또는 서버 패키지를 제공했는가?
- 설치 출처와 현재 실행 코드의 무결성을 검증할 수 있는가?
- 버전 또는 commit이 고정되어 있는가?
- 설치 이후 파일이나 설정이 변경되었는가?
- manifest가 선언한 기능과 실제 등록되는 Tool·Server가 일치하는가?
- Plugin 또는 Skill이 새로운 MCP Server, hook, Tool 또는 정책 예외를 추가하는가?
- 업데이트가 사용자 검토 없이 실행 코드나 권한을 변경할 수 있는가?
- 전이 의존성이 추가 코드 실행 또는 외부 통신을 발생시키는가?

1차 스캐너는 출처·버전·무결성·설정·권한·의존 관계를 중심으로 분석한다. 전체 소스코드의 취약점 탐지, 악성코드 판별 및 패키지 생태계 전체의 보안 감사는 별도 심화 분석 범위로 둔다.

---

## 7. 자산 축 C — 권한·자격증명 필드

### 7.1 포함 범위

MCP 연결, Tool 실행, Skill·Plugin 및 서드파티 서버가 보유하거나 사용할 수 있는 인증정보와 실행 권한을 독립 공격 표면이 아닌 자산 속성으로 수집한다.

| 세부 영역 | 분석 대상 |
|---|---|
| 인증 | OAuth, 정적 Header, 환경변수, API key 전달 방식, mTLS |
| 자격증명 생명주기 | 발급 주체, 대상 audience/resource, scope, 만료, 저장 위치, 갱신 방식 |
| 실행 권한 | 프로세스 사용자, command 실행, sandbox, 관리자 권한 |
| 파일시스템 | 읽기·쓰기 가능 경로, workspace 외부 접근, 민감 파일 접근 |
| 네트워크 | 허용된 목적지, 내부망 접근, 외부 전송 가능성 |
| 데이터 권한 | DB·SaaS·클라우드 계정에서 수행 가능한 읽기·변경·삭제 범위 |
| 정책·승인 | Tool filter, 사용자 승인, 조직 정책, Node 차단 규칙 |
| 격리 | Agent별·사용자별·Server별 자격증명 및 실행 환경 분리 여부 |

### 7.2 핵심 확인 항목

- 자격증명이 공유형인가, 사용자·요청·서버별로 분리되어 있는가?
- 토큰의 scope와 실제 Tool 기능이 최소 권한 원칙에 맞는가?
- 토큰의 대상 audience/resource가 해당 서버로 제한되는가?
- 환경변수나 Header를 통해 다른 Server 또는 Tool에 자격증명이 전파될 수 있는가?
- stdio 서버와 Plugin이 어떤 OS 사용자 및 파일 권한으로 실행되는가?
- 읽기 Tool과 외부 전송 Tool을 결합하여 민감정보를 반출할 수 있는가?
- Tool 실행 전 사용자 승인 또는 정책 검사가 설정에 선언되어 있는가?
- 권한 변경과 자격증명 갱신을 추적할 수 있는가?

권한과 자격증명 필드는 침해된 Tool·Server·Plugin이 만들 수 있는 피해 범위와 권한 확대 가능성을 설명한다. 따라서 공격 진입점 자체가 아니라 A의 노출도와 잠재 영향을 해석하는 분석 축으로 사용한다.

### 7.3 민감정보 수집 원칙

- `headers`, `env`, 토큰, client key 및 secret의 실제 값은 저장하거나 표시하지 않는다.
- 자격증명의 존재 여부, 유형, 참조 방식, scope, 만료 여부 및 분리 수준만 기록한다.
- 파일 경로 자체가 민감할 때는 정규화하거나 정책 범주로 대체한다.
- 로그와 Tool 결과에 secret이 노출되는지도 별도 상태로 기록한다.

---

## 8. 포함·제외 범위

### 8.1 포함 범위

아래 항목은 핵심 공격 표면 A와 이를 설명하는 B·C 자산 필드의 전체 분석 범위이다. 현재 단계에서는 각 항목의 설정·등록·정의·선언 정보만 수집하고, 실제 통신과 실행 결과는 후속 런타임 단계에서 수집한다.

- MCP Host·Client·Server의 연결, 발견 및 JSON-RPC 통신
- Tool·Resource·Prompt, client capability 및 활성 extension
- Agent별 노출 상태, 잠재 호출 가능성 및 선언된 정책
- Skill·Plugin 파일, 설정, manifest, 설치·업데이트 출처 및 의존성
- Skill·Plugin이 등록하거나 실행하는 서드파티 MCP Server
- OAuth 토큰, Header·환경변수 기반 인증, mTLS 및 자격증명 위임 구조
- 파일시스템·네트워크·프로세스·데이터 권한과 sandbox·승인 정책
- Tool과 backend resource, 외부 전송 대상 및 Tool 간 조합 가능성

### 8.2 제외 범위

- 모델 학습 데이터 공격, 모델 탈취, 적대적 머신러닝 등 모델 자체 취약점
- Prompt Injection 문자열을 판별하는 탐지 모델 개발
- 실제 공격 성공 여부를 검증하는 침투 테스트 및 공격 페이로드 실행
- 모든 Skill·Plugin 및 의존 패키지 소스코드에 대한 완전한 정적 분석
- 운영체제와 외부 SaaS 자체의 일반 취약점 분석

Prompt Injection과 악성 Tool 설명·Resource·Prompt는 비신뢰 입력의 출처로 포함한다. 다만 문장 자체를 분류하는 것보다 해당 입력이 어떤 Tool·권한·데이터 경로에 도달할 수 있는지를 가시화한다.

---

## 9. 전체 공격 표면 개념 모델

이 장의 모델은 신뢰 경계와 잠재 공격 경로를 빠짐없이 설명하기 위한 **논리적 보안 모델**이다. 여기에 포함된 모든 정점이 1차 스캐너의 직접 수집 대상이라는 뜻은 아니다. 직접 구현할 정점은 10장의 1차 Scanner Schema에서 별도로 제한한다.

### 9.1 개념 정점

| 정점 | 식별 기준 | 출처 |
|---|---|---|
| User/Identity | 사용자·서비스 계정 식별자 | 제품 설정 + 프로젝트 정규화 |
| Agent | Agent 식별정보 | OpenClaw 자산 + 프로젝트 정규화 |
| MCP Host | Host 또는 Gateway 인스턴스 ID | 제품 자산 + 프로젝트 정규화 |
| MCP Client | Host ID + Server ID + 연결 식별자 | 설정에서 도출한 논리 자산 + 프로젝트 정규화 |
| MCP Server | 선언 위치 + 서버 이름 또는 endpoint | 제품 설정 기반 |
| Tool | MCP Server ID + Tool `name` | MCP 공식 필드 기반 |
| MCP Resource | MCP Server ID + Resource `uri` | MCP 공식 필드 기반 |
| Prompt | MCP Server ID + Prompt `name` | MCP 공식 필드 기반 |
| Skill/Plugin | 공급자 + 패키지 ID + 버전 | manifest·설치 정보 |
| Credential | 비밀값이 아닌 자격증명 참조 ID와 유형 | 제품 설정 + 프로젝트 정규화 |
| Backend Resource | 정규화한 파일·DB·API 식별자 | 설정·로그·추론 |
| External System | 정규화한 서비스·endpoint 식별자 | 설정·로그·추론 |

서버 이름이나 Tool 이름만 전역 ID로 사용하지 않는다. 서로 다른 서버의 동명 자산 충돌을 방지하기 위해 `server_id + asset_type + official_identifier` 형태의 복합 식별자를 사용한다.

### 9.2 개념 관계

| 관계 | 의미 |
|---|---|
| `HOSTS_CLIENT` | MCP Host가 Client를 생성·관리함 |
| `CONNECTS_TO` | MCP Client가 특정 MCP Server와 통신함 |
| `ADVERTISES` | MCP Server가 Tool·Resource·Prompt·capability를 제공함 |
| `EXPOSES_TO` | 자산이 정책 적용 후 Agent에게 표시됨 |
| `MAY_CALL` | 정적 설정상 Agent가 Tool을 호출할 가능성이 있음 |
| `CAN_CALL` | 런타임 검증 결과 Agent가 Tool을 실제 호출할 수 있음 |
| `REQUESTS_INPUT_FROM` | Server가 Client/User에 추가 입력을 요청할 수 있음 |
| `INSTALLS` | 공급 경로가 Skill·Plugin 또는 Server를 설치함 |
| `DEPENDS_ON` | Skill·Plugin·Server가 다른 패키지나 구성요소에 의존함 |
| `REGISTERS` | Skill·Plugin이 Tool, hook 또는 MCP Server를 등록함 |
| `USES_CREDENTIAL` | Client·Server·Tool·Plugin이 자격증명을 사용함 |
| `GRANTS_ACCESS_TO` | 자격증명 또는 정책이 자원 접근 권한을 부여함 |
| `ACCESSES` | Tool·Server·Plugin이 backend resource에 접근함 |
| `SENDS_TO` | 데이터 또는 결과를 외부 시스템으로 전송할 수 있음 |
| `CAN_CHAIN_TO` | 한 기능의 결과가 다른 기능의 입력·실행으로 이어질 수 있음 |

`MAY_CALL`, `ACCESSES`, `SENDS_TO`, `CAN_CHAIN_TO`는 정적 정보나 공식 MCP 응답만으로 항상 확정할 수 없다. 관계마다 근거와 신뢰도를 함께 기록하고, 런타임에서 확인되기 전에는 추론 관계로 표시한다.

### 9.3 근거와 신뢰도

| 필드 | 값 예시 |
|---|---|
| `evidence_type` | config, manifest, protocol, schema, description, runtime_log, manual |
| `confidence` | confirmed, high, medium, low |
| `observed_at` | 관찰 시각 |
| `source_ref` | 원본 파일·응답·로그 참조 |
| `inference_rule` | 관계를 생성한 규칙 ID |
| `protocol_version` | 연결 또는 응답의 MCP 규격 버전 |
| `policy_context` | 노출·호출 판정에 사용한 정책 버전 |

---

## 10. 1차 Scanner Schema

### 10.1 구현 범위

1차 스캐너는 회의에서 합의한 다음 **7종의 정적 자산만 직접 정점으로 생성**한다.

| MVP 정점 | 주요 수집 원천 | 역할 |
|---|---|---|
| Gateway | OpenClaw 설정·상태 파일 | MCP Server 선언과 정책이 위치하는 Gateway 식별 |
| Node | OpenClaw Node 설정·상태 파일 | Node-hosted MCP Server 및 실행 위치 식별 |
| MCP Server | MCP 설정 파일, 등록 Server 목록 | 연결 방식과 제공 자산의 소유 Server 식별 |
| Tool | MCP 공식 Tool 정의 | `name`, `description`, `inputSchema` 등 기능 정의 수집 |
| Resource/Prompt | MCP 공식 Resource·Prompt 정의 | 서버가 제공하는 context·data 및 Prompt 정의 수집 |
| Skill | Skill 파일과 metadata | MCP 사용·등록 여부와 공급망 속성 수집 |
| Plugin | Plugin manifest·설정 | MCP Server·Tool 등록과 공급망 속성 수집 |

`Resource`와 `Prompt`는 MCP 공식 객체로 수집할 때 각자의 필드와 유형을 보존한다. 다만 MVP 자산 분류와 대시보드의 정점 유형에서는 `Resource/Prompt` 한 종류로 묶고 `asset_subtype`으로 구분할 수 있다.

### 10.2 B·C 자산 필드 흡수

B와 C는 별도 정점 또는 별도 공격 표면으로 구현하지 않고, 관련 MVP 정점의 속성으로 저장한다.

| 자산 축 | 적용 정점 | 대표 필드 |
|---|---|---|
| B: 공급망 | MCP Server, Skill, Plugin | `source_type`, `source_uri`, `provider`, `version`, `commit`, `integrity_status`, `modified`, `dependencies`, `update_policy` |
| C: 권한·자격증명 | Gateway, Node, MCP Server, Tool, Skill, Plugin | `auth_type`, `credential_ref`, `oauth_scopes`, `filesystem_permissions`, `network_permissions`, `process_identity`, `sandbox`, `approval_policy` |

비밀값은 저장하지 않는다. `credential_ref`에는 실제 토큰이나 환경변수 값이 아니라 자격증명의 유형, 참조 이름 또는 비식별 ID만 기록한다.

### 10.3 개념 모델과 MVP 매핑

| 전체 개념 모델 | 1차 Scanner Schema 표현 | 구현 방식 |
|---|---|---|
| User/Identity | 관련 자산의 identity·owner 필드 | 별도 정점으로 생성하지 않음 |
| Agent | Gateway/Node의 agent 식별 필드 | 설정에서 식별 가능할 때만 기록 |
| MCP Host | Gateway 또는 Node | 제품 구현 역할로 매핑 |
| MCP Client | Gateway/Node–MCP Server 관계 | 별도 정점 대신 `CONNECTS_TO` 관계로 표현 |
| MCP Server | MCP Server | 직접 수집 정점 |
| Tool | Tool | 직접 수집 정점 |
| MCP Resource | Resource/Prompt | `asset_subtype: resource`로 구분 |
| Prompt | Resource/Prompt | `asset_subtype: prompt`로 구분 |
| Skill | Skill | 직접 수집 정점 |
| Plugin | Plugin | 직접 수집 정점 |
| Credential | 관련 자산의 권한·자격증명 필드 | 비밀값 없이 참조 정보만 저장 |
| Backend Resource | Tool의 잠재 접근 대상 필드·추론 관계 | 직접 정점으로 생성하지 않음 |
| External System | Server/Tool의 endpoint·destination 필드 | 직접 정점으로 생성하지 않음 |

### 10.4 MVP 관계

1차 스캐너가 직접 생성하는 관계도 수집 가능한 정적 근거로 제한한다.

| 관계 | 의미 | 근거 |
|---|---|---|
| `DECLARES` | Gateway/Node가 MCP Server를 선언함 | 설정 파일·등록 목록 |
| `ADVERTISES` | MCP Server가 Tool·Resource·Prompt를 제공한다고 광고함 | MCP 공식 목록 응답의 스냅샷 |
| `ASSOCIATED_WITH` | Skill·Plugin이 MCP Server 또는 Tool과 연관됨 | manifest·설정·파일 참조 |
| `MAY_EXPOSE_TO` | 정적 정책상 자산이 Agent에 노출될 가능성이 있음 | filter·정책 설정 |
| `MAY_ACCESS` | 설명·스키마·설정상 자원 접근 가능성이 있음 | 정적 추론과 근거 수준 |
| `MAY_SEND_TO` | 설정·스키마상 외부 목적지로 전송할 가능성이 있음 | 정적 추론과 근거 수준 |

`CAN_CALL`, 실제 `ACCESSES`, 실제 `SENDS_TO`와 같은 확정 관계는 1차 스캐너가 생성하지 않는다. 후속 런타임 단계에서 관찰 근거가 확보된 경우에만 개념 모델의 확정 관계로 승격한다.

### 10.5 후속 확장 대상

다음은 전체 개념 모델에는 포함되지만 MVP 구현 범위에서는 제외한다.

- User/Identity, Agent, MCP Client, Credential의 독립 정점화
- Backend Resource와 External System의 독립 정점화
- 실제 JSON-RPC 요청·응답과 Tool 호출 추적
- 실제 자격증명 사용, 파일·DB·API 접근 및 외부 전송 확인
- 런타임 관찰을 통한 `CALLABLE`, `ACCESSES`, `SENDS_TO` 관계 확정

---

## 11. 공식 정보와 프로젝트 확장 정보

Tool·Resource·Prompt와 MCP 메시지·capability는 MCP `2026-07-28` 공식 스키마의 필드명, 자료형 및 의미를 따른다. 공식 객체를 수집할 때 임의로 필드 의미를 변경하지 않고 원본 표현을 보존한다.

다만 프로젝트의 전체 출력 형식이 하나의 MCP 공식 스키마에 그대로 존재하는 것은 아니다. 제품 설정과 공급망 정보, 자산 간 관계를 함께 표현해야 하므로 다음 세 종류의 정보를 정규화해 통합한다.

| 구분 | 원천 | 대표 정보 |
|---|---|---|
| MCP 공식 정보 | MCP `2026-07-28` 규격과 활성 extension | Tool·Resource·Prompt, capability, 요청·응답 필드 |
| 제품·공급망 정보 | OpenClaw 설정·상태, Skill·Plugin manifest와 설치 metadata | Server 선언, 연결 설정, 정책, 출처, 버전, 의존성 |
| 프로젝트 확장 정보 | 프로젝트 정규화·분석 로직 | 신뢰 경계, 노출 상태, 관계, 위험 태그, 근거와 신뢰도 |

OpenClaw 설정 필드는 사용 중인 제품 버전의 실제 스키마와 CLI 출력을 기준으로 수집한다. 제품 설정 필드를 MCP 표준 필드로 표현하지 않는다.

프로젝트가 추가한 필드는 별도 namespace 또는 `project_*` 계열로 구분하여 MCP 공식 필드로 오인되지 않게 한다. 공식 스키마에 없는 `exposed`, `callable`, `risk_tags`, 관계와 추론 신뢰도 등은 프로젝트 확장 정보로 명시한다.

### 11.1 정보 계층

| 계층 | 수집 내용 | 의미 |
|---|---|---|
| 선언 계층 | Server, Skill·Plugin, endpoint, 실행 명령, 인증·정책 설정 | 운영자 또는 공급자가 구성한 것 |
| 공급망 계층 | 출처, 버전, hash·서명, 의존성, 변경 상태 | 설치된 구성요소의 신뢰 근거 |
| 발견 계층 | 등록 Server 목록, Tool·Resource·Prompt 정의, capability, extension | 특정 시점에 구성요소가 제공한다고 선언·광고한 정적 스냅샷 |
| 권한 계층 | credential type, scope, filesystem·network·process 권한 | 실행 시 사용할 수 있는 권한 |
| 관계 계층 | Agent–Host–Client–Server–Tool–Resource 연결 | 여러 원천을 결합해 해석한 것 |
| 사용 계층 | 호출 시각·횟수·성공 여부·데이터 흐름 | 실제로 관찰된 것 |

현재 1차 정적 스캐너는 선언·공급망·발견·권한 계층의 스냅샷과 잠재 관계 추론을 대상으로 한다. 실제 JSON-RPC 요청·응답, 호출 시각·횟수·성공 여부, 실제 접근 자원 및 데이터 흐름은 로그·텔레메트리 기반 후속 런타임 수집으로 구분한다.

---

## 12. MVP 최소 수집 필드

아래 항목은 현재 단계의 정적 자산 최소 수집 필드이다. 실행 이력이 필요한 필드는 포함하지 않는다.

### 12.1 Gateway·Node·MCP Server

| 범주 | 최소 필드 |
|---|---|
| 식별 | gateway_id/node_id, server_id, 서버 이름, 선언 위치, source path |
| 연결 | command/args 또는 endpoint, transport, TLS 검증 여부 |
| 규격 | protocol_version, client capabilities, server capabilities, extensions |
| 상태 | declared, discovered, 정적 정책으로 판정한 exposed 및 potentially_callable 여부 |
| 스냅샷 | collected_at, catalog hash, capability hash |

### 12.2 Tool·Resource/Prompt

| 자산 | 최소 필드 |
|---|---|
| Tool | server_id, name, title, description, inputSchema, outputSchema, annotations, 정적 exposure state |
| Resource/Prompt | server_id, asset_subtype, uri 또는 name, description, mimeType·size 또는 arguments, exposure state |

### 12.3 Skill·Plugin

| 범주 | 최소 필드 |
|---|---|
| 식별 | package_id, name, provider, version/commit |
| 출처 | source_type, source_uri, registry/marketplace |
| 무결성 | hash/signature 존재 여부와 검증 결과, modified 상태 |
| 실행 | entry point, script/binary 유형, 실행 위치 |
| 확장 | 등록 Server·Tool·hook, dependency 목록 |
| 업데이트 | pinned 여부, update channel, auto-update 여부, last_updated |

### 12.4 B·C 흡수 필드

| 자산 축 | 범주 | 최소 필드 |
|---|---|---|
| B | 공급 출처 | source_type, source_uri, provider, registry/marketplace |
| B | 버전·무결성 | version/commit, hash/signature 검증 결과, modified, pinned 여부 |
| B | 의존·업데이트 | dependencies, update channel, auto-update 여부 |
| C | 인증 | credential reference ID, type, 사용 주체, 대상 Server/API |
| C | OAuth | issuer, audience/resource, scope, 만료 여부, 사용자별 분리 여부 |
| C | 실행 | process identity, sandbox, command 권한 |
| C | 파일 | 읽기·쓰기 범위와 workspace 외부 접근 여부 |
| C | 네트워크 | 허용 목적지 범주, 내부망·외부망 접근 여부 |
| C | 정책 | Tool filter, approval mode, 적용 정책과 판정 결과 |

### 12.5 후속 런타임 수집 필드

다음 항목은 전체 공격 표면에는 포함되지만 현재 정적 자산 구현 범위에서는 제외한다.

- JSON-RPC 요청·응답 시각, method, 성공·오류 상태
- Tool의 실제 호출 횟수, 호출 주체 및 승인 결과
- 실행 시 사용된 자격증명과 인증 성공·실패
- 실제 접근한 파일·DB·API 및 네트워크 목적지
- 요청·응답을 통해 이동한 데이터의 분류와 민감도
- 런타임 카탈로그·capability 변경 이력

---

## 13. 최종 정리

본 프로젝트의 핵심 공격 표면은 **A: MCP 통신 경계**이다. Host·Client·Server 사이에서 어떤 JSON-RPC 요청·응답, Tool·Resource·Prompt 및 양방향 capability가 이동할 수 있는지를 분석한다.

다음 두 항목은 별도 공격 표면이 아니라 MCP 자산을 설명하는 분석 축과 필드로 흡수한다.

1. **B: Skill·Plugin 공급망 필드** — 출처, 버전, 무결성, 의존성, 변경 상태 및 서드파티 MCP Server 등록 정보
2. **C: 권한·자격증명 필드** — OAuth scope, 환경변수·Header 사용, 파일·네트워크·프로세스 권한 및 승인 정책

현재 단계에서는 A의 통신 구조와 B·C 속성을 결합한 **정적 자산 분석**을 수행한다. MCP 설정 파일, 등록된 MCP Server 목록, Tool description·입력 스키마를 포함한 Tool 정의, Skill·Plugin 파일, 권한·자격증명 선언을 MCP 공식 스키마와 제품별 설정 형식에 맞추어 수집한다. 공식 필드는 원래 의미를 보존하고, 노출 상태·자산 관계·위험 태그와 같은 분석 결과만 프로젝트 확장 필드로 분리한다.

전체 공격 표면 개념 모델은 User/Identity, Agent, MCP Host·Client, Credential, Backend Resource 및 External System까지 포함하지만, 이는 보안 관계를 설명하기 위한 범위이다. 1차 스캐너는 **Gateway, Node, MCP Server, Tool, Resource/Prompt, Skill, Plugin의 7종만 직접 정점으로 생성**하고, 나머지 개념은 속성·관계 또는 후속 확장 대상으로 표현한다.

실제 JSON-RPC 메시지, Tool 호출, 인증 결과, 파일·네트워크 접근 및 데이터 흐름은 후속 런타임 분석에서 수집한다. 따라서 현재 정적 분석에서 `CALLABLE` 또는 실제 접근 관계를 확정하지 않고, 설정과 정의로 확인 가능한 잠재 노출·접근 가능성과 그 근거를 기록한다.

공격 표면은 자산의 존재만으로 확정하지 않는다. **신뢰 경계, 비신뢰 주체의 통제 가능성, 현재 정책상 도달 가능성 및 보안 영향**을 함께 평가한다. 또한 선언·발견·노출·호출 가능·실제 사용 상태를 구분하고, 추론 관계에는 근거와 신뢰도를 표시한다.

이 원칙을 적용하면 스캐너와 대시보드는 다음 질문에 답할 수 있다.

- 어떤 비신뢰 입력이 어느 경계를 통해 들어오는가?
- 해당 입력이 어떤 Tool과 권한에 도달할 수 있는가?
- 어떤 공급망 구성요소가 연결과 권한을 추가하거나 변경했는가?
- 여러 기능이 결합될 때 어떤 데이터 접근·외부 전송 경로가 만들어지는가?
- 각 판단은 설정, 공식 응답, manifest, 로그 또는 추론 중 무엇에 근거하는가?

---

## 참고 자료

1. Model Context Protocol, **Specification 2026-07-28**  
   <https://modelcontextprotocol.io/specification/2026-07-28>
2. Model Context Protocol, **Architecture 2026-07-28**  
   <https://modelcontextprotocol.io/specification/2026-07-28/architecture>
3. Model Context Protocol, **Tools 2026-07-28**  
   <https://modelcontextprotocol.io/specification/2026-07-28/server/tools>
4. Model Context Protocol, **Resources 2026-07-28**  
   <https://modelcontextprotocol.io/specification/2026-07-28/server/resources>
5. Model Context Protocol, **Prompts 2026-07-28**  
   <https://modelcontextprotocol.io/specification/2026-07-28/server/prompts>
6. Model Context Protocol, **Extensions**  
   <https://modelcontextprotocol.io/extensions>
7. OpenClaw, **MCP CLI overview**  
   <https://docs.openclaw.ai/cli/mcp>
8. OpenClaw, **MCP JSON output shapes**  
   <https://docs.openclaw.ai/cli/mcp/json-output>
9. OpenClaw, **MCP transports and OAuth**  
   <https://docs.openclaw.ai/cli/mcp/transports>
10. OWASP, **Top 10 for Agentic Applications** — Tool Misuse, Identity and Privilege Abuse, Supply Chain Vulnerabilities
