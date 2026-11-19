# 사용 현황 API 응답 사본 — 테스트베드 실측 (11.18)

대시보드가 API 없이 열릴 때 쓰는 정적 사본이다. 파일 이름·경로는 대시보드 파이프라인(`dashboard/pipeline/build_data.py`의 `USAGE_API_FILES`)과 같다.
대시보드에 넣을 때는 이 폴더의 8개 파일을 `dashboard/public/data/usage-api/`에 그대로 덮어쓴다.

| 파일 | API 경로 |
|---|---|
| `health.json` | `/api/v1/usage/health` |
| `summary.json` | `/summary` |
| `by-asset.asset.json` / `.server` / `.pattern` | `/by-asset?group=asset` / `server` / `pattern` |
| `records.json` | `/records?limit=500` |
| `timeseries.json` | `/timeseries` |
| `brake-events.json` | `/brake-events?limit=500` |

## 만든 방법

- 데이터: 테스트베드 tb-gw(OpenClaw 2026.9.6, OVA SNAP-2-P2를 VirtualBox로 가져와 `docs/testbed-setup.md` 3~8절 적용)에서
  `openclaw agent`로 MCP 서버 4개를 쓰는 요청을 보내 남은 스팬 파일·플러그인 기록. 원본 기록 파일은 저장소에 올리지 않는다(`.gitignore`).
- 스냅샷: `snap-p2-20261117T101837Z`(`feature/dashboard`의 `dashboard/public/data/snapshots/P2/snapshot.json`, 스키마 0.7.0-draft)
- 실행(고정 응답 모드, 커밋 9de729d 이후 계산기):

```bash
agentscope-usage-api --env agentscope-testbed --profile tb-openclaw \
  --inventory snapshot.json --input agentscope-traces.jsonl \
  --tool-results agentscope-tool-results.jsonl --include-cache-in-prompt
```

## 결과

기록 37건, 귀속 토큰 39,118, 토큰 수 누락 0, 전부 P2 스냅샷의 Tool 자산에 `matched`.

| 서버 | 호출 | 토큰 |
|---|---|---|
| fs-workspace | 3 | 11,107 |
| kg-memory (노드) | 4 | 2,817 |
| inventory-remote | 4 | 1,669 |
| demo-everything (노드) | 2 | 934 |
| 내장 도구(core) | 24 | 22,591 |

- 브레이크는 `warn` 모드이고 기준을 넘은 실행이 없어 `brake-events`는 0건이다.
- 테스트 요청은 MCP 도구 이름을 지정해서 보낸 것이라, 사용량 크기는 정상 사용 분포가 아니다.
