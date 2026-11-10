# MCP 버전 호환성과 manifest 서버 선언 수집

작성일: 2026-10-31 · 기준 커밋: `ed7652e328a57c0a73a3d2e2ec44527015ba6c30` · 이번 변경은 미커밋

## 작업 범위

팀 테스트베드 사양이 수정될 예정이라는 안내에 따라, 기존 자료와의 결과 대조·수집률·누락 계산은 보류했다. 앞서 탐색적으로 만든 대조 결과도 공식 성과로 사용하지 않는다. 테스트베드 전용 코드·export 어댑터는 이번 변경에 포함하지 않는다.

이번에는 MCP 공식 규격과 OpenClaw 공식 문서를 근거로 아래 두 기능을 보완했다. 2026-10-31에 별도 Linux 작업 사본에서 개발했다(과거 기록). 이후 사용자 Windows 프로젝트의 `feature/scanner-config` 작업 트리에 PR #5 피드백 수정과 함께 통합했으며, 이 문서 작성 시점에는 커밋·push·PR 변경을 하지 않았다.

## 바뀐 동작

| 항목 | 이전 | 변경 후 |
| --- | --- | --- |
| MCP 2025-11-25 | 미지원으로 중단 | 해당 버전의 `tools/list` 구조로 읽음. 최신 버전 전용 완료·캐시 필드를 필수로 요구하지 않음 |
| MCP 2026-07-28 | 기존 완료·캐시 검사 | 유지 |
| 미지원 버전 | 실패 | 유지. 버전 이름을 고치거나 응답 모양으로 추측하지 않음 |
| 플러그인 서버 선언 | 설정 파일의 두 영역만 수집 | `--plugin-manifest`로 지정한 파일의 `mcpServers`도 수집 |
| 명시적 `nextCursor: null` | 필드가 없는 것으로 잘못 판단해 `complete`가 될 수 있었음 | 두 지원 버전 모두 `partial`과 `next_cursor_invalid`. 읽은 Tool은 보존 |

MCP 프로토콜 버전과 SDK 패키지 버전은 다른 개념이다. SDK는 기존 `mcp==2.3.0`을 유지했고, 실제 협상된 프로토콜 버전에 따라 파서를 선택한다. 저장 응답의 경우 입력에 선언된 버전을 사용한다.

플러그인 선언의 실행 명령·인자·주소·명시된 `enabled`·출처·선언 위치를 기존 정적 수집 방식으로 기록한다. 상대 경로는 원문으로 보존한다. 플러그인 설치·활성화, 사용자 설정과의 우선순위 병합, 실제 서버 등록 성공을 판정하지 않으며 Plugin 자체를 새 자산 유형으로 수집한 것도 아니다.

## 검증 결과

### 현재 검증: Windows 통합 상태

환경: Windows 10 Pro 10.0.19045, 프로젝트 `.venv`의 Python 3.14.4. 호환성·manifest 보완과 PR #5 피드백 3건 수정을 통합한 작업 트리에서 실행했다.

| 검증 | 결과 | pytest 종료 코드 |
| --- | --- | --- |
| 회귀(`test_pr5_feedback`, `test_plugin_manifest`, `test_protocol_2025`) | **66개 통과**, 6.47초 | **0** |
| 전체 테스트 | **332개 통과**, 471.79초 | **0** |

실행 기록은 `output/review-pr5/integrated-regression.log`, `integrated-full.log`, `integrated-exit-codes.txt`(Git 제외)에 있다. 아래 Linux 결과는 이 결과로 대체되지 않는다.

### 과거 기록: 2026-10-31 Linux 작업 사본 (현재 결과 아님)

실행 환경: Linux x86_64, Python 3.12.14, pytest 9.1.1, json5 0.15.0, MCP Python SDK 2.3.0. 당시 Windows 실행 결과는 없었다. 기존 문서의 Windows·SDK 2.0.0 기록도 과거 버전에 대한 기록이다. 아래 표의 301개는 PR #5 수정이 없던 코드에 대한 것이다.

