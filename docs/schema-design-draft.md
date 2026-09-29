# Agent Scope 스키마 설계 항목 초안

> 작성일: 2026-09-24 · 상태: 팀 검토용 제안 v0.1
> 목적: 어느 부분에 어떤 데이터 계약이 필요한지 정리하고, 스캐너·대시보드·QA가 먼저 합의할 항목을 선정한다. 아래 이름과 필드는 제안이며 확정된 구현 스키마가 아니다.

## 1. 설계 기준과 범위

**가장 먼저 정할 스키마는 스캐너 출력이자 대시보드 입력인 `InventorySnapshot`이다.** 이 안에 자산, 관계, 근거, 경고, 수집 상태를 담고, 각 객체의 세부 형식을 나누어 정의한다. 아래 목록은 논리적인 스키마 구분이며, 각각을 별도 DB 테이블이나 파일로 만들자는 뜻은 아니다.

검토한 근거 문서:

- [공격 표면 정의 v2.0](mcp-attack-surface.md): 9~12장의 식별자, 정점·관계, 근거, 최소 수집 필드.
- 위협 시나리오（내부 자료: 위협시나리오.md）: S1~S5의 탐지 입력, 기대 경고, 검증 방법.
- QA Ground Truth（내부 자료: QA/QA_GroundTruth.md）: 정답 자산·관계·경고 및 증적 비교.
- QA 테스트 계획（내부 자료: QA/QA_테스트계획.md）: 계약 검증, 비밀값 미수집, 재현성 및 지표.
- 2026-09-22 회의록（내부 자료: 회의록/20260922.md）: 스캐너–대시보드 출력 계약과 선언·광고 계층 논의.
- README（내부 자료: 2026-agent-scope/README.md）: 공통 인터페이스 변경 시 관련 담당자 확인 원칙.

IDE에 열린 AI 보안 가이드북 PDF는 이번 초안에서 본문을 검토하지 못했으므로, 특정 보안 요구사항이나 페이지를 근거로 인용하지 않았다. 가이드북 통제항목과 탐지 규칙의 매핑은 후속 검토 대상으로 둔다.

적용 원칙:

1. 직접 수집 정점은 Gateway, Node, MCP Server, Tool, Resource/Prompt, Skill, Plugin의 7종이다.
2. 공급망(B)과 권한·자격증명(C)은 자산 속성이다. 별도 공격 표면이나 독립 정점으로 늘리지 않는다.
3. 정적 스냅샷과 잠재 관계를 기록한다. 실제 호출·접근·전송·토큰 사용량은 후속 범위다.
4. 시나리오 ID는 현재 `위협시나리오.md`를 따른다. 회의록의 후보 S1~S5와 번호·내용이 다르므로 혼용하지 않는다.
5. 회의록의 결정란이 비어 있는 논점은 합의 완료로 간주하지 않는다. 특히 광고 목록의 온라인 수집 방식은 결정이 필요하다.

## 2. 필요한 스키마 전체 목록

우선순위는 **P0: 모듈 간 계약을 위해 먼저 정의**, **P1: MVP 탐지·검증 구현 전에 정의**, **P2: 후속 기능 구현 시 정의**로 구분한다. P1도 MVP에 필요한 항목이다.

