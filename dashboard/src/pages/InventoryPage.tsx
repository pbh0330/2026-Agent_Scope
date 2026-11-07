import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Model, SecurityStatus } from '../data/model'
import { SCENARIOS, STATE_LABEL, STATE_ORDER, STATUS_LABEL, SUBTYPE_LABEL, TYPE_LABEL, TYPE_ORDER } from '../data/model'
import { Sev, TypeIcon } from '../components/ui'
import type { AssetType, StateName } from '../types/contracts'

export function InventoryPage({ model, selected, onSelect }: { model: Model; selected: string | null; onSelect: (id: string) => void }) {
  const [q, setQ] = useState('')
  const [type, setType] = useState<AssetType | ''>('')
  const [state, setState] = useState<StateName | ''>('')
  const [sec, setSec] = useState<SecurityStatus | ''>('')
  const [scn, setScn] = useState('')

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return model.assets
      .filter(a => !type || a.asset_type === type)
      .filter(a => !state || model.stateValue(a, state) === true)
      .filter(a => !sec || model.security(a) === sec)
      .filter(a => !scn || (model.alertsByAsset.get(a.asset_id) ?? []).some(x => x.scenario_id === scn)
        || (model.evalsByAsset.get(a.asset_id) ?? []).some(x => x.scenario_id === scn && x.result !== 'not_applicable'))
      .filter(a => !needle || `${a.name} ${a.asset_id} ${a.project.canonical_key ?? ''} ${TYPE_LABEL[a.asset_type]}`.toLowerCase().includes(needle))
      .sort((x, y) => TYPE_ORDER.indexOf(x.asset_type) - TYPE_ORDER.indexOf(y.asset_type))
  }, [model, q, type, state, sec, scn])

  return (
    <>
      <div className="toolbar">
        <label className="field" style={{ width: 260 }}><Search size={15} />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="이름, 자산 ID, 식별 키" aria-label="검색" /></label>
        <label className="field"><span>유형</span>
          <select value={type} onChange={e => setType(e.target.value as AssetType | '')}>
            <option value="">전체</option>{TYPE_ORDER.map(t => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
          </select></label>
        <label className="field"><span>확인된 상태</span>
          <select value={state} onChange={e => setState(e.target.value as StateName | '')}>
            <option value="">전체</option>{STATE_ORDER.slice(0, 4).map(s => <option key={s} value={s}>{STATE_LABEL[s]}</option>)}
          </select></label>
        <label className="field"><span>보안</span>
          <select value={sec} onChange={e => setSec(e.target.value as SecurityStatus | '')}>
            <option value="">전체</option>{(['high', 'warning', 'unknown', 'normal', 'none'] as SecurityStatus[]).map(s => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select></label>
        <label className="field"><span>시나리오</span>
          <select value={scn} onChange={e => setScn(e.target.value)}>
            <option value="">전체</option>{SCENARIOS.map(s => <option key={s.id} value={s.id}>{s.id} {s.short}</option>)}
          </select></label>
        <span className="muted small" style={{ marginLeft: 'auto' }}>{rows.length}개 / 전체 {model.assets.length}개</span>
      </div>
      <div className="panel table-wrap">
        <table className="table">
          <thead><tr><th>자산</th><th>유형</th><th>위치와 소속</th><th>확인 단계</th><th>보안</th></tr></thead>
          <tbody>
            {rows.map(a => {
              const parent = model.parentOf(a)
              return (
                <tr key={a.asset_id} className={selected === a.asset_id ? 'sel' : ''} onClick={() => onSelect(a.asset_id)}
                  tabIndex={0} onKeyDown={e => e.key === 'Enter' && onSelect(a.asset_id)}>
                  <td><div className="name">{a.name}</div><div className="key">{a.project.canonical_key ?? a.asset_id}</div></td>
                  <td style={{ whiteSpace: 'nowrap' }}><span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                    <TypeIcon type={a.asset_type} subtype={a.asset_subtype} size={14} />{TYPE_LABEL[a.asset_type]}</span>
                    {a.asset_subtype && <div className="tiny muted">{SUBTYPE_LABEL[a.asset_subtype] ?? a.asset_subtype}</div>}</td>
                  <td className="small">{model.host(a)}{parent && <div className="muted">{parent.name}</div>}</td>
                  <td><StepStrip model={model} id={a.asset_id} /></td>
                  <td><Sev status={model.security(a)} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!rows.length && <div className="empty">조건에 맞는 자산이 없습니다. 필터를 줄여 보세요.</div>}
      </div>
    </>
  )
}

function StepStrip({ model, id }: { model: Model; id: string }) {
  const a = model.byId.get(id)!
  const furthest = model.furthest(a)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ display: 'inline-flex', gap: 2 }} aria-hidden>
        {STATE_ORDER.map(n => {
          const v = model.stateValue(a, n)
          const bg = v === true ? 'var(--accent)' : v === null ? 'var(--hatch)' : 'transparent'
          const ring = v === false ? 'inset 0 0 0 1.5px var(--ink-3)' : v === undefined ? 'inset 0 0 0 1px var(--line)' : v === null ? 'inset 0 0 0 1px var(--unk)' : 'none'
          return <i key={n} title={`${STATE_LABEL[n]}: ${v === true ? '확인' : v === false ? '아님' : v === null ? '확인 못함' : '평가 대상 아님'}`}
            style={{ width: 10, height: 12, borderRadius: 2, display: 'block', background: bg, boxShadow: ring }} />
        })}
      </span>
      <span className="small">{furthest ? STATE_LABEL[furthest] : '확인 없음'}</span>
    </span>
  )
}
