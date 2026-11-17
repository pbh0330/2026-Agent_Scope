# 위협 구성 S5-T3 — https인데 sslVerify 항목 없음 (안전)

S5 설정 사본 3개 중 세 번째. `inventory-remote.sslVerify` 항목을 삭제한다(url은 https 그대로). **경고 없음(안전)** — sslVerify 생략은 OpenClaw 2026.9.6 기본값에서 **인증서 검증을 그대로 수행(ON)**하므로 `sslVerify: true`와 같게 안전하다. S5-C3으로 경고를 내면 FAIL이다(생략은 `false`가 아니다).

전체 설명·T1·T2 비교: [../S5-T1/README.md](../S5-T1/README.md) · 정답: [../../ground-truth/S5-T3.json](../../ground-truth/S5-T3.json)

## 결정 — OpenClaw 기본 sslVerify 동작 (2026-11-17)

> 이전 상태: `unknown`(기본값 미확인). 아래 검증으로 **안전**으로 확정하고 정답(`expected_unknown` → `expected_no_alert`)을 갱신함.

**질문:** `sslVerify` 줄이 없을 때 OpenClaw가 기본으로 인증서 검증을 하는가?

**① 소스 근거 (권위 있는 기준, OpenClaw 2026.9.6 `eb377ac`)**

`dist/mcp-http-fetch-*.mjs`의 원격 MCP fetch 구성:

```js
// 커스텀 디스패처는 sslVerify===false 또는 clientCert/Key가 있을 때만 생성
const needsCustomDispatcher = params.sslVerify === false || Boolean(params.clientCert || params.clientKey);
// rejectUnauthorized:false 는 오직 sslVerify===false 일 때만 설정
customConnect ??= {
  ...params.sslVerify === false ? { rejectUnauthorized: false } : {},
  ...
};
```

`dist/mcp-transport-config-*.mjs`는 `sslVerify`가 **정의된 경우에만** 설정에 통과시킨다(`!== void 0`). 즉 **항목을 생략하면 `sslVerify`는 undefined → `=== false`가 아님 → 검증 비활성화 경로를 타지 않고 Node/undici 기본값(검증 ON)으로 연결**된다. `ssl_verify`(snake_case)도 동일하게 정규화된다.

**② 실측 (팀원 제안 방식, 게이트웨이 tb-gw)**

게이트웨이에서 실습용 CA 신뢰(`NODE_EXTRA_CA_CERTS`)를 빼고, sslVerify를 생략한 채 `inventory-remote`(https, 실습 CA 서명 인증서)로 연결:

| 조건 | 결과 |
|---|---|
| CA 신뢰 O (`NODE_EXTRA_CA_CERTS` 설정) | **연결됨** (TLS 통과, HTTP 401 = 인증 헤더만 없음) |
| CA 신뢰 X (`NODE_EXTRA_CA_CERTS` 제거) | **거부됨** (`UNABLE_TO_VERIFY_LEAF_SIGNATURE`) |

CA를 신뢰하지 않으면 TLS 단계에서 거부된다 → **기본적으로 인증서를 검증한다.** 팀원 규칙("거부되면 안전")에 따라 **sslVerify 생략 = 안전**.

**결론:** 생략은 `sslVerify: true`와 동치(검증 ON). S5-T3은 **경고를 내면 안 된다**(`expected_no_alert`). 참고로 **명시적 `sslVerify: false`(S5-T2)만** 검증을 끄므로 high 경고 대상이다.

> 재현: tb-gw에서 `node -e 'fetch("https://tb-node:8443/mcp").then(r=>console.log(r.status)).catch(e=>console.log(e.cause?.code))'`를, `~/.profile`을 읽은 로그인 셸(CA 신뢰 O)과 `NODE_EXTRA_CA_CERTS`를 unset한 셸(CA 신뢰 X)에서 각각 실행.
