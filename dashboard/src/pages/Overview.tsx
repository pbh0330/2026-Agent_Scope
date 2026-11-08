import { AlertTriangle, Boxes, ChevronRight, Eye, GitBranch } from 'lucide-react'
import type { Model } from '../data/model'
import { SCENARIOS, STATE_LABEL, fmtTime } from '../data/model'
import type { ManifestSnapshot, StateName } from '../types/contracts'
import { Panel, Scn, SeverityTag } from '../components/ui'
import { Donut, GroupedBars, Ring } from '../components/charts'
import type { PageKey } from '../App'

// 6묶음 — dataviz 검증 팔레트(--d1~--d6). 값과 이름을 범례에 함께 표시
const TYPE_GROUPS: { label: string; types: string[] }[] = [
  { label: 'Tool', types: ['tool'] },
  { label: 'Resource / Prompt', types: ['resource_prompt'] },
  { label: '권한 / 인증', types: ['permission_auth'] },
  { label: 'MCP 서버', types: ['mcp_server'] },
  { label: 'Skill · Plugin', types: ['skill', 'plugin'] },
  { label: 'Gateway · Node', types: ['gateway', 'node'] },
]

export function Overview({ model, entry, go }: {
  model: Model; entry: ManifestSnapshot; go: (p: PageKey, opts?: { scenario?: string; alert?: string }) => void; onSelect: (id: string) => void
}) {
  const s = model.snapshot
  const servers = model.ofType('mcp_server')
  const tools = model.ofType('tool')
  const exposed = tools.filter(t => model.stateValue(t, 'EXPOSED') === true).length
  const alerts = model.detections.alerts
  const highs = alerts.filter(a => a.severity === 'high' || a.severity === 'critical').length
  const evals = model.detections.evaluations
  const qa = model.bundle.qa
  const audit = model.bundle.audit

  const ringOf = (n: StateName) => {
    const evaluated = model.assets.filter(a => model.state(a, n))
    const yes = evaluated.filter(a => model.stateValue(a, n) === true).length
    return { value: evaluated.length ? yes / evaluated.length : null, sub: `${yes} / ${evaluated.length}` }
  }

  const bars = servers.map(srv => {
    const kids = model.children.get(srv.asset_id) ?? []
    const t = kids.filter(k => k.asset_type === 'tool')
    const ex = t.filter(x => model.stateValue(x, 'EXPOSED') === true).length
    const unk = t.filter(x => model.stateValue(x, 'EXPOSED') === null).length
    return { label: srv.name, values: [t.length, ex], note: unk ? `노출 확인 못함 ${unk}개` : undefined }
  })

  const typeData = TYPE_GROUPS.map((g, i) => ({ label: g.label, value: model.assets.filter(a => g.types.includes(a.asset_type)).length, color: `var(--d${i + 1})` }))
  const filtered = tools.filter(t => model.stateValue(t, 'EXPOSED') === false).length
  const unknownExpo = tools.filter(t => model.stateValue(t, 'EXPOSED') === null).length
  const expoChecks = qa?.checks.filter(c => c.condition_id === 'EXPOSED') ?? []

  return (
    <div className="dash">
      <section className="kpis">
        <Kpi tone="violet" icon={<Boxes size={20} />} label="식별 자산" value={model.assets.length} sub="8종 분류 기준 고유 ID" onClick={() => go('inventory')} />
        <Kpi tone="teal" icon={<GitBranch size={20} />} label="자산 관계" value={model.relations.length} sub="선언·광고·적용·인증 관계" onClick={() => go('map')} />
        <Kpi tone="orange" icon={<Eye size={20} />} label="에이전트 노출 도구" value={exposed} suffix={`/ ${tools.length}`} sub={`MCP 서버 ${servers.length}개가 광고`} onClick={() => go('map')} />
        <Kpi tone={alerts.length ? 'pink' : 'green'} icon={<AlertTriangle size={20} />} label="보안 경고" value={alerts.length}
          sub={alerts.length ? `높음 ${highs}건 포함` : 'S1~S5 탐지 없음'} onClick={() => go('security')} />
      </section>

      <section className="row row-a">
        <Panel title="서버별 도구 광고와 노출" note="서버가 광고한 도구 중 실제로 에이전트에 보이는 수" action={<button className="chip-btn" onClick={() => go('map')}>자산 지도<ChevronRight size={14} /></button>}>
          <GroupedBars groups={bars} series={[{ name: '광고한 도구', color: 'var(--c1)' }, { name: '에이전트 노출', color: 'var(--c2)' }]} />
        </Panel>
        <Panel title="자산 유형 구성" note={`전체 ${model.assets.length}개`}>
          <div className="donut-wrap">
            <Donut data={typeData} center={<><b>{model.assets.length}</b><span>자산</span></>} />
            <ul className="donut-legend">
              {typeData.map(d => <li key={d.label}><i style={{ background: d.color }} /><span>{d.label}</span><b>{d.value}</b></li>)}
            </ul>
          </div>
        </Panel>
      </section>

      <section className="row row-b">
        <Panel title="어디까지 확인했나" note="평가 대상 자산 중 근거로 확인된 비율">
          <div className="rings">
            {(['DECLARED', 'DISCOVERED', 'EXPOSED'] as StateName[]).map((n, i) => {
              const r = ringOf(n)
              return <Ring key={n} value={r.value} label={STATE_LABEL[n]} sub={r.sub} color={['var(--c1)', 'var(--c3)', 'var(--c2)'][i]} />
            })}
            <Ring value={null} label="호출·사용" sub="범위 밖" color="var(--ink-3)" />
          </div>
          <div className="mini-stats" style={{ marginTop: 20 }}>
            <div><span>필터로 숨긴 도구</span><b>{filtered}</b></div>
            <div><span>노출 확인 못한 도구</span><b className="warn">{unknownExpo}</b></div>
            <div><span>호출 가능·사용</span><b className="sm">런타임 단계</b></div>
          </div>
        </Panel>

        <Panel title="위협 시나리오" note="규칙별 평가 결과" action={<button className="chip-btn" onClick={() => go('security')}>전체<ChevronRight size={14} /></button>}>
          <ul className="people">
            {SCENARIOS.map(sc => {
              const ev = evals.filter(e => e.scenario_id === sc.id)
              const det = ev.filter(e => e.result === 'detected').length
              const unk = ev.filter(e => e.result === 'unknown' || e.result === 'not_evaluated').length
              const state = det ? ['bad', `탐지 ${det}`] : unk ? ['unk', `판단 불가 ${unk}`] : ['ok', '이상 없음']
              return (
                <li key={sc.id}>
                  <button onClick={() => go('security', { scenario: sc.id })}>
                    <span className={`avatar ${state[0]}`}>{sc.id}</span>
                    <span className="who"><b>{sc.title}</b><small>평가 {ev.length}건</small></span>
                    <span className={`status ${state[0]}`}>{state[1]}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </Panel>

        {qa ? (
          <Panel title="정답 목록 일치" note={`테스트베드 ${qa.ground_truth_version}`}>
            <div className="progress-list">
              {qa.metrics.map((m, i) => (
                <div key={m.name} className="progress">
                  <div><span>{m.name === 'declared_asset_recall' ? '선언 자산' : m.name === 'advertised_asset_recall' ? '광고 자산' : '관계'}</span><b>{m.numerator}/{m.denominator}</b></div>
                  <div className="pbar"><span style={{ width: `${(m.value ?? 0) * 100}%`, background: ['var(--c1)', 'var(--c3)', 'var(--c2)'][i] }} /></div>
                </div>
              ))}
              {expoChecks.length > 0 && (
                <div className="progress">
                  <div><span>노출 판정</span><b>{expoChecks.filter(c => c.result === 'PASS').length}/{expoChecks.length}</b></div>
                  <div className="pbar"><span style={{ width: `${expoChecks.filter(c => c.result === 'PASS').length / expoChecks.length * 100}%`, background: 'var(--c4)' }} /></div>
                </div>
              )}
            </div>
            <p className="foot-note">정답에 없는 권한·인증 자산 {qa.extra_assets.length}개는 비교에서 제외</p>
          </Panel>
        ) : (
          <Panel title="변경 내용" note="P2 설정에서 바꾼 부분">
            <ul className="notes">{(s.testbed_context?.notes ?? []).map(n => <li key={n}>{n}</li>)}</ul>
            <p className="foot-note">{entry.synthetic ? '테스트베드에 실제로 주입한 결과가 아닌 합성 구성입니다.' : '테스트베드 담당이 만든 위험 구성 사본입니다.'}</p>
          </Panel>
        )}
      </section>

      <section className="row row-c">
        <Panel title={alerts.length ? '먼저 볼 경고' : '수집 상태'} note={alerts.length ? `${alerts.length}건` : `스캔 ${s.scan.status === 'success' ? '완료' : '부분 완료'}`}
          action={<button className="chip-btn" onClick={() => go(alerts.length ? 'security' : 'collection')}>자세히<ChevronRight size={14} /></button>}>
          {alerts.length ? (
            <ul className="item-list">
              {alerts.map(al => (
                <li key={al.alert_id}>
                  <button onClick={() => go('security', { alert: al.alert_id })}>
                    <Scn id={al.scenario_id} />
                    <span className="who"><b>{al.title}</b><small>{al.message}</small></span>
                    <SeverityTag severity={al.severity} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mini-stats">
              <div><span>수집 작업</span><b>{s.collection_results.length}</b></div>
              <div><span>성공</span><b className="ok">{s.collection_results.filter(c => c.status === 'success').length}</b></div>
              <div><span>부분</span><b className="warn">{s.collection_results.filter(c => c.status === 'partial').length}</b></div>
              <div><span>원본 관측</span><b className="sm">{fmtTime(s.testbed_context?.captured_at)}</b></div>
              <div><span>OpenClaw</span><b className="sm">{s.environment.openclaw_version ?? '미확인'}</b></div>
              <div><span>스캐너</span><b className="sm">{s.producer.upstream?.[0]?.version ?? '—'}</b></div>
            </div>
          )}
        </Panel>

        {audit && (
          <Panel title="OpenClaw 내장 보안 감사" note={`심각 ${audit.summary.critical ?? 0} · 경고 ${audit.summary.warn ?? 0}`}>
            <ul className="item-list">
              {audit.findings.filter(f => f.severity !== 'info').map(f => (
                <li key={f.checkId} title={f.remediation ?? f.detail}>
                  <div className="row-static">
                    <span className={`dot-sev ${f.severity === 'critical' ? 'bad' : 'warn'}`} />
                    <span className="who"><b>{f.title}</b><small>{f.checkId}</small></span>
                    <span className={`status ${f.severity === 'critical' ? 'bad' : 'warn'}`}>{f.severity === 'critical' ? '심각' : '경고'}</span>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </section>
      {entry.kind === 'scenario' && <p className="foot-note">{entry.synthetic ? 'P2 설정을 바꿔 만든 합성 위험 구성입니다.' : '테스트베드 S1 구성 사본입니다. 노출 목록은 아직 S1에서 다시 수집하지 않았습니다.'}{entry.test_case_ids?.length ? ` 테스트 ${entry.test_case_ids.join(', ')}` : ''}</p>}
    </div>
  )
}

function Kpi({ tone, icon, label, value, suffix, sub, onClick }: {
  tone: string; icon: React.ReactNode; label: string; value: number; suffix?: string; sub: string; onClick: () => void
}) {
  return (
    <button className={`kpi ${tone}`} onClick={onClick}>
      <span className="kpi-icon">{icon}</span>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value.toLocaleString('ko-KR')}{suffix && <small>{suffix}</small>}</span>
      <span className="kpi-sub">{sub}</span>
    </button>
  )
}