| ID | 필요한 부분 | 스키마 제안 | 용도 | 주요 필드 후보 | 우선순위 |
|---|---|---|---|---|---|
| SC-01 | 스캐너 → 대시보드·QA | `InventorySnapshot` | 한 번의 수집 결과를 전달하는 공통 최상위 계약 | `schema_version`, `snapshot_id`, `environment_id`, `scan`, `assets`, `relations`, `evidence`, `findings`, `assessment_results`, `collection_results`, `policy_ref` | P0 |
| SC-02 | 모든 자산의 공통 구조 | `AssetBase` | 7종 자산의 식별·소속·관찰 정보 통일 | `asset_id`, `asset_type`, `asset_subtype`, `name`, `official_identifier`, `owner_ref`, `evidence_refs`, `mcp`, `product`, `project` | P0 |
| SC-03 | Gateway·Node 수집 | `GatewayNodeDetails` | 서버 선언 위치, 실행 환경, Agent 식별 연결 | `instance_id`, `node_role`, `config_ref`, `agent_refs`, `product_version` | P0 |
| SC-04 | MCP Server 수집 | `ServerDetails` | 서버 식별, 연결 보안, 규격·capability 표현 | `server_id`, `declaration_owner_ref`, `declaration_ref`, `transport`, `endpoint`, `command`, `args`, `tls_verification`, `protocol_version`, `client_capabilities`, `server_capabilities`, `extensions` | P0 |
| SC-05 | Tool 수집 | `ToolDefinition` | 공식 정의를 보존하고 서버별 동명 Tool 구별 | `server_id`, `name`, `title`, `description`, `inputSchema`, `outputSchema`, `annotations` | P0 |
| SC-06 | Resource/Prompt 수집 | `ResourcePromptDefinition` | 한 정점 유형 안에서 두 객체의 필드 구분 | `server_id`, `asset_subtype`; Resource의 `uri`, `mimeType`, `size`; Prompt의 `name`, `arguments`; 공통 `description` | P0 |
| SC-07 | Skill·Plugin 수집 | `SkillPluginDetails` | 설치 구성요소와 등록 자산 연결 | `package_id`, `installation_ref`, `entry_point`, `execution_type`, `registered_asset_refs`, `hooks`, `dependency_refs` | P0 |
| SC-08 | 자산의 공급망 속성 | `SupplyChainProfile` | 출처·무결성·업데이트 위험 기록 | `source_type`, `source_uri`, `provider`, `version`, `commit`, `integrity_status`, `modified`, `pinned`, `dependencies`, `update_policy` | P1 |
| SC-09 | 자산의 권한·인증 속성 | `PermissionProfile` | 권한 범위와 자격증명 공유·격리 표현 | `credentials[]`, `filesystem_permissions`, `network_permissions`, `process_identity`, `sandbox`, `command_permissions`, `data_permissions`, `approval_policy`, `tool_filter` | P1 |
| SC-10 | Agent별 노출 판정 | `ExposureAssessment` | 선언·발견·노출·잠재 호출 상태와 판정 맥락 기록 | `asset_ref`, `agent_ref`, `declared`, `discovered`, `exposed`, `potentially_callable`, `policy_ref`, `reason`, `evidence_refs` | P0 |
| SC-11 | 자산 그래프의 관계 | `Relation` + `TargetRef` | 6종 MVP 관계 및 비정점 대상 표현 | `relation_id`, `relation_type`, `source_asset_ref`, `target`, `evidence_refs`, `confidence`, `inference_rule`, `policy_ref` | P0 |
| SC-12 | 수집·추론 근거 | `Evidence` | 자산·관계·경고에서 원천을 역추적 | `evidence_id`, `evidence_type`, `source_ref`, `field_path`, `observed_at`, `collection_context_ref`, `redaction_status` | P0 |
| SC-13 | 수집 실행·실패 처리 | `ScanRun` + `CollectionResult` | 미수집과 실제 빈 목록을 구분하고 재현 조건 기록 | `scan_id`, `scanner_version`, `started_at`, `finished_at`, `target_ref`, `layer`, `method`, `status`, `error_code`, `auth_context_ref`, `catalog_hash`, `capability_hash` | P0 |
| SC-14 | 탐지 기준 입력 | `PolicyBaseline` | 승인 목록·최소 권한·정책의 비교 기준 | `policy_id`, `version`, `approved_servers`, `approved_endpoints`, `trusted_providers`, `allowed_scopes`, `expected_audiences`, `approval_requirements`, `baseline_snapshot_ref` | P1 |
| SC-15 | 위협 탐지 규칙 | `DetectionRule` | S1~S5의 판정 조건·필수 입력·출력 코드 정의 | `rule_id`, `rule_version`, `scenario_id`, `required_fields`, `condition`, `severity`, `warning_code`, `missing_data_behavior` | P1 |
| SC-16 | 탐지 실행 결과·경고 | `AssessmentResult` + `Finding` | 평가 불가와 정상 구분, 경고의 근거·영향 자산 표시 | 평가: `rule_ref`, `subject_refs`, `status`, `reason`; 경고: `finding_id`, `warning_code`, `scenario_id`, `severity`, `asset_refs`, `relation_refs`, `evidence_refs`, `confidence`, `message` | P1 |
| SC-17 | QA 정답 데이터 | `GroundTruthDataset` | 수동 정답과 실제 출력 비교 | `gt_version`, `environment_id`, `baseline_snapshot_ref`, `expected_assets`, `expected_relations`, `expected_findings`, `forbidden_findings`, `id_mapping`, `evidence_refs` | P1 |
| SC-18 | QA 실행 결과 | `QARunResult` | 재현 조건, 통과 여부, 누락·오탐·지표 기록 | `run_id`, `test_case_id`, `gt_version`, `actual_snapshot_ref`, `versions`, `status`, `missing_items`, `unexpected_items`, `metrics`, `defect_refs` | P1 |
| SC-19 | 스냅샷 비교·변경 이력 | `SnapshotDiff` | 추가·삭제·정의·권한 변경 기록 | `before_snapshot_ref`, `after_snapshot_ref`, `comparison_context`, `added`, `removed`, `changed`, `field_changes` | P2 |
| SC-20 | 런타임 관찰·사용량 | `RuntimeEvent` + `UsageRecord` | 실제 호출·접근과 토큰 사용량의 후속 연결 | `event_id`, `trace_id`, `asset_ref`, `method`, `timestamp`, `outcome`, `usage_scope`, `input_tokens`, `output_tokens`, `attribution_method` | P2 |

