# QA Ground Truth

## 1. 목적

스캐너 및 대시보드 결과를 비교할 수 있도록 테스트베드에 실제로 구성한 자산, 관계 및 기대 경고를 수동으로 기록한다. 추정값이 아니라 설정 파일, manifest 및 MCP 목록 응답으로 확인한 값을 사용한다.

테스트베드의 정답 JSON을 인수하면 자산·관계의 원본으로 참조하고, 이 문서는 QA 검토·ID 매핑·기대 조건·증적 연결을 관리한다. [PR 4](https://github.com/pbh0330/2026-Agent_Scope/pull/4)의 형식은 초안이므로 예시를 실제 정답으로 복사하지 않는다. 적용 JSON과 스키마의 버전 및 변환 규칙을 확인한 뒤 비교한다.

## 2. 기준 환경

| 항목 | 값 |
|---|---|
| Ground Truth 버전 | GT-001 |
| 작성일 | TBD |
| 작성자·검토자 | TBD / TBD |
| 기준 스냅샷 ID | TBD |
| 프로파일·위협 구성 ID | TBD (P0/P1/P2 또는 위협 구성) |
| 정답 JSON 경로·commit | TBD (인수한 실제 파일 기준) |
| 기준 프로파일·변경분 적용 규칙 | TBD (차분이면 추가·변경·삭제 및 관계 처리 규칙 포함) |
| 수집 범위·인증 맥락 | TBD (안전한 참조만 기록) |
| Gateway 식별자 | TBD |
| Node 식별자 | TBD |
| OpenClaw 버전·commit | TBD |
| 출력 스키마 버전 | TBD |
| 실행 기준 시나리오 문서·ID·버전 | S1~S5 / 문서 버전 TBD |
| 관련 설정·manifest | 비밀값을 제거한 경로 또는 증적 ID 기록 |

## 3. 정답 자산 목록

`정답 ID`는 테스트 문서용 안정 식별자다. 실제 출력 ID와 별도로 관리하고 비교 시 매핑한다.

| 정답 ID | JSON asset_key | 출력 asset_id | 출력 owner_ref | 선언/광고 계층 | 유형 변환·매핑 근거 |
|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | declared / advertised | TBD |

JSON이 `resource`·`prompt`를 별도 유형으로 제공하면 합의된 출력의 `resource_prompt` 및 `asset_subtype`으로 대응시킨다. ID 생성 규칙과 소속 서버를 확인하고 이름만으로 매핑하지 않는다. 관계의 ADVERTISES, evidence_refs·confidence 등 필수 정보가 원본에 없으면 보완 근거를 인수하며 임의로 채우지 않는다.

| 정답 ID | 자산 유형 | 이름·공식 식별자 | 선언/소유 주체 | 출처 | 정상/위협 | 필수 기대 속성 | 증적 ID |
|---|---|---|---|---|---|---|---|
| GT-A-001 | Gateway | TBD | - | Gateway 설정 | 정상 | TBD | EV-001 |
| GT-A-002 | Node | TBD | GT-A-001 | Node 설정 | 정상 | TBD | EV-002 |
| GT-A-003 | MCP Server | 승인 테스트 서버 | GT-A-001 | 설정 | 정상 | endpoint, transport, TLS 상태 | EV-003 |
| GT-A-004 | MCP Server | 비인가 테스트 서버 | GT-A-002 또는 Skill/Plugin | 설정 | S1 | source, endpoint, 노출 상태 | EV-004 |
| GT-A-005 | Tool | 동명 테스트 Tool | GT-A-003 | `tools/list` | 정상 | name, description, inputSchema | EV-005 |
| GT-A-006 | Tool | 동명 테스트 Tool | GT-A-004 | `tools/list` | S3 | name, description, inputSchema | EV-006 |
| GT-A-007 | Resource/Prompt | TBD | GT-A-003 | 목록 응답 | 정상 | asset_subtype, uri 또는 name | EV-007 |
| GT-A-008 | Skill | TBD | Gateway/Node | SKILL.md | 정상 또는 S1 | source, version/commit, integrity | EV-008 |
| GT-A-009 | Plugin | TBD | Gateway | manifest·설정 | 정상 또는 S1 | provider, version, 등록 자산 | EV-009 |

실제 테스트베드 구성에 맞추어 행을 추가·삭제한다. 존재하지 않는 예시 행을 정답으로 집계하지 않는다.

위 자산 및 아래 관계 목록은 S1~S5 검증을 준비하기 위한 작성 예시다. 담당자와 합의한 정상/위협 구성 및 실제 설정·목록 응답으로 확인한 값에 따라 갱신한다. 예시만으로 정답 자산·관계가 확보된 것으로 처리하지 않는다.

## 4. 정답 관계 목록

| 정답 ID | 시작 자산 | 관계 | 도착 자산 | 근거 유형 | 신뢰도 | 증적 ID |
|---|---|---|---|---|---|---|
| GT-R-001 | GT-A-001 | `DECLARES` | GT-A-003 | config | confirmed | EV-003 |
| GT-R-002 | GT-A-002 | `DECLARES` | GT-A-004 | config | confirmed | EV-004 |
| GT-R-003 | GT-A-003 | `ADVERTISES` | GT-A-005 | protocol | confirmed | EV-005 |
| GT-R-004 | GT-A-004 | `ADVERTISES` | GT-A-006 | protocol | confirmed | EV-006 |
| GT-R-005 | GT-A-008 또는 GT-A-009 | `ASSOCIATED_WITH` | GT-A-004 | manifest/config | confirmed 또는 high | EV-008 |

## 5. S1~S5 시나리오별 기대 경고

아래 표는 [위협 시나리오 후보](../위협시나리오.md)의 S1~S5를 검증하기 위한 기대 경고 초안이다. 실행 전 담당자와 정상/위협 구성별 기대 조건을 확정하고 고유 ID를 부여해 경고·근거·관련 자산과 발생하면 안 되는 경고를 기록한다. 조건 ID는 실행결과와 연결한다. 활성 상태와 세부 조건이 미확정인 행은 확정 정답 수에 포함하지 않는다.

| 시나리오 | 활성 상태 | 기대 경고 | 관련 정답 자산·관계 | 발생하면 안 되는 경고 |
|---|---|---|---|---|
| S1 비인가 서버 | TBD | 미승인 Server, 불명확한 출처, 잠재 노출 | TBD | 승인 서버에 대한 비인가 경고 |
| S2 과도한 권한 Tool | TBD | 위험 입력·권한·승인 정책 누락 | TBD | 실제 접근·전송이 발생했다는 확정 표현 |
| S3 동명 Tool 충돌 | TBD | 서로 다른 Server의 동일 이름 및 차이 | TBD | 두 Tool의 단일 자산 병합 |
| S4 자격증명 공유 | TBD | 동일 참조 공유, scope 과다, audience 불일치 | TBD | 실제 자격증명 값 표시 |
| S5 안전하지 않은 연결 | TBD | 평문 또는 TLS 검증 비활성화 | TBD | 정상 HTTPS 연결에 대한 경고 |

각 기대 경고·금지 경고를 아래 표의 개별 조건으로 구체화한다. 하나의 행은 하나의 판정 가능한 조건이며, 위 요약 표의 행 수를 기대 경고 수로 사용하지 않는다.

| 조건 ID | 시나리오 | 관련 TC ID | 정상/위협 구성·프로파일 | 기대 결과·금지 결과 | 관련 자산·관계·증적 | 합의 상태·기준 버전 |
|---|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD | 미확정 |

## 6. 집계값

| 항목 | 정답 수 |
|---|---:|
| 전체 자산 | TBD |
| Gateway | TBD |
| Node | TBD |
| MCP Server | TBD |
| Tool | TBD |
| Resource/Prompt | TBD |
| Skill | TBD |
| Plugin | TBD |
| 전체 관계 | TBD |
| 기대 경고 | TBD |

## 7. 증적 목록

증적에는 실제 비밀값이 포함되지 않도록 마스킹 여부를 재확인한다.

| 증적 ID | 유형 | 설명 | 파일·URL·캡처 위치 | 수집일 | 마스킹 확인 |
|---|---|---|---|---|---|
| EV-001 | config/screenshot | TBD | TBD | TBD | [ ] |

## 8. 변경 이력

| 버전 | 일자 | 변경 내용 | 작성자 | 검토자 |
|---|---|---|---|---|
| GT-001 | TBD | 최초 작성 | TBD | TBD |
