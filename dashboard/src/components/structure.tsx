// 자산 지도: 어디서 실행되나(게이트웨이·노드) → 무엇이 연결됐나(MCP 서버) → 무엇을 할 수 있나(도구·리소스)
// 플러그인·스킬·권한·인증은 실행 위치 상자 안에 개수로, 세부는 오른쪽 패널에서 보여 준다.
// 색은 상태에만 쓴다: 빨강=위협, 초록=에이전트에 보이는 도구, 회색=막힘·확인 못 함.
import { ChevronDown, ChevronRight, Lock, X } from 'lucide-react'
import { useState } from 'react'
import type { Model } from '../data/model'
import { type Present, TYPE_DESC, TYPE_KO, copyForAsset, serverLead, serverStats } from '../data/present'
import type { UsageBundle } from '../data/usage'
import { usageForAsset } from '../data/usage'
import type { Asset, AssetType } from '../types/contracts'

export type MapPick = { kind: 'asset'; id: string } | { kind: 'group'; host: string; type: AssetType }

const W = 980, C1 = 20, HW = 230, C2 = 300, SW = 320, C3 = 660, RH = 60, CH = 38

export function StructureMap({ model, present, mode = 'all', focus, picked, onPick }: {
  model: Model; present: Present; mode?: 'all' | 'risk'; focus?: Set<string>; picked?: MapPick | null; onPick?: (p: MapPick) => void
}) {
  const hosts = [...model.ofType('gateway'), ...model.ofType('node')]
  const alertsOn = (ids: string[]) => new Set(ids.flatMap(id => (model.alertsByAsset.get(id) ?? []).map(a => a.alert_id))).size
  const dim = (risk: number) => (mode === 'risk' && !risk ? 0.28 : 1)
  const out: JSX.Element[] = []
  let y = 52
  let prevHostBottom: number | null = null

  hosts.forEach((h, hi) => {
    const rows = present.servers.filter(s => present.hostAsset(s)?.asset_id === h.asset_id)
    const groups = (['permission_auth', 'plugin', 'skill'] as AssetType[])
      .map(t => ({ t, items: model.ofType(t).filter(a => present.hostAsset(a)?.asset_id === h.asset_id) }))
      .filter(g => g.items.length)
    const hostH = Math.max(76 + groups.length * CH, rows.length * RH - 12, 120)
    const top = y
    const hy = top + Math.min(hostH / 2, 120)

    if (prevHostBottom !== null) {
      out.push(<line key={`pair${hi}`} x1={C1 + HW / 2} y1={prevHostBottom} x2={C1 + HW / 2} y2={top} stroke="var(--indigo)" strokeWidth={2} strokeDasharray="5 5" />)
    }
    const hostPicked = picked?.kind === 'asset' && picked.id === h.asset_id
    out.push(
      <g key={h.asset_id}>
        <rect x={C1} y={top} width={HW} height={hostH} rx={20} fill="url(#sm-host)" stroke={hostPicked ? 'var(--ink)' : 'none'} strokeWidth={2.5} />
        <g className="sm-hit" onClick={() => onPick?.({ kind: 'asset', id: h.asset_id })} role="button" tabIndex={0}
          onKeyDown={e => { if (e.key === 'Enter') onPick?.({ kind: 'asset', id: h.asset_id }) }}>
          <rect x={C1} y={top} width={HW} height={62} rx={20} fill="transparent" />
          <text x={C1 + 20} y={top + 32} fontSize={18} fontWeight={800} fill="#fff">{present.name(h)}</text>
          <text x={C1 + 20} y={top + 52} fontSize={12} fill="#fff" opacity={0.88}>{TYPE_DESC[h.asset_type]}</text>
        </g>
        {groups.map((g, gi) => {
          const risk = alertsOn(g.items.map(i => i.asset_id))
          const gy = top + 68 + gi * CH
          const isPicked = picked?.kind === 'group' && picked.host === h.asset_id && picked.type === g.t
          return (
            <g key={g.t} className="sm-hit" opacity={dim(risk)} onClick={() => onPick?.({ kind: 'group', host: h.asset_id, type: g.t })}
              role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') onPick?.({ kind: 'group', host: h.asset_id, type: g.t }) }}>
              <title>{`${TYPE_KO[g.t]} ${g.items.length}개 · 눌러서 보기`}</title>
              <rect x={C1 + 16} y={gy} width={HW - 32} height={30} rx={9} fill={risk ? 'var(--rose-t)' : 'rgba(255,255,255,.18)'}
                stroke={risk ? 'var(--rose)' : isPicked ? '#fff' : 'none'} strokeWidth={1.2} />
              <text x={C1 + 30} y={gy + 20} fontSize={13} fontWeight={800} fill={risk ? '#C92F49' : '#fff'}>{TYPE_KO[g.t]} {g.items.length}</text>
              <text x={C1 + HW - 30} y={gy + 20} textAnchor="end" fontSize={11} fill={risk ? '#C92F49' : '#fff'} opacity={0.85}>보기</text>
              {risk > 0 && <Badge x={C1 + HW - 16} y={gy} n={risk} />}
            </g>
          )
        })}
      </g>,
    )

    rows.forEach((s, i) => {
      const ry = top + i * RH, cy = ry + 24
      const risk = alertsOn([s.asset_id])
      const st = serverStats(model, s)
      const nt = st.tools.length
      const step = nt ? Math.min(15, (W - C3 - 150) / nt) : 15
      const sel = picked?.kind === 'asset' && picked.id === s.asset_id
      const foc = focus?.has(s.asset_id)
      out.push(
        <g key={s.asset_id} opacity={dim(risk)}>
          <path d={`M${C1 + HW},${hy} C${C1 + HW + 35},${hy} ${C1 + HW + 35},${cy} ${C2},${cy}`} fill="none" stroke={risk ? '#F6A5B3' : 'var(--line-strong)'} strokeWidth={1.6} />
          <g className="sm-hit" onClick={() => onPick?.({ kind: 'asset', id: s.asset_id })} role="button" tabIndex={0}
            onKeyDown={e => { if (e.key === 'Enter') onPick?.({ kind: 'asset', id: s.asset_id }) }}>
            <title>{`${present.name(s)} · 눌러서 자세히 보기`}</title>
            <rect x={C2} y={ry} width={SW} height={48} rx={12} fill={risk ? '#FFF5F6' : 'var(--surface)'}
              stroke={sel || foc ? 'var(--indigo)' : risk ? 'var(--rose)' : 'var(--line-strong)'} strokeWidth={sel || foc ? 2.2 : risk ? 1.3 : 1.2} />
            <text x={C2 + 14} y={ry + 21} fontSize={14} fontWeight={800} fill="var(--ink)">{present.name(s)}</text>
            <text x={C2 + 14} y={ry + 39} fontSize={11.5} fill={risk ? '#D9374F' : 'var(--ink-2)'}>{present.sub(s)}</text>
            {risk > 0 && <Badge x={C2 + SW} y={ry} n={risk} />}
          </g>
          <line x1={C2 + SW} y1={cy} x2={C3} y2={cy} stroke="var(--line)" strokeWidth={1.5} />
          {st.tools.map((t, ti) => {
            const ex = model.state(t, 'EXPOSED')
            const on = ex?.value === true
            const why = on ? '에이전트에 보이는 도구' : ex?.value === false ? `막힌 도구 · ${exposureReason(ex.reason)}` : `확인 못 한 도구 · ${exposureReason(ex?.reason)}`
            return <rect key={t.asset_id} x={C3 + 6 + ti * step} y={cy - 6} width={Math.min(12, step - 2)} height={12} rx={3} fill={on ? 'var(--mint)' : 'var(--off)'}>
              <title>{why}</title>
            </rect>
          })}
          {nt === 0 && <text x={C3 + 6} y={cy + 4} fontSize={11.5} fill="var(--ink-3)">도구 목록 없음</text>}
          {nt > 0 && <text x={C3 + 14 + nt * step} y={cy + 4} fontSize={12} fontWeight={700} fill="var(--ink-2)">{st.usable}/{nt}</text>}
          {st.res > 0 && (() => {
            const rx = C3 + 14 + Math.max(nt, 1) * step + 44
            const label = `리소스 ${st.res}`
            const w = 30 + label.length * 9
            return (
              <g>
                <title>{`서버가 에이전트에게 주는 자료(파일·문서·프롬프트 등) ${st.res}개`}</title>
                <rect x={rx} y={cy - 11} width={w} height={22} rx={8} fill="var(--indigo-t)" />
                <path d={`M${rx + 10},${cy - 1} l6,-4 l6,4 l-6,4 z M${rx + 10},${cy + 3} l6,4 l6,-4`} fill="none" stroke="var(--indigo)" strokeWidth={1.4} strokeLinejoin="round" />
                <text x={rx + 26} y={cy + 4} fontSize={11.5} fontWeight={700} fill="var(--indigo)">{label}</text>
              </g>
            )
          })()}
        </g>,
      )
    })
    prevHostBottom = top + hostH
    y = top + Math.max(hostH, rows.length * RH - 12) + 44
  })
  const H = y - 20

  return (
    <div className="sm-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="sm" role="img" aria-label="자산 지도: 실행 위치, 연결된 서버, 도구">
        <defs>
          <linearGradient id="sm-host" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#5B5FEF" /><stop offset="1" stopColor="#8B6CF6" /></linearGradient>
        </defs>
        {[[C1 + HW / 2, '어디서 실행되나'], [C2 + SW / 2, '무엇이 연결됐나'], [(C3 + W) / 2, '무엇을 할 수 있나']].map(([x, t]) => (
          <text key={t as string} x={x as number} y={22} textAnchor="middle" fontSize={14} fontWeight={800} fill="var(--ink-3)">{t}</text>
        ))}
        <line x1={20} x2={W - 20} y1={36} y2={36} stroke="var(--line)" />
        {out}
      </svg>
    </div>
  )
}

