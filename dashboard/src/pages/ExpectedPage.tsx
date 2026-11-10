import { ChevronRight, Info } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getJSON } from '../data/load'
import type { Model } from '../data/model'
import type { ExpectedCheck, ExpectedKind, ExpectedReport, Manifest, ManifestSnapshot, ScenarioCatalog } from '../types/contracts'
import { Panel, Scn } from '../components/ui'

const KIND: Record<ExpectedKind, { label: string; hint: string }> = {
  required: { label: '나와야 할 경고', hint: '같은 조건 ID로 대상 자산에 경고가 나와야 함' },
  optional: { label: '동반 경고 (선택)', hint: '나와도 정답, 안 나와도 누락 아님' },
  unknown: { label: '판단 불가로 남아야 함', hint: '경고 없이 unknown으로 평가돼야 함' },
  no_alert: { label: '나오면 안 되는 경고', hint: '대상에 해당 시나리오 경고가 나오면 오탐' },
  extra: { label: '기대 결과에 없는 경고', hint: '규칙과 기대 결과 중 어느 쪽을 고칠지 확인' },
}
const ORDER: ExpectedKind[] = ['required', 'optional', 'unknown', 'no_alert', 'extra']
const RESULT: Record<string, [string, string]> = {
  PASS: ['일치', 'ok'], PARTIAL: ['심각도 다름', 'warn'], FAIL: ['불일치', 'bad'], SKIP: ['나오지 않음', 'unk'], INFO: ['확인 필요', 'warn'],
}
const VERDICT: Record<string, [string, string]> = { PASS: ['모두 일치', 'ok'], PARTIAL: ['일부 차이', 'warn'], FAIL: ['불일치 있음', 'bad'] }
const SEV: Record<string, string> = { critical: '심각', high: '높음', medium: '보통', low: '낮음', info: '정보' }

