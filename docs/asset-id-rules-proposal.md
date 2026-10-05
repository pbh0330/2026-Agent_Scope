# 자산 ID 생성 규칙 — 팀 협의안

> 문서 버전: v0.1 · 수정일: 2026-10-06
> 상태: 자산 ID 생성 규칙 팀 협의안
> 범위: 8종 분류안을 전제로 한 ID 생성 및 동일 자산 식별 규칙

## 우선 제안과 확인 요청

**B안(Canonical Key + Hash), 수집 결과 DB 초기화 후 재현성 보장, 식별 키 변경 시 새 ID 생성을 우선 제안합니다.** 표시 이름이나 설명만 바뀌면 ID를 유지합니다. 스캐너·테스트베드 담당자는 2절 표의 원천 값을 실제로 수집할 수 있는지, 반복 조회·프로필 변경·재설치 때 유지되는지 확인해 주세요.

| 결정할 내용 | 우선 제안 | 확인 담당 |
| --- | --- | --- |
| ID 표현 | B안. 안전한 원천 식별 정보의 정규화된 조합을 해시 | 스캐너·QA |
| 자산별 식별 정보 | 2절 후보를 실제 출력으로 확인 후 확정 | 스캐너·테스트베드 |
| 표시 이름·속성 변경 | 식별 키가 같으면 ID 유지 | 스캐너·대시보드 |
| 식별 키 변경 | 새 ID 생성. 이전 자산의 제거 여부는 별도 판정 | 스캐너·QA |
| 재현성 | 원천 식별값과 생성 규칙이 같으면 결과 DB 초기화 후에도 동일 ID | 스캐너·QA |

아래 짧은 해시와 UUID는 형식 설명용이며 실제 계산 결과나 권장 길이가 아니다. 최종 규칙을 정한 뒤 실제 입력·출력 테스트 벡터를 공유한다.

# 1. ID 표현 방식

| 후보 | 방식 | 예시 | 특징 |
| --- | --- | --- | --- |
| **A. 계층형 문자열 ID** | 유형 + 부모 + 원천 이름 | `tool:server-a:read_file` | 가장 이해하기 쉬움 |
| **B. Canonical Key 기반 Hash** | 안정적 원천정보 조합 → Hash | `ast_8f21a93c` | 안정적이고 시스템 친화적 |
| **C. Deterministic UUID** | 안정적 원천정보 조합 → UUID v5 등 | `550e8400-...` | 표준적이고 충돌 관리 용이 |
| **D. 내부 UUID + Source Key 분리** | 최초 발견 시 UUID 발급, 원천 식별자는 별도 저장 | `ast_01H...` + `source_key` | 유연하지만 영속 저장 필요 |

## 후보A - 계층형 문자열 ID

```
{asset_type}:{parent_identifier}:{source_identifier}
```

ex)

```
gateway:env-a:profile-a:gw01

mcp_server:env-a:profile-a:gw01:config-main:mcp.servers:filesystem

tool:env-a:profile-a:gw01:config-main:mcp.servers:filesystem:read_file

resource_prompt:env-a:profile-a:gw01:config-main:mcp.servers:filesystem:prompt:config

skill:env-a:profile-a:skills-root:pdf-reader

plugin:env-a:profile-a:extensions-root:github-plugin

permission_auth:env-a:profile-a:config-main:github-auth:authentication
```