## 3. 핵심 스키마별 초안 결정 사항

### 3.1 공통 출력과 데이터 소유권

스캐너·분석기가 만든 `InventorySnapshot`을 대시보드와 QA가 함께 소비하도록 한다. 대시보드는 동일한 자산을 별도 ID로 다시 생성하지 않는다. 화면 좌표·색상·접힘 상태는 화면 설정으로 관리하며 보안 분석의 원본 데이터와 분리한다.

권장 구조는 다음과 같다. 실제 JSON Schema 파일은 이 목록을 검토한 뒤 작성한다.

```text
InventorySnapshot
├── schema_version / snapshot_id / environment_id / policy_ref
├── scan                         # 실행 시각·수집기 버전
├── assets[]                     # AssetBase + 유형별 세부 구조
│   ├── mcp                      # 공식 객체가 있는 경우 원래 필드명 보존
│   ├── product                  # 제품 설정에서 얻은 정보
│   └── project                  # 공급망·권한·노출 등 프로젝트 정규화 정보
├── relations[]                  # 직접 정점 또는 비정점 대상 참조
├── evidence[]                   # 비밀값을 제거한 원천 참조
├── collection_results[]         # 원천별 성공·부분 성공·실패·미수행
├── assessment_results[]         # 규칙별 평가 상태
└── findings[]                   # 탐지된 위험 경고
```

공식 객체를 갖지 않는 자산에는 `mcp`를 억지로 채우지 않는다. 원본 객체의 선택 필드는 원본에서 없으면 생략한다. `inputSchema`는 Tool이 받는 입력의 형식이며, 이번에 설계할 인벤토리 전체 스키마와는 다른 대상이다.

### 3.2 식별자와 자산 유형

| 대상 | 식별 기준 제안 | 주의할 점 |
|---|---|---|
| Gateway·Node | 환경 ID + 인스턴스 식별자 | 이름만 같다고 같은 장비로 합치지 않음 |
| MCP Server | 환경 ID + 선언 주체 ID + 정규화된 선언 위치 + 서버 키 | 같은 endpoint를 쓰는 서로 다른 선언은 우선 별도 인스턴스로 보존 |
| Tool | `server_id + asset_type + name` | 서버가 다르면 동명 Tool도 별도 자산 |
| Resource | `server_id + asset_type + asset_subtype + uri` | Backend 파일·DB와 혼동하지 않음 |
| Prompt | `server_id + asset_type + asset_subtype + name` | Resource와 같은 정점 분류여도 공식 객체는 구분 |
| Skill·Plugin | 환경·설치 위치 + 공급자 + package ID | 버전은 변경 비교가 가능하도록 속성으로 보존하는 안을 제안 |

