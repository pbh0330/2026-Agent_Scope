# 위협 구성 S5-T3 — https인데 sslVerify 항목 없음 (unknown)

S5 설정 사본 3개 중 세 번째. `inventory-remote.sslVerify` 항목을 삭제한다(url은 https 그대로). **경고 없음** — S5-C3은 OpenClaw 기본값을 확인하기 전까지 `unknown`이며, `detected`/`not_detected`로 나오면 FAIL이다(생략은 `false`가 아니다).

전체 설명·T1·T2 비교: [../S5-T1/README.md](../S5-T1/README.md) · 정답: [../../ground-truth/S5-T3.json](../../ground-truth/S5-T3.json)
