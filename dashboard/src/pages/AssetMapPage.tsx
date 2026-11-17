// 자산 지도: 8종 요약 → 구조도(+상세 패널) → AI 사용량
import { BookOpen, Boxes, KeyRound, Monitor, Puzzle, Server, Smartphone, Wrench } from 'lucide-react'
import { useEffect, useState } from 'react'
import { AreaChart } from '../components/charts'
import { AssetPanel, MapLegend, type MapPick, StructureMap } from '../components/structure'
import type { Model } from '../data/model'
import { type Present, REL_KO, TYPES_8, TYPE_DESC, TYPE_KO, usageToolName } from '../data/present'
import type { UsageBundle } from '../data/usage'
import type { AssetType } from '../types/contracts'

const TYPE_ICON: Record<AssetType, typeof Server> = {
  gateway: Monitor, node: Smartphone, mcp_server: Server, tool: Wrench, resource_prompt: Boxes, skill: BookOpen, plugin: Puzzle, permission_auth: KeyRound,
}

export function AssetMapPage({ model, present, usage, onThreat, initial }: {
  model: Model; present: Present; usage: UsageBundle | null; onThreat: (alertId: string) => void; initial?: string
}) {
  const [pick, setPick] = useState<MapPick | null>(() => toPick(initial))
  useEffect(() => setPick(toPick(initial)), [initial])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setPick(null) }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [])
  return (
    <>
      <section className="types8" aria-label="자산 8종">
        {TYPES_8.map(t => {
          const list = model.ofType(t)
          const risk = list.filter(a => (model.alertsByAsset.get(a.asset_id) ?? []).length).length
          const Icon = TYPE_ICON[t]
          return (
            <div key={t} className="t8">
              <span className="ti"><Icon size={19} strokeWidth={1.9} /></span>
              <b>{list.length}</b><strong>{TYPE_KO[t]}</strong><em>{TYPE_DESC[t]}</em>
              {risk > 0 && <i>위협 {risk}</i>}
            </div>
          )
        })}
      </section>
      <RelationStrip model={model} />

      <section className="card">
        <StructureMap model={model} present={present} picked={pick} onPick={setPick} />
        <MapLegend />
      </section>
      {pick && <AssetPanel model={model} present={present} pick={pick} usage={usage} onClose={() => setPick(null)} onThreat={onThreat} onPick={setPick} />}

      <UsageSection usage={usage} />
    </>
  )
}

/**
 * 자산 사이 관계: 저장된 관계를 종류별로 세고 방향(어느 자산 → 어느 자산)을 함께 적는다.
 * 지도에 보조로 그린 선은 세지 않는다. 숫자는 스냅숏의 relations 개수와 같다.
 */
function RelationStrip({ model }: { model: Model }) {
  const groups = new Map<string, { n: number; from: Set<string>; to: Set<string> }>()
  for (const r of model.relations) {
    const g = groups.get(r.relation_type) ?? { n: 0, from: new Set<string>(), to: new Set<string>() }
    g.n++
    const src = model.byId.get(r.source_asset_ref)
    const dst = r.target.asset_ref ? model.byId.get(r.target.asset_ref) : undefined
    if (src) g.from.add(TYPE_KO[src.asset_type])
    g.to.add(dst ? TYPE_KO[dst.asset_type] : r.target.kind)
    groups.set(r.relation_type, g)
  }
  const rows = [...groups.entries()].sort((a, b) => b[1].n - a[1].n)
  if (!rows.length) return null
  return (
    <section className="rels" aria-label="자산 사이 관계">
      <div className="rels-h"><b>{model.relations.length}</b><span>자산 사이 관계</span></div>
      <ul>
        {rows.map(([type, g]) => (
          <li key={type}>
            <strong>{REL_KO[type] ?? type}</strong><b>{g.n}</b>
            <em>{[...g.from].join(', ')} → {[...g.to].join(', ')}</em>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** 다른 화면에서 넘어온 대상: 자산 ID 또는 group:<실행 위치 ID>:<자산 종류> */
function toPick(v?: string): MapPick | null {
  if (!v) return null
  if (v.startsWith('group:')) { const [, host, type] = v.split(':'); return { kind: 'group', host, type: type as AssetType } }
  return { kind: 'asset', id: v }
}

function UsageSection({ usage }: { usage: UsageBundle | null }) {
  if (!usage) {
    return (
      <section className="usage-sec">
        <h2 className="sec-title">AI 사용량</h2>
        <div className="card empty-card">아직 AI 사용 기록이 없어요. 토큰 수집기가 기록을 남기면 여기에 표시돼요.</div>
      </section>
    )
  }
  const s = usage.summary
  const fmt = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' })
  const day = new Date(s.window.start).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })
  const points = usage.timeseries.total.points.map(p => ({ label: fmt(p.t), value: p.tokens, note: `요청 ${p.calls}번` }))
  const items = usage.byAsset.asset.items.slice().sort((a, b) => b.tokens - a.tokens)
  const max = Math.max(1, ...items.map(i => i.tokens))
  const linked = items.filter(i => i.asset_id).length
  return (
    <section className="usage-sec">
      <h2 className="sec-title">AI 사용량</h2>
      <div className="usage-row">
        <div className="card">
          <div className="card-h row"><h2>사용 흐름</h2><small className="muted">{day} {fmt(s.window.start)}~{fmt(s.window.end)}</small></div>
          <div className="utot">
            <div><span>사용한 토큰</span><b>{s.attributed_tokens.toLocaleString('ko-KR')}</b></div>
            <div><span>요청</span><b>{s.calls}번</b></div>
            <div><span>예상 비용</span><b>{s.estimated_cost_usd == null ? '—' : `약 $${s.estimated_cost_usd < 0.01 ? s.estimated_cost_usd.toFixed(3) : s.estimated_cost_usd.toFixed(2)}`}</b></div>
          </div>
          <AreaChart points={points} unit=" 토큰" />
        </div>
        <div className="card">
          <div className="card-h row"><h2>어디에 썼나</h2><small className="muted">도구별</small></div>
          <ul className="ul">
            {items.map(i => {
              const n = usageToolName(i.label, i.tool_source)
              return (
                <li key={i.key}>
                  <div><b>{n.name}</b><em>{n.kind} · {i.calls}번</em></div>
                  <strong>{i.tokens.toLocaleString('ko-KR')}</strong>
                  <div className="bar"><span style={{ width: `${Math.max(1, (i.tokens / max) * 100)}%` }} /></div>
                </li>
              )
            })}
          </ul>
          {linked < items.length && <p className="emp">자산 지도의 서버와 아직 연결되지 않은 기록이 있어요. 연결되면 서버를 눌렀을 때 그 서버의 사용량이 함께 보여요.</p>}
        </div>
      </div>
    </section>
  )
}
