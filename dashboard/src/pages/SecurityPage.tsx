import { useEffect, useRef, useState } from 'react'
import type { Model } from '../data/model'
import { RELATION_LABEL, RESULT_LABEL, SCENARIOS } from '../data/model'
import { Panel, ResultMark, Scn, SeverityTag } from '../components/ui'

const RESULTS = ['detected', 'not_detected', 'unknown', 'not_applicable', 'not_evaluated', 'error'] as const

export function SecurityPage({ model, scenario, alertId, onSelect, onMap }: {
  model: Model; scenario?: string; alertId?: string; onSelect: (id: string) => void; onMap: (id: string) => void
}) {
  const [scn, setScn] = useState(scenario ?? '')
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { setScn(scenario ?? '') }, [scenario])
  useEffect(() => {
    if (alertId) document.getElementById(alertId)?.scrollIntoView({ block: 'center' })
  }, [alertId])
  const { evaluations, alerts, ruleset } = model.detections
  const shownAlerts = alerts.filter(a => !scn || a.scenario_id === scn)
  const shownEvals = evaluations.filter(e => !scn || e.scenario_id === scn)
    .sort((a, b) => RESULTS.indexOf(a.result as any) - RESULTS.indexOf(b.result as any))
  const name = (id: string) => model.byId.get(id)?.name ?? id

  return (
    <div ref={ref}>
      <Panel title="규칙별 평가 결과" note={`규칙 세트 ${ruleset.id} ${ruleset.version}. 경고가 없다는 것과 평가하지 못한 것을 구분합니다`}>
        <div className="matrix" role="table">
          <div className="h" role="columnheader">시나리오</div>
          {RESULTS.map(r => <div key={r} className="h c" role="columnheader">{RESULT_LABEL[r]}</div>)}
          {SCENARIOS.map(sc => {
            const ev = evaluations.filter(e => e.scenario_id === sc.id)
            return [
              <div key={sc.id} role="rowheader"><button className="link" style={{ textDecoration: 'none' }} onClick={() => setScn(scn === sc.id ? '' : sc.id)}>
                <Scn id={sc.id} /> {sc.title}</button></div>,
              ...RESULTS.map(r => {
                const n = ev.filter(e => e.result === r).length
                return <div key={sc.id + r} className={`c ${r}${n ? '' : ' zero'}`} role="cell">{n}</div>
              }),
            ]
          })}
        </div>
      </Panel>

      <div className="toolbar" style={{ marginTop: 22 }}>
        <div className="seg" role="group" aria-label="시나리오 필터">
          <button aria-pressed={!scn} onClick={() => setScn('')}>전체</button>
          {SCENARIOS.map(s => <button key={s.id} aria-pressed={scn === s.id} onClick={() => setScn(s.id)}>{s.id}</button>)}
        </div>
        <span className="muted small">경고 {shownAlerts.length}건</span>
      </div>

      {shownAlerts.length === 0 && (
        <div className="notice">
          <span />
          <span>{scn ? `${scn}에서` : '이 스냅샷에서'} 탐지된 경고가 없습니다. 아래 평가 기록에서 판단 불가 항목이 남아 있는지 확인하세요.</span>
        </div>
      )}

      {shownAlerts.map(al => {
        const ev = evaluations.find(e => e.evaluation_id === al.evaluation_id)
        return (
          <article className="alert-card" key={al.alert_id} id={al.alert_id} style={alertId === al.alert_id ? { boxShadow: '0 0 0 2px var(--accent)' } : undefined}>
            <span className={`stripe ${al.severity === 'medium' || al.severity === 'low' ? 'medium' : ''}`} />
            <div className="alert-body">
              <div className="alert-top">
                <Scn id={al.scenario_id} />
                <h3>{al.title}</h3>
                <SeverityTag severity={al.severity} />
                <span className="tag">근거 명확성 {al.confidence === 'high' ? '높음' : al.confidence === 'medium' ? '보통' : '낮음'}</span>
                <span className="tiny muted" style={{ marginLeft: 'auto' }} title={ev?.rule_name}><code>{al.rule_id}</code></span>
              </div>
              <p className="alert-msg">{al.message}</p>
              <div className="chain">
                <div>
                  <h4>관련 자산</h4>
                  <ul>{al.asset_ids.map(id => <li key={id}><button className="link" onClick={() => onSelect(id)}>{name(id)}</button></li>)}</ul>
                </div>
                <div>
                  <h4>관계</h4>
                  <ul>
                    {al.relation_ids.slice(0, 6).map(rid => {
                      const r = model.relById.get(rid)
                      return r && <li key={rid}>{name(r.source_asset_ref)} <span className="muted">{RELATION_LABEL[r.relation_type] ?? r.relation_type}</span> {name(r.target.asset_ref ?? '')}</li>
                    })}
                    {al.relation_ids.length > 6 && <li className="muted">외 {al.relation_ids.length - 6}개</li>}
                    {!al.relation_ids.length && <li className="muted">연결된 관계 없음</li>}
                  </ul>
                </div>
                <div>
                  <h4>근거와 기준</h4>
                  <ul>
                    {al.evidence_refs.slice(0, 3).map(e => {
                      const x = model.evidence.get(e)
                      return <li key={e}><code>{x ? `${x.source_ref}${x.field_path ? '#' + x.field_path : ''}` : e}</code></li>
                    })}
                    {ev?.policy_refs.map(p => <li key={p.id} className="muted">기준 <code>{p.id}</code> {p.version}</li>)}
                  </ul>
                </div>
              </div>
              {ev?.reason && <p className="small muted">판정 사유: {ev.reason}</p>}
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                {al.recommendation && <p className="reco" style={{ flex: 1 }}>{al.recommendation}</p>}
                <button className="btn" onClick={() => onMap(al.asset_ids[0])}>지도에서 보기</button>
              </div>
            </div>
          </article>
        )
      })}

      <Panel title="평가 기록" note={`${shownEvals.length}건. 탐지되지 않은 항목도 근거와 함께 남깁니다`} className="">
        {shownEvals.map(e => (
          <div className="eval-row" key={e.evaluation_id}>
            <span title={e.rule_name}><Scn id={e.scenario_id} /> <span className="tiny muted">{e.rule_id.replace(`${e.scenario_id}-`, '')}</span></span>
            <ResultMark result={e.result} />
            <span className="small">{e.asset_ids.slice(0, 3).map(id => (
              <button key={id} className="link" style={{ marginRight: 8 }} onClick={() => onSelect(id)}>{name(id)}</button>))}
              {e.asset_ids.length > 3 && <span className="muted">외 {e.asset_ids.length - 3}</span>}</span>
            <span className="small muted">{e.rule_name && <b className="rule-name">{e.rule_name}</b>}{e.reason}</span>
          </div>
        ))}
      </Panel>
    </div>
  )
}
