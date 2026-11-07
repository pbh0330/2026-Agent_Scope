import { Fragment, useEffect, useState } from 'react'
import { loadBundle, loadDiff } from '../data/load'
import type { Model } from '../data/model'
import { TYPE_LABEL } from '../data/model'
import type { DetectionReport, Manifest, SnapshotDiff } from '../types/contracts'
import { Panel, Scn, SeverityTag } from '../components/ui'

const CHANGE_LABEL: Record<string, string> = {
  added: '추가', modified: '변경', removed_from_scope: '범위에서 사라짐', not_observed: '이번에 확인 못함',
  opened: '새 경고', persisting: '계속', resolved: '해결', not_evaluated: '재평가 없음',
}

export function ChangesPage({ model, manifest, current, onSelect }: { model: Model; manifest: Manifest; current: string; onSelect: (id: string) => void }) {
  const options = manifest.diffs
  const initial = options.find(d => d.to === current) ?? options[0]
  const [pick, setPick] = useState(initial?.file)
  const [diff, setDiff] = useState<SnapshotDiff | null>(null)
  const [prevDet, setPrevDet] = useState<DetectionReport | null>(null)
  useEffect(() => { setPick((options.find(d => d.to === current) ?? options[0])?.file) }, [current])
  const meta = options.find(d => d.file === pick)
  useEffect(() => {
    if (!pick || !meta) return
    loadDiff(pick).then(setDiff)
    const prev = manifest.snapshots.find(s => s.key === meta.from)
    if (prev) loadBundle(prev.files).then(b => setPrevDet(b.detections))
  }, [pick])

  if (!options.length) return <div className="empty">비교할 스냅샷 쌍이 없습니다.</div>
  const sameTarget = meta?.to === current
  const groups = ['added', 'modified', 'removed_from_scope', 'not_observed'] as const
  const nameOf = (id: string, prev?: { name: string; asset_type: string }) => {
    const a = model.byId.get(id)
    return a ? `${a.name}` : prev?.name ?? id
  }

  return (
    <>
      <div className="toolbar">
        <div className="seg" role="group" aria-label="비교 쌍">
          {options.map(o => <button key={o.file} aria-pressed={o.file === pick} onClick={() => setPick(o.file)}>{o.from} 에서 {o.to}</button>)}
        </div>
      </div>
      {!sameTarget && meta && (
        <div className="notice warn"><span /><span>지금 선택한 스냅샷은 {current}입니다. 이 비교는 {meta.from}와 {meta.to} 사이의 변화라 자산 이름을 일부 찾지 못할 수 있습니다. 위쪽 타임라인에서 {meta.to}를 고르면 정확히 연결됩니다.</span></div>
      )}
      {diff && (
        <>
          <div className="grid-3" style={{ marginBottom: 18 }}>
            <Panel title="자산 변화" note={diff.comparison_status === 'complete' ? '같은 범위를 끝까지 비교함' : '일부 범위는 비교하지 못함'}>
              <dl className="kv">
                {groups.map(g => <Fragment key={g}><dt>{CHANGE_LABEL[g]}</dt><dd>{diff.changes.filter(c => c.change_type === g).length}</dd></Fragment>)}
              </dl>
            </Panel>
            <Panel title="관계 변화">
              <dl className="kv">
                <dt>추가</dt><dd>{diff.relation_changes.filter(r => r.change_type === 'added').length}</dd>
                <dt>사라짐</dt><dd>{diff.relation_changes.filter(r => r.change_type !== 'added').length}</dd>
              </dl>
            </Panel>
            <Panel title="경고 변화">
              {diff.alert_changes.length === 0 && <p className="small muted">경고 변화가 없습니다.</p>}
              {diff.alert_changes.map(c => {
                const al = model.detections.alerts.find(a => a.alert_id === c.current_alert_id) ?? prevDet?.alerts.find(a => a.alert_id === c.previous_alert_id)
                return (
                  <div key={c.finding_key} className="change" style={{ gridTemplateColumns: '64px minmax(0,1fr) auto' }}>
                    <span className={`ctype ${c.change_type}`}>{CHANGE_LABEL[c.change_type]}</span>
                    <span className="small">{al && <><Scn id={al.scenario_id} /> {al.title}</>}</span>
                    {al && <SeverityTag severity={al.severity} />}
                  </div>
                )
              })}
            </Panel>
          </div>
          <Panel title="자산별 변경" note="삭제를 단정하지 않습니다. 끝까지 조회한 범위에서 없을 때만 범위에서 사라짐으로 표시합니다">
            {diff.changes.length === 0 && <p className="small muted">같은 자산 목록입니다.</p>}
            {diff.changes.map(c => {
              const a = model.byId.get(c.asset_id)
              return (
                <div className="change" key={c.asset_id + c.change_type}>
                  <span className={`ctype ${c.change_type}`}>{CHANGE_LABEL[c.change_type]}</span>
                  <span>
                    {a ? <button className="link" onClick={() => onSelect(c.asset_id)}>{nameOf(c.asset_id)}</button> : <b>{nameOf(c.asset_id, c.previous)}</b>}
                    <span className="muted small"> {TYPE_LABEL[(a?.asset_type ?? c.previous?.asset_type) as keyof typeof TYPE_LABEL] ?? ''}</span>
                    {c.changed_fields.length > 0 && <div className="tiny muted">바뀐 필드 {c.changed_fields.map(f => <code key={f} style={{ marginRight: 6 }}>{f}</code>)}</div>}
                  </span>
                  <span className="tiny muted" style={{ maxWidth: 260, textAlign: 'right' }}>{c.reason}</span>
                </div>
              )
            })}
          </Panel>
        </>
      )}
    </>
  )
}