export function ExpectedPage({ manifest, entry, model, onSelect, onSnapshot }: {
  manifest: Manifest; entry: ManifestSnapshot; model: Model; onSelect: (id: string) => void; onSnapshot: (key: string) => void
}) {
  const withExp = manifest.snapshots.filter(s => s.files.expected)
  const [reports, setReports] = useState<Record<string, ExpectedReport>>({})
  const [catalog, setCatalog] = useState<ScenarioCatalog | null>(null)
  useEffect(() => {
    Promise.all(withExp.map(s => getJSON<ExpectedReport>(s.files.expected!).then(r => [s.key, r] as const)))
      .then(rs => setReports(Object.fromEntries(rs))).catch(() => setReports({}))
    getJSON<ScenarioCatalog>('scenario-catalog.json').then(setCatalog).catch(() => setCatalog(null))
  }, [manifest])

  if (!withExp.length) return <div className="empty">기대 결과가 연결된 스냅샷이 없습니다. 파이프라인이 docs/threat-scenarios/expected-results.md를 읽었는지 확인하세요.</div>

  const condName = (id: string | null) => {
    if (!id || !catalog) return ''
    for (const s of catalog.scenarios) for (const c of s.conditions) if (c.condition_id === id) return c.name
    return ''
  }
  const rep = reports[entry.key]
  const total = withExp.reduce((acc, s) => {
    const r = reports[s.key]
    if (!r) return acc
    const req = r.checks.filter(c => c.kind === 'required')
    acc.req += req.length; acc.hit += req.filter(c => c.result === 'PASS' || c.result === 'PARTIAL').length
    acc.fp += r.checks.filter(c => c.kind === 'no_alert' && c.result === 'FAIL').length
    acc.unk += r.checks.filter(c => c.kind === 'unknown').length; acc.unkOk += r.checks.filter(c => c.kind === 'unknown' && c.result === 'PASS').length
    acc.extra += r.checks.filter(c => c.kind === 'extra').length
    return acc
  }, { req: 0, hit: 0, fp: 0, unk: 0, unkOk: 0, extra: 0 })

  return (
    <div className="dash">
      <div className="notice">
        <Info size={16} />
        <span>기준: 위협 시나리오 v{manifest.expected?.version} <code>expected-results.md</code>, S1은 테스트베드 <code>S1.json</code>.
          경고 하나가 맞으려면 <b>조건 ID</b>와 <b>대상 자산</b>이 같아야 하고, 심각도가 다르면 "심각도 다름"으로 표시합니다. 판단 불가 항목은 경고가 없을 뿐 아니라 unknown으로 평가돼야 맞습니다.</span>
      </div>

      <section className="exp-tiles">
        <Stat label="나와야 할 경고" value={`${total.hit}/${total.req}`} tone={total.hit === total.req ? 'ok' : 'bad'} sub="모든 위험 구성 합계" />
        <Stat label="오탐" value={String(total.fp)} tone={total.fp ? 'bad' : 'ok'} sub="나오면 안 되는 경고가 나온 수" />
        <Stat label="판단 불가 유지" value={`${total.unkOk}/${total.unk}`} tone={total.unkOk === total.unk ? 'ok' : 'bad'} sub="unknown으로 남아야 할 항목" />
        <Stat label="기대 밖 경고" value={String(total.extra)} tone={total.extra ? 'warn' : 'ok'} sub="문서에 없는 경고" />
      </section>

      <Panel title="구성별 결과" note="행을 누르면 그 구성으로 바뀝니다" pad={false}>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>구성</th><th>테스트</th><th className="num">나와야 할 경고</th><th className="num">동반 경고</th><th className="num">판단 불가</th><th className="num">오탐</th><th className="num">기대 밖</th><th>판정</th><th /></tr></thead>
            <tbody>
              {withExp.map(s => {
                const r = reports[s.key]
                const cnt = (k: ExpectedKind, ok = (c: ExpectedCheck) => c.result === 'PASS' || c.result === 'PARTIAL') => {
                  const cs = r?.checks.filter(c => c.kind === k) ?? []
                  return cs.length ? `${cs.filter(ok).length}/${cs.length}` : '—'
                }
                const v = VERDICT[r?.verdict ?? s.expected?.verdict ?? 'PASS']
                return (
                  <tr key={s.key} aria-selected={s.key === entry.key} className={s.key === entry.key ? 'sel' : ''} onClick={() => onSnapshot(s.key)}>
                    <td><b>{s.key}</b> <span className="small muted">{s.label.split(' · ')[1] ?? ''}</span>{s.synthetic && <span className="tag" style={{ marginLeft: 6 }}>합성</span>}</td>
                    <td className="small muted">{s.test_case_ids?.join(', ') || (s.kind === 'normal' ? '정상군' : '—')}</td>
                    <td className="num">{cnt('required')}</td>
                    <td className="num">{cnt('optional', c => c.result === 'PASS')}</td>
                    <td className="num">{cnt('unknown', c => c.result === 'PASS')}</td>
                    <td className="num">{r ? r.checks.filter(c => c.kind === 'no_alert' && c.result === 'FAIL').length : '—'}</td>
                    <td className="num">{r ? r.checks.filter(c => c.kind === 'extra').length : '—'}</td>
                    <td><span className={`status ${v[1]}`}>{v[0]}</span></td>
                    <td><ChevronRight size={14} className="muted" /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {!rep ? (
        <div className="notice warn"><Info size={16} /><span><b>{entry.key}</b>에는 위협 시나리오 기대 결과가 정의되어 있지 않습니다. P0·P1은 테스트베드 정답 목록 비교만 합니다(수집과 검증 화면). 위 표에서 구성을 고르세요.</span></div>
      ) : (
        <Panel title={`${entry.key} 항목별 대조`} note={`${rep.expected_source} · 탐지 ${rep.detection_report_id}`}
          action={<span className={`status ${VERDICT[rep.verdict][1]}`}>{VERDICT[rep.verdict][0]}</span>}>
          {ORDER.map(k => {
            const cs = rep.checks.filter(c => c.kind === k)
            if (!cs.length) return null
            return (
              <div className="exp-group" key={k}>
                <h3>{KIND[k].label} <span className="muted small">{KIND[k].hint}</span></h3>
                {cs.map(c => {
                  const name = c.asset_id ? model.byId.get(c.asset_id)?.name : null
                  const [rl, rc] = RESULT[c.result]
                  const exp = c.expected, act = c.actual
                  return (
                    <div className="exp-row" key={c.check_id}>
                      <span className={`status ${rc}`}>{rl}</span>
                      <span className="exp-cond">
                        {c.condition_id ? <span className="exp-id"><Scn id={c.scenario_id.split('/')[0]} /><code>{c.condition_id}</code></span> : <span className="small muted">{c.scenario_id} 전체</span>}
                        {c.condition_id && <small>{condName(c.condition_id)}</small>}
                      </span>
                      <span className="exp-target">
                        {c.asset_id && name ? <button className="link" onClick={() => onSelect(c.asset_id!)}>{name}</button> : <span>{c.target ?? '—'}</span>}
                        <small><code>{c.target}</code></small>
                      </span>
                      <span className="exp-vs small">
                        {k === 'required' || k === 'optional' ? <>
                          기대 {exp.severity ? SEV[exp.severity] : '경고'}{exp.confidence ? ` · 근거 ${SEV[exp.confidence] ?? exp.confidence}` : ''}
                          <br />실제 {act.alerts?.length ? act.alerts.map((a: any) => `${SEV[a.severity]} · 근거 ${SEV[a.confidence] ?? a.confidence}`).join(', ') : '경고 없음'}
                        </> : k === 'unknown' ? <>기대 판단 불가<br />실제 {act.results?.length ? act.results.map((r: string) => r === 'unknown' ? '판단 불가' : r).join(', ') : '평가 없음'}</>
                          : k === 'no_alert' ? <>기대 경고 없음<br />실제 {act.alerts?.length ? act.alerts.map((a: any) => a.rule_id).join(', ') : '경고 없음'}</>
                          : <>실제 {act.alerts?.map((a: any) => SEV[a.severity]).join(', ')}</>}
                      </span>
                      <span className="exp-why small muted">{c.reason}</span>
                    </div>
                  )
                })}
              </div>
            )
          })}
          <p className="foot-note">{rep.limitations.join(' · ')}</p>
        </Panel>
      )}
    </div>
  )
}

function Stat({ label, value, tone, sub }: { label: string; value: string; tone: 'ok' | 'bad' | 'warn'; sub: string }) {
  return (
    <div className={`exp-stat ${tone}`}>
      <span>{label}</span>
      <b>{value}</b>
      <small>{sub}</small>
    </div>
  )
}