- 장점: 사람이 ID만 보고도 무슨 자산인지 알 수 있으며 Ground Truth 작성 편리.
- 단점: 이름이 바뀌면 ID가 바뀔 수 있고, 부모가 여러 단계가 되면 ID가 길어짐
    
    해결방안
    
    1. **이름이 바뀌면 ID도 바뀌는 것을 허용**
        
        ```
        식별에 사용하는 등록 키·원래 이름 변경
           ↓
        asset_id 변경
           ↓
        새 ID 생성, 이전 ID의 미관측·제거 여부는 별도 판정
        ```
        
        구현은 가장 단순하지만 자산 변경 이력을 추적하려면 좋지는 않음.
        
    2. **변경되지 않는 식별값을 A안에 넣는 것**
        
        예를 들어 gateway나 mcp server 자체가 안정적인 id를 제공한다면
        
        ```
        표시 이름:
        filesystem → local-files
        
        원천 고유 ID:
        srv-001 → srv-001
        
        asset_id:
        mcp_server:env-a:profile-a:gw01:srv-001
        → 그대로 유지
        ```
        
        ```text
        {
          "asset_id": "mcp_server:env-a:profile-a:gw01:srv-001",
          "asset_type": "mcp_server",
          "name": "local-files"
        }
        ```
        
        결국 수집하는 모든 자산에 `srv-001` 같은 안정적인 고유값이 존재하느냐가 문제.
        

## 후보B - Canonical Key + Hash

**자산별 안정적인 원천 식별 정보로 canonical key를 구성하고 이를 기반으로 ID 생성**

자산의 안정적인 정보를 이용해 `canonical_key` 를 만들고

```
["gateway","env-a","profile-a","gw01"]

["mcp_server","env-a","profile-a","gw01","config-main","mcp.servers","filesystem"]

["tool","env-a","profile-a","gw01","config-main","mcp.servers","filesystem","read_file"]
```

그걸 hash

```
asset_id = ast_a83f21c9
```

데이터 예시

```
{
  "asset_id": "ast_a83f21c9",
  "asset_type": "tool",
  "canonical_key": ["tool","env-a","profile-a","gw01","config-main","mcp.servers","filesystem","read_file"],
  "name": "read_file"
}
```

- 장점: 동일한 canonical key라면 반복 수집해도 같은 ID를 생성
- 단점: 사람이 `ast_a83f21c9`만 보고는 어떤 자산인지 모른다
    - 따라서 Dashboard나 QA에서는 `name`, `canonical_key`를 같이 확인해야 함.

## 후보 C - Deterministic UUID

**canonical key를 기반으로 동일 자산에 항상 동일 UUID 생성**

B와 유사

```
canonical key
        ↓
UUID v5
        ↓
asset_id
```

ex)

```
["tool","env-a","profile-a","gw01","config-main","mcp.servers","filesystem","read_file"]
        ↓
550e8400-e29b-41d4-a716-446655440000
```

- 장점: 표준화된 ID 형식을 사용할 수 있고 길이도 고정
- 단점: 프로젝트 규모에 비해 UUID가 과할 수 있고 Ground Truth를 사람이 볼 때 불편

## 후보 D - 랜덤 내부 ID + Source Key

발견된 자산에 시스템이 ID를 발급

```
{
  "asset_id": "ast_000042",
  "asset_type": "tool",

  "source_key": "env-a:profile-a:gw01:config-main:mcp.servers:filesystem:read_file",

  "name": "read_file"
}
```

나중에 다시 수집하면 DB에서

```
source_key 조회
      ↓
기존 자산 있음
      ↓
asset_id = ast_000042 재사용
```

- 프로젝트에 비해 복잡.
- DB의 상태에 의존하기 때문에 Ground Truth나 테스트베드를 초기화했을 때 동일 ID 재현 문제도 생각해야 함.

### B vs C

간단하게 B안과 C안의 차이점 정리

**B안:**

자산 식별 정보를 Hash하여 프로젝트 자체 형식의 ID를 생성. ID 길이·접두사 등을 자유롭게 정할 수 있음.

**C안:**

동일한 자산 식별 정보를 기반으로 deterministic UUID를 생성. UUID 표준 형식을 그대로 사용할 수 있음.

