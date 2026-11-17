# 위협 구성 S5 — 보안이 약한 연결 (설정 사본 T1~T3)

> 기준: `SNAP-2-P2`. 기대 경고: PR #7 `expected-results.md` 7절 (v2.1)
> 정답 목록: [T1](../../ground-truth/S5-T1.json) · [T2](../../ground-truth/S5-T2.json) · [T3](../../ground-truth/S5-T3.json)
> 상태: 원격 서버가 `inventory-remote` 하나라 세 케이스가 같은 항목을 바꾼다. 한 스냅샷에 함께 넣을 수 없어 **설정 사본 3개**로 정적 검증한다. S5는 설정만 보는 규칙이라 VM 스냅샷 없이 판정할 수 있다(VM 반영 여부는 선택).

## 1. 위험 구성 (tb-gw `mcp.servers.inventory-remote`, P2 대비 변경)

| 사본 | 변경 | 판정 |
|---|---|---|
| **S5-T1** ([tb-gw](tb-gw.openclaw.json)) | `url` → `http://tb-node:8080/mcp`, `sslVerify` 항목 삭제 | S5-C1(암호화되지 않은 전송, high). + 동반 S1-C2·S4-C3(`required: false`) |
| **S5-T2** ([../S5-T2](../S5-T2/tb-gw.openclaw.json)) | `sslVerify`: `true` → `false` (url 그대로) | S5-C2(인증서 검증 명시적 비활성화, high) |
| **S5-T3** ([../S5-T3](../S5-T3/tb-gw.openclaw.json)) | `sslVerify` 항목 삭제 (url 그대로 https) | **경고 없음(안전).** sslVerify 생략 = OpenClaw 2026.9.6 기본 검증 ON(2026-11-17 확정). S5-C3 경고를 내면 FAIL |

- S5-T1은 http 평문이라 Bearer 헤더가 노출될 수 있는 설정이다. endpoint가 바뀌어 S1-C2, 바뀐 endpoint로 토큰이 가서 S4-C3 동반 경고가 날 수 있다(둘 다 `required: false`).
- S5-T3의 핵심: 항목 생략은 `false`가 아니다. **2026-11-17 OpenClaw 2026.9.6 기본값을 확인한 결과, sslVerify 생략 시 인증서 검증을 그대로 수행(ON)**하므로 생략은 **안전**이다(경고 없음, `expected_no_alert`). 근거: 소스 `mcp-http-fetch`에서 `rejectUnauthorized: false`는 `sslVerify === false`일 때만 설정됨 + 실측(게이트웨이에서 실습 CA 신뢰를 빼면 `UNABLE_TO_VERIFY_LEAF_SIGNATURE`로 거부). 자세한 검증은 [../S5-T3/README.md](../S5-T3/README.md).
- stdio 서버 4종(`fs-workspace`·`kg-memory`·`demo-everything`·`asset-catalog`)은 S5 대상이 아니다(`not_applicable`).
- S5-C4·C5(연결 대상 검증 정보 부족, 적용 범위 불명확)는 v2.1에서 평가하지 않는다.

## 2. 정답 목록 재생성

```bash
python testbed/tools/build_ground_truth.py S5-T1 S5-T2 S5-T3
```

세 사본 모두 tb-node 설정은 P2와 동일하고, tb-gw는 `inventory-remote` 한 서버만 다르다. 생성기는 `changed_assets`에 `url`·`ssl_verify`의 before/after를 기록한다(`sslVerify` 생략은 `after: null`).
