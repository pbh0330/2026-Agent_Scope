# OpenClaw 실환경 검증 전 수집 보완

- 기준: `feature/scanner-config`의 `e742cf7` 이후
- 목적: 기존 대응표의 실제 수집 원천 누락을 보완하고, 실환경 확인·팀 협의 항목과 분리
- 범위: 스캐너 코드·테스트·문서. 대시보드·공통 ID·팀원 코드 변경 없음
- 검증: 가상 설정·저장 자료·로컬 시험 서버·현재 검사 프로세스 사용. 실제 OpenClaw·OVA 사용 없음

## 이번 원천 보완

| 요구 범주 | 새 입력·구현 | 결과 필드·의미 | 제한 |
|---|---|---|---|
| 채널 접근 정책 | `permission_auth --config` | `items[].category: channel_policy`, `config_path/config_pointer`, `applies_to.channel`, 선언된 정책·허용/차단 목록 | 공통·문서화된 중첩 경로. 플러그인 임의 설정 전체나 실효 권한을 계산하지 않음 |
| 계정·그룹별 정책 | 같은 수집기의 계정·그룹·guild·room·topic·발신자 경로 | 개별 원천 항목 보존. 개인 식별 목록은 개수만, 개인 대상 키는 자리표시자 | 가려진 경로는 `original_config_pointer_available: false`. 같은 표시 경로라도 합치지 않음 |
| Plugin·Skill 탐색 | `installation_inventory --state-dir/--workspace-dir/--installation-root` | `discovery[]`, 기존 형식의 `assets.plugins[]/skills[]` | 지정 경계 안에서만 탐색. 홈 전체·다른 계정·보호 경로 자동 탐색 없음 |
| 설정의 추가 설치 경로 | `--config`, 선택 `--resolve-includes` | `plugins.load.paths`, `skills.load.extraDirs`에서 발견한 실제 파일 | 상대 경로·`~`·환경변수는 추측하지 않음. 경계 밖이면 기록하고 따라가지 않음 |
| 설치 인덱스 | `--plugin-index-json`, `--state-db` | `installation_records[]`, `assets.plugins[].index_record_refs` | 인덱스 버전 1. `plugins[]`와 `installRecords` 원천을 별도로 보존하고 id와 root가 모두 같을 때만 실제 설치본에 연결. 최신 상태·무결성을 검증한 뜻이 아님 |
| SQLite 설치 기록 | `config_machine_state`, `plugins.installedIndex` 고정 행 | 원래 설치 방식·버전·설치 시각·출처 보존 | DB·WAL 사본에서만 조회. 원본 SHM·DB 생성·마이그레이션 없음 |
| Skill YAML | PyYAML 6.0.3의 구문 노드 + 한도 있는 JSON 자료형 변환 | `frontmatter_parser`, 기존 frontmatter·metadata·중복·한도 진단 | 비순환 앵커·별칭·매핑 병합·흐름 문법·핵심 태그 지원. Python/사용자 태그·복합 키·순환·한도 초과는 해석하지 않음 |
| 인증 프로필 | `auth_metadata --auth-profiles-json` | 허용된 provider·issuer·공개 endpoint·clientId·만료 선언 | 인증값·인증값 해시·email·subject·account identity 비저장. 자동 로그인·토큰 갱신 없음 |
| 사용자별 모델 계정 | 선택 `--model-account-db`의 `secret_store_entries` | `identity/model-account:` 영역의 허용 메타데이터와 `stored_owner_partition_ref` | 다른 secret store 영역·삭제 행 제외. 원래 사용자 ID·프로필 이름 비저장. 소유자 구분은 파일 내 임시 참조이며 실제 사용자 identity를 확정하지 않음 |
| MCP OAuth 원천 | `--mcp-oauth-json`, `--state-db`의 `mcp_oauth_stores` | issuer·resource·scope·공개 discovery 메타데이터·만료 선언 | 지원 포맷 버전 1. resource를 JWT audience로 바꾸지 않음 |
| JWT audience | 선택 `--inspect-token-claims` | `token_claim_observations[].claims`의 iss·aud·scope·exp만 | `decoded_unverified`, `signature_verified: false`. 토큰이나 사용자 식별 클레임 비저장. 서명·인증 성공·실효 범위 판정 아님 |
| 만료 시각 | 인증 원천의 밀리초 시각 | `expired_against_scanner_clock` | 스캐너 시계와 저장된 마감의 비교. 서버가 현재 허용한다는 뜻이 아님 |
| 실행 계정 관측 | `process_identity --pid` | Linux proc의 UID/GID(실제·유효·saved·filesystem), 보조 그룹·시작 tick | 명시한 PID만 조회. PID가 OpenClaw라는 연결·영속 ID·실효 권한은 추정하지 않음 |
| script/binary 근거 | `--entry-file`, 설치 탐색의 package 진입점 | `file_kind`, `basis`, 파일 크기·filesystem mtime | 헤더 근거와 확장자 힌트 구분. 코드 실행·본문·해시 저장 없음. mtime은 last_updated가 아님 |

