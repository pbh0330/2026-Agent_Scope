// 자산 지도: 8종 요약 → 구조도(+상세 패널) → AI 사용량
import { BookOpen, Boxes, CircleCheck, CircleMinus, KeyRound, Monitor, Puzzle, Server, Smartphone, Wrench } from 'lucide-react'
import { useEffect, useState } from 'react'
import { AreaChart } from '../components/charts'
import { AssetPanel, MapLegend, type MapPick, StructureMap, exposureReason, toolsListOf } from '../components/structure'
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
      <ScanScope model={model} present={present} />
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

const SCOPE_KO: Record<string, string> = {
  gateway_config: '게이트웨이 설정', node_config: '노드 설정', skill_files: '스킬 파일', plugin_manifest: '플러그인 정보',
  server_discovery: '서버 정보', tools_list: '도구 목록', resources_list: '리소스 목록', prompts_list: '프롬프트 목록',
  resource_templates_list: '리소스 템플릿 목록', gateway_identity: '게이트웨이 식별 정보', node_identity: '노드 식별 정보',
  gateway_pairing: '노드 연결 정보', agent_exposure: '에이전트 도구 목록',
}
const STATUS_KO: Record<string, string> = { partial: '일부만 읽음', failed: '읽지 못함', not_attempted: '시도하지 못함' }

/**
 * 점검 범위: 이번 점검에서 무엇을 확인했고 무엇은 확인하지 못했는지.
 * 부분 수집(partial)은 오류가 아니라 정상 결과로 받아서, 빠진 범위를 여기서 보여 준다.
 */
function ScanScope({ model, present }: { model: Model; present: Present }) {
  const cols = model.snapshot.collection_results
  type Row = { ok: boolean; text: string; title?: string; items?: string[] }
  const rows: Row[] = []

  // 1. 설정 파일
  const cfg = cols.filter(c => c.scope === 'gateway_config' || c.scope === 'node_config')
  const cfgBad = cfg.filter(c => c.status === 'failed' || c.status === 'not_attempted')
  const secrets = cfg.reduce((n, c) => n + ((c.details?.unresolved ?? []) as unknown[]).length, 0)
  if (cfg.length) {
    const where = cfg.map(c => SCOPE_KO[c.scope]).join('·')
    rows.push(cfgBad.length
      ? { ok: false, text: `${cfgBad.map(c => SCOPE_KO[c.scope]).join('·')}을 읽지 못했어요.`, title: cfgBad.map(c => c.reason).filter(Boolean).join('\n') }
      : { ok: true, text: `${where}을 읽었어요.${secrets ? ` 토큰 같은 비밀값 ${secrets}개는 보안을 위해 값은 읽지 않고 이름만 기록했어요.` : ''}` })
  }

  // 2. 서버별 도구 목록
  const servers = present.servers
  const notListed = servers.filter(sv => toolsListOf(model, sv.asset_id)?.status !== 'success')
  if (servers.length) {
    rows.push({
      ok: notListed.length === 0,
      text: `MCP 서버 ${servers.length}개 중 ${servers.length - notListed.length}개의 도구 목록을 확인했어요.`,
      items: notListed.map(sv => {
        const c = toolsListOf(model, sv.asset_id)
        return `${present.name(sv)} · ${c ? STATUS_KO[c.status] ?? c.status : '수집 기록 없음'}${c?.reason ? ` (${c.reason})` : ''}`
      }),
    })
  }

  // 3. 에이전트에 보이는지
  const tools = model.ofType('tool')
  const unk = tools.filter(t => model.stateValue(t, 'EXPOSED') == null)
  if (tools.length) {
    const why = new Map<string, number>()
    for (const t of unk) { const r = exposureReason(model.state(t, 'EXPOSED')?.reason); why.set(r, (why.get(r) ?? 0) + 1) }
    rows.push({
      ok: unk.length === 0,
      text: unk.length ? `도구 ${tools.length}개 중 ${unk.length}개는 에이전트에 보이는지 확인하지 못했어요.` : `도구 ${tools.length}개 모두 에이전트에 보이는지 확인했어요.`,
      items: [...why.entries()].map(([r, n]) => `${r} · ${n}개`),
    })
  }

  // 4. 그 밖에 실패·부분 수집한 작업
  const others = cols.filter(c => c.status !== 'success' && !['gateway_config', 'node_config', 'tools_list'].includes(c.scope))
  for (const c of others) rows.push({ ok: false, text: `${SCOPE_KO[c.scope] ?? c.scope}: ${STATUS_KO[c.status] ?? c.status}`, title: c.reason })

  // 5. 원래 확인하지 않는 것
  const nv = new Set(cfg.flatMap(c => (c.details?.not_verified ?? []) as string[]))
  const neverChecked = nv.has('callability') || nv.has('connection')

  const status = model.snapshot.scan.status
  return (
    <section className="card scope" aria-label="점검 범위">
      <div className="card-h row">
        <h2>점검 범위</h2>
        <span className={`st ${status === 'success' ? 'ok' : status === 'failed' ? 'bad' : 'off'}`}>
          {status === 'success' ? '모두 확인' : status === 'failed' ? '수집 실패' : '일부만 확인'}
        </span>
      </div>
      <ul className="scope-l">
        {rows.map((r, i) => (
          <li key={i} className={r.ok ? 'ok' : ''} title={r.title}>
            {r.ok ? <CircleCheck size={17} /> : <CircleMinus size={17} />}
            <div>
              <span>{r.text}</span>
              {r.items && r.items.length > 0 && <ul>{r.items.map(t => <li key={t}>{t}</li>)}</ul>}
            </div>
          </li>
        ))}
      </ul>
      {neverChecked && <p className="scope-note">서버에 실제로 연결해 도구를 호출해 보지는 않아요. 설정과 서버가 알려 준 목록으로만 판단해요.</p>}
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
