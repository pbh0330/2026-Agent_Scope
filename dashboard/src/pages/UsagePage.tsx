import { Activity, Coins, Gauge, Info, Link2, RefreshCw, ShieldAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Model } from '../data/model'
import { fmtTime } from '../data/model'
import { loadUsageBundle, type UsageBundle, type UsageGroup } from '../data/usage'
import type { Manifest, UsageItem } from '../types/contracts'
import { Panel } from '../components/ui'
import { AreaChart } from '../components/charts'

const PATTERN: Record<string, string> = { sequential: '순차', parallel: '병렬', batch: '배치', unattributed: '귀속 불가' }
const METHOD: Record<string, string> = { sequential: '순차 실측', allocated: '병렬·배치 배분', not_computed: '계산 못 함' }
const MAPPING: Record<string, string> = { matched: '연결됨', ambiguous: '후보 여럿', unmatched: '연결 안 됨' }
const GROUP: Record<UsageGroup, string> = { asset: '도구(자산)', server: '서버·출처', pattern: '호출 구간' }
const LEVEL: Record<string, [string, string]> = { warn: ['경고', 'warn'], approve: ['승인 요청', 'warn'], block: ['차단', 'bad'] }
const DECISION: Record<string, string> = { 'allow-once': '이번만 허용', 'allow-always': '항상 허용', deny: '거부', timeout: '시간 초과', cancelled: '취소' }

const n = (v: number | null | undefined) => v === null || v === undefined ? '—' : v.toLocaleString('ko-KR')
const usd = (v: number | null | undefined, d = 4) => v === null || v === undefined ? '—' : `$${v.toFixed(d)}`
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })

