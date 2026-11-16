// 자산 현황: 지금 안전한가? → 무엇이 식별됐나 → 시나리오별 상태
import { Boxes, ChartColumn, ChevronRight, Eye, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Donut } from '../components/charts'
import type { Model } from '../data/model'
import { type Present, SCENARIO_KO, bySeverity, copyFor, isUnknown } from '../data/present'
import type { UsageBundle } from '../data/usage'

export type Go = (page: 'home' | 'map' | 'threats', opts?: { scenario?: string; alert?: string }) => void

const DONUT: { label: string; types: string[]; color: string }[] = [
  { label: '도구', types: ['tool'], color: '#2DBE8B' },
  { label: '리소스·프롬프트', types: ['resource_prompt'], color: '#8B6CF6' },
  { label: 'MCP 서버', types: ['mcp_server'], color: '#4A8CF7' },
  { label: '권한·인증', types: ['permission_auth'], color: '#FF9F2E' },
  { label: '스킬·플러그인', types: ['skill', 'plugin'], color: '#14B8C4' },
  { label: '게이트웨이·노드', types: ['gateway', 'node'], color: '#5B5FEF' },
]

export function HomePage({ model, present, usage, go }: { model: Model; present: Present; usage: UsageBundle | null; go: Go }) {
  const alerts = model.detections.alerts.slice().sort(bySeverity)
  const tools = model.ofType('tool')
  const usable = tools.filter(t => model.stateValue(t, 'EXPOSED') === true).length
  const riskyAssets = new Set(alerts.flatMap(a => a.asset_ids)).size
  const servers = present.servers
  const riskyServers = servers.filter(s => (model.alertsByAsset.get(s.asset_id) ?? []).length).length
  const donut = DONUT.map(d => ({ label: d.label, color: d.color, value: model.assets.filter(a => d.types.includes(a.asset_type)).length }))

  // 배너 문장: 같은 조건끼리 묶어 많은 순으로 두 가지
  const byRule = new Map<string, number>()
  for (const a of alerts) byRule.set(a.rule_id, (byRule.get(a.rule_id) ?? 0) + 1)
  const phrases = [...byRule.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2).map(([r, n]) => copyFor(r).phrase(n))

  return (
    <div className="home">
      <div className="home-main">
        {alerts.length ? (
          <section className="hero">
            <div className="big">{alerts.length}</div>
            <div><h2>고쳐야 할 위협이 있어요</h2><p>{phrases.join(' · ')}{byRule.size > 2 ? ' 외' : ''}</p></div>
            <button className="btn light" onClick={() => go('threats')}>세부 정보 보기</button>
          </section>
        ) : (
          <section className="hero ok">
            <div className="big">0</div>
            <div><h2>고쳐야 할 위협이 없어요</h2><p>점검한 자산에서 위협 조건에 맞는 설정이 나오지 않았어요.</p></div>
            <button className="btn light" onClick={() => go('map')}>자산 지도 보기</button>
          </section>
        )}

        <section className="kpis">
          <Kpi tone="sky" icon={<Boxes size={22} />} label="식별된 자산" value={model.assets.length.toLocaleString('ko-KR')} onClick={() => go('map')} />
          <Kpi tone="rose" icon={<TriangleAlert size={22} />} label="위협 자산" value={String(riskyAssets)} onClick={() => go('threats')} />
          <Kpi tone="mint" icon={<Eye size={22} />} label="쓸 수 있는 도구" value={String(usable)} unit={`/ ${tools.length}`} onClick={() => go('map')} />
          <Kpi tone="lav" icon={<ChartColumn size={22} />} label="AI 사용량" value={usage ? usage.summary.attributed_tokens.toLocaleString('ko-KR') : '—'} unit={usage ? '토큰' : ''} onClick={() => go('map')} />
        </section>

        <div className="home-row">
          <section className="card">
            <h2 className="card-h">자산 유형</h2>
            <div className="dw">
              <Donut data={donut} size={160} thickness={24} center={<><b>{model.assets.length}</b><span>자산</span></>} />
              <ul className="lg">{donut.map(d => <li key={d.label}><i style={{ background: d.color }} /><span>{d.label}</span><b>{d.value}</b></li>)}</ul>
            </div>
          </section>
          <section className="card">
            <h2 className="card-h">노출과 위협</h2>
            <div className="rings">
              <RingStat value={tools.length ? usable / tools.length : 0} text={tools.length ? `${Math.round((usable / tools.length) * 100)}%` : '—'} color="var(--mint)"
                title="도구 노출" desc={`${tools.length}개 중 ${usable}개를 에이전트가 쓸 수 있어요`} />
              <RingStat value={servers.length ? riskyServers / servers.length : 0} text={`${riskyServers}/${servers.length}`} color="var(--rose)"
                title="위협이 있는 MCP 서버" desc={`${servers.length}개 중 ${riskyServers}개`} />
            </div>
          </section>
        </div>
      </div>

      <aside className="card home-side">
        <div className="card-h row"><h2>위협 시나리오</h2><button className="more" onClick={() => go('threats')}>전체</button></div>
        <ul className="scl">
          {SCENARIO_KO.map(sc => {
            const ev = model.detections.evaluations.filter(e => e.scenario_id === sc.id)
            const det = alerts.filter(a => a.scenario_id === sc.id).length
            const unk = ev.filter(e => isUnknown(e.result)).length
            const [cls, label] = det ? ['bad', `위협 ${det}`] : unk ? ['off', `확인 못 함 ${unk}`] : ev.length ? ['ok', '안전'] : ['off', '점검 안 함']
            return (
              <li key={sc.id}>
                <button onClick={() => go('threats', { scenario: sc.id })}>
                  <span className={`av ${sc.id.toLowerCase()}`}>{sc.id}</span>
                  <span className="who"><b>{sc.name}</b><small>{sc.what}</small></span>
                  <span className={`st ${cls}`}>{label}</span>
                  <ChevronRight size={15} className="chev" />
                </button>
              </li>
            )
          })}
        </ul>
      </aside>
    </div>
  )
}

function Kpi({ tone, icon, label, value, unit, onClick }: { tone: string; icon: ReactNode; label: string; value: string; unit?: string; onClick?: () => void }) {
  return (
    <button className={`kpi ${tone}`} onClick={onClick}>
      <span className="kpi-icon">{icon}</span>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}{unit && <small>{unit}</small>}</span>
    </button>
  )
}

function RingStat({ value, text, color, title, desc }: { value: number; text: string; color: string; title: string; desc: string }) {
  const r = 30, c = 2 * Math.PI * r
  return (
    <div className="rs">
      <svg width={80} height={80} viewBox="0 0 76 76" aria-hidden>
        <circle r={r} cx={38} cy={38} fill="none" stroke="var(--sunken)" strokeWidth={9} />
        <circle r={r} cx={38} cy={38} fill="none" stroke={color} strokeWidth={9} strokeLinecap="round" strokeDasharray={`${c * Math.min(1, value)} ${c}`} transform="rotate(-90 38 38)" />
        <text x={38} y={43} textAnchor="middle" fontSize={15} fontWeight={800} fill="var(--ink)">{text}</text>
      </svg>
      <div><b>{title}</b><p>{desc}</p></div>
    </div>
  )
}
