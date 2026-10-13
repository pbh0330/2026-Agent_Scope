# 자산 ID 식별 요구사항 정리와 테스트베드 자료 요청

확인일: 2026-10-06 · 대상: 팀 저장소 Issue #10, PR #11, 테스트베드 브랜치 · 스캐너 기준: 현재 `feature/scanner-config` 작업 트리

이 문서는 스캐너 내부 정리다. 공통 ID는 구현하지 않았고, 팀 합의 전 규칙을 확정 사실로 취급하지 않는다. 커밋·push·Issue 댓글도 하지 않았다.

## 1. 확인한 자료와 한계

| 자료 | 상태 | 읽은 방법 |
| --- | --- | --- |
| Issue #10 "자산 ID 생성 방식 및 유형별 식별 기준 협의" | 열림, 댓글 없음 | 웹 페이지 (`gh` 미설치) |
| PR #11 "자산 ID 생성 규칙 협의안 추가" (`docs/asset-id-rules-proposal.md`, v0.1, 2026-10-06) | **미병합**, 리뷰어·담당자 없음 | 웹 페이지 + `origin/pr/11` 읽기 전용 fetch 후 `git show` |
| 테스트베드 `docs/testbed-snap1` (PR #9), QA `docs/QA` (PR #8) | 마지막 커밋 10/4, 10/2 | `git show` |

- 로컬 작업 브랜치는 건드리지 않았다. 다른 팀원 브랜치는 병합·체크아웃하지 않았고, 원격 참조(`origin/pr/*`, `origin/docs/asset-id-rules-proposal`)만 fetch했다.
- 웹 페이지 요약은 요약 모델을 거친 것이다. 규칙 내용은 PR #11 문서 원문(`git show`)으로 대조했다. Issue #10 본문은 웹 요약만 확인했다.
- PR #11은 협의안이다. 아래 요구사항은 확정 규칙이 아니다.

## 2. PR #11이 요구하는 식별 정보 (제안 상태)

- **ID 방식**: B안(Canonical Key + Hash)을 우선 제안한다. 권장 형식은 `ast_` + SHA-256 전체 소문자 hex 64자리다. 입력은 규칙 버전(`asset-id-v1` 등)을 맨 앞에 둔 유형별 JSON 배열이며, UTF-8·BOM 없음·공백 없음으로 직렬화한다.
- **필수값 누락**: 빈 문자열이나 `unknown`으로 대체해 정상 ID를 발급하지 않고 "식별 미완료"로 기록한다.
- **MCP Server 식별 후보**: 선언 주체의 완전한 ID(환경·프로필·Gateway/Node) + 원본 설정 위치 + 서버 등록 키.
- **식별에서 제외할 값**: description, 상태, 관찰 시각, 버전, 파일 내용 해시. `command`·`endpoint`·패키지 정보는 변경 비교 속성으로 둔다. 비밀값과 그 해시는 ID 입력에 넣지 않는다.
- **이름 변경**: 등록 키가 바뀌면 새 ID를 만든다. 이전 ID의 제거 판정은 수집 완전성을 확인한 뒤에만 한다.
- **재현성**: 같은 원천 값과 같은 규칙이면 결과 DB를 초기화해도 같은 ID가 나와야 한다.
- **미결 사항**: "원본 설정 위치"가 물리 경로인지 논리 경로인지는 문서에도 "추가 합의 필요"로 남아 있다. Gateway·Node의 device identity는 팀 댓글의 제안이며 실제 출력으로 검증되지 않았다.
- **Issue #10 완료 기준**: 실제 원천값 확인, 변경 유지 여부 검증, 동일 ID 연결·집계·재현성 검토, 공통 입력·출력 예제 검토. 문서 PR 병합만으로 종료하지 않는다.

## 3. 현재 스캐너 출력과의 대조

대상 필드는 `output/two-servers.result.json`의 `servers[]` 항목이다. 이 항목은 가짜 입력으로 만든 결과다.

| PR #11이 요구하는 값 | 현재 스캐너 | 판단 |
| --- | --- | --- |
| 서버 등록 키 | `registration_key` | 있음 |
| 설정 내 선언 경로 (논리) | `declaration_path`, `declaration_pointer` | 있음. `--registry-path`로 `mcp.servers`와 `nodeHost.mcp.servers`를 구분해 읽는다. |
| 원본 설정 위치 (물리) | `source_path`에 `--config`로 받은 로컬 절대 경로를 그대로 기록 | **ID 입력으로 부적합.** PC마다 달라 재현성을 깨뜨린다. 물리·논리 중 무엇을 쓸지 팀 합의 전까지 ID 입력으로 쓰지 않는다. |
| 환경·프로필 범위 | 없음 | 스캐너가 알 수 없다. 외부 입력이 필요하다. |
| Gateway / Node device identity | 없음 | 설정 파일에서 읽지 않는다. 실제 설정에 해당 필드가 있는지 확인되지 않았다. |
| "식별 미완료" 상태 | 없음 | `collection_status`는 수집 완전성만 나타내며, 식별 완전성과는 별개다. |
| 비밀값 제외 | 가림 처리 후 출력 (R1 반영 완료) | 충족. 비밀값 해시를 식별자로 저장하지 않는다. |

Tool·Resource·Prompt는 V3 수집 범위에 없어 대조하지 못했다.

## 4. 검증 가능 여부

PR #11이 요청한 "2절 원천 값의 실제 수집 가능성"은 **지금은 검증할 수 없다.**

- 확인한 SNAP-1 설정(`tb-gw`, `tb-node`)에는 스캐너가 선택한 MCP 등록 영역이 없다(`registry_absent`, `server_count: null`). 서버 0개(`empty_registry`, `server_count: 0`)가 아니다. 이 결과는 `snap1-validation.md`에 기록했다. `--registry-path nodeHost.mcp.servers`로 다시 읽은 결과도 두 설정 모두 `registry_absent`, `server_count: null`이다(`snap1-validation.md` 11장).
- 정답 목록은 아직 없다. `testbed/ground-truth/README.md`는 형식만 정의하고 "6주차 SNAP-2 구성 시 작성"이라 적었다. 그 안의 JSON은 가상 예시이며 `<TB_USER>` 같은 자리표시자가 남아 있다. `QA/QA_GroundTruth.md`는 거의 전부 TBD다.
- 테스트베드 README의 일정상 정상군 P0/P1/P2, 정답 목록, SNAP-2는 10/12까지 예정이다. `docs/testbed-snap1`의 마지막 커밋은 10/4이고 이후 갱신은 없다.
- 테스트베드 README §5.2의 P0 선언 예시는 "초안"이다. 실제 설정으로 취급하지 않고 검증 근거로도 쓰지 않았다.

## 5. 테스트베드 담당자에게 요청할 자료

비밀값은 반드시 제거한 사본으로 받는다. 실제 설정 원본과 토큰·키·사용자 홈 경로는 요청하지 않는다. 두 묶음은 목적이 다르다. ①이 없으면 등록 서버 검증을 시작할 수 없고, ②는 없어도 ①의 검증은 진행할 수 있다.

### ① 등록 서버 검증에 꼭 필요한 자료

현재 스캐너(`--registry-path`로 `mcp.servers` / `nodeHost.mcp.servers` 선택)가 읽고 정답과 대조할 수 있게 하는 최소 자료다.

| 번호 | 자료 | 용도 |
| --- | --- | --- |
| 1 | 서버가 실제 등록된 Gateway 설정의 비밀값 제거 사본(`mcp.servers.<등록 키>` 포함)과 그 커밋·경로 | 스캐너 입력 (P0) |
| 2 | 같은 시점의 `openclaw mcp list` 출력 | 서버 수·등록 키의 독립 대조 근거. 이 명령은 `mcp.servers`만 보여 주고 mcporter 서버는 포함하지 않는다고 SNAP-1 기준선에 적혀 있다. |
| 3 | P0 정답 목록(`ground-truth/P0.json`): 서버 수, 등록 키, `declared_at` | 필드 단위 대조 |
| 4 | 실제 OpenClaw 버전, 활성 설정 파일 위치, `$include` 사용 여부 | `$include`로 설정이 나뉘면 스캐너가 읽지 못하는 부분이 생기고 결과가 `partial`이 된다. |
| 5 | 노드 설정의 `nodeHost.mcp.servers` 비밀값 제거 사본(P1, 서버 2종)과 P1 정답 목록 | `--registry-path nodeHost.mcp.servers` 검증 |

### ② 향후 공통 ID 협의에 필요한 자료

PR #11의 담당자 확인 사항에 해당한다. 서버 등록 검증에는 필요하지 않고, 팀이 ID 규칙을 정할 때 필요하다.

| 번호 | 자료 | 용도 |
| --- | --- | --- |
| 6 | Gateway·Node device identity 필드가 설정 또는 CLI 출력의 어디에 있는지. 실제 필드명, 프로필별 유일성, 초기화·복제·재페어링 후 유지 여부 | 선언 주체 ID |
| 7 | 환경(`env-a` 등)·프로필 값을 누가 어디서 정의하는지. 설정 파일에서 읽을 수 있는지, 실행 인자로 받아야 하는지 | 범위 값 입력 경로 결정 |
| 8 | 같은 설정을 재수집하거나 서버를 재설치했을 때 등록 키·식별값이 유지되는지에 대한 관찰 기록 | 재현성 검증 |
| 9 | 같은 서버가 Gateway와 Node 양쪽에 선언되는지, 서로 다른 환경·프로필에 동명 서버가 있는지 | 동명 서버 구분 규칙 |
| 10 | S3 동명 Tool 시나리오용으로 서로 다른 서버에 같은 이름의 Tool을 둔 구성 | Tool 단계 ID 협의. 현재 스캐너는 Tool을 수집하지 않는다. |

## 6. 자료가 오면 할 일 (이번에는 하지 않음)

1. 받은 설정을 `--registry-path` 값별로 현재 스캐너로 실행한다. 기본 경로와 `nodeHost.mcp.servers` 경로를 각각 실행한다.
2. 정답 목록과 서버 수·등록 키·선언 경로를 필드 단위로 대조한다. 이름만으로 매핑하지 않는다.
3. 결과(성공·불일치·미확인)를 `docs/`에 기록한다. 같은 입력으로 두 번 실행해 등록 키·선언 경로가 같은지도 기록한다.
4. 팀이 규칙을 확정하면 공통 ID 구현을 시작한다. 그전에는 구현하지 않는다.

## 7. 팀에 제안할 사항 (Issue #10 의견용 초안)

- `source_path`가 로컬 절대 경로라는 점을 알리고, ID 입력에는 `--config` 절대 경로 대신 논리 경로(`declaration_path`)와 외부에서 받은 환경·프로필·Gateway/Node 식별값을 쓰자고 제안한다. 그 식별값을 스캐너가 어디서 받는지는 5장 ②의 6번·7번 답변에 달려 있다.
- 식별값이 부족한 서버는 `collection_status`와 별도의 식별 상태로 남기는 방안을 협의 항목으로 올린다.

## 8. 확인 기록: 복합 명령의 `Exit code 1`

대화 중 `--help`, `ls`, 스캐너 실행, `python -c`를 `;`로 이어 한 번에 실행했을 때 도구가 `Exit code 1`을 보고했다. 복합 명령의 종료 코드는 마지막 명령의 값이므로 어느 단계가 실패했는지 따로 알 수 없었다. 같은 단계를 개별 실행해 확인했다(2026-10-06, Windows 10, `.venv`의 Python 3.14.4, 콘솔 cp949 상태, `PYTHONUTF8` 미설정).

| 단계 | 명령 | 종료 코드 | stderr | 판정 |
| --- | --- | --- | --- | --- |
| A | `python -m asset_scanner --help` | 0 | 비어 있음 | 정상. 프로그램 실패 아님 |
| B | `ls examples output` | 0 | 비어 있음 | 정상 |
| C | `python -m asset_scanner --config examples/node-and-gateway.json5 --registry-path nodeHost.mcp.servers --output <임시 경로>` | **1** | 비어 있음 | **의도된 종료 코드.** 결과가 `partial`(`sample-node-remote` 항목이 불완전)이며 README 종료 코드 표의 1에 해당한다. 결과 파일은 저장됐다. 실행 실패 아님 |
| C2 | C와 같고 `PYTHONUTF8=1` | 1 | 비어 있음 | C와 같은 결과. 표시만 한글로 정상 출력 |
| D1 | `python -c "...os.path.expandvars('$TEMP/o.json')..."` (시스템 Python) | **1** | `SyntaxError: (unicode error) 'unicodeescape' codec can't decode bytes in position 2-3: truncated \UXXXXXXXX escape` | **실제 실패.** 셸이 `$TEMP`를 `C:\Users\...`로 치환해 Python 문자열 리터럴 안에 들어가 `\U`가 유니코드 이스케이프로 해석됐다. 스캐너와 무관한 호출 방식의 오류 |
| D2 | 경로를 인자로 넘기는 `python -c` (`.venv`, `-X utf8`) | 0 | 비어 있음 | 정상. 결과 파일의 `collection.status`는 `partial` |

**결론**
- 복합 명령의 `Exit code 1`은 두 가지가 겹친 결과다. 마지막 단계 D1의 `SyntaxError`(호출 방식 오류)가 도구가 보고한 종료 코드의 원인이다. 스캐너의 종료 코드 1(C)은 `partial`을 뜻하는 정상 동작이며, 복합 명령에서는 마지막 명령에 가려져 보이지 않았다.
- **한글 깨짐은 실행 실패가 아니다.** 도구 출력(Git Bash로 리다이렉트한 cp949 상태)에서 한글이 `���`로 보인 것은 표시 인코딩 문제다. 종료 코드와 결과 파일에는 영향이 없다. 같은 명령을 `PYTHONUTF8=1`로 실행하면(C2) 같은 종료 코드와 내용이 한글로 정상 표시된다. 두 실행의 stdout 해석에는 이 인코딩 차이만 있다. 이번에 이 두 가지를 같은 실행에서 비교해 확인했다.
- C의 출력 중 `—`는 깨짐이 아니다. 줄표(—)를 cp949로 표현할 수 없어 README(78행)에 적힌 대로 이스케이프한 것이다. C2에서는 `—`로 표시된다.
- 스캐너 실행 결과를 판단할 때는 복합 명령으로 묶지 말고 스캐너 호출 하나의 종료 코드와 stderr를 따로 기록한다.
- 이번 세션에서 이 조사로 코드는 수정하지 않았다.