/** 노출 판정 사유를 사람 말로 */
export function exposureReason(r?: string): string {
  if (!r) return '이유 기록 없음'
  if (r.includes('toolFilter.include')) return '도구 필터의 허용 목록에 없음'
  if (r.includes('toolFilter.exclude')) return '도구 필터로 막음'
  if (r.includes('taskSupport')) return 'OpenClaw가 지원하지 않는 방식의 도구라 에이전트에 올리지 않음'
  if (r.includes('probe 대상 아님')) return '플러그인이 등록한 서버라 에이전트 도구 목록을 수집하지 못함'
  return r
}

function Badge({ x, y, n }: { x: number; y: number; n: number }) {
  return <g><circle cx={x} cy={y} r={9} fill="var(--rose)" /><text x={x} y={y + 4} textAnchor="middle" fontSize={11} fontWeight={800} fill="#fff">{n}</text></g>
}

export function MapLegend() {
  return (
    <div className="mk">
      <span><i className="sq" style={{ background: 'var(--mint)' }} />도구 · 에이전트에 보임</span>
      <span><i className="sq" style={{ background: 'var(--off)' }} />도구 · 막혀 있거나 확인 못 함</span>
      <span>2/14 · 보이는 도구 / 전체 도구</span>
      <span><i className="rs-pill">리소스 2</i>서버가 주는 자료</span>
      <span><i className="bd" />위협이 있는 자산</span>
      <span><i className="ct">2</i>위협 수</span>
      <span className="hint">상자를 누르면 자세히 볼 수 있어요</span>
    </div>
  )
}