export function UsagePage({ manifest, model, onSelect }: { manifest: Manifest; model: Model; onSelect: (id: string) => void }) {
  const [b, setB] = useState<UsageBundle | null | undefined>(undefined)
  const [group, setGroup] = useState<UsageGroup>('asset')
  const [busy, setBusy] = useState(false)

  const reload = (force: boolean) => {
    setBusy(true)
    loadUsageBundle(manifest, force).then(x => { setB(x); setBusy(false) })
  }
  useEffect(() => { reload(false) }, [manifest])
  useEffect(() => {  // 실시간 API에 붙었을 때만 30초마다 다시 읽음(API는 15초마다 파일 확인)
    if (b?.source !== 'live' || b.health.mode !== 'live') return
    const id = setInterval(() => reload(true), 30_000)
    return () => clearInterval(id)
  }, [b?.source, b?.health.mode])

  if (b === undefined) return <div className="empty">토큰 사용 데이터를 불러오는 중</div>
  if (b === null) return (
    <div className="empty">
      사용 현황 API에 연결하지 못했고 저장된 사본도 없습니다.<br />
      <span className="small muted">token-collector/backend/usageapi에서 <code>agentscope-usage-api</code>를 띄우면(기본 127.0.0.1:8088) 개발 서버가 /api로 붙습니다.</span>
    </div>
  )

  const { health, summary: s, records, timeseries, brakes } = b
  const items = b.byAsset[group].items
  const max = Math.max(1, ...items.map(i => i.tokens))
  const inModel = (id: string | null) => !!id && model.byId.has(id)
  const linked = s.by_mapping.matched > 0
  const seqShare = s.attributed_tokens ? s.by_method.sequential.tokens / s.attributed_tokens : 0

  return (
    <div className="dash">
      <div className={`notice${health.status === 'ok' ? '' : ' warn'}`}>
        <Info size={16} />
        <span>
          {b.source === 'live'
            ? <>사용 현황 API에 <b>실시간 연결</b>되었습니다 · {health.mode === 'live' ? '실시간 모드(파일이 바뀌면 다시 계산)' : '고정 응답 모드'} · 상태 {health.status}{health.last_error ? ` (${health.last_error})` : ''}.</>
            : <>사용 현황 API가 꺼져 있어 <b>저장된 응답 사본</b>({fmtTime(b.fetchedAt)} 저장)을 보여 줍니다. API를 띄우면 자동으로 실시간 값으로 바뀝니다.</>}
          {' '}입력 <code>{health.sources.join(', ') || '없음'}</code>, 데이터 구간 {fmtTime(health.data_window?.start)} ~ {fmtTime(health.data_window?.end)}.
          {' '}<button className="link" onClick={() => reload(true)} disabled={busy}><RefreshCw size={12} style={{ verticalAlign: '-1px' }} /> 다시 읽기</button>
        </span>
      </div>

      <section className="kpis">
        <Tile tone="violet" icon={<Activity size={20} />} label="도구 호출" value={n(s.calls)} sub={`${hhmm(s.window.start)} ~ ${hhmm(s.window.end)}`} />
        <Tile tone="teal" icon={<Coins size={20} />} label="귀속 토큰 (추정)" value={n(s.attributed_tokens)}
          sub={`순차 실측 ${Math.round(seqShare * 100)}% · 배분 ${100 - Math.round(seqShare * 100)}%`} />
        <Tile tone="orange" icon={<Gauge size={20} />} label="추정 비용" value={usd(s.estimated_cost_usd)}
          sub={s.pricing.sources.includes('reference_list_price') ? '공식 정가 참고값 · 청구액 아님' : s.pricing.sources.join(', ')} />
        <Tile tone={brakes.available && brakes.total ? 'pink' : 'green'} icon={<ShieldAlert size={20} />} label="소비 브레이크"
          value={brakes.available ? n(brakes.total) : '—'}
          sub={brakes.available ? `경고 ${brakes.by_level.warn} · 승인 ${brakes.by_level.approve} · 차단 ${brakes.by_level.block}` : '플러그인 기록 없음'} />
      </section>

      <section className="row row-a">
        <Panel title="시간대별 귀속 토큰" note={`${timeseries.step.replace('m0s', '분').replace('h0m0s', '시간')} 단위 · 기록이 없는 구간은 0`}>
          <AreaChart unit=" 토큰" points={timeseries.total.points.map(p => ({ label: hhmm(p.t), value: p.tokens, note: `호출 ${p.calls}건` }))} />
        </Panel>
        <Panel title="계산 방식" note="병렬·배치는 구간 증가분을 결과별 토큰 수 비율로 나눔">
          <div className="method-stack" role="img" aria-label="계산 방식별 토큰 비율">
            <span style={{ flex: s.by_method.sequential.tokens, background: 'var(--c1)' }} />
            <span style={{ flex: s.by_method.allocated.tokens, background: 'var(--c2)' }} />
          </div>
          <dl className="kv" style={{ marginTop: 14 }}>
            <dt><i className="mdot" style={{ background: 'var(--c1)' }} />{METHOD.sequential}</dt><dd>{n(s.by_method.sequential.tokens)} 토큰 · {s.by_method.sequential.calls}건</dd>
            <dt><i className="mdot" style={{ background: 'var(--c2)' }} />{METHOD.allocated}</dt><dd>{n(s.by_method.allocated.tokens)} 토큰 · {s.by_method.allocated.calls}건</dd>
            <dt><i className="mdot" style={{ background: 'var(--hatch)' }} />{METHOD.not_computed}</dt><dd>{s.by_method.not_computed.calls}건 <span className="muted">(0으로 채우지 않음)</span></dd>
          </dl>
          <div className="mini-stats" style={{ marginTop: 16 }}>
            <div><span>자산 연결</span><b className={linked ? 'ok' : 'warn'}>{s.by_mapping.matched}/{s.calls}</b></div>
            <div><span>배분 근거 누락</span><b>{s.data_quality.missing_counts}</b></div>
            <div><span>단가 없음</span><b>{s.data_quality.calls_without_cost}</b></div>
          </div>
        </Panel>
      </section>

      {!linked && (
        <div className="notice warn">
          <Link2 size={16} />
          <span>사용 기록이 지금 보는 스냅샷의 자산과 연결되지 않았습니다(연결 {s.by_mapping.matched}건). 사용 현황 API를 <code>--inventory</code>에 이 스냅샷을 주고
            같은 environment_id·profile_id로 띄우면 도구가 자산 ID로 묶이고, 자산 상세에 "실제 사용"이 표시됩니다. 이름이 비슷해도 대시보드가 임의로 연결하지 않습니다.</span>
        </div>
      )}

      <Panel title="어디에 토큰을 썼나" note={`${GROUP[group]} 기준 · 막대 = 순차 실측 + 배분 · 많이 쓴 순`}
        action={<div className="seg" role="group" aria-label="묶음 기준">
          {(Object.keys(GROUP) as UsageGroup[]).map(g => <button key={g} aria-pressed={group === g} onClick={() => setGroup(g)}>{GROUP[g]}</button>)}
        </div>}>
        <div role="list">
          {items.map(it => <UsageRow key={it.key} it={it} max={max} group={group} canOpen={inModel(it.asset_id)} onOpen={() => it.asset_id && onSelect(it.asset_id)} />)}
        </div>
        <div className="legend-line"><i style={{ background: 'var(--c1)' }} />순차 실측 <i style={{ background: 'var(--c2)' }} />병렬·배치 배분</div>
      </Panel>

      <Panel title="실행 제한 기록" note="token-guard 플러그인의 소비 브레이크. 위협 시나리오(S1~S5) 경고와 별개입니다">
        {!brakes.available ? (
          <p className="small muted">플러그인 기록(<code>agentscope-tool-results.jsonl</code>)을 사용 현황 API에 <code>--tool-results</code>로 주지 않아 표시할 기록이 없습니다. 테스트베드 실시간 모드에서는 자동으로 채워집니다.</p>
        ) : brakes.items.length === 0 ? (
          <p className="small muted">이 구간에 브레이크가 걸린 호출이 없습니다.</p>
        ) : (
          <ul className="item-list">
            {brakes.items.map((e, i) => (
              <li key={i}>
                <div className="row-static">
                  <span className={`dot-sev ${LEVEL[e.level][1]}`} />
                  <span className="who">
                    <b><code>{e.tool_name}</code> · {e.reasons.map(r => `${r.scope}.${r.metric} ${r.value}/${r.limit}`).join(', ')}</b>
                    <small>{fmtTime(e.time)} · {e.enforced ? '실제 적용' : '경고만'}{e.resolution ? ` · 응답: ${DECISION[e.resolution.decision] ?? e.resolution.decision}` : ''}{e.trace_id ? ` · trace ${e.trace_id.slice(0, 8)}` : ''}</small>
                  </span>
                  <span className={`status ${LEVEL[e.level][1]}`}>{LEVEL[e.level][0]}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="호출 기록" note={`최신순 ${records.items.length}/${records.total}건 · 토큰을 계산 못 한 호출은 비워 둠`} pad={false}>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>시각</th><th>도구</th><th>구간 · 방식</th><th className="num">토큰</th><th className="num">비용</th><th className="num">실행 ms</th><th>자산 연결</th><th>실행 기록</th></tr></thead>
            <tbody>
              {records.items.map(r => (
                <tr key={r.usage_id} style={{ cursor: inModel(r.asset_id) ? 'pointer' : 'default' }} onClick={() => inModel(r.asset_id) && onSelect(r.asset_id!)}>
                  <td className="small">{hhmm(r.time)}</td>
                  <td><code>{r.tool_name}</code> <span className="tiny muted">{r.tool_source === 'mcp' ? `MCP${r.mcp_server ? ' · ' + r.mcp_server : ''}` : '내장'}</span></td>
                  <td className="small">{PATTERN[r.pattern] ?? r.pattern} · <span className="muted">{METHOD[r.method] ?? r.method}</span></td>
                  <td className="num small">{r.tokens === null ? <span className="muted">계산 못 함</span> : n(r.tokens)}</td>
                  <td className="num small">{usd(r.estimated_cost_usd, 6)}</td>
                  <td className="num small">{r.duration_ms ?? '—'}</td>
                  <td className="small"><span className={`sev ${r.mapping_status === 'matched' ? 'normal' : 'none'}`}>{MAPPING[r.mapping_status] ?? r.mapping_status}</span></td>
                  <td className="tiny muted"><code title={r.trace_id ?? ''}>{r.trace_id ? r.trace_id.slice(0, 8) : '—'}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {health.limitations?.length ? (
        <details className="limits">
          <summary>계산 한계와 주의 ({health.limitations.length})</summary>
          <ul>{health.limitations.map(l => <li key={l}>{l}</li>)}</ul>
        </details>
      ) : null}
      <p className="foot-note">모든 토큰·비용은 토큰 수집기의 추정치입니다. 도구 결과 내용·인자 값은 수집하지 않습니다. 출처: {manifest.usage_api?.source ?? 'token-collector usageapi'}</p>
    </div>
  )
}

function Tile({ tone, icon, label, value, sub }: { tone: string; icon: React.ReactNode; label: string; value: string; sub: string }) {
  return (
    <div className={`kpi static-kpi ${tone}`} role="group" aria-label={label}>
      <span className="kpi-icon">{icon}</span>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      <span className="kpi-sub">{sub}</span>
    </div>
  )
}

function UsageRow({ it, max, group, canOpen, onOpen }: { it: UsageItem; max: number; group: UsageGroup; canOpen: boolean; onOpen: () => void }) {
  const label = group === 'pattern' ? (PATTERN[it.label] ?? it.label) : it.label
  return (
    <div className="usage-row" role="listitem">
      <div className="u-name">
        {canOpen ? <button className="link" onClick={onOpen}><code>{label}</code></button> : <code>{label}</code>}
        <span className="tiny muted">
          {group !== 'pattern' && (it.tool_source === 'core' ? '내장' : it.tool_source === 'mcp' ? 'MCP' : it.tool_source ?? '')}
          {group === 'asset' && it.mapping_status ? ` · ${MAPPING[it.mapping_status]}` : ''}
        </span>
      </div>
      <div className="u-bar" title={`순차 ${it.tokens_sequential.toLocaleString('ko-KR')} · 배분 ${it.tokens_allocated.toLocaleString('ko-KR')}`}>
        <span style={{ width: `${(it.tokens_sequential / max) * 100}%`, background: 'var(--c1)' }} />
        <span style={{ width: `${(it.tokens_allocated / max) * 100}%`, background: 'var(--c2)' }} />
      </div>
      <div className="u-num"><b>{it.tokens.toLocaleString('ko-KR')}</b><span className="tiny muted">{Math.round(it.share * 1000) / 10}%</span></div>
      <div className="u-meta tiny muted">호출 {it.calls}{it.calls_not_computed ? ` (계산 못 함 ${it.calls_not_computed})` : ''} · {it.last_used_at ? `마지막 ${hhmm(it.last_used_at)}` : '—'}</div>
    </div>
  )
}
