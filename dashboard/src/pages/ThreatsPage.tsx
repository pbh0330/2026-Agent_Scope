// 위협과 조치: 위협 목록 → 고른 위협의 상세(무슨 위협 / 어떤 자산 / 세부 내용 / 할 일)
// 위치는 상세의 '자산 지도에서 보기'로 자산 지도 화면에서 확인한다.
import { ChevronDown, ChevronRight, Network } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { Model } from '../data/model'
import { type Present, SCENARIO_KO, SEVERITY_KO, TYPE_KO, bySeverity, copyForAsset, isOutOfScope, isUnknown, reasonFor, serverStats } from '../data/present'
import type { Asset, SecurityAlert } from '../types/contracts'

export function ThreatsPage({ model, present, scenario, alertId, onScenario, onShowMap }: {
  model: Model; present: Present; scenario?: string; alertId?: string; onScenario: (id?: string) => void; onShowMap: (assetId: string) => void
}) {
  const all = useMemo(() => model.detections.alerts.slice().sort(bySeverity), [model])
  const list = scenario ? all.filter(a => a.scenario_id === scenario) : all
  // 처음에는 모두 접어 둔다. 다른 화면에서 특정 위협을 골라 들어온 경우만 그 위협을 펼친다.
  const [open, setOpen] = useState<string | undefined>(alertId)
  useEffect(() => { setOpen(alertId) }, [alertId, scenario, model])
  const scoped = model.detections.evaluations.filter(e => !scenario || e.scenario_id === scenario)
  const unknowns = scoped.filter(e => isUnknown(e.result))
  const outOfScope = scoped.filter(e => isOutOfScope(e.result))
  const reasons = [...new Set(unknowns.map(reasonFor))]
  const notChecked = [...new Set(outOfScope.map(reasonFor))]
  const skipped = new Set(outOfScope.map(e => e.rule_id)).size
  // 위협이 없는 시나리오를 열면 확인 못 한·점검하지 않은 이유를 바로 펼쳐 보여 준다.
  const [showUnk, setShowUnk] = useState(list.length === 0)
  useEffect(() => { setShowUnk(list.length === 0) }, [scenario, model])

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
        <section className="card empty-card">{skipped
          ? `점검한 조건에서는 위협이 나오지 않았지만, 검사하지 않은 조건이 ${skipped}개 있어서 안전하다고 확정할 수 없어요. 이유는 아래에 있어요.`
          : scenario ? '이 시나리오에서는 고쳐야 할 위협이 나오지 않았어요.' : '고쳐야 할 위협이 없어요.'}</section>
      ) : (
        <ol className="tlist">
          {list.map((a, i) => {
            const isOpen = open === a.alert_id
            return (
              <li key={a.alert_id} className={isOpen ? 'open' : ''}>
                <button className="th" onClick={() => setOpen(isOpen ? undefined : a.alert_id)} aria-expanded={isOpen}>
                  <span className="n">{i + 1}</span>
                  <span className="who"><b>{copyForAsset(a.rule_id, primaryAsset(model, a)).title}</b><small>{whereLine(model, present, a)}</small></span>
                  <span className={`sv ${a.severity}`}>{SEVERITY_KO[a.severity] ?? a.severity}</span>
                  {isOpen ? <ChevronDown size={18} className="chev" /> : <ChevronRight size={18} className="chev" />}
                </button>
                {isOpen && <ThreatDetail model={model} present={present} alert={a} onShowMap={onShowMap} />}
              </li>
            )
          })}
        </ol>
      )}

      {(reasons.length > 0 || notChecked.length > 0) && (
        <section className="card unk">
          <button className="unk-h" onClick={() => setShowUnk(!showUnk)} aria-expanded={showUnk}>
            <span>
              <b>{[unknowns.length ? `확인 못 한 항목 ${unknowns.length}건` : '', skipped ? `점검하지 않은 조건 ${skipped}개` : ''].filter(Boolean).join(' · ')}</b>
              <small>{unknowns.length ? '위협인지 판단할 정보가 부족했던 곳이에요' : '이번 버전에서는 검사하지 않는 조건이에요'}</small>
            </span>
            {showUnk ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </button>
          {showUnk && (
            <>
              {reasons.length > 0 && <ul>{reasons.map(r => <li key={r}>{r}</li>)}</ul>}
              {notChecked.length > 0 && (
                <>
                  {reasons.length > 0 && <p className="unk-sub">이번 버전에서 검사하지 않는 조건 (어느 환경에서나 같아요)</p>}
                  <ul className="muted-list">{notChecked.map(r => <li key={r}>{r}</li>)}</ul>
                </>
              )}
            </>
          )}
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
  // 토큰 공유(S4)는 토큰이, 그 밖에는 서버가 위협의 중심이다
  const order = a.scenario_id === 'S4'
    ? ['permission_auth', 'mcp_server', 'plugin', 'tool', 'skill', 'resource_prompt', 'node', 'gateway']
    : ['mcp_server', 'plugin', 'permission_auth', 'tool', 'skill', 'resource_prompt', 'node', 'gateway']
  return assets.sort((x, y) => order.indexOf(x.asset_type) - order.indexOf(y.asset_type))[0]
}

function whereLine(m: Model, p: Present, a: SecurityAlert): string {
  const as = a.asset_ids.map(id => m.byId.get(id)).filter(Boolean) as Asset[]
  const main = primaryAsset(m, a)
  if (!main) return ''
  // '인증 토큰 · 원격 MCP 서버 1'처럼 대상이 붙은 이름은 '인증 토큰(원격 MCP 서버 1)'로 짧게
  const short = (x: Asset) => { const [h, ...t] = p.name(x).split(' · '); return t.length ? `${h}(${t.join(' · ')})` : h }
  const others = as.filter(x => x !== main && x.asset_type !== 'tool' && !(main.asset_type === 'permission_auth' && x.asset_type === 'mcp_server'))
  return [short(main), ...others.slice(0, 1).map(short)].join(' → ') + ` · ${p.where(main)}`
}

function doesLine(m: Model, p: Present, a: Asset): string {
  if (a.asset_type === 'mcp_server') {
    const st = serverStats(m, a)
    const n = st.tools.length
    const res = st.res ? ` 자료(리소스) ${st.res}개도 함께 제공해요.` : ''
    if (!n) return `에이전트에게 제공하는 도구가 없어요.${res}`
    const unknown = st.tools.filter(t => m.stateValue(t, 'EXPOSED') == null).length
    if (unknown === n) return `에이전트에게 도구 ${n}개를 제공해요. 이 도구들이 에이전트에 실제로 올라갔는지는 확인하지 못했어요.${res}`
    if (st.usable === n) return `에이전트에게 도구 ${n}개를 제공하고, 에이전트는 이 도구를 모두 쓸 수 있는 상태예요.${res}`
    if (st.usable === 0) return `도구 ${n}개를 갖고 있지만 설정으로 모두 막혀 있어 에이전트가 쓸 수 없어요.${res}`
    return `도구 ${n}개를 갖고 있고, 그중 ${st.usable}개만 에이전트가 쓸 수 있게 열려 있어요. 나머지는 설정으로 막혀 있어요.${res}`
  }
  if (a.asset_type === 'plugin') return `설치되면 MCP 서버를 함께 등록해요. (${p.sub(a)})`
  if (a.asset_type === 'permission_auth') return a.asset_subtype === 'authentication' ? '서버에 접속할 때 쓰는 인증 토큰이에요. 값은 읽지 않고 이름만 확인해요.' : '에이전트에게 열어 줄 도구를 정하는 규칙이에요.'
  if (a.asset_type === 'tool') return '에이전트가 부를 수 있는 기능이에요.'
  return ''
}

function ThreatDetail({ model, present, alert, onShowMap }: { model: Model; present: Present; alert: SecurityAlert; onShowMap: (assetId: string) => void }) {
  const main = primaryAsset(model, alert)
  const c = copyForAsset(alert.rule_id, main)
  const related = alert.asset_ids.map(id => model.byId.get(id)).filter((a): a is Asset => !!a && a !== main)
  const [raw, setRaw] = useState(false)
  useEffect(() => setRaw(false), [alert.alert_id])
  return (
    <div className="td">
      <div className="tt">
        <small>무슨 위협인가요?</small>
        <p>{c.why}</p>
      </div>
      <div className="bd">
        {main && (
          <section className="sec">
            <h4>어떤 자산인가요?</h4>
            <dl className="kv">
              <dt>자산 종류</dt><dd><span className="tg">{TYPE_KO[main.asset_type]}</span></dd>
              <dt>이름</dt><dd>{present.name(main)}</dd>
              <dt>위치</dt><dd>{present.where(main)}</dd>
              <dt>하는 일</dt><dd>{doesLine(model, present, main)}</dd>
              {related.length > 0 && <><dt>함께 걸린 자산</dt><dd>{related.map(r => present.name(r).startsWith(TYPE_KO[r.asset_type]) ? present.name(r) : `${TYPE_KO[r.asset_type]} · ${present.name(r)}`).join(', ')}</dd></>}
            </dl>
            <button className="map-link" onClick={() => onShowMap(mapTarget(model, present, main))}><Network size={16} />자산 지도에서 위치 보기</button>
          </section>
        )}
        <section className="sec">
          <h4>해야 할 일</h4>
          <ol className="steps">{c.steps.map(s => <li key={s}>{s}</li>)}</ol>
        </section>
        <section className="sec full">
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
      </div>
    </div>
  )
}