|  | B. Hash 기반 | C. Deterministic UUID |
| --- | --- | --- |
| 생성 | canonical key를 SHA-256 등으로 해시 | canonical key + namespace로 UUID v5 등 생성 |
| 예시 | `ast_a83f21c91234abcd` | `f47ac10b-58cc-5...` |
| 길이 | 우리가 정할 수 있음 | UUID 형식으로 고정 |
| 접두사 | `ast_`, `tool_` 등 자유롭게 가능 | 일반적으로 UUID 그대로 사용 |
| 가독성 | 프로젝트에 맞게 만들기 쉬움 | 사람이 보기엔 어려움 |
| 표준성 | 프로젝트 자체 규칙 필요 | UUID라는 표준 형식 사용 |
| 재현성 | 같은 입력 → 같은 Hash | 같은 namespace+입력 → 같은 UUID |
- B안
    - 형식을 직접 설계하는 느낌.
    
    ```text
    canonical_key
    ["tool","env-a","profile-a","gw01","config-main","mcp.servers","filesystem","read_file"]
    
    ↓ SHA-256
    
    3e91a75c08f29...
    
    ↓ 프로젝트 규칙
    
    asset_id = ast_3e91a75c08f29abc
    ```
    
    - `ast_ + hash 앞 16자리` 처럼 형식을 정할 수 있음.
        - 충돌 가능성을 고려해서 길이를 정해야 함.
    - 또는 유형을 보여주고 싶다면 `tool_3e91a75c08f29abc` 와 같은 형식도 가능.
    - 대신 `"SHA-256을 쓴다"`, `"몇 자리를 쓴다"`, `"접두사는 어떻게 한다"` 같은 프로젝트 자체 규칙 명시가 필요함.
- C안
    - 이미 정해진 UUID 규칙을 이용
    - 예를 들어 UUID v5를 사용한다면:
        
        ```text
        프로젝트 namespace UUID
                +
        ["tool","env-a","profile-a","gw01","config-main","mcp.servers","filesystem","read_file"]
                ↓
              UUID v5
                ↓
        e8ab8c2d-.......
        ```
        
        같은 namespace와 같은 canonical key를 넣으면 항상 같은 UUID가 나와.
        
    - **namespace:** 프로젝트용 UUID 생성 영역
        - 다른 프로젝트도 `["tool","env-a","profile-a","gw01","config-main","mcp.servers","filesystem","read_file"]`
        라는 똑같은 문자열을 사용하더라도 namespace가 다르면 다른 UUID 생성.

### B안 채택 시 확정할 구현 규칙

| 항목 | 제안 및 확인 내용 |
| --- | --- |
| 알고리즘·길이 | SHA-256 전체 소문자 16진수 64자리 + `ast_` 접두사 권장. 화면에서만 축약하며 저장·조인에는 전체 ID 사용 |
| 입력 구조 | 단순 `\|`·`:` 연결 대신 유형별 순서가 정해진 JSON 배열. 배열 순서가 식별 의미를 가짐 |
| 바이트 표현 | UTF-8, BOM 없음, 들여쓰기·구분자 주변 공백 없음. 문자열 내부 공백은 보존. 비ASCII 문자·슬래시·제어문자의 이스케이프 방식도 공통 구현으로 고정 |
| 문자열 정규화 | 원래 이름·URI의 대소문자나 공백을 임의 변경하지 않음. 경로 구분자·상대 경로·심볼릭 링크·Unicode 처리 규칙은 실제 원천에 맞춰 별도 확정 |
| 생성 규칙 버전 | 입력 맨 앞에 `asset-id-v1` 같은 규칙 버전 식별자를 포함하는 안. 규칙 변경 시 기존 ID와의 매핑·전환 방식도 결정 |
| 필수값 누락 | 빈 문자열·unknown으로 대체해 정상 ID를 발급하지 않음. 식별 미완료로 기록 |
| 충돌 처리 | 서로 다른 canonical key가 같은 ID를 만들면 자동 병합하지 않고 오류로 기록 |
| 검증 예제 | 스캐너·QA가 동일 입력으로 같은 ID를 만드는 실제 테스트 벡터 공유 |

