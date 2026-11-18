# 업로드 스냅샷 후속 검증·수정 (2026-11-18)

## 검증 기준과 결론

- 기준 파일: `scanner-current-20261118-171045.zip`
- 원본 ZIP SHA-256: `33a981cfc1bc0369cbb4aa365f902a03c1e7ba1fba3d9027d31129c710ec23d6`
- 이 ZIP에 포함된 **미커밋 작업을 포함한 전체 소스**가 기준이다. Git HEAD `0b2ff6b` 자체에 적용하는 패치가 아니다. ZIP에는 `.git`이 없어 로컬 브랜치·원격 상태를 이번 실행으로 검증하지 않았다.
- 최종 전체: **935 passed / 0 failed / 0 skipped**, pytest 자체 종료 코드 **0**, 218.04초. 파일별 과거 통과 수를 합산한 값이 아니라 한 번에 끝난 전체 실행이다.
- 환경: Linux·Python 3.12.14, json5 0.15.0, mcp/mcp-types 2.3.0, pytest 9.1.1. 제공된 Windows lock과 같은 버전을 설치했고 Windows 전용 pywin32는 제외했다. `pip check`도 종료 코드 0이었다.
- 실제 OpenClaw 설치·OVA·실제 원격 HTTPS 서버는 조회하지 않았다. 개발용 서버 프로세스·루프백 통신은 테스트에 포함된다.

## 이번에 고친 문제

| 문제 | 재현과 수정 | 의미 |
|---|---|---|
| Windows 형태 Skill 경로의 OS별 차이 | `..\outside`·드라이브·UNC 경로를 POSIX에서도 경계 검사. 플러그인 안의 `skills\lab`은 구분자를 정규화해 읽음. 추가 6개가 수정 전 실패·수정 후 통과 | Linux에서 경로 문자열을 리터럴 파일명으로 보던 동작을 보완. 실제 경로 탈출 공격이 재현됐다는 뜻은 아님 |
| YAML 따옴표·주석·쉼표·문단 | 따옴표 뒤 주석으로 name/description이 누락되거나 `"a,b"`를 두 값으로 나누던 문제 수정. 선행 빈 줄·더 들여쓴 문단·여러 줄 문단 보존 | 이름·의존성·설명을 잘못 기록하지 않도록 함 |
| 흐름 값의 제한·중복 키 누락 | JSON5 흐름 값과 metadata 폴백에도 깊이·노드·문자열 제한을 적용. 파싱 전에 구조 깊이를 제한하고 중복 키의 위치를 보존 | 한도 초과는 `unparsed`·`limit_hits`, 중복은 `duplicate_key`로 보고. 모든 YAML을 지원하는 것은 아님 |
| 전송 실패의 증거 오기록 | SDK 쓰기 스트림의 send가 성공한 뒤에만 `client_capabilities_sent`를 기록 | 서버 수신 확인을 뜻하지 않음. send 실패를 전송됨으로 표시하지 않음 |
| 문서의 의미·예시 불일치 | 실제 CLI 출력으로 가상 예시 재생성. Skill 설치 시각과 last_updated, 설치 방식과 script/binary 판정을 구분 | 원천에 없는 의미를 만들어 완료 처리하지 않음 |

기존 의존성·공통 ID·공통 스키마·권한 판정 규칙은 바꾸지 않았다. 새 회귀 테스트는 경로 6개와 나머지 17개로 총 23개다. 원본 기존 테스트의 기대값을 완화해 통과시키지 않았다.

## 실행 기록을 읽는 방법

| 실행 | 결과 | pytest 종료 코드 |
|---|---|---:|
| 원본 영향 테스트 | 320 passed, 1 failed (Windows 경로 분류 차이) | 1 |
| 경로 신규 회귀, 수정 전 | 6 failed | 1 |
| 경로 수정 후 영향 테스트 | 327 passed | 0 |
| 경로만 수정한 중간 코드 전체 | 918 passed | 0 |
| 추가 회귀 11개, 수정 전 | 10 failed, 1 passed | 1 |
| 중간 수정의 기존 영향 테스트 | 81 passed, 1 failed (metadata 폴백이 탭 문법을 잘못 수용) | 1 |
| 최종 영향 테스트 17개 파일 | 302 passed | 0 |
| **최종 전체** | **935 passed, 0 failed, 0 skipped** | **0** |

중간 실패도 삭제하지 않고 검토 ZIP `review/logs/`에 보존했다. 최종 결과는 `final-full.log`·`final-full.json`이다. 중간 로그와 최종 통과 수를 합산하지 않는다. 실행 명령은 다음과 같다.

```text
python -m pytest -q -rs -p no:cacheprovider
```

별도 CLI 예시 7회: assets 0, permission 1(SecretRef 미해석으로 의도된 partial), tools 0, lists 0, gateway 0, node 0, demo-stdio 0. 모두 stderr가 비었고 입력 11개 파일의 전후 SHA-256이 일치했다. 가짜 토큰·명령 기록·Skill 본문 표식의 결과 비노출도 검사했다. [입력 조건과 실제 출력](virtual-samples-and-outputs.md)에 기록했다.

## 아직 남는 항목

- **실환경 검증**: OVA/OpenClaw 실제 출력·설치본·프로필·반복 identity·inventory-remote 인증/TLS. 이번 Linux 통과는 Windows와 실제 VM 검증을 대체하지 않는다.
- **실제 미구현**: devices list 파서(`paired[].clientId` 수집 포함), Gateway/Node 서비스 실행 사용자, 채널·모델 제공자별 네트워크 정책, `OPENCLAW_INCLUDE_ROOTS`, 설치본 인덱스.
- **원천·의미 확인**: Plugin·Skill last_updated, modified 상태, 실제 script/binary 유형. 설치 시각·설치 방식으로 대신 채우지 않는다.
- **협의 대기**: 공통 ID·스키마, provider 최종 의미, 서명·무결성 신뢰 기준, 최종 실효 권한·노출·호출 가능성 판정. 이번 수정에서 확정하지 않았다.
- YAML은 제한된 부분집합이다. JSON 비호환 큰따옴표 escape·앵커·별칭·태그 등은 해석하지 않는다.

원본 ZIP과 사용자 PC는 수정하지 않았다. 커밋·push·외부 댓글·병합·팀원 코드 수정도 하지 않았다. 패치는 이 업로드본에서 바뀐 파일에만 적용하며, PC의 현재 파일과 다르면 자동 덮어쓰기하지 않는다. 적용 방법은 검토 ZIP의 `review/APPLY.md`에 있다.
