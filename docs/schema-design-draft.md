# Agent Scope 공통 데이터 스키마 — 팀 검토용 초안

> 작성일: 2026-09-29 · 상태: 팀 협의 전 초안
> 문서 버전: v0.2 · 문서 변경 이력 관리: Notion 예정
> 데이터 계약 버전: `0.2.0-draft` · 예제의 `schema_version`과 동일
> 설계 기준 MCP 규격: **2026-07-28**
> 대상 환경: OpenClaw 기반 테스트베드. 정확한 설치 버전·commit은 담당자가 확인하여 기록한다.

## 1. 문서 목적과 적용 범위

이 문서는 **자산 스캐너가 어떤 데이터를 출력하고, 대시보드와 QA가 이를 어떻게 읽을지** 정하기 위한 초안이다. 스키마란 전달 데이터의 필드 이름, 자료형, 필수 여부와 해석 규칙을 뜻한다. 팀원은 이 문서의 필드 표와 JSON 예제를 보고 출력 가능 여부·화면 요구사항·검증 조건을 확인한다.

`2026-07-28`은 MCP 통신 규격의 버전이다. OpenClaw 제품 버전과 프로젝트 데이터 형식의 `schema_version`은 각각 별도로 기록한다. 설계 기준 버전이 정해졌어도 실제 서버가 그 규격을 사용한다고 가정하지 않는다.

문서 버전은 설명·표·협의 내용의 변경을 추적하기 위한 값으로 본문에서 관리한다. `schema_version`은 프로그램이 주고받는 데이터 형식의 버전이다. Notion 문구 수정만으로 데이터 계약 버전을 올리지는 않으며, 필드·자료형·의미·필수 조건을 변경할 때 별도로 검토한다.

- 직접 수집 대상은 Gateway, Node, MCP Server, Tool, Resource/Prompt, Skill, Plugin의 7종이다. 각 자산의 선언·발견·노출·호출·사용 여부는 6개 상태로 구분한다.
- MCP 공식 객체는 `mcp.definition`에, OpenClaw 원천 설정은 `product.config`에 구분한다.
- 프로젝트가 만든 ID·관계·상태 판정·정규화 속성은 공식 필드와 별도로 저장한다.
- 실제 적용 MCP 버전과 설치 OpenClaw 버전을 설계 기준에서 자동 복사하지 않는다.
- 사용량·비용 및 위험 경고는 별도 계약으로 연결한다. 여기서 시나리오나 탐지 규칙을 확정하지 않는다.

공식 MCP 객체의 내부 필드는 해당 규격을 따른다. 이 문서에서 제안하는 최상위 구조, 공통 ID, 관계와 판정 필드는 프로젝트의 추가 구조다. 예제는 실제 수집 결과가 아닌 설명용 가상 데이터다.

### 1.1 데이터를 만드는 쪽과 사용하는 쪽

| 담당 영역 | 이 문서에서 확인할 내용 |
|---|---|
| 스캐너 | 원천 설정·목록을 읽어 자산 ID, 관계, 근거, 수집 결과를 출력할 수 있는지 |
| 대시보드 | 동일 ID로 목록과 그래프를 연결하고, 미확인·실패를 올바르게 표시할 수 있는지 |
| 테스트베드 | 환경 ID, 설치 버전, 정상 구성과 수집 대상 위치를 제공할 수 있는지 |
| QA | 정답 목록과 출력의 자산·관계·상태를 같은 기준으로 비교할 수 있는지 |
| 모니터링 | 이후 사용량을 연결할 때 환경 ID·자산 ID·관측 시각을 참조할 수 있는지 |

### 1.2 전체 데이터 구조

스캐너를 한 번 실행해 얻은 결과를 **스냅샷**이라고 부른다. 한 스냅샷에는 이번에 수집한 자산과 관계뿐 아니라 무엇을 근거로 수집했는지, 어느 범위를 수집하지 못했는지도 담는다.

```text
InventorySnapshot                    한 번의 수집 결과
├── 환경·버전·수집기·시각             어느 환경에서 언제 얻은 결과인지
├── assets[]                         발견·선언된 자산
│   ├── mcp.definition               MCP 서버가 제공한 공식 객체
│   ├── product.config               OpenClaw에 저장된 설정
│   └── project                      상태 판정·자격증명 참조·공급망 해석
├── relations[]                      자산 연결과 잠재 접근 관계
├── evidence[]                       설정·응답 등 판단 근거의 참조
└── collection_results[]             대상별 수집 성공·부분 성공·실패
```