위 내용은 구현 권장안이며 아직 확정 규칙이 아니다. 앞의 배열은 식별 정보 설명용이고, 최종 해시 입력에는 규칙 버전과 합의된 직렬화를 적용한다. 같은 JSON 내용이어도 출력 바이트가 다르면 해시가 달라지므로 각 구현의 기본 JSON 설정에 맡기지 않는다. 계층형 문자열 예시의 `:`도 설명용이며 A안을 채택하면 별도의 이스케이프 규칙이 필요하다.

예제 확인 항목: 같은 원천 재수집, 다른 환경·프로필의 동명 서버, 다른 서버의 동명 Tool, 하위 유형이 다른 Resource/Prompt, 표시명·URL 변경, 등록 키 변경, 특수문자가 포함된 이름·경로, 수집 결과 DB 초기화.

canonical key에는 안전한 원천 식별 정보만 넣는다. 해시는 민감정보 제거 수단이 아니며 원본 비밀값을 해시해 저장하지 않는다. QA는 필요하면 정답의 논리 키와 실제 asset_id 사이의 명시적인 매핑을 사용할 수 있다.

# 2. 자산 유형별 식별 기준

**자산의 정체성을 어떤 값으로 판단할 것인가?**

```text
MCP Server
→ 어떤 값이 바뀌지 않는 식별값인가?

Tool
→ Server ID + tool name이면 충분한가?

Gateway
→ 어떤 설치/인스턴스 식별값이 존재하는가?

Plugin
→ plugin ID가 존재하는가?
...
```

공통적으로 **동일 자산은 반복 수집 시 동일 ID를 유지하고, 서로 다른 자산은 이름이 같더라도 구분되는 것**을 기준으로 생각하고 있습니다.

특히 스캐너/테스트베드 쪽에서 각 자산 유형별로 안정적으로 사용할 수 있는 원천 식별 정보가 무엇인지 의견 부탁드립니다.

⇒

**각 자산을 스캐너에서 수집했을 때, 동일 유형의 다른 자산과 구분하기 위해 안정적으로 사용할 수 있는 원본 값이 무엇인지 궁금합니다.**

예를 들어 MCP Server는 설정상의 서버 이름/등록 키, Tool은 서버 정보 + tool name처럼 식별할 수 있는 값이 있는지 확인하고 싶습니다. 반복 수집해도 동일하게 얻을 수 있는 값이면 좋을 것 같습니다.

## 식별 기준 후보 — 실제 출력 확인 후 결정

| 자산 유형 | 식별에 사용할 원본 정보 후보 | 담당자 확인 사항 |
| --- | --- | --- |
| Gateway | 환경·프로필 범위 + Gateway device identity | 실제 필드, 프로필별 유일성, 초기화·복제 시 유지 여부 |
| Node | 환경 범위 + Node device identity | Gateway 재페어링 시 같은 Node로 볼지, 프로필 포함 여부 |
| MCP Server | 선언 주체의 완전한 ID + 원본 설정 위치 + 서버 등록 키 | 등록 주체와 실행 위치 구분, include 등 원본 위치 처리 |
| Tool | MCP Server ID + Tool 원래 name | 노출명·표시명과 원래 name의 구분 |
| Resource/Template/Prompt | Server ID + 하위 유형 + uri/uriTemplate/name | 각각 resource/resource_template/prompt 구분, 원천 값 보존 |
| Skill | 환경·프로필 범위 + 정규화한 설치 위치 + 원천 식별자 | 동명 설치본·섀도잉·설치 위치 이동 처리 |
| Plugin | 환경·프로필 범위 + 정규화한 설치 위치 + manifest ID | 같은 Plugin ID의 복수 설치본 구분 |
| Permission/Auth | 환경·프로필 범위 + 원본 설정 위치 + 설정 키 + 하위 유형 | permission/authentication 수집 단위, 비밀값 제외 |