## 읽기·가림·한도

- 탐색: 깊이 8, 디렉터리 항목 5,000개, 자산 종류별 500개. 한도 초과는 성공한 전체 수집으로 표시하지 않음
- DB: 원본·WAL 각각 최대 64MiB, JSON 행 최대 4MiB, MCP 행 최대 1,000개. 고정 테이블/컬럼만 조회
- DB의 view·가상 테이블·다른 스키마·누락/손상·다른 버전은 구분해 거부. 사용자 제공 SQL·확장 모듈 실행 없음
- DB/WAL 읽는 동안 파일이 바뀌면 사본 관측을 거부. 실행 중인 서버의 원자적 전체 스냅샷을 보장하지 않음
- 파일: 경계 이탈·비일반 파일·메타데이터 링크 거부. 파일 내용은 결과에 저장하지 않음
- YAML: 깊이 20, 필드별 변환 노드 2,000개, 문서 전체 변환 노드 10,000개, 문자열 64KiB. 별칭 그래프를 제한 없이 확장하지 않음
- JWT: 토큰 길이 최대 32KiB, payload 최대 8KiB. 불투명 토큰을 해독·검증했다고 기록하지 않음
- 모든 새 CLI: 입력 덮어쓰기 거부, 엄격한 UTF-8 JSON, 임시 결과 후 원자적 교체, 수집 상태에 따른 종료 코드

## 실행 예

- 먼저 설치 의존성을 갱신: `python -m pip install -r requirements-dev.txt`
- 아래 경로는 가상 예시. 실제 원천 위치와 읽기 범위는 담당자가 확인해서 지정
- 출력은 탐색·원천 경계 밖 별도 디렉터리 사용

```powershell
.\.venv\Scripts\python.exe -m asset_scanner.installation_inventory --state-dir C:\testbed\.openclaw --workspace-dir C:\testbed\workspace --output C:\scanner-results\installations.json
.\.venv\Scripts\python.exe -m asset_scanner.installation_inventory --state-db C:\testbed\state\openclaw.sqlite --allow-root C:\testbed\plugins --output C:\scanner-results\index.json
.\.venv\Scripts\python.exe -m asset_scanner.auth_metadata --mcp-oauth-json C:\testbed\exports\mcp-oauth.json --output C:\scanner-results\auth.json
```

- Linux 실제 PID 관측은 `python -m asset_scanner.process_identity --pid <담당자가_확인한_PID> --output /별도출력경로/process.json`
- JWT 클레임 해석을 원할 때만 `--inspect-token-claims` 추가
- 인증 JSON·DB·토큰을 GitHub나 채팅에 업로드할 필요 없음. 수집 결과와 원본 자료를 혼동하지 않음

## 검증 근거

- 새 테스트: `test_channel_policy_sources.py`, `test_skill_yaml_standard.py`, `test_auth_metadata_sources.py`, `test_installation_discovery.py`, `test_process_identity.py`
- 가상 입력 조건: 사람이 만든 JSON/JSON5·SKILL.md·설치 트리·SQLite와 WAL. 실제 운영 계정·토큰 사용 없음
- 자기 테스트 프로세스의 실제 UID/GID는 OS 함수와 대조. 이것은 실제 OpenClaw 프로세스 검증이 아님
- 기존 시험: 개발용 MCP stdio·HTTP·TLS 서버, 가짜 OpenClaw CLI 유지
- 최종 전체 실행: **Linux / Python 3.12.14 / PyYAML 6.0.3 / pytest 9.1.1, 50개 파일·1,130 passed / 0 failed / 0 skipped, pytest 종료 코드 0, 236.49초**
- GitHub와 같은 LF 줄바꿈의 게시용 사본에서 전체 검사를 재현. 초기 검증본과 소스·테스트의 내용은 줄바꿈 외 동일
- 기준 1,028개에 신규 회귀 102개 포함. 한 번에 완료한 전체 실행이며 영향 검사·과거 결과와 합산하지 않음
- 영향 검사: 272개 통과, 종료 코드 0
- 보호 장치 변형 검사: 설치 경계·JWT 개인정보 제외·YAML 문서 한도·모델 계정 namespace 필터를 각각 제거한 별도 사본에서 해당 회귀가 실패(각 종료 코드 1). 실제 검증본에는 변형을 적용하지 않음
- 새 CLI 4종의 실제 실행: installation_inventory·auth_metadata·permission_auth·process_identity 모두 종료 코드 0, stderr 비어 있음, 입력 파일 전후 바이트 일치, 결과/콘솔의 가짜 비밀 표식 노출 0건
- 새 실행 의존성 PyYAML 6.0.3을 설치하고 pip check 통과. Windows 최신 코드 전체 실행은 아직 하지 않음