예를 들어 설정에 서버가 등록돼 있고 그 서버의 Tool 목록에서 `search_docs`를 찾았다면, 서버와 Tool을 각각 자산으로 만든다. 서버가 Tool을 광고한다는 관계를 연결하고 설정·목록 응답을 근거로 남긴다. 목록을 얻었다는 사실만으로 Tool 실행 성공까지 판정하지 않는다.

### 1.3 표를 읽는 방법

| 표기 | 뜻 |
|---|---|
| string / number / boolean | 문자열 / 숫자 / true 또는 false |
| object | 이름과 값을 가진 중첩 객체 |
| `Asset[]`, `string[]` | 자산 객체 목록, 문자열 목록 |
| 필수 O | 해당 객체에 반드시 있어야 하는 필드 |
| 조건부 | 표에 적힌 조건을 충족하면 필요한 필드 |
| null | 확인할 수 없는 값. 허용한 필드에서만 사용 |
| `_ref`, `_refs` | 다른 객체나 증적의 ID를 가리키는 참조, 참조 목록 |

명시하지 않은 필드는 선택이다. 필수인 객체 안에도 선택 필드가 있을 수 있다. 예를 들어 `project`와 그 안의 `state_assessments` 배열은 필수지만 `supply_chain`은 선택이다.

## 2. 최상위 InventorySnapshot

| 필드 | 자료형 | 필수 | 의미 |
|---|---|---|---|
| `schema_version` | string | O | 예제는 `0.2.0-draft` |
| `snapshot_id` | string | O | 수집 실행마다 새 ID, 재전송은 유지 |
| `environment_id` | string | O | 테스트베드의 논리 환경 ID |
| `basis` | object | O | 설계 기준. `mcp_spec_version: "2026-07-28"` |
| `environment` | object | O | `openclaw_version`, `openclaw_commit`: string 또는 null. 미확인이면 `version_note` 필수 |
| `producer` | object | O | 수집기 `name`, `version` 문자열 |
| `generated_at` | string | O | UTC 시각 |
| `scan` | object | O | `started_at`, `finished_at`, `status` |
| `assets` | Asset[] | O | 직접 수집 자산 |
| `relations` | Relation[] | O | 근거가 있는 관계 |
| `evidence` | Evidence[] | O | 안전하게 보관한 원천 참조 |
| `collection_results` | CollectionResult[] | O | 실행 대상으로 정한 범위별 수집 결과 |

시각은 시간대를 포함한 UTC 문자열이다. 미확인은 허용한 필드에서만 null로 표현한다. 선택 필드 생략은 미제공이며 안전·없음·false를 의미하지 않는다. 빈 배열만으로 정상적인 빈 수집을 판정하지 않는다.

## 3. Asset 공통 구조와 7종 매핑

| 필드 | 자료형 | 필수 | 규칙 |
|---|---|---|---|
| `asset_id` | string | O | 반복 수집 시 유지하는 ID |
| `asset_type` | string | O | 아래 7종 |
| `asset_subtype` | string | 조건부 | resource_prompt면 resource 또는 prompt |
| `name` | string | O | 표시 이름 |
| `owner_ref` | string | 조건부 | Server는 선언 Gateway/Node, Tool·Resource/Prompt는 소속 Server |
| `evidence_refs` | string[] | O | 하나 이상의 근거 ID |
| `mcp` | object | 조건부 | 공식 객체가 수집됐을 때 |
| `product` | object | 조건부 | OpenClaw 설정·설치 원천이 있을 때 |
| `project` | object | O | `state_assessments[]` 필수. 선택 정규화 속성 포함 |

| asset_type | 원천·저장 내용 | 식별 기준 제안 |
|---|---|---|
| `gateway` | 안전한 Gateway 설정과 인스턴스 정보 | 환경 + 인스턴스 |
| `node` | Node 설정·식별 정보. 정확한 원천 키는 설치 버전 확인 후 | 환경 + Node 식별자 |
| `mcp_server` | 선언 위치·서버 설정, 확보한 발견 응답 | 선언 주체 + 선언 위치 + 서버 키 |
| `tool` | 공식 Tool 객체 | 서버 ID + 유형 + name |
| `resource_prompt` | 공식 Resource 또는 Prompt 객체 | 서버 ID + 하위 유형 + uri 또는 name |
| `skill` | 설치·SKILL.md·설정 근거 | 환경 + 설치 위치 + 패키지 식별자 |
| `plugin` | manifest·설치·설정 근거 | 환경 + 설치 위치 + Plugin ID |