부모 ID는 환경·프로필·등록 주체 등 부모 식별에 필요한 범위를 포함한 완전한 ID다. 서버 이름만으로 대체하지 않는다. Gateway·Node의 device identity는 팀 댓글의 제안이며 실제 출력 검증 전 확정 값으로 취급하지 않는다. 식별값이 부족하면 임의 이름이나 공통 unknown 값으로 ID를 만들지 않고 식별 미완료 관측으로 남긴다.
원본 설정 위치: 추가 합의 필요.

## 만약 안정적인 고유 식별자가 아예 없는 자산이 있다면

```text
① 원천에서 안정적인 고유 ID 제공
        ↓ 없으면
② 안정적인 속성 조합
        ↓ 어려우면
③ 부모 자산 ID + 원천 이름
        ↓ 이것도 변경되면
④ 새로운 자산으로 판단
```

### 방법 1 - 자산의 안정적인 원천 식별 정보 조합

자체 고유 ID는 없지만, 원천에서 해당 자산을 안정적으로
구분할 수 있는 식별 정보가 여러 개 존재하는 경우 이를 조합한다.

```text
선언 주체의 완전한 ID
+ 원본 설정 위치
+ 서버 등록 키
```

등 **어떤 등록 항목을 같은 자산으로 관리할지 정한 값**을 조합한다. 단순히 자주 바뀌지 않는다는 이유로 속성을 식별 키에 넣지는 않는다.

```text
Gateway의 환경·프로필을 포함한 ID
+ 설정 파일 식별자 및 mcp.servers 경로
+ filesystem 등록 키

→ 동일 자산 판단 기준
```

`description`, 상태, 관찰 시각, 버전, 파일 내용 해시는 식별 기준에서 제외한다. `command`, `endpoint`, 패키지 정보도 기본적으로 변경 비교 속성으로 둔다. 같은 등록 키의 URL·실행 명령 수정이 자동으로 새 자산이 되지 않도록 한다. 실제 배후 서비스가 동일하다는 보장은 별개의 문제다. 비밀값과 비밀값 해시를 ID 입력에 넣지 않는다.

#### 조합의 대표 사례 - 부모 자산 ID + 자식의 원천 식별 이름

자산 자체에서 충분한 식별 정보를 확보하기 어려운 경우,
부모 자산의 완전한 ID와 자식의 원천 이름·키를 조합해 식별한다.

안정적인 속성도 없다면:

```text
MCP Server
→ 선언 주체의 완전한 ID + 원본 설정 위치 + Server 등록 키

Tool
→ MCP Server ID + Tool name

Prompt
→ MCP Server ID + Prompt name

```

처럼 부모 범위 안에서 원래 식별 이름으로 구분한다. Gateway뿐 아니라 Node가 선언한 서버도 같은 원칙을 적용한다.

구현은 간단하지만 이름이 변경되면 새로운 자산으로 판단하게 될 수 있음.

### 방법 2 - 유사 자산 매칭

이름이 변경되더라도:

```text
기존 filesystem
새로운 local-files

package 동일
command 동일
endpoint 동일

→ 동일 자산일 가능성이 높음
```

처럼 여러 속성을 비교해서 기존 자산과 연결.

`동일 가능성 80%` 같은 애매한 상황이 발생할 수 있어서 **프로젝트 범위에는 복잡할 가능성이 큼**.

# 3. 이름 변경 처리

## 정책 A - 식별 기준이 바뀌면 새 자산

```text
filesystem
→ local-files

이전 ID의 제거·미관측 여부는 수집 완전성을 확인해 판정
새 ID 생성
```

우선 제안하는 방식이다. 같은 출처·수집 범위·인증 맥락의 목록을 끝까지 성공적으로 읽었을 때만 이전 항목을 ‘해당 목록에서 제거됨’으로 판정한다. 실패·부분 수집이면 미관측으로 남긴다. 새 ID 생성만으로 이전 자산의 설치 삭제를 확정하거나 과거 기록을 지우지 않는다.

## 정책 B — 다른 안정적인 식별값이 같으면 기존 자산