/** 오른쪽 상세 패널: 사람이 읽는 설명 → 위협과 할 일 → 연결된 자산 → AI 사용량 → 세부 정보 */
export function AssetPanel({ model, present, pick, usage, onClose, onThreat, onPick }: {
  model: Model; present: Present; pick: MapPick; usage: UsageBundle | null
  onClose: () => void; onThreat: (alertId: string) => void; onPick: (p: MapPick) => void
}) {
  if (pick.kind === 'group') {
    const host = model.byId.get(pick.host)!
    const items = model.ofType(pick.type).filter(a => present.hostAsset(a)?.asset_id === pick.host)
    return (
      <aside className="ap">
        <PanelHead title={`${TYPE_KO[pick.type]} ${items.length}개`} tags={[present.name(host)]} onClose={onClose} />
        <p className="ap-lead">{TYPE_DESC[pick.type]}. {present.name(host)}에 있는 것들이에요.</p>
        <ul className="ap-list">
          {items.map(a => {
            const al = model.alertsByAsset.get(a.asset_id) ?? []
            return (
              <li key={a.asset_id} className={al.length ? 'bad' : ''}>
                <div className="t"><b>{present.name(a)}</b>{al.length > 0 && <span className="pill bad">위협 {al.length}</span>}</div>
                <p>{groupItemLine(model, present, a)}</p>
                {al.map(x => { const c = copyForAsset(x.rule_id, a); return <button key={x.alert_id} className="thr" onClick={() => onThreat(x.alert_id)}><b>{c.title}</b>{c.steps[0]}</button> })}
                <Details rows={rawRows(model, a)} />
              </li>
            )
          })}
        </ul>
      </aside>
    )
  }
  const a = model.byId.get(pick.id)
  if (!a) return null
  const alerts = model.alertsByAsset.get(a.asset_id) ?? []
  const u = usageForAsset(usage, a.asset_id)
  const isServer = a.asset_type === 'mcp_server'
  const st = isServer ? serverStats(model, a) : null
  const rules = isServer ? model.policiesFor(a) : []
  const servers = (a.asset_type === 'gateway' || a.asset_type === 'node') ? present.servers.filter(s => present.hostAsset(s)?.asset_id === a.asset_id) : []
  return (
    <aside className="ap">
      <PanelHead title={present.name(a)} tags={[TYPE_KO[a.asset_type], ...(alerts.length ? [`위협 ${alerts.length}`] : [])]} onClose={onClose} />
      <p className="ap-lead">{isServer ? serverLead(model, present, a) : `${TYPE_DESC[a.asset_type]}예요.`}</p>
      {alerts.length > 0 && (
        <section className="ap-sec">
          <h4>위협</h4>
          {alerts.map(x => { const c = copyForAsset(x.rule_id, a); return <button key={x.alert_id} className="thr" onClick={() => onThreat(x.alert_id)}><b>{c.title}</b>{c.steps[0]}</button> })}
        </section>
      )}
      {st && (
        <section className="ap-sec">
          <h4>연결된 자산</h4>
          <div className="ap-rel">
            <div><b>{st.tools.length}</b>도구</div><div><b>{st.usable}</b>에이전트에 보임</div><div><b>{st.res}</b>리소스</div>
          </div>
          {rules.length > 0 && (
            <ul className="ap-rules">
              {rules.map(r => (
                <li key={r.asset_id}><Lock size={13} /><span><b>{present.name(r).split(' · ')[0]}</b>{r.asset_subtype === 'authentication' ? '이 서버에 접속할 때 쓰는 토큰을 설정이 가리키고 있어요. 값은 읽지 않아요.' : '이 서버의 도구 중 에이전트에게 열어 줄 것과 막을 것을 정한 규칙이에요.'}</span></li>
              ))}
            </ul>
          )}
        </section>
      )}
      {servers.length > 0 && (
        <section className="ap-sec">
          <h4>등록된 서버 {servers.length}</h4>
          <ul className="ap-mini">
            {servers.map(s => <li key={s.asset_id}><button onClick={() => onPick({ kind: 'asset', id: s.asset_id })}>{present.name(s)}<ChevronRight size={14} /></button></li>)}
          </ul>
        </section>
      )}
      <div className="ap-use"><span>AI 사용량</span><b>{u ? `${u.tokens.toLocaleString('ko-KR')} 토큰 · ${u.calls}번` : '연결된 사용 기록 없음'}</b></div>
      <Details rows={rawRows(model, a)} tools={st?.tools.map(t => ({ name: t.name, on: model.stateValue(t, 'EXPOSED') === true }))} />
    </aside>
  )
}

