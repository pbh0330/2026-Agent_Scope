// 위협과 조치: 위협 목록 → 고른 위협의 상세(무슨 위협 / 어떤 자산 / 세부 내용 / 할 일)
// 위치는 상세의 '자산 지도에서 보기'로 자산 지도 화면에서 확인한다.
import { ChevronDown, ChevronRight, Network } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { Model } from '../data/model'
import { type Present, SCENARIO_KO, SEVERITY_KO, TYPE_KO, bySeverity, copyFor, isUnknown, reasonFor, serverStats } from '../data/present'
import type { Asset, SecurityAlert } from '../types/contracts'

export function ThreatsPage({ model, present, scenario, alertId, onScenario, onShowMap }: {
  model: Model; present: Present; scenario?: string; alertId?: string; onScenario: (id?: string) => void; onShowMap: (assetId: string) => void
}) {
  const all = useMemo(() => model.detections.alerts.slice().sort(bySeverity), [model])
  const list = scenario ? all.filter(a => a.scenario_id === scenario) : all
  const [sel, setSel] = useState<string | undefined>(alertId ?? list[0]?.alert_id)
  useEffect(() => { setSel(alertId ?? list[0]?.alert_id) }, [alertId, scenario, model])
  const current = list.find(a => a.alert_id === sel) ?? list[0]
  const unknowns = model.detections.evaluations.filter(e => isUnknown(e.result) && (!scenario || e.scenario_id === scenario))
  const reasons = [...new Set(unknowns.map(reasonFor))]
  const [showUnk, setShowUnk] = useState(false)

  return (
    <>
      <div className="seg" role="group" aria-label="시나리오로 거르기">
        <button aria-pressed={!scenario} onClick={() => onScenario(undefined)}>전체 {all.length}</button>
        {SCENARIO_KO.map(s => {
          const n = all.filter(a => a.scenario_id === s.id).length
          return <button key={s.id} aria-pressed={scenario === s.id} onClick={() => onScenario(s.id)}>{s.name} {n}</button>
        })}
      </div>

      {list.length === 0 ? (
        <section className="card empty-card">{scenario ? '이 시나리오에서는 고쳐야 할 위협이 나오지 않았어요.' : '고쳐야 할 위협이 없어요.'}</section>
      ) : (
        <div className="rk">
          <div className="rk-main">
            <ol className="tlist">
              {list.map((a, i) => (
                <li key={a.alert_id}>
                  <button className={a.alert_id === current?.alert_id ? 'on' : ''} onClick={() => setSel(a.alert_id)} aria-pressed={a.alert_id === current?.alert_id}>
                    <span className="n">{i + 1}</span>
                    <span className="who"><b>{copyFor(a.rule_id).title}</b><small>{whereLine(model, present, a)}</small></span>
                    <span className={`sv ${a.severity}`}>{SEVERITY_KO[a.severity] ?? a.severity}</span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
          {current && <ThreatDetail model={model} present={present} alert={current} index={list.indexOf(current) + 1} onShowMap={onShowMap} />}
        </div>
      )}

      {reasons.length > 0 && (
        <section className="card unk">
          <button className="unk-h" onClick={() => setShowUnk(!showUnk)} aria-expanded={showUnk}>
            <span><b>확인 못 한 항목 {unknowns.length}건</b><small>위협인지 판단할 정보가 부족했던 곳이에요</small></span>
            {showUnk ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </button>
          {showUnk && <ul>{reasons.map(r => <li key={r}>{r}</li>)}</ul>}
        </section>
      )}
    </>
  )
}

/** 지도에서 열 자산: 지도에 상자로 나오는 서버·실행 위치는 그대로, 나머지는 그 자산이 놓인 곳 */
function mapTarget(m: Model, p: Present, a: Asset): string {
  if (a.asset_type === 'mcp_server' || a.asset_type === 'gateway' || a.asset_type === 'node') return a.asset_id
  if (a.asset_type === 'tool' || a.asset_type === 'resource_prompt') return a.owner_ref ?? a.asset_id
  return `group:${p.hostAsset(a)?.asset_id ?? ''}:${a.asset_type}`
}

/** 위협이 걸린 대표 자산: 서버 → 플러그인 → 권한·인증 → 그 외 순서 */
function primaryAsset(m: Model, a: SecurityAlert): Asset | undefined {
  const assets = a.asset_ids.map(id => m.byId.get(id)).filter(Boolean) as Asset[]
  const order = ['mcp_server', 'plugin', 'permission_auth', 'tool', 'skill', 'resource_prompt', 'node', 'gateway']
  return assets.sort((x, y) => order.indexOf(x.asset_type) - order.indexOf(y.asset_type))[0]
}

function whereLine(m: Model, p: Present, a: SecurityAlert): string {
  const as = a.asset_ids.map(id => m.byId.get(id)).filter(Boolean) as Asset[]
  const main = primaryAsset(m, a)
  if (!main) return ''
  const others = as.filter(x => x !== main && x.asset_type !== 'tool').map(x => p.name(x).split(' · ')[0])
  return [p.name(main).split(' · ')[0], ...others.slice(0, 1)].join(' → ') + ` · ${p.where(main)}`
}

function doesLine(m: Model, p: Present, a: Asset): string {
  if (a.asset_type === 'mcp_server') {
    const st = serverStats(m, a)
    return st.tools.length ? `도구 ${st.tools.length}개 중 ${st.usable}개를 에이전트가 쓸 수 있어요.${st.res ? ` 리소스 ${st.res}개도 내놓아요.` : ''}` : '도구 목록을 받지 못했어요.'
  }
  if (a.asset_type === 'plugin') return `설치되면 MCP 서버를 함께 등록해요. (${p.sub(a)})`
  if (a.asset_type === 'permission_auth') return a.asset_subtype === 'authentication' ? '서버에 접속할 때 쓰는 인증 토큰이에요. 값은 읽지 않고 이름만 확인해요.' : '에이전트에게 열어 줄 도구를 정하는 규칙이에요.'
  if (a.asset_type === 'tool') return '에이전트가 부를 수 있는 기능이에요.'
  return ''
}

function ThreatDetail({ model, present, alert, index, onShowMap }: { model: Model; present: Present; alert: SecurityAlert; index: number; onShowMap: (assetId: string) => void }) {
  const c = copyFor(alert.rule_id)
  const main = primaryAsset(model, alert)
  const related = alert.asset_ids.map(id => model.byId.get(id)).filter((a): a is Asset => !!a && a !== main)
  const [raw, setRaw] = useState(false)
  useEffect(() => setRaw(false), [alert.alert_id])
  return (
    <aside className="td">
      <div className="tt">
        <small>위협 {index} · 심각도 {SEVERITY_KO[alert.severity] ?? alert.severity}</small>
        <h2>{c.title}</h2>
        <p>{c.why}</p>
      </div>
      <div className="bd">
        {main && (
          <section className="sec">
            <h4>어떤 자산인가요?</h4>
            <dl className="kv">
              <dt>자산 종류</dt><dd><span className="tg">{TYPE_KO[main.asset_type]}</span>자산 8종 중 하나</dd>
              <dt>이름</dt><dd>{present.name(main)}</dd>
              <dt>위치</dt><dd>{present.where(main)}</dd>
              <dt>하는 일</dt><dd>{doesLine(model, present, main)}</dd>
              {related.length > 0 && <><dt>함께 걸린 자산</dt><dd>{related.map(r => `${TYPE_KO[r.asset_type]} · ${present.name(r)}`).join(', ')}</dd></>}
            </dl>
            <button className="map-link" onClick={() => onShowMap(mapTarget(model, present, main))}><Network size={16} />자산 지도에서 위치 보기</button>
          </section>
        )}
        <section className="sec">
          <button className="raw-btn" onClick={() => setRaw(!raw)} aria-expanded={raw}>세부 내용 보기{raw ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</button>
          {raw && (
            <div className="raw">
              <p>{alert.message}</p>
              {[main, ...related].filter(Boolean).map(a => (
                <dl key={a!.asset_id}>
                  <dt>{present.name(a!)}</dt>
                  <dd>설정에 적힌 이름 <code>{a!.name}</code></dd>
                  {a!.product?.config_path && <dd>설정 위치 <code>{a!.product.config_path}</code></dd>}
                </dl>
              ))}
              <p className="muted tiny">판정 조건 {alert.rule_id} · 근거 {alert.evidence_refs.length}건</p>
            </div>
          )}
        </section>
        <section className="sec">
          <h4>해야 할 일</h4>
          <ol className="steps">{c.steps.map(s => <li key={s}>{s}</li>)}</ol>
        </section>
      </div>
    </aside>
  )
}
