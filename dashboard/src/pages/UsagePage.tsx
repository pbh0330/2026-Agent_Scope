import { Info } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'
import { loadUsage } from '../data/load'
import { fmtTime } from '../data/model'
import type { Manifest, UsageReport } from '../types/contracts'
import { Panel } from '../components/ui'
import { AreaChart } from '../components/charts'

const PATTERN: Record<string, string> = { sequential: '순차', parallel: '병렬', batch: '배치', unattributed: '귀속 불가' }

export function UsagePage({ manifest, snapshotId }: { manifest: Manifest; snapshotId: string }) {
  const [rep, setRep] = useState<UsageReport | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  useEffect(() => { if (manifest.usage) loadUsage(manifest.usage.file).then(setRep) }, [manifest])
  if (!manifest.usage) return <div className="empty">usage.json이 없습니다. 파이프라인에 --usage로 토큰 수집기 출력을 넘기세요.</div>
  if (!rep) return <div className="empty">불러오는 중</div>

  const byTool = new Map<string, { calls: number; tokens: number; tokenCalls: number; dur: number; cost: number; src: string; mapped: string }>()
  for (const r of rep.records) {
    const k = r.tool_name
    const cur = byTool.get(k) ?? { calls: 0, tokens: 0, tokenCalls: 0, dur: 0, cost: 0, src: r.tool_source, mapped: r.mapping_status }
    cur.calls++
    if (r.approx_input_tokens !== null) { cur.tokens += r.approx_input_tokens; cur.tokenCalls++ }
    cur.dur += r.duration_ms ?? 0
    cur.cost += r.estimated_cost_usd ?? 0
    byTool.set(k, cur)
  }
  const tools = [...byTool.entries()].sort((a, b) => b[1].tokens - a[1].tokens)
  const max = Math.max(1, ...tools.map(([, v]) => v.tokens))
  const linked = rep.inventory_snapshot_id === snapshotId
  const totalTokens = tools.reduce((n, [, v]) => n + v.tokens, 0)
  const nullTokens = rep.records.filter(r => r.approx_input_tokens === null).length

  return (
    <>
      <div className={`notice${linked ? '' : ' warn'}`}>
        <Info size={16} />
        <span>
          토큰 수집기({rep.producer.name} {rep.producer.version})가 만든 usage.json입니다.
          {linked ? ' 이 스냅샷의 자산과 연결됩니다.' : <> 연결된 스냅샷은 <code>{rep.inventory_snapshot_id ?? '없음'}</code>(환경 <code>{rep.environment_id}</code>)이라 지금 보고 있는 테스트베드 스냅샷과는 연결되지 않습니다. 테스트베드에서 텔레메트리를 수집하면 같은 화면에서 자산별로 이어집니다.</>}
        </span>
      </div>
      <div className="grid-3" style={{ marginBottom: 18 }}>
        <Panel title="수집 구간">
          <dl className="kv">
            <dt>시작</dt><dd>{fmtTime(rep.window.start)}</dd>
            <dt>끝</dt><dd>{fmtTime(rep.window.end)}</dd>
            <dt>도구 호출</dt><dd>{rep.records.length}건</dd>
          </dl>
        </Panel>
        <Panel title="추정 입력 토큰" note="도구 결과가 다음 모델 입력에 더한 양의 근사값">
          <p className="lede" style={{ fontSize: '1.6rem' }}>{totalTokens.toLocaleString('ko-KR')}</p>
          <p className="small muted">순차 구간만 계산했습니다. 배치·병렬 호출 {nullTokens}건은 균등 배분하지 않고 비워 둡니다.</p>
        </Panel>
        <Panel title="자산 연결" note="서버와 도구 이름이 스냅샷의 Tool 하나와만 맞을 때 연결">
          <dl className="kv">
            {(['matched', 'ambiguous', 'unmatched'] as const).map(m => (
              <Fragment key={m}><dt>{{ matched: '연결됨', ambiguous: '후보 여럿', unmatched: '연결 안 됨' }[m]}</dt>
                <dd>{rep.records.filter(r => r.mapping_status === m).length}건</dd></Fragment>
            ))}
          </dl>
          <p className="tiny muted" style={{ marginTop: 6 }}>내장(core) 도구에는 MCP 자산을 만들지 않습니다.</p>
        </Panel>
      </div>
      <Panel title="호출 순서별 추정 입력 토큰" note="도구 결과가 다음 모델 입력에 더한 양. 빈 원은 병렬·배치 구간이라 배분하지 않은 호출">
        <AreaChart unit=" 토큰" points={rep.records.map((r, i) => ({ label: `#${i + 1}`, value: r.approx_input_tokens, note: `${r.tool_name}, ${PATTERN[r.pattern]}, ${r.duration_ms ?? '—'}ms` }))} />
      </Panel>
      <Panel title="도구별 추정 입력 토큰" note="막대: 순차 구간 합계. 빗금: 토큰을 배분하지 않은 호출이 있는 도구">
        <div role="img" aria-label="도구별 추정 입력 토큰 막대 그래프">
          {tools.map(([name, v]) => (
            <div className="usage-bar" key={name} onMouseEnter={() => setHover(name)} onMouseLeave={() => setHover(null)} style={{ position: 'relative' }}>
              <span><code>{name}</code> <span className="tiny muted">{v.src === 'core' ? '내장' : 'MCP'}</span></span>
              <span className="bar">
                {v.tokens > 0 ? <span style={{ width: `${(v.tokens / max) * 100}%` }} /> : <span className="hatched" style={{ width: '100%' }} />}
              </span>
              <span className="num small">{v.tokenCalls ? v.tokens.toLocaleString('ko-KR') : '배분 안 함'}</span>
              {hover === name && <div className="rung-tip" style={{ left: 190, top: -30 }}>호출 {v.calls}건, 토큰 계산 {v.tokenCalls}건, 실행 {Math.round(v.dur)}ms, 추정 비용 ${v.cost.toFixed(6)}</div>}
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="호출 기록" pad={false} className="">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>도구</th><th>구간</th><th className="num">실행 ms</th><th className="num">추정 토큰</th><th className="num">추정 비용</th><th>자산 연결</th><th>모델</th></tr></thead>
            <tbody>
              {rep.records.map(r => (
                <tr key={r.usage_id} style={{ cursor: 'default' }}>
                  <td><code>{r.tool_name}</code></td>
                  <td className="small">{PATTERN[r.pattern]}</td>
                  <td className="num small">{r.duration_ms ?? '—'}</td>
                  <td className="num small">{r.approx_input_tokens ?? <span className="muted">배분 안 함</span>}{r.negative_delta && <span className="tiny muted"> 보정 0</span>}</td>
                  <td className="num small">{r.estimated_cost_usd !== null ? `$${r.estimated_cost_usd.toFixed(6)}` : '—'}</td>
                  <td className="small"><span className={`sev ${r.mapping_status === 'matched' ? 'normal' : 'none'}`}>{r.mapping_status === 'matched' ? '연결됨' : r.mapping_status === 'ambiguous' ? '후보 여럿' : '연결 안 됨'}</span></td>
                  <td className="tiny muted">{r.model}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <p className="tiny muted" style={{ marginTop: 12, maxWidth: '80ch' }}>단가: {rep.records[0]?.pricing.source === 'reference_list_price' ? `공개 목록가 참고값(${rep.records[0]?.pricing.version})이며 실제 청구액이 아닙니다.` : rep.records[0]?.pricing.source}</p>
    </>
  )
}
