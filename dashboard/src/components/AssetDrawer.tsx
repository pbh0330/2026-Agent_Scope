import { X } from 'lucide-react'
import { useEffect } from 'react'
import type { Model } from '../data/model'
import { RELATION_LABEL, SCENARIOS, STATE_HINT, STATE_LABEL, STATE_ORDER, SUBTYPE_LABEL, TYPE_LABEL } from '../data/model'
import { Glyph, ResultMark, Scn, Sev, SeverityTag } from './ui'

export function AssetDrawer({ model, id, onSelect, onClose, onAlert }: {
  model: Model; id: string; onSelect: (id: string) => void; onClose: () => void; onAlert: (alertId: string) => void
}) {
  const a = model.byId.get(id)
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  if (!a) return null
  const parent = model.parentOf(a)
  const alerts = model.alertsByAsset.get(a.asset_id) ?? []
  const evals = model.evalsByAsset.get(a.asset_id) ?? []
  const out = model.out.get(a.asset_id) ?? []
  const inn = model.inn.get(a.asset_id) ?? []
  const kids = model.children.get(a.asset_id) ?? []
  const def = a.mcp?.definition
  const props = def?.inputSchema?.properties as Record<string, any> | undefined
  const pa = a.project.permission_auth
  const creds = pa?.credential_refs ?? a.project.credential_refs ?? []
  const evidence = a.evidence_refs.map(e => model.evidence.get(e)).filter(Boolean)
  const typeText = `${TYPE_LABEL[a.asset_type]}${a.asset_subtype ? ` / ${SUBTYPE_LABEL[a.asset_subtype] ?? a.asset_subtype}` : ''}`

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={`${a.name} 상세`}>
        <div className="drawer-head">
          <Glyph asset={a} />
          <div>
            <div className="type">{typeText}</div>
            <h2>{a.name}</h2>
            <div style={{ marginTop: 6 }}><Sev status={model.security(a)} /></div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="닫기"><X size={16} /></button>
        </div>
        <div className="drawer-body">
          <div className="sect">
            <dl className="kv">
              <dt>자산 ID</dt><dd><code>{a.asset_id}</code></dd>
              {a.project.canonical_key && <><dt>식별 키</dt><dd><code>{a.project.canonical_key}</code></dd></>}
              <dt>위치</dt><dd>{model.host(a)}</dd>
              {parent && <><dt>소속</dt><dd><button className="link" onClick={() => onSelect(parent.asset_id)}>{parent.name}</button> <span className="muted small">{TYPE_LABEL[parent.asset_type]}</span></dd></>}
              {a.product && <><dt>원천</dt><dd><code>{a.product.source_ref}</code><br /><code className="muted">{a.product.config_path}</code></dd></>}
              {a.mcp?.protocol_version && <><dt>MCP 버전</dt><dd>{a.mcp.protocol_version} <span className="muted small">설계 기준 2026-07-28</span></dd></>}
            </dl>
          </div>

          <div className="sect">
            <h3>어디까지 확인했나</h3>
            <div className="states">
              {STATE_ORDER.map(n => {
                const s = model.state(a, n)
                const cls = !s ? 'na' : s.value === true ? 'yes' : s.value === false ? 'no' : 'unk'
                const text = !s ? '평가 대상 아님' : s.value === true ? '확인됨' : s.value === false ? '아님' : '확인 못함'
                return (
                  <div className="state-row" key={n} title={STATE_HINT[n]}>
                    <span className={`dot ${cls}`} aria-hidden />
                    <b>{STATE_LABEL[n]}</b>
                    <span>{text}{s?.subject_ref?.agent_key && <span className="muted"> · 에이전트 {s.subject_ref.agent_key}</span>}
                      {s?.reason && <div className="why">{s.reason}</div>}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {(alerts.length > 0 || evals.length > 0) && (
            <div className="sect">
              <h3>보안 평가</h3>
              {alerts.map(al => (
                <button key={al.alert_id} className="node-chip hot" style={{ width: '100%', marginBottom: 6 }} onClick={() => onAlert(al.alert_id)}>
                  <Scn id={al.scenario_id} /><span style={{ flex: 1 }}>{al.title ?? al.message}</span><SeverityTag severity={al.severity} />
                </button>
              ))}
              <div style={{ display: 'grid', gap: 6, marginTop: 6 }}>
                {SCENARIOS.map(sc => {
                  const ev = evals.filter(e => e.scenario_id === sc.id)
                  if (!ev.length) return null
                  return (
                    <div key={sc.id} className="small" style={{ display: 'grid', gridTemplateColumns: '34px 1fr auto', gap: 8, alignItems: 'start' }}>
                      <Scn id={sc.id} /><span className="muted">{ev[0].reason}</span><ResultMark result={ev[0].result} />
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {creds.length > 0 && (
            <div className="sect">
              <h3>자격증명 참조</h3>
              <p className="tiny muted" style={{ marginBottom: 8 }}>참조 이름과 위치만 기록합니다. 실제 값은 수집하지 않습니다.</p>
              {creds.map((c, i) => (
                <dl className="kv" key={i} style={{ marginBottom: 8 }}>
                  <dt>참조</dt><dd><code>{c.reference_id ?? '식별 불가'}</code></dd>
                  <dt>저장소</dt><dd><code>{c.namespace}</code></dd>
                  <dt>설정 위치</dt><dd><code>{c.source_field}</code></dd>
                  {c.reason && <><dt>비고</dt><dd className="muted">{c.reason}</dd></>}
                </dl>
              ))}
            </div>
          )}

          {pa && (pa.patterns || pa.effect) && (
            <div className="sect">
              <h3>정책</h3>
              <dl className="kv">
                <dt>효과</dt><dd>{pa.effect === 'allow' ? '허용 목록' : pa.effect === 'deny' ? '제외 목록' : pa.effect}</dd>
                <dt>패턴</dt><dd>{pa.patterns?.map(p => <code key={p} style={{ marginRight: 6 }}>{p}</code>)}</dd>
                <dt>적용 대상</dt><dd>{pa.target_refs.map(t => <button key={t} className="link" style={{ marginRight: 8 }} onClick={() => onSelect(t)}>{model.byId.get(t)?.name ?? t}</button>)}</dd>
                {pa.reason && <><dt>비고</dt><dd className="muted">{pa.reason}</dd></>}
              </dl>
            </div>
          )}

          {def && (
            <div className="sect">
              <h3>서버가 보낸 정의</h3>
              {def.description && <p className="small" style={{ marginBottom: 8 }}>{String(def.description)}</p>}
              {props && Object.keys(props).length > 0 && (
                <table className="table" style={{ marginBottom: 8 }}>
                  <thead><tr><th>입력</th><th>형식</th><th>필수</th></tr></thead>
                  <tbody>
                    {Object.entries(props).map(([k, v]) => (
                      <tr key={k} style={{ cursor: 'default' }}><td><code>{k}</code></td><td className="muted">{v?.type ?? '—'}</td>
                        <td>{(def.inputSchema?.required ?? []).includes(k) ? '필수' : ''}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
              {def.annotations && <p className="tiny muted">힌트: {Object.entries(def.annotations).map(([k, v]) => `${k}=${v}`).join(', ')}</p>}
              <p className="tiny muted" style={{ marginTop: 4 }}>서버가 제공한 문장은 신뢰하지 않는 데이터로만 표시합니다.</p>
            </div>
          )}

          {a.product?.config && Object.keys(a.product.config).length > 0 && (
            <div className="sect">
              <h3>설정 값</h3>
              <div className="codeblock">{JSON.stringify(a.product.config, null, 2)}</div>
              {a.project.normalizations?.length > 0 && (
                <p className="tiny muted" style={{ marginTop: 6 }}>
                  {a.project.normalizations.map((n: any) => n.source_field.split('.').pop()).join(', ')}은 스캐너 0.1.0이 키 이름만 수집해 어댑터가 보강한 값입니다.
                </p>
              )}
            </div>
          )}

          {(out.length > 0 || inn.length > 0 || kids.length > 0) && (
            <div className="sect">
              <h3>관계</h3>
              <div className="rel-list">
                {inn.map(r => {
                  const s = model.byId.get(r.source_asset_ref)
                  return s && <button key={r.relation_id} onClick={() => onSelect(s.asset_id)}>
                    <span className="rt">{RELATION_LABEL[r.relation_type] ?? r.relation_type} 받음</span><span>{s.name}</span>
                    <span className="tiny muted">{r.confidence === 'confirmed' ? '확인' : r.confidence}</span></button>
                })}
                {out.filter(r => r.relation_type !== 'ADVERTISES').map(r => {
                  const t = r.target.asset_ref ? model.byId.get(r.target.asset_ref) : undefined
                  return t && <button key={r.relation_id} onClick={() => onSelect(t.asset_id)}>
                    <span className="rt">{RELATION_LABEL[r.relation_type] ?? r.relation_type}</span><span>{t.name}</span>
                    <span className="tiny muted">{r.confidence === 'confirmed' ? '확인' : r.confidence}</span></button>
                })}
                {kids.length > 0 && <p className="tiny muted" style={{ padding: '4px 6px' }}>광고한 항목 {kids.length}개(도구·리소스·프롬프트)</p>}
              </div>
            </div>
          )}

          <div className="sect">
            <h3>근거</h3>
            {evidence.map(e => e && (
              <div className="ev" key={e.evidence_id}>
                <div><code>{e.source_ref}</code>{e.field_path && <> <code className="muted">#{e.field_path}</code></>}</div>
                <div className="muted">{e.evidence_type} · 관측 {new Date(e.observed_at).toLocaleString('ko-KR')}
                  {e.redaction_status === 'redacted' && <> · 가림 {e.redacted_fields?.length}건</>}</div>
                {e.note && <div className="muted">{e.note}</div>}
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
  )
}