ID는 환경·소속·원천 식별자를 일정한 규칙으로 조합해 만든다. 문자열 결합·해시 등 구체적인 생성 방법은 구현 담당과 합의한다. 수집 시각·제품 버전은 자산 ID에 넣지 않는다. 다른 서버의 동명 Tool은 별도 자산이다. 서버를 참조할 때는 서버 자산의 `asset_id`를 사용한다.

예: `srv-A`의 `search`와 `srv-B`의 `search`는 서로 다른 Tool ID를 갖는다. 같은 환경에서 다시 수집한 `srv-A`의 `search`는 자산 ID를 유지하고, 이번 실행 결과를 구분하는 snapshot_id만 바뀐다. 예제의 `srv-01`, `tool-01`은 설명용 ID다.

## 4. MCP 공식 객체 저장

`mcp` 포장은 프로젝트 필드이며 내부 공식 객체와 구분한다.

| 필드 | 자료형 | 규칙 |
|---|---|---|
| `protocol_version` | string 또는 null | 실제 수집에 적용된 규격. null이면 `version_note` 필수 |
| `definition` | object | Tool·Resource·Prompt의 공식 객체, 해당 자산에서 필수 |
| `discovery` | object | Server의 공식 발견 결과를 확보했을 때 선택 |

공식 필드 확인표:

| 객체 | 공식 필수 필드 | 선택 필드 예 |
|---|---|---|
| Tool | `name`, `inputSchema` | title, description, outputSchema, annotations, icons, _meta |
| Resource | `name`, `uri` | title, description, mimeType, size, annotations, icons, _meta |
| Prompt | `name` | title, description, arguments, icons, _meta |

필드명·자료형·중첩 구조를 임의로 바꾸지 않는다. Tool 입력 스키마와 프로젝트 전달 스키마는 다르다. 목록 응답은 개별 definition이 아닌 증적에 보관한다. 페이지별 응답·요청 메타데이터와 인가 맥락을 증적에 연결해 목록의 완전성을 확인한다. 이 표가 공식 선택 필드를 삭제하는 기준은 아니다.

