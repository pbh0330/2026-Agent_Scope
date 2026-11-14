# AI Agent Asset Visualization Dashboard Specification

> AI 에이전트 자산 가시화 대시보드 설계 및 구현 규격

| 항목 | 값 |
|---|---|
| 문서 버전 | **v2.0** (2026-11-15) · v1.0: 2026-10-01 |
| 작성 | 고혜림 (대시보드·위협 시나리오) |
| 기준 데이터 계약 | 공통 스키마 `0.7.0-draft` (문서 [schema-design-draft.md](../schema-design-draft.md) v0.7.5, PR #18) |
| 기준 위협 규칙 | 위협 시나리오 v2.1 ([docs/threat-scenarios](../threat-scenarios/README.md), PR #7) |
| 구현 | `dashboard/` (PR #13) |
| 적용 범위 | OpenClaw + MCP 환경의 정적 자산·관계·보안 평가 가시화, 토큰 사용량 표시 |

v2.0은 v1.0의 자체 데이터 모델(대문자 유형, 단일 상태, `PROVIDES`·`CONNECTS_TO` 관계, `Normal/Warning/High`)을 **공통 스키마 0.7로 바꾸고**, 실제 구현된 화면 8개를 기준으로 다시 썼다. v1.0 표기와의 대응은 [15절](#15-v10--v20-변환)에 있다.

---

## 1. 목적

대시보드는 스캐너·테스트베드·탐지·토큰 수집기 결과를 한 화면에서 보고, 다음 질문에 답할 수 있게 한다.

1. 어떤 자산이 있고 서로 어떻게 연결되는가 (8종 자산, 관계)
2. 각 자산을 **어디까지 확인했는가** (선언 → 발견 → 노출 → … 근거와 함께)
3. 어떤 위협 조건이 **탐지됐고, 무엇은 이상 없고, 무엇은 판단할 수 없었는가**
4. 위협 시나리오 문서가 기대한 결과와 실제 탐지가 **맞는가**
5. 구성이 바뀌면 무엇이 추가·변경·사라졌는가
6. 도구 호출에 토큰이 얼마나 쓰였고 어느 자산에 귀속되는가

## 2. 설계 원칙

| 원칙 | 내용 |
|---|---|
| 근거 우선 | 모든 판정·경고·관계는 근거(evidence)로 거슬러 올라갈 수 있어야 한다. 근거 없는 간선·판정은 그리지 않는다 |
| 미확인 ≠ 정상 | `null`·`unknown`·`not_evaluated`·`error`를 "이상 없음"으로 표시하지 않는다. 수집 실패와 삭제를 구분한다 |
| 정적 우선 | 정적 분석으로 `CALLABLE`·`USED`를 판정하지 않는다. 사용 기록은 상태를 바꾸지 않고 따로 표시한다 |
| 비밀값 비수집 | 실제 비밀값은 수집·저장·표시하지 않는다. 참조 이름·저장 위치·존재 여부만 표시한다 |
| 원천 비신뢰 | 서버가 보낸 설명·스키마는 신뢰하지 않는 데이터로 그대로 표시만 한다 |
| 계약 소비자 | 대시보드는 공통 계약 파일만 읽는다. 스캐너 내부 형식은 어댑터(`pipeline/`)를 거친다 |

## 3. 데이터 흐름

```text
feature/scanner-config   스캐너: 설정 수집(mcp.servers, nodeHost.mcp.servers), --plugin-manifest, tools_catalog
testbed (develop, #24)   profiles/<구성>, ground-truth/raw/<구성>, 정답, approved-servers.json
docs/threat-scenarios    시나리오 카탈로그 v2.1, S2 기준 정책, 기대 결과
token-collector          사용 현황 API(usageapi)
          │
          ▼
dashboard/pipeline/build_data.py   어댑터 + 정적 탐지기 + 비교기
          │
          ▼
dashboard/public/data/*.json       공통 계약 파일
          │
          ▼
dashboard (React)                  화면 8개
```

토큰 사용은 API가 켜져 있으면 실시간으로 읽고(`/api/v1/usage`), 꺼져 있으면 파이프라인이 저장한 응답 사본을 읽는다.

## 4. 입력 파일

| 파일 | 공통 스키마 | 생성 | 화면 |
|---|---|---|---|
| `manifest.json` | — | 파이프라인 | 스냅샷 목록, 출처, 비교 쌍 |
| `snapshots/<구성>/snapshot.json` | 2~7절 InventorySnapshot | 어댑터 | 모든 화면 |
| `snapshots/<구성>/detections.json` | 13.1 DetectionReport | 정적 탐지기 | 개요, 보안 경고, 상세 |
| `snapshots/<구성>/expected.json` | 16.2 QAResult(checks) | 기대 결과 비교 | 기대 결과 비교 |
| `snapshots/<구성>/qa.json` | 16.2 QAResult | 정답 목록 비교(정상군) | 개요, 수집과 검증 |
| `diffs/<A>__<B>.json` | 12.5·12.9 SnapshotDiff | 비교기 | 변경 비교 |
| `scenario-catalog.json` | 13절 ScenarioDefinition | 위협 시나리오 사본 | 보안 경고, 기대 결과 비교 |
| `usage-api/*.json` | 14.3 사용 현황 API 응답 | API 응답 저장 | 토큰 사용, 상세 |

`snapshot.json`(필수)과 `detections.json`(선택)은 화면에 끌어다 놓아 바로 볼 수도 있다.

## 5. 자산 8종

| `asset_type` | 화면 표기 | 하위 유형(`asset_subtype`) | 소속(`owner_ref`) |
|---|---|---|---|
| `gateway` | Gateway | — | — |
| `node` | Node | — | — |
| `mcp_server` | MCP 서버 | — | 선언 주체(Gateway·Node·Plugin) |
| `tool` | Tool | — | 소속 서버 |
| `resource_prompt` | Resource / Prompt | `resource`, `resource_template`, `prompt` | 소속 서버 |
| `skill` | Skill | — | — |
| `plugin` | Plugin | — | — |
| `permission_auth` | 권한 / 인증 | `permission`(권한 정책), `authentication`(인증 참조) | — (`target_refs`로 적용 대상) |

- 다른 서버의 같은 이름 Tool은 별도 자산이다(QA-UI-02).
- 모든 자산의 `context.gateway_ref`는 같은 스냅샷의 Gateway `asset_id`다(12.7, QA-INT-01).
- 자산 ID는 협의안 B(`<접두사>_<sha256(환경\n canonical key)[:16]>`)를 쓰며, 이슈 #10 확정 시 `pipeline/agentscope_pipeline/ids.py`만 바꾼다.

## 6. 상태 표시

`project.state_assessments[]`의 6단계를 그대로 표시한다. 하나의 상태로 덮어쓰지 않는다.

| `state` | 화면 | 정적 단계에서 |
|---|---|---|
| `DECLARED` | 선언 | 설정 근거로 판정 |
| `DISCOVERED` | 발견 | 설치 파일·목록 응답 근거로 판정 |
| `EXPOSED` | 노출 | 에이전트 노출 목록(`mcp probe`, `nodes describe`)이 있을 때 판정. 대상(`subject_ref`) 표시 |
| `POTENTIALLY_CALLABLE` | 잠재 호출 | 미평가 |
| `CALLABLE` | 호출 가능 | 판정하지 않음 |
| `USED` | 사용됨 | 판정하지 않음. 토큰 수집기 기록은 상세의 "실제 사용"에 따로 표시 |

값 표시: `true` 채움, `false` 테두리, `null` 빗금 + 사유. 상태가 배열에 없으면 미평가로 표시한다.

## 7. 관계

| `relation_type` | 출발 → 대상 | 비고 |
|---|---|---|
| `DECLARES` | Gateway/Node → Server·Skill, Gateway → Plugin | 설정의 선언 주체 |
| `PAIRED_WITH` | Gateway → Node | 페어링 원본이 있을 때만. 없으면 만들지 않는다 |
| `ADVERTISES` | Server → Tool/Resource/Prompt | 서버 목록 응답 근거 |
| `ASSOCIATED_WITH` | Plugin → Server(manifest가 등록), Skill → Server(스킬이 사용하는 서버) | manifest·SKILL.md 근거 |
| `APPLIES_TO` | 권한 정책 → Gateway·Server | **구현 관계**. 공통 후보 표에는 없음(스키마 15.2). 권한 집계 확정 시 `target_refs` 표현과 함께 정리 |
| `AUTHENTICATES` | 인증 참조 → Server | **구현 관계**. 자격증명 참조를 쓰는 서버(P2 이후). `APPLIES_TO`와 함께 정리 |

- `MAY_EXPOSE_TO`·`MAY_ACCESS`·`MAY_SEND_TO` 같은 추론 관계는 생성하지 않는다.
- 관계 수는 저장된 고유 `relation_id` 수다. `target_refs`로 그린 보조 선, Gateway 묶음은 세지 않는다(QA-UI-01).

## 8. 위협 평가와 경고

DetectionReport의 **평가(evaluations)를 항상 함께 읽는다.** 경고만으로는 "이상 없음"과 "판단 불가"를 구분할 수 없기 때문이다.

| `result` | 화면 | 경고 |
|---|---|---|
| `detected` | 탐지 | 생성 |
| `not_detected` | 이상 없음 | 없음 |
| `unknown` | 판단 불가 | 없음, 정상으로 세지 않음 |
| `not_applicable` | 해당 없음 | 없음 |
| `not_evaluated` | 미평가 | 없음 |
| `error` | 오류 | 없음 |

- `severity`(영향)와 `confidence`(근거의 확실성)는 따로 표시한다. confidence는 공격 성공 확률이 아니다.
- 경고마다 조건 ID(`S1-C1` 등)와 조건 이름, 관련 자산·관계·근거·기준 정책(`policy_refs`)을 보여 준다.
- 자산별 보안 상태: 높음(high/critical 경고) > 주의(그 밖의 경고) > 판단 불가(unknown·not_evaluated·error 평가) > 이상 없음 > 평가 대상 아님.

### 8.1 S1~S5 조건

조건 정의와 기본 severity/confidence는 `scenario-catalog.json`이 원본이다. 화면은 구현 우선순위 순서(S1 → S2 → S4 → S3 → S5)로 보여 준다.

| 시나리오 | 조건 | 판정 기준 |
|---|---|---|
| S1 비인가 서버 등록 | C1 미승인 서버, C2 Endpoint 불일치, C3 미승인 Plugin 등록, C4 선언 위치 이상 | `approved-servers.json` |
| S2 과도한 도구 권한 | C1 필터 밖 도구 노출, C2 파일 범위 과다, C3 명령·네트워크 입력, C4 인증정보 입력 | `expected-tool-policy.json` |
| S4 자격증명 공유 | C1 같은 저장소 공유, C2 다른 저장소 같은 이름(판단 불가), C3 미승인 Endpoint 전송, C4 범위 과다(미평가) | 참조 이름·저장 위치, `approved-servers.json` |
| S3 도구 이름 충돌 | C1 정의 다름, C2 정의 같음, C3 한쪽 미수집(판단 불가) | 서버가 광고한 정의 |
| S5 약한 연결 보안 | C1 평문 전송, C2 인증서 검증 끔, C3 sslVerify 없음(판단 불가), C4·C5 미평가 | 선언된 url·sslVerify |

## 9. 집계 규칙

| 표시 | 계산 |
|---|---|
| 식별 자산 | 8종 고유 `asset_id` 수. Gateway·permission_auth 포함 |
| 자산 관계 | 고유 `relation_id` 수 |
| 에이전트 노출 도구 | `EXPOSED = true`인 Tool 수 / 전체 Tool |
| 보안 경고 | 선택 스냅샷 detections의 `alerts` 수 |
| 확인 비율(링 차트) | 해당 상태가 평가된 자산 중 `true` 비율. 평가되지 않은 자산은 분모에서 제외 |

## 10. 화면

| 화면 | 보는 것 | 주요 규칙 |
|---|---|---|
| **개요** | 핵심 수치 4개, 서버별 광고·노출 도구, 자산 유형 구성, 상태 확인 비율, S1~S5 요약, 먼저 볼 경고, 정답 일치율, OpenClaw 내장 감사 | 미평가를 정상으로 집계하지 않음 |
| **자산 지도** | 호스트(tb-gw/tb-node)별 서버·플러그인·스킬. 도구 하나가 눈금 하나 | 채움 = 노출, 테두리 = 필터로 미노출, 빗금 = 확인 못함 |
| **자산 목록** | 유형·상태·보안 판정·시나리오 필터와 검색 | 이름·ID·canonical key로 검색 |
| **보안 경고** | 규칙별 평가 행렬, 경고별 자산·관계·근거·정책, 전체 평가 기록 | 경고 → 자산 → 근거까지 클릭으로 이동(QA-UI-03) |
| **기대 결과 비교** | 위협 시나리오 기대 결과와 탐지 결과 대조 | [12절](#12-기대-결과-비교) |
| **변경 비교** | P0 → P1 → P2, P2 → 각 위험 구성의 자산·관계·경고 변화 | `not_observed`는 삭제 수에 넣지 않음 |
| **수집과 검증** | 수집 작업별 성공·부분·미수행, 정답 목록 수집률 | 수집 실패와 정상 0건 구분 |
| **토큰 사용** | 호출 수·귀속 토큰·추정 비용, 시간대별, 계산 방식, 도구·서버·구간별, 소비 브레이크, 호출 기록 | [13절](#13-토큰-사용) |

**자산 상세(오른쪽 패널)**: 식별 키, 6단계 상태와 사유, 보안 평가, 자격증명 참조(이름·위치만), 서버 정의, 설정 값, 관계, 근거, 실제 사용(토큰 수집기가 이 자산 ID로 연결한 경우만).

공통: 위쪽 탭에서 스냅샷을 고르고, 밝게/어둡게 테마를 지원하며, 390px 휴대폰 폭에서 가로 스크롤 없이 보인다. 선택 필드가 없으면 "확인 못함"·"—"로 표시하고 화면이 깨지지 않는다(QA-UI-04).

## 11. 스냅샷

| 구성 | 종류 | 출처 |
|---|---|---|
| P0, P1, P2 | 정상군 | 테스트베드 SNAP-2 설정·수집본, 정답 목록 비교 |
| S1, S2, S4, S3 | 위험 구성 · **VM 수집** | SNAP-3 수집본(PR #24) |
| S1-T5, S5-T1~T3 | 위험 구성 · **설정 사본** | VM 미구축. 수집본은 P2 기준, 바뀐 서버의 노출은 확인 못함 |

화면 머리말에 "테스트베드 정상 구성 / VM 수집 / 설정 사본"을 표시한다.

## 12. 기대 결과 비교

기대 결과는 테스트베드 정답 파일(`ground-truth/<구성>.json`의 `expected_alerts`·`expected_no_alert`·`expected_unknown`)을 우선 쓰고, 없으면 `docs/threat-scenarios/expected-results.md`를 쓴다.

| 항목 | 규칙 |
|---|---|
| 일치 | 같은 `condition_id` + 대상 자산(`asset_key`)이 경고에 포함 |
| 나와야 할 경고 (`required: true`) | 없으면 불일치. 탐지율 분모에 포함 |
| 동반 경고 (`required: false`) | 나오면 일치, 안 나오면 "나오지 않음". 분모 제외 |
| 심각도 차이 | 경고는 맞고 severity만 다르면 "심각도 다름"(PARTIAL) |
| 판단 불가 유지 | 그 조건 평가가 모두 `unknown`이어야 일치 |
| 나오면 안 되는 경고 | 대상에 해당 시나리오 경고가 나오면 오탐 |
| 기대 밖 경고 | "확인 필요"(INFO). 비경고 범위에 걸리면 오탐 |

이 규칙의 확정은 QA 합의 대상이다(QA_GroundTruth, 스키마 16.1.1).

## 13. 토큰 사용

- 사용 현황 API 응답 필드를 그대로 쓴다(`src/types/contracts.ts`의 Usage* 타입).
- 계산하지 못한 토큰(`null`)을 0으로 바꾸지 않는다. 미귀속·후보 여럿도 지우지 않고 보여 준다(QA-USAGE-03).
- 자산 연결은 API가 매핑한 `asset_id`만 쓴다. 이름이 비슷해도 대시보드가 임의로 연결하지 않는다(QA-USAGE-01).
- 사용 기록은 자산 상태 `USED`를 바꾸지 않는다(스키마 14.2).
- 소비 브레이크(token-guard 플러그인의 경고·승인 요청·차단)는 S1~S5 경고와 따로 표시한다.
- 모든 토큰·비용은 추정치이며 청구 금액이 아니라고 표시한다.

## 14. 데이터 처리 원칙

| 항목 | 규칙 |
|---|---|
| 비밀값 | 비밀번호, API 키, 토큰, 개인 키 값은 수집·표시하지 않는다. `credential_refs`의 참조 이름·저장 위치·사용 위치·존재 여부만 표시 |
| 근거 | 경고 → 자산·관계 → 근거(`evidence`) → 원천 파일·설정 경로까지 이동 가능 |
| 원천 텍스트 | 서버 설명·스키마는 텍스트로만 표시하고 실행·링크로 해석하지 않는다 |
| 경로 | 출력 파일에 실행 PC의 절대 경로를 남기지 않는다(저장소 상대 경로) |
| 불완전 데이터 | `scan.status = partial`, 수집 작업의 `not_attempted`·`failed`를 사유와 함께 표시 |

## 15. v1.0 → v2.0 변환

스키마 12.8절 대응표를 따른다.

| v1.0 | v2.0 | 변환 규칙 |
|---|---|---|
| `MCP_SERVER` 등 대문자 유형, 7종 | 소문자 `asset_type` 8종 | Gateway는 `gateway` 자산, Resource/Prompt는 `resource_prompt` + subtype, 권한·인증은 `permission_auth` |
| 단일 `state` | `project.state_assessments[]` | 상태별 값·근거·대상 표시 |
| Asset `source` | `product.source_ref`, `evidence_refs` | |
| Asset `confidence` | 상태·관계·탐지 결과별 confidence | 자산 전체에 일괄 부여하지 않음 |
| Relation `source`/`target` | `source_asset_ref` / `target`(TargetRef) | |
| `PROVIDES` | `ADVERTISES` | 서버 목록 근거가 있을 때만 |
| `CONNECTS_TO` | `DECLARES`(선언), `PAIRED_WITH`(페어링) | 선언을 연결 성공으로 바꾸지 않음 |
| `EXPOSES`, `USES` | 상태 `EXPOSED`, 사용 기록 | 관계로 만들지 않음 |
| `CONTAINS`, `REFERENCES`, `AUTHENTICATES` | `ASSOCIATED_WITH`, `permission_auth.target_refs`, 구현 관계 `APPLIES_TO`·`AUTHENTICATES` | 공통 후보에 없는 관계는 구현 관계로 표시하고 합의 전 늘리지 않음 |
| `HIGH/MEDIUM/LOW` | `high/medium/low` | severity와 confidence 분리 |
| `Normal/Warning/High` | 평가 결과 6종 + 경고 severity | unknown·not_evaluated·error를 Normal로 표시하지 않음 |
| `SNAP-S1` 등 | `SNAP-3-S1`, 설정 사본 구성 | 위험 구성 이름은 테스트베드 기준 |

## 16. 남은 차이와 미확정

| 항목 | 현재 | 다음 |
|---|---|---|
| `schema_version` 표기 | 출력은 `0.6.0-draft` 표기 | 0.7 계약 항목을 대조한 뒤 전환(문자열만 바꾸지 않음) |
| 자산 ID | 협의안 B | 이슈 #10 확정 후 `ids.py` 교체 |
| 권한·인증 집계 | 권한·인증 자산 + 구현 관계 `APPLIES_TO`·`AUTHENTICATES` | 집계 단위·표현 합의(#15) |
| 서버 실행 위치 | 선언 위치(`host`)만 | `project.execution_location` 후보 반영 |
| 페어링 | P0 수집본에 원본 없음 → 관계 없음 | `devices list` 수집 시 `PAIRED_WITH` 생성 |
| VM 미구축 구성 | S1-T5, S5-T1~T3은 설정 사본 | VM 수집본이 생기면 자동으로 "VM 수집"으로 전환 |
| 탐지 모듈 | 대시보드 파이프라인의 정적 탐지기 | 팀 탐지 모듈이 생기면 같은 `detections.json`으로 교체 |
| 토큰 자산 연결 | 저장 사본은 PC 실측 데이터라 연결 0건 | 테스트베드 실시간 API를 `--inventory`로 연결 |

## 17. 완료 기준

- [x] 스캐너 출력(어댑터 변환)을 입력받는다
- [x] 8종 자산을 표현한다
- [x] 관계를 표현하고 자산에서 관련 관계를 확인한다
- [x] 6단계 상태와 사유를 표현한다
- [x] 근거와 confidence를 확인한다
- [x] S1~S5 평가와 경고를 표현하고, 경고에서 관련 자산으로 이동한다
- [x] 실제 비밀값이 화면에 나오지 않는다
- [x] 스냅샷 간 변경을 확인한다
- [x] 테스트베드 결과를 확인한다(정상군 정답 대비 선언·광고·노출 100%, 관계 P1·P2 100%·P0 15/16)
- [x] 위협 시나리오 기대 결과와 대조한다(위험 구성 8개, 나와야 할 경고 12/12, 오탐 0)
- [x] 토큰 사용량을 표시한다
- [ ] QA 첫 통합 실행(QA-INT-01·02, QA-UI-01~04, QA-USAGE-01~04) 통과
- [ ] 공통 스키마 0.7 확정본으로 전환

## 18. 문서 구조

```text
docs/
└── dashboard/
    └── dashboard-spec.md     이 문서
dashboard/
    README.md                 실행·데이터 생성·QA 대조표
```

세부 구현·실행 방법은 `dashboard/README.md`에 둔다.

## 19. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1.0 | 2026-10-01 | 대시보드 설계·구현 규격 초안 |
| v2.0 | 2026-11-15 | 공통 스키마 0.7 기준으로 데이터 모델 전면 개정(8종 자산, 6단계 상태, 관계 이름, 평가 결과 6종). 구현된 화면 8개, 기대 결과 비교, 토큰 사용, 스냅샷 구성 반영. 위치를 `docs/dashboard/`로 이동 |