결합 키는 단순 문자열 이어붙이기로 충돌하지 않도록 정규화한 튜플을 직렬화하거나 해시한다. 알고리즘과 정규화 규칙은 구현 전에 고정한다. 수집 시각은 안정 ID에 넣지 않는다.

`asset_type` 후보는 `gateway`, `node`, `mcp_server`, `tool`, `resource_prompt`, `skill`, `plugin`이다. `resource_prompt`에서는 `asset_subtype`을 `resource` 또는 `prompt`로 필수 지정한다.

### 3.3 관계와 비정점 대상

Agent·Backend Resource·External System은 MVP 직접 수집 정점이 아니지만 관계의 대상이 된다. 따라서 모든 관계에 `target_asset_id`만 요구하면 표현할 수 없는 관계가 생긴다.

`TargetRef`를 다음 중 하나로 정의하는 안을 제안한다.

| `kind` | 필드 후보 | 사용처 |
|---|---|---|
| `asset` | `asset_ref` | `DECLARES`, `ADVERTISES`, `ASSOCIATED_WITH` |
| `agent` | `owner_asset_ref`, `agent_key` | `MAY_EXPOSE_TO` |
| `backend_resource` | `resource_kind`, `normalized_locator` 또는 `scope_category` | `MAY_ACCESS` |
| `external_destination` | `destination_kind`, `normalized_endpoint` 또는 `scope_category` | `MAY_SEND_TO` |

`asset` 참조는 반드시 같은 스냅샷의 자산으로 연결되어야 한다. 나머지는 속성 기반 대상이며 7종 자산 수에 포함하지 않는다. 대시보드에서 보조 도형으로 표시하더라도 직접 수집 자산과 시각적으로 구분한다.

정의 문서 10.3의 `CONNECTS_TO`와 10.4의 6종 MVP 관계 목록에는 차이가 있다. **초안에서는 10.4와 QA 범위의 6종만 사용**하고, 실제 연결이 확인된 것처럼 보일 수 있는 `CONNECTS_TO` 추가는 팀 검토 항목으로 남긴다.

### 3.4 권한·자격증명과 정책 기준

`PermissionProfile.credentials[]` 내부에는 `credential_ref`, `reference_namespace`, `auth_type`, `issuer`, `audience`, `resource`, `oauth_scopes`, `expiry_status`, `isolation_scope`, `subject_ref`, `target_ref`, `evidence_refs`를 후보로 둔다. 이 객체는 자산 속성이며 Credential 정점이 아니다.

- 참조 이름이 같아도 서로 다른 저장소·환경의 자격증명일 수 있다. 공유 여부는 namespace를 포함한 정규화된 참조로 판정한다.
- 참조가 다르다고 실제 비밀값도 다르다고 단정하지 않는다. 실제 비밀값을 읽어 비교하거나 비밀값의 해시를 저장하는 방식은 사용하지 않는다.
- Tool 권한이 서버에서 상속된다면 `inherited_from_ref`와 적용 정책을 기록한다. 근거 없이 서버 권한을 모든 Tool의 확정 권한으로 복사하지 않는다.
- scope 과다 판정에는 최소 필요 scope 기준이, audience 불일치 판정에는 기대 대상 API가 필요하다. endpoint 문자열만으로 기대 audience를 단정하지 않는다.
- 승인 목록이 없으면 미승인 여부는 `unknown`이다. 출처 불명과 명시적 미승인은 구분한다.

비밀값 미수집은 `credentials`에만 적용하지 않는다. `command/args`, URL 쿼리, 설명·스키마의 예시·기본값, 오류 메시지 및 증적에도 적용한다. 원문 보존과 충돌하면 비밀값 제거를 우선하고, 제거된 필드 경로와 처리 상태만 남긴다.

### 3.5 상태·근거·불완전한 수집