function PanelHead({ title, tags, onClose }: { title: string; tags: string[]; onClose: () => void }) {
  return (
    <div className="ap-head">
      <div><h2>{title}</h2><div className="ap-tags">{tags.map(t => <span key={t} className={t.startsWith('위협') ? 'r' : ''}>{t}</span>)}</div></div>
      <button className="ap-x" onClick={onClose} aria-label="닫기"><X size={18} /></button>
    </div>
  )
}

function groupItemLine(m: Model, p: Present, a: Asset): string {
  if (a.asset_type === 'plugin') return p.sub(a)
  if (a.asset_type === 'skill') return '에이전트가 작업할 때 따르는 지침이에요.'
  const targets = (m.out.get(a.asset_id) ?? []).map(r => r.target.asset_ref && m.byId.get(r.target.asset_ref)).filter(Boolean) as Asset[]
  const t = targets[0]
  if (!t) return TYPE_DESC[a.asset_type]
  if (a.asset_subtype === 'authentication') return t.asset_type === 'mcp_server' ? `${p.name(t)}에 접속할 때 쓰는 토큰이에요.` : `${p.name(t)}에 들어오는 사람을 확인하는 규칙이에요.`
  return t.asset_type === 'mcp_server' ? `${p.name(t)}의 도구 중 열어 줄 것과 막을 것을 정해요.` : `에이전트에게 허용한 도구 범위를 정해요.`
}

function rawRows(m: Model, a: Asset): [string, string][] {
  const rows: [string, string][] = [['설정에 적힌 이름', a.name]]
  if (a.product?.config_path) rows.push(['설정 위치', a.product.config_path])
  if (a.project.transport) rows.push(['연결 방식', String(a.project.transport)])
  const ep = m.endpoint(a)
  if (ep) rows.push([a.product?.config?.url ? '주소' : '실행 명령', ep])
  const h = m.host(a)
  if (h && h !== '—') rows.push(['장치 이름', h])
  for (const c of a.project.credential_refs ?? []) if (c.reference_id) rows.push(['토큰 이름', c.reference_id])
  return rows
}

function Details({ rows, tools }: { rows: [string, string][]; tools?: { name: string; on: boolean }[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="ap-det">
      <button onClick={() => setOpen(!open)} aria-expanded={open}>세부 정보 보기{open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</button>
      {open && (
        <>
          <dl>{rows.map(([k, v]) => <div key={k + v}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
          {tools && tools.length > 0 && (
            <ul className="ap-tools">{tools.map(t => <li key={t.name} className={t.on ? 'on' : ''}><i />{t.name}<em>{t.on ? '사용 가능' : '막힘·확인 못 함'}</em></li>)}</ul>
          )}
        </>
      )}
    </div>
  )
}