공식 기준은 [MCP 2026-07-28 Schema](https://modelcontextprotocol.io/specification/2026-07-28/schema)다. ResourceTemplate은 URI에 매개변수를 넣어 리소스를 찾는 템플릿이다. 우선 목록 증적으로 보관하며 직접 자산으로 표시할지는 별도로 합의한다.

## 5. OpenClaw 원천 설정 저장·매핑

`product`의 필수 하위 필드는 `name: "openclaw"`, `source_ref`, `config_path`이다. 설정을 수집했을 때 `config`를 포함한다. `config_path`는 안전하게 정규화한 원천 내부 키 경로이며 운영 파일 전체 경로일 필요는 없다. 설치 파일 원천은 해당 문서 내부 위치로 표시한다.

다음 자료형은 프로젝트 수집 계약의 후보다. 설치 버전 검증 전 OpenClaw의 모든 허용 타입을 대체하지 않는다. 값이 명시됐을 때 보존하고 생략된 값을 임의 기본값으로 채우지 않는다.

| OpenClaw 원천 | 저장 위치 | 후보 자료형 | 처리 |
|---|---|---|---|
| `mcp.servers.<name>.enabled` | Server `product.config.enabled` | boolean | 명시 값 보존 |
| `.command`, `.args` | `product.config.command/args` | string, string[] | 비밀값 포함 부분 제거 |
| `.url`, `.transport` | `product.config.url/transport` | string | 원격 주소·전송 원천 유지 |
| `.sslVerify` | `product.config.sslVerify` | boolean | 생략을 false로 바꾸지 않음 |
| `.requestTimeoutMs`, `.connectionTimeoutMs` | 같은 이름 | number | 단위 ms 유지 |
| `.supportsParallelToolCalls` | 같은 이름 | boolean | 힌트를 실행 사실로 해석하지 않음 |
| `.auth`, `.oauth.identity`, `.oauth.scope` | 같은 중첩 경로 | string | 선언값 보존, 인증 성공과 구분 |
| `.toolFilter.include/exclude` | 같은 중첩 경로 | string[] | 정확 이름·패턴 원형 유지 |
| `.codex.agents`, `.codex.defaultToolsApprovalMode` | 같은 중첩 경로 | string[], string | 해당 런타임에서만 판정에 사용 |
| `skills.load`, `skills.allowBundled` | 소유 Gateway/Node의 config 하위 원천 경로 | object, string[] | 전역 정책과 개별 Skill 설정 구분 |
| `skills.entries.<key>.enabled` | Skill config.enabled | boolean | 설치 발견과 활성화 구분 |
| `plugins.enabled/allow/deny/load` | 소유 Gateway/Node의 config 하위 원천 경로 | boolean/배열/object | 전역 정책 보존 |
| `plugins.entries.<id>.enabled/hooks/llm` | Plugin config 내부 동일 경로 | boolean/object | 개별 정책 보존 |
| Header·env·apiKey·clientKey | 원문 config에서 제외, 아래 참조 메타데이터 | — | 실제 값·비밀값 해시 저장 금지 |

제품 원천: [OpenClaw 설정 문서](https://docs.openclaw.ai/gateway/config-extensions). Node 쪽 선언 경로는 별도 검증 전 고정하지 않는다.

표의 `.url`처럼 점으로 시작하는 키는 `mcp.servers.<name>` 아래 항목을 뜻한다. 예를 들어 `mcp.servers.docs.url`의 값을 서버 자산의 `product.config.url`에 저장하고, `product.config_path`에는 `mcp.servers.docs`를 기록한다. 이렇게 하면 저장된 값이 어느 설정에서 왔는지 확인할 수 있다.

`toolFilter`는 도구 목록과 함께 해석한다. 도구가 목록에 있어도 필터나 대상 Agent 정책에 따라 노출되지 않을 수 있다. `codex` 하위 설정은 해당 런타임에만 적용한다. Skill·Plugin은 설치됐다는 사실과 활성화·허용됐다는 사실을 구분한다.

### 5.1 자격증명·공급망 정규화 정보

아래는 `project` 내부 선택 객체이며 OpenClaw 공식 객체가 아니다.

| 객체 | 필드 후보와 자료형 |
|---|---|
| `credential_refs[]` | `reference_id: string 또는 null`, `namespace: string`, `source_field: string`, `kind: string`, `presence: boolean 또는 null`, `evidence_refs: string[]` |
| `supply_chain` | `provider`, `package_id`, `version`, `commit`, `source_uri`: string; `integrity_status`: verified/failed/unknown; `evidence_refs: string[]` |
| `normalizations[]` | `source_field: string`, `target_field: string`, `rule_id: string`, `evidence_refs: string[]` |

reference_id를 안전하게 알 수 없으면 null과 reason을 남긴다. 같은 환경변수 이름만으로 공유 자격증명이라고 확정하지 않는다. 무결성 verified는 검증 증적이 있을 때만 사용한다. 인증서 경로 등 민감한 식별정보도 필요하면 범주·증적 ID로 치환하고 제거한 필드 경로를 증적에 남긴다.

`endpoint`, `tls_verification` 같은 별칭은 이번 초안에서 추가하지 않고 `url`, `sslVerify` 원천을 유지한다. 나중에 별칭을 추가하면 normalizations에 변환 근거를 남긴다.

## 6. 자산 상태 — 선언부터 실제 사용까지

자산 상태는 “스캐너가 성공했는가”가 아니라 **이 자산에 대해 어디까지 확인했는가**를 나타낸다.

| state | 의미 | 정적 단계 |
|---|---|---|
| `DECLARED` | 설정에 선언됨 | 설정 근거로 판정 |
| `DISCOVERED` | 설치 파일 또는 런타임 응답에서 발견됨 | 파일·목록 응답 근거로 판정 |
| `EXPOSED` | 특정 Agent/Host에 표시되거나 연결됨 | 대상·정책 확인 가능한 경우 판정 |
| `POTENTIALLY_CALLABLE` | 정적 조건상 호출 가능성이 있음 | 정적 근거와 추론 규칙으로 판정 |
| `CALLABLE` | 런타임 검증 결과 실제 호출 가능함 | 미검증 |
| `USED` | 실행 로그에서 실제 사용이 관찰됨 | 미관찰 |

`project.state_assessments[]`의 구조:

| 필드 | 자료형 | 규칙 |
|---|---|---|
| `state` | string | 위 6개 중 하나 |
| `value` | boolean 또는 null | true/false는 판정 결과, null은 미확인 |
| `evidence_refs` | string[] | true/false이면 하나 이상 |
| `reason` | string | null일 때 필수 |
| `subject_ref` | TargetRef | 대상별 true/false 판정 시 필수 |
| `policy_ref` | string | 정책 기반 판정 시 필수, 버전을 식별할 수 있어야 함 |
| `inference_rule` | string | 추론 판정 시 필수 |

비대상 판정은 subject_ref를 생략한다. 대상이 필요한 상태는 EXPOSED·POTENTIALLY_CALLABLE·CALLABLE·USED다. 미평가 상태는 배열에서 생략해도 되며 소비자는 unknown으로 취급한다. 배열이 비어 있으면 전체 미평가다. 이들은 일괄 자동 승격하는 단계가 아니라 근거별 판정이다. 이 정적 계약에서는 CALLABLE·USED에 true/false를 출력하지 않는다.

| 예 | 기록할 값 | 해석 |
|---|---|---|
| 설정에 서버 등록 확인 | DECLARED = true | 선언 근거가 있음 |
| Tool 목록에서 도구 확인 | DISCOVERED = true | 해당 시점 목록에 존재함 |
| 특정 Agent의 필터가 도구를 제외함을 확인 | 해당 Agent의 EXPOSED = false | 정책과 대상이 확인된 부정 판정 |
| Agent별 정책을 확인하지 못함 | EXPOSED = null, 사유 기록 | 미확인이므로 false와 다름 |
| 실제 호출을 검증하지 않음 | CALLABLE = null | 목록 조회 성공과 구분 |

subject_ref는 “누구에게 노출·호출 가능한가”의 대상이다. 같은 Tool도 Agent별로 다른 판정이 가능하므로 상태 하나만 전역으로 덮어쓰지 않는다.

## 7. 관계·근거·수집 결과

### Relation

관계는 그래프의 연결선에 해당한다. source_asset_ref는 시작 자산을, target은 연결 대상을 가리킨다. evidence_refs를 따라가면 그 연결을 만든 근거를 확인할 수 있다.

필수: `relation_id: string`, `relation_type: string`, `source_asset_ref: string`, `target: TargetRef`, `evidence_refs: string[]`(하나 이상), `confidence: confirmed/high/medium/low`. 추론이면 `inference_rule` 필수, 정책 기반이면 `policy_ref` 필수.

| 관계 | 출발 → 대상 |
|---|---|
| DECLARES | Gateway/Node → Server |
| ADVERTISES | Server → Tool/Resource/Prompt |
| ASSOCIATED_WITH | Skill/Plugin → Server/Tool |
| MAY_EXPOSE_TO | 관련 자산 → Agent/Host |
| MAY_ACCESS | 관련 자산 → 접근 자원 |
| MAY_SEND_TO | 관련 자산 → 외부 목적지 |

TargetRef는 다음 구조 중 하나다. 키의 값은 모두 문자열이다.

- 자산: `kind: asset`, `asset_ref`. Host 대상은 Gateway/Node여야 한다.
- Agent: `kind: agent`, `owner_asset_ref`, `agent_key`.
- 접근 자원: `kind: backend_resource`, `resource_kind`, `normalized_locator` 또는 `scope_category`.
- 외부 목적지: `kind: external_destination`, `destination_kind`, `normalized_endpoint` 또는 `scope_category`.

비정점 대상은 직접 수집 자산 수에 포함하지 않는다. confirmed는 해당 주장에 대한 근거 수준이며 안전성·실행 성공을 뜻하지 않는다.

### Evidence

근거 객체는 설정 파일·manifest·목록 응답의 내용을 어디서 확인할 수 있는지 알려준다. evidence_id는 이 스냅샷에서 근거를 참조하는 ID이고, source_ref는 실제 증적 보관 위치를 찾는 안전한 ID다. collection_ref는 그 증적을 확보한 수집 작업을 가리킨다.

필수: `evidence_id`, `evidence_type`, `source_ref`, `observed_at`, `collection_ref`, `redaction_status`(모두 string).

evidence_type은 config/manifest/protocol/schema/description/manual. redaction_status는 not_needed/redacted. 선택 필드는 `field_path: string`, `redacted_fields: string[]`. 원본에 민감정보가 있으면 안전한 증적으로 바꾸고 변경 위치를 기록한다.

### CollectionResult

수집 결과는 “어느 대상의 어느 범위를 어떤 방식으로 수집했는가”를 기록한다. 서버 설정 읽기와 Tool 목록 조회는 서로 다른 작업으로 남긴다.

| 필드 | 자료형 | 규칙 |
|---|---|---|
| `collection_id`, `source_ref`, `scope`, `collected_at` | string | 필수 |
| `target_ref` | string 또는 null | 필수. 식별 전 실패는 null과 reason |
| `mode` | string | local_file/online_catalog/imported_catalog |
| `status` | string | success/partial/failed/not_attempted |
| `protocol_version` | string 또는 null | MCP 목록·발견 수집 시 필수, 실제 적용 버전 |
| `auth_context_ref` | string 또는 null | MCP 수집 시 필수. 익명도 명시적 맥락 ID 사용 |
| `reason` | string | 실패·부분 수집·미수행 또는 null 맥락일 때 필수 |
| `error_code` | string | 선택 |

scope 후보: gateway_config/node_config/skill_files/plugin_manifest/server_discovery/tools_list/resources_list/prompts_list/resource_templates_list. 하나의 작업이 수집하도록 계획한 페이지를 모두 완료해야 success다.

전체 scan.status는 모두 success이면 success, 일부 완료·확보했지만 실패 또는 미수행이 있으면 partial, 전혀 완료·확보하지 못했으면 failed. 수집 계획이 빈 실행은 거부한다. 정상 완료한 빈 목록은 성공이다. **이 값은 6개 자산 상태와 별개다.**

| 수집 status | 뜻 | 예 |
|---|---|---|
| success | 계획한 범위를 모두 수집 | Tool 목록의 마지막 페이지까지 확인 |
| partial | 일부만 수집 | 첫 페이지는 받았으나 다음 페이지에서 실패 |
| failed | 해당 범위의 수집 실패 | 목록 요청 시간 초과 |
| not_attempted | 계획했으나 실행하지 못함 | 선행 연결 실패로 목록 요청을 시도하지 못함 |

상위 scan.status에는 success/partial/failed만 사용한다. 조회를 계획하지 않은 범위는 완료했다고 표시하지 않는다. auth_context_ref는 어떤 인증·사용자 맥락으로 조회했는지 식별하는 안전한 참조이며 토큰 값이 아니다.

## 8. 통합 정상 예제

설정과 Tool 목록만 수집한 예제다. 제품 버전은 미확인, MCP 응답은 기준 버전으로 수집했다는 가정이다. 원본 요청·페이지 응답은 source_ref가 가리키는 가상 증적에 있고 아래 definition은 Tool 객체만 포함한다.

```json
{
  "schema_version": "0.2.0-draft",
  "snapshot_id": "snap-001",
  "environment_id": "env-test-01",
  "basis": {"mcp_spec_version": "2026-07-28"},
  "environment": {"openclaw_version": null, "openclaw_commit": null, "version_note": "Reported as latest; installed version not yet recorded."},
  "producer": {"name": "asset-scanner", "version": "example"},
  "generated_at": "2026-09-29T01:00:03Z",
  "scan": {"started_at": "2026-09-29T01:00:00Z", "finished_at": "2026-09-29T01:00:02Z", "status": "success"},
  "assets": [
    {"asset_id": "gw-01", "asset_type": "gateway", "name": "Test Gateway", "evidence_refs": ["ev-config"], "project": {"state_assessments": []}},
    {
      "asset_id": "srv-01", "asset_type": "mcp_server", "name": "docs", "owner_ref": "gw-01", "evidence_refs": ["ev-config"],
      "product": {"name": "openclaw", "source_ref": "fixture-config", "config_path": "mcp.servers.docs", "config": {"url": "https://example.com/mcp", "transport": "streamable-http", "enabled": true, "sslVerify": true, "toolFilter": {"include": ["search_*"], "exclude": ["admin_*"]}}},
      "project": {"state_assessments": [{"state": "DECLARED", "value": true, "evidence_refs": ["ev-config"]}]}
    },
    {
      "asset_id": "tool-01", "asset_type": "tool", "name": "search_docs", "owner_ref": "srv-01", "evidence_refs": ["ev-tools"],
      "mcp": {"protocol_version": "2026-07-28", "definition": {"name": "search_docs", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
      "project": {"state_assessments": [
        {"state": "DECLARED", "value": null, "evidence_refs": [], "reason": "No independent Tool declaration checked."},
        {"state": "DISCOVERED", "value": true, "evidence_refs": ["ev-tools"]},
        {"state": "EXPOSED", "value": null, "evidence_refs": [], "reason": "Effective target policy not resolved."},
        {"state": "POTENTIALLY_CALLABLE", "value": null, "evidence_refs": [], "reason": "Static call conditions not assessed."},
        {"state": "CALLABLE", "value": null, "evidence_refs": [], "reason": "Runtime validation outside static collection."},
        {"state": "USED", "value": null, "evidence_refs": [], "reason": "Runtime usage not observed."}
      ]}
    }
  ],
  "relations": [
    {"relation_id": "rel-01", "relation_type": "DECLARES", "source_asset_ref": "gw-01", "target": {"kind": "asset", "asset_ref": "srv-01"}, "evidence_refs": ["ev-config"], "confidence": "confirmed"},
    {"relation_id": "rel-02", "relation_type": "ADVERTISES", "source_asset_ref": "srv-01", "target": {"kind": "asset", "asset_ref": "tool-01"}, "evidence_refs": ["ev-tools"], "confidence": "confirmed"}
  ],
  "evidence": [
    {"evidence_id": "ev-config", "evidence_type": "config", "source_ref": "fixture-config", "observed_at": "2026-09-29T01:00:01Z", "collection_ref": "collect-config", "redaction_status": "not_needed"},
    {"evidence_id": "ev-tools", "evidence_type": "protocol", "source_ref": "fixture-tools", "observed_at": "2026-09-29T01:00:02Z", "collection_ref": "collect-tools", "redaction_status": "not_needed"}
  ],
  "collection_results": [
    {"collection_id": "collect-config", "source_ref": "fixture-config", "scope": "gateway_config", "target_ref": "gw-01", "mode": "local_file", "status": "success", "collected_at": "2026-09-29T01:00:01Z"},
    {"collection_id": "collect-tools", "source_ref": "fixture-tools", "scope": "tools_list", "target_ref": "srv-01", "mode": "online_catalog", "status": "success", "collected_at": "2026-09-29T01:00:02Z", "protocol_version": "2026-07-28", "auth_context_ref": "anonymous-test"}
  ]
}
```

목록 수집은 성공했지만 노출·호출 가능 여부는 미확인이다. 필터에 이름이 맞는 것만으로 EXPOSED나 CALLABLE을 true로 만들지 않았다.

### 예제를 화면과 연결해 읽기

1. `assets`의 세 항목으로 Gateway·Server·Tool을 표시한다.
2. `relations`의 두 항목으로 Gateway → Server → Tool 연결을 표시한다.
3. 서버 상세에서는 `product.config`의 주소·전송·TLS·필터 설정을 보여준다.
4. Tool 상세에서는 `mcp.definition`의 이름·입력 구조를 보여준다.
5. 상태에는 “발견됨 / 노출 여부 미확인 / 실제 호출 미검증”을 구분해 표시한다.
6. 근거 보기를 선택하면 `evidence_refs` → `evidence.source_ref`로 연결한다.
7. 수집 요약에는 설정과 Tool 목록 수집 성공을 표시한다. Resource·Prompt까지 수집했다고 표시하지 않는다.

## 9. 실패·경계 사례의 기대 출력

| 상황 | 출력·표시 규칙 |
|---|---|
| 설정 성공, Tool 목록 시간 초과 | 전체 partial. Gateway·Server와 DECLARES만 유지. tools_list는 failed와 TIMEOUT, Tool과 ADVERTISES는 이번 결과에서 생성하지 않음 |
| 위 실패 후 이전 Tool 존재 | 이전 스냅샷에서 확인 가능. 이번 누락을 삭제로 판정하지 않음 |
| 정상 조회 후 Tool 빈 목록 | tools_list success와 Tool 0개. 실패와 구분 |
| 서버 선언이 enabled false | DECLARED는 true 가능. 비활성 근거만으로 모든 범위의 사용 이력 부재를 확정하지 않음 |
| 동일 이름의 Tool을 다른 서버에서 발견 | 각각 다른 ID와 owner_ref |
| 실제 MCP 버전이 기준과 다름 | 실제 버전 기록. 해당 버전 어댑터가 없으면 지원 불가로 기록하고 기준 버전 객체로 위장하지 않음 |
| 민감 필드 제거로 원천 객체가 달라짐 | redacted_fields와 증적 기록. 변환된 사본을 수정 없는 원본이라고 표시하지 않음 |

## 10. 데이터 수용·검증 규칙

1. ID 중복·없는 참조·잘못된 관계 양끝·필수 필드 누락은 계약 오류로 거부한다. 유효한 partial 결과는 수용한다.
2. project 상태의 true/false에는 근거가 있어야 한다. 정적 출력에서 CALLABLE·USED의 확정을 금지한다.
3. 제품 원천 이름과 공식 MCP 내부 필드를 보존하고, 정규화에는 변환 근거를 남긴다.
4. 생산자·대시보드·QA가 같은 정상·실패 예제로 표시와 비교 결과를 확인한다.
5. 설치 OpenClaw 버전·Node 설정 경로·실제 MCP 지원 버전·ID 생성 알고리즘·증적 저장 위치를 담당자가 확정한다.

계약 오류는 데이터 형식 자체가 잘못된 경우다. 수집 실패는 형식이 올바른 결과 안에 실패 상태가 기록된 경우다. 대시보드는 전자는 오류 위치를 알리고 거부하며, 후자는 수집 한계를 표시하면서 읽는 방식을 제안한다.

## 11. 팀에서 확인하고 결정할 사항

| 결정할 내용 | 초안의 제안 | 확인 담당 | 합의 결과 |
|---|---|---|---|
| 필수 출력 묶음 | 자산·관계·근거·수집 상태를 함께 제공 | 스캐너·대시보드·QA | |
| 최초 전달 방식 | JSON 파일로 먼저 연동 확인 | 스캐너·대시보드 | |
| ID 생성 규칙 | 환경·소속·원천 식별자 기반으로 재수집 ID 유지 | 스캐너·테스트베드 | |
| 상태 판정 범위 | 정적 근거로 판정 가능한 상태부터 제공, 미확인은 null | 스캐너·QA | |
| 실제 버전·설정 위치 | OpenClaw 설치 버전과 Gateway/Node 원천 확인 | 테스트베드·스캐너 | |
| 증적 보관·조회 | 안전한 증적 ID로 연결, 저장 위치와 조회 방법 지정 | 스캐너·대시보드·QA | |
| 유형별 수집 가능 필드 | 실제 예제로 필수·선택 필드 조정 | 스캐너 | |
| 부분 실패 표시 | 최신 결과에 실패 범위를 표시하고 이전 스냅샷은 별도 조회 | 대시보드·QA | |
| 계약 관리 | 정리 담당·검토 담당·예제 제출일 지정 | 전체 | |

공유할 예제는 정상 수집, Tool 목록 실패, 다른 서버의 동명 Tool 세 가지다. 현재 8절은 정상 수집 예제이며 9절은 실패·경계 사례의 기대 처리 규칙이다. 담당자들은 실제 출력으로 같은 결과가 표현되는지 확인한다.

합의 후에는 필드 명세를 기계 검증용 JSON Schema로 옮기고, 예제와 함께 생산자·소비자·QA에서 검증한다. 아직 원천 예제가 없는 자산 유형의 세부 필수 필드는 확인 필요로 남긴다.

### 11.1 이 문서로 정할 수 있는 범위와 남은 명세

이 문서는 **정적 자산 스캐너와 대시보드·QA 사이의 공통 계약을 정하기 위한 출발안**이다. 프로젝트 전체 모듈의 필드를 빠짐없이 정의한 최종 명세는 아니다.

| 범위 | 현재 준비된 내용 | 확정 전에 필요한 작업 |
|---|---|---|
| 공통 전달 구조 | 스냅샷·ID·자산·관계·근거·수집 결과·6개 자산 상태 | 생산자·소비자 검토, 참조·오류·버전 호환 규칙 최종 합의 |
| 7종 자산 상세 | 공통 필드, 유형별 원천과 식별 기준 | Node·Skill·Plugin 등을 포함한 실제 예제, 상세 필수 조건과 허용값 확정 |
| MCP 공식 객체 | 공식 정의를 저장할 위치와 주요 필드 | 적용 규격의 전체 중첩 타입을 검증기에 연결 |
| 제품 설정·분석 속성 | OpenClaw 원천 매핑, 자격증명·공급망 후보 | 설치 버전별 타입·기본값 확인, 파일·네트워크·실행 권한 및 적용 정책의 상세 구조 |
| 보안 점검 결과 | 자산·근거와 연결할 방향 | 생성 담당, 평가·경고 객체와 규칙·정책 참조 계약 별도 정의 |
| 사용량·비용 | 환경·자산 ID로 연결할 방향 | 관측 단위, 측정·추정, 귀속·집계·단가 필드 별도 정의 |
| QA 결과 | 공통 데이터 검증 기준 | 정답·실행 결과·지표·결함 연결의 저장 형식 별도 정의 |

따라서 공통 구조는 이 문서를 보며 합의하고, 각 파트의 실제 예제로 세부 명세를 채운다. 전체 스키마 확정은 필요한 모듈별 계약과 실패·경계 예제까지 검토한 뒤 판단한다.