| 항목 | 초안 규칙 |
|---|---|
| 알 수 없는 값 | 프로젝트 정규화 필드의 `null`은 미확인, 필드 생략은 해당 없음으로 정한다. 필요하면 `unknown_reason`을 함께 기록한다. 공식 객체 내부에는 이 규칙을 강제하지 않는다. |
| 목록 | `[]`는 해당 범위를 정상적으로 수집했지만 항목이 없다는 뜻이다. 수집 실패는 `collection_results`에 기록한다. |
| 정적 상태 | `declared`, `discovered`, `exposed`, `potentially_callable`을 개별 판정으로 관리한다. 노출·잠재 호출은 Agent·정책별로 기록한다. |
| 런타임 상태 | MVP가 `CALLABLE`, `USED` 또는 실제 접근·전송을 확정하지 못하도록 검증한다. |
| 근거 신뢰도 | `confirmed`, `high`, `medium`, `low`를 사용하되, `confirmed`는 그 근거로 확인한 주장에만 적용한다. 서버가 기능을 광고했다는 사실과 기능의 안전성은 다르다. |
| 평가 결과 | `matched`, `not_matched`, `insufficient_data`, `not_applicable`, `error`를 구분한다. 경고 0개만으로 정상 판정을 하지 않는다. |
| 시각·버전 | 시각은 시간대가 포함된 문자열로 통일한다. 프로젝트 `schema_version`, 수집기 버전, `protocol_version`, 규칙·정책 버전을 구분한다. |

광고 목록은 조회 시각, 서버, 자격증명 참조·인가 맥락, 목록 종류, 페이지 수집 완료 여부를 함께 기록한다. 로컬 파일 수집과 서버 접속을 통한 목록 조회를 `collection_mode`로 구분하고, 목록 조회 성공을 Tool 호출 성공으로 해석하지 않는다.

## 4. S1~S5와 스키마 연결

| 시나리오 | 필요한 입력 스키마 | 경고 코드 | 필수 판단 기준·주의점 |
|---|---|---|---|
| S1 비인가 MCP 서버 등록 및 노출 | Server, Skill/Plugin, SupplyChain, PolicyBaseline, Exposure, Relation, Evidence | `UNAUTHORIZED_MCP_SERVER` | 승인 서버·endpoint 목록과 비교. 신규 여부는 기준 스냅샷이 있어야 판단 가능. Skill/Plugin 연관은 별도 근거로 연결 |
| S2 과도한 권한 Tool 광고 | ToolDefinition, PermissionProfile, Exposure, PolicyBaseline, Evidence | `HIGH_RISK_TOOL_EXPOSURE` | 위험 입력 필드와 선언 권한·승인 정책을 조합. `path`나 `url`이라는 이름만으로 악성을 확정하지 않음 |
| S3 Tool 이름 충돌 | AssetBase, ServerDetails, ToolDefinition, SupplyChain, PermissionProfile | `TOOL_NAME_COLLISION` | 서로 다른 서버의 동일 이름을 별도 자산으로 유지. 유사 이름 탐지는 정확 일치 규칙과 분리하고 임계값 기록 |
| S4 자격증명 과다 노출 | PermissionProfile, PolicyBaseline, Relation, Evidence | `CREDENTIAL_OVEREXPOSURE` | 정규화된 참조 공유, 최소 scope, 기대 audience/API와 격리 기준 필요. 공유만으로 고권한이라고 단정하지 않음 |
| S5 안전하지 않은 MCP 연결 | ServerDetails, SupplyChain, PermissionProfile, PolicyBaseline | `INSECURE_MCP_CONNECTION` | 원격 연결 여부·TLS 적용·검증 상태 구분. stdio의 TLS 미적용을 평문 원격 연결로 오탐하지 않음 |

모든 경고에는 `rule_id/rule_version`, `scenario_id`, 관련 자산, 근거, 신뢰도, 적용 정책 참조를 연결한다. 위험 등급과 근거 신뢰도는 별도 필드다.

S1의 현재 승인 여부 탐지는 전체 변경 이력 기능 없이 구현할 수 있다. 신규 등록 시점 판정과 Rug Pull 탐지를 포함하는 일반 `SnapshotDiff`는 후속 범위로 둔다. 추후 비교 시 인가 맥락이나 수집 완전성이 다르면 단순 삭제·변경으로 판정하지 않는다.

## 5. QA 스키마에서 먼저 정할 것