## 실환경·합의 후 확인할 항목

- 실제 OpenClaw·OVA의 설치 경로·출력·DB 버전·접근 권한·프로필과 일치하는지 확인
- 실제 원격 도메인·공인 CA·프록시·인증 환경 확인
- 실제 Gateway/Node PID·설정 선택·재시작/복제/재페어링 후 identity 유지 대조
- 공통 ID·provider 의미·환경/프로필 계약·catalog/capability 해시 직렬화·정책 묶음은 협의 유지
- 서명/무결성 신뢰 기준·modified 기준·Plugin/Skill last_updated의 권위 있는 원천은 임의 생성하지 않음
- Plugin 고유 정책 전체·다른 플랫폼의 실시간 프로세스 조회·암호화된 보호 저장소·전체 OpenClaw 설정 검증·실효 권한 계산은 이번 기능으로 구현됐다고 표현하지 않음
- 대시보드 어댑터 매핑은 담당자와 연결해야 하며 이번 작업에서는 수정하지 않음

## 원천

- OpenClaw [`eb377ac59e6c9fd6c7705028034812becf00271b`](https://github.com/openclaw/openclaw/tree/eb377ac59e6c9fd6c7705028034812becf00271b)
  - `src/config/{types.channels,zod-schema.channel-messaging-common,types.telegram,types.discord,types.slack,zod-schema.root-shape,zod-schema.installs}.ts`
  - `src/plugins/{roots,install-paths,installed-plugin-index-types,installed-plugin-index-store,installed-plugin-index-row}.ts`
  - `src/agents/auth-profiles/{types,credential-schema,constants}.ts`, `src/agents/mcp-oauth-store.{types,kernel}.ts`, `src/state/user-model-accounts.ts`
- PyYAML [`6.0.3` SafeLoader](https://github.com/yaml/pyyaml/blob/6.0.3/lib/yaml/loader.py): 구문 노드만 사용하며 Python 객체 생성자를 호출하지 않음.
- Linux [`v6.12` proc 문서](https://github.com/torvalds/linux/blob/v6.12/Documentation/filesystems/proc.rst)


### 신규 회귀의 구성

- `tests/test_auth_metadata_sources.py`: 27개
- `tests/test_channel_policy_sources.py`: 26개
- `tests/test_installation_discovery.py`: 20개
- `tests/test_process_identity.py`: 15개
- `tests/test_skill_yaml_standard.py`: 14개

### 실제 가상 출력 발췌

- 입력: 사람이 만든 sample-plugin 설치 트리·가상 SQLite, 가짜 토큰, 가상 채널 설정. 실제 OpenClaw 자료가 아님
- 설치/메타데이터/정책의 CLI를 실행한 결과에서 관련 필드만 발췌

```json
{
  "installation": {
    "plugin_id": "sample-plugin",
    "install": {
      "source": "npm",
      "spec": "sample-plugin@1.0.0",
      "installedAt": "2026-11-01T00:00:00Z"
    },
    "digest_metadata": {
      "integrity": {
        "declared": true,
        "verified": false
      }
    }
  },
  "entry_file": {
    "file_kind": "script_hint",
    "basis": "extension_only_not_runtime_verified",
    "executed_or_imported": false,
    "mtime_is_last_updated": false
  },
  "token_claims": {
    "credential_field": "token",
    "status": "decoded_unverified",
    "signature_verified": false,
    "claim_time_unit": "unix_seconds",
    "claims": {
      "iss": "https://issuer.example.test",
      "aud": "sample-mcp",
      "scope": "docs:read",
      "exp": 1900000000
    }
  },
  "owner_partition": {
    "stored_owner_partition_ref": "auth-source[2]:owner[0]",
    "owner_identity_resolved": false
  }
}
```