| 검증 | 결과 | 종료 코드 |
| --- | --- | --- |
| 커서 문제 수정 전 재현 | 비문자열 커서 8개 중 `null` 2개 실패, 나머지 6개 통과 | 1 |
| 독립 기능 관련 선택 테스트 | 42개 통과, 27개 선택 제외 | 0 |
| 전체 테스트 | **301개 통과, 실패·skip 없음, 81.42초** | **0** |
| manifest 예제 CLI | `complete`, 등록 선언 2개, stderr 없음 | 0 |
| 2025 저장 응답 예제 CLI | `complete`, Tool 1개, stderr 없음 | 0 |
| 기존 설정 예제 CLI | `complete`, 서버 2개, stderr 없음 | 0 |

pytest는 파이프로 감싸지 않고 자식 프로세스의 `returncode`를 직접 기록했다. 세 CLI 예제의 입력 SHA-256·수정 시각은 전후 동일했다. 가짜 인증정보가 있는 별도 회귀 테스트에서는 가림 후 결과에 해당 값이 남지 않는지 검사한다. 비밀이 없는 기본 예제의 통과를 모든 인증정보 가림 기능의 검증으로 확대 해석하지 않는다.

실제 통신 검증 대상은 프로젝트에 포함된 **개발용 MCP 서버 하나**다. 2025-11-25로 협상하는 흐름에서 정상 목록·빈 목록·다음 페이지·빈 문자열 커서·뒤 페이지 오류·수량 제한·가림을 검사했다. 서버가 받은 요청 기록으로 `initialize`와 `tools/list`, `tools/call` 없음, 서버 프로세스 종료를 확인한다. 팀 테스트베드·실제 운영 서버 검증이 아니다.

실행 기록은 검토 ZIP의 `verification/pytest-full.log`, `pytest-full-exit.json`, `targeted-after.log`, `targeted-after-exit.json`, `cursor-before.log`, `cli-checks.json`에 담았다. 수정 전 재현의 실패 2건은 이번 `null` 문제에 대한 것이며, 301개 전체 테스트의 실패가 아니다.

## 재현

`asset-scanner` 폴더에서 기존 가상환경 Python을 사용한다. 아래 명령은 직접 작성한 예제만 읽는다.

```powershell
.\.venv\Scripts\python.exe -m asset_scanner --plugin-manifest examples\plugin-servers.json5 --output output\plugin.result.json
.\.venv\Scripts\python.exe -m asset_scanner.tools_catalog --capture examples\tools-list-2025.json --output output\tools-2025.result.json
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rs
```

전체 pytest는 개발용 MCP 서버를 별도 프로세스로 실행하는 테스트를 포함한다. 설정 파일에 적힌 외부 명령을 실행하지 않으며, 외부 계정·인증정보가 필요 없다. 구버전 개발용 서버 테스트만 확인하려면 `python -m pytest tests/test_live_tools.py -q -k legacy`로 실행할 수 있다.

## 남은 작업

- 수정된 테스트베드 사양·설정·정답 목록이 제공되면 근거부터 확인하고 별도 검증한다. 기존 수집률·누락 수치를 새 자료의 결과로 재사용하지 않는다.
- 원격 HTTP·인증 서버 조회, 실제 OpenClaw에서의 등록·노출·호출 가능 여부는 아직 검증하지 않았다.
- Resource·Prompt·Skill·Plugin 자산 수집, 공통 ID·공통 스키마 확정과 구현은 이번 범위 밖이다.
- Windows 통합 테스트는 통과했다(위 현재 검증). 커밋 여부는 검토 후 정한다.

공식 원문과 커밋 SHA, 필드 매핑은 [field-mapping.md 8장](field-mapping.md#8-독립적인-버전-호환성과-manifest-수집-보완)을 참조한다.