`GroundTruthDataset`은 스캐너 출력과 같은 자산·관계 의미를 사용하되, 정답 ID와 출력 ID를 별도로 유지한다. 정답은 스캐너 결과를 그대로 복사하지 않고 설정·manifest·목록 응답을 수동 검토하여 작성한다.

| 비교 대상 | 필요한 규칙 |
|---|---|
| 자산 | `GT-A-* → asset_id` 매핑, 유형·소속 서버·공식 식별자 비교, 필수 기대 속성 명시 |
| 관계 | 시작·대상·관계 유형과 증적 비교. 비정점 대상도 `TargetRef`와 같은 구조로 표현 |
| 경고 | 시나리오 활성 여부, 기대 경고 코드·대상, 발생하면 안 되는 경고, 기대 평가 상태 |
| 무결성 | ID 중복, 존재하지 않는 자산·근거 참조, 잘못된 유형 조합, 필수 필드 누락 탐지 |
| 비밀값 | 출력·로그·증적·대시보드에 테스트 비밀값이 남지 않는지 확인 |
| 지표 | 분자·분모·값을 함께 기록. 분모 0은 값 `null`과 상태 `not_applicable`로 표현하고 화면에 N/A 표시 |

Ground Truth의 예시 행이나 `TBD`는 실제 정답 집계에서 제외한다. `schema_version`이 다른 출력끼리 비교할 때는 변환 규칙 또는 비교 불가 사유를 남긴다.

## 6. 작성 순서와 팀 검토 항목

1. **공통 계약:** SC-01~07, SC-10~13의 필수 필드·자료형·ID·참조·상태 규칙부터 정한다. 스캐너 담당과 대시보드 담당이 같은 예제 스냅샷을 확인한다.
2. **탐지 계약:** SC-08~09, SC-14~16으로 공급망·권한·정책 입력과 S1~S5 경고 출력을 정의한다.
3. **검증 계약:** SC-17~18로 정상·위협·부분 수집 사례의 정답 및 기대 결과를 작성한다. JSON 형식 검증과 참조 무결성·탐지 의미 검증은 구분한다.
4. **후속 확장:** SC-19~20을 설계한다. 토큰이 세션 총량으로만 수집되면 Tool별 사용량으로 임의 배분하지 않고 관측 단위를 기록한다.

| 결정할 항목 | 초안 제안 | 관련 담당 |
|---|---|---|
| 최초 전달 방식 | JSON 스냅샷 파일을 공통 계약으로 시작. API가 필요해지면 동일 객체 재사용 | 김규민·고혜림 |
| 공식 정보·확장 정보 구분 | `mcp` / `product` / `project` 구조 | 김규민·고혜림 |
| 광고 목록 수집 범위 | 입력으로 받은 목록 스냅샷과 온라인 조회를 구분하고 허용 모드를 명시 | 김규민·박병하 |
| 비정점 대상 표현 | `TargetRef` 사용, 수집 정점은 7종 유지 | 김규민·고혜림·정서진 |
| 선언 인스턴스·설치 자산 ID | 선언 위치·설치 위치를 포함하고 버전 변경은 속성으로 관리 | 김규민·정서진 |
| `CONNECTS_TO` 포함 여부 | MVP에서는 제외하고 6종 관계 유지 | 김규민·고혜림·정서진 |
| 승인·최소 권한 기준 관리 | 버전이 있는 `PolicyBaseline`을 테스트베드와 함께 관리 | 박병하·정서진 |
| 불완전한 수집·평가 표시 | 실패·미확인·정상을 구분해 QA와 화면에서 동일하게 표현 | 김규민·고혜림·정서진 |
| 런타임 사용량의 관측 단위 | 확보 가능한 데이터에 맞춰 세션·요청·Tool 귀속을 명시 | 이정철·고혜림 |

다음 산출물은 **P0 스키마 정의 파일, 정상 스냅샷 예제, S1~S5 위험 스냅샷 예제, 부분 수집 실패 예제, 대응 Ground Truth**로 제안한다. 이 문서는 그 작성을 위한 설계 목록이며 공통 인터페이스 확정이나 구현 완료를 의미하지 않는다.

> 자료 위치 안내: 내부 자료로 표시한 문서는 이 PR에 포함하지 않았습니다.