```text
name 변경
filesystem → local-files

server_id 동일
srv-001 → srv-001

→ asset_id 유지
```

이는 표시 이름만 바뀌고 실제 식별 기준은 유지되는 경우다. Tool name이나 서버 등록 키 자체를 식별에 사용한다면 그 값의 변경에는 정책 A를 적용한다. 정책 B와 A는 서로 다른 변경 상황에 적용된다.

## 정책 C — 변경 이력까지 관리

```text
asset_id = 동일

name_history:
filesystem
→ local-files
```

name_history는 이력 저장 기능이며 이름이 바뀐 두 레코드가 같은 자산이라는 근거를 대신하지 않는다. 먼저 정책 A/B로 동일성을 결정하고 이력 저장 방식은 별도로 정한다. 유사성만으로 기존 ID에 자동 병합하는 방식은 이번 초안에서 제외한다.

# 4. 추가 논의 - DB 초기화 후 재현성

**수집 결과 DB만 초기화하고 원천 식별값이 유지되면 동일 ID를 생성하는 것을 권장한다.** OpenClaw의 신원 저장소 초기화·재설치로 device identity 자체가 바뀌는 경우까지 동일 ID를 보장한다는 뜻은 아니다.

| 선택 | 의미 |
| --- | --- |
| **재현성 필요** | 같은 원천 자산 → DB를 초기화해도 같은 `asset_id` |
| **재현성 불필요** | 같은 자산이어도 새 DB에서는 새로운 `asset_id`가 나올 수 있음 |

예를 들어 테스트베드가 그대로인 상황에서

```text
[Testbed]
Gateway A
└─ filesystem MCP Server
   └─ read_file Tool
```

첫 번째 스캔:

```text
Gateway     → gateway:env-a:profile-a:gw-a
MCP Server  → mcp_server:env-a:profile-a:gw-a:config-main:mcp.servers:filesystem
Tool        → tool:env-a:profile-a:gw-a:config-main:mcp.servers:filesystem:read_file
```

그 다음 DB를 삭제하고 새로 만든 뒤 똑같은 테스트베드를 다시 스캔했을 때:

```text
Gateway     → gateway:env-a:profile-a:gw-a
MCP Server  → mcp_server:env-a:profile-a:gw-a:config-main:mcp.servers:filesystem
Tool        → tool:env-a:profile-a:gw-a:config-main:mcp.servers:filesystem:read_file
```

와 같이 같은 결과가 나오면 재현이 가능한 것.

반대로 DB에서 순번이나 랜덤 ID 발급:

```text
1차 스캔
filesystem → ast_001

DB 초기화

2차 스캔
filesystem → ast_017
```

처럼 될 수 있다. → (실제 자산은 같지만 ID가 달라짐)

**검토하는 이유**

Ground Truth를 만들고 Scanner 결과와 비교해야하기 때문에

Ground Truth:

```text
{
  "asset_id": "tool:env-a:profile-a:gw-a:config-main:mcp.servers:filesystem:read_file"
}
```

Scanner 결과:

```text
{
  "asset_id": "tool:env-a:profile-a:gw-a:config-main:mcp.servers:filesystem:read_file"
}
```

이면 바로 비교 가능

하지만 DB를 초기화할 때마다 결과가 달라지면, 같은 자산인데도 ID만 보고 비교가 불가능하므로 별도의 매핑 작업 필요.

재현 필요의 경우엔 ID 표현 방식의 D안 우선순위 내려갈 예정

이번 협의에서 확인할 사항
1. B안(Canonical Key + Hash)을 공통 ID 방식으로 사용할지
2. DB 초기화 후 동일 ID 재현을 요구할지
3. 자산 유형별 식별 정보 후보를 실제로 수집할 수 있는지
4. 식별 키 변경 시 새 ID를 생성하는 정책에 동의하는지
5. B안 채택 시 SHA-256 및 canonical key 직렬화 규칙을 적용할 수 있는지