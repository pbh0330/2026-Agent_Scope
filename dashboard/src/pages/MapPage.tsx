import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Asset } from '../types/contracts'
import type { Model } from '../data/model'
import { SUBTYPE_LABEL } from '../data/model'
import { Glyph, Scn, TypeIcon } from '../components/ui'

interface Props { model: Model; selected: string | null; onSelect: (id: string) => void }

export function MapPage({ model, selected, onSelect }: Props) {
  const [q, setQ] = useState('')
  const [onlyAlerts, setOnlyAlerts] = useState(false)
  const [open, setOpen] = useState<Record<string, boolean>>({})

  const focus = useMemo(() => {
    if (q.trim()) {
      const needle = q.trim().toLowerCase()
      const hit = new Set<string>()
      for (const a of model.assets) {
        const scn = (model.alertsByAsset.get(a.asset_id) ?? []).map(x => x.scenario_id).join(' ')
        if (`${a.name} ${a.asset_id} ${a.project.canonical_key ?? ''} ${scn}`.toLowerCase().includes(needle)) {
          hit.add(a.asset_id)
          if (a.owner_ref) hit.add(a.owner_ref)
        }
      }
      return hit
    }
    if (onlyAlerts) {
      const s = new Set<string>()
      for (const al of model.detections.alerts) al.asset_ids.forEach(id => s.add(id))
      return s
    }
    if (selected) return model.neighbours(selected)
    return null
  }, [q, onlyAlerts, selected, model])

  const hosts = [...model.ofType('gateway'), ...model.ofType('node')]
  const declaredBy = (host: Asset, type: string) =>
    (model.out.get(host.asset_id) ?? []).filter(r => r.relation_type === 'DECLARES').map(r => model.byId.get(r.target.asset_ref!)!)
      .filter(a => a && a.asset_type === type)
  const placed = new Set<string>()
  hosts.forEach(h => {
    declaredBy(h, 'mcp_server').forEach(s => placed.add(s.asset_id))
    declaredBy(h, 'plugin').forEach(p => (model.out.get(p.asset_id) ?? []).forEach(r => r.target.asset_ref && placed.add(r.target.asset_ref)))
  })
  const orphans = model.ofType('mcp_server').filter(s => !placed.has(s.asset_id))
  const paired = model.relations.some(r => r.relation_type === 'PAIRED_WITH')

  const dim = (id: string) => focus !== null && !focus.has(id)
  const toggle = (id: string) => setOpen(o => ({ ...o, [id]: !o[id] }))
  const autoOpen = (srv: Asset) => q.trim() !== '' && (model.children.get(srv.asset_id) ?? []).some(c => focus?.has(c.asset_id))

  const ServerRow = ({ srv }: { srv: Asset }) => {
    const kids = model.children.get(srv.asset_id) ?? []
    const tools = kids.filter(k => k.asset_type === 'tool')
    const rps = kids.filter(k => k.asset_type === 'resource_prompt')
    const exposed = tools.filter(t => model.stateValue(t, 'EXPOSED') === true).length
    const alerts = model.alertsByAsset.get(srv.asset_id) ?? []
    const pols = model.policiesFor(srv)
    const ep = model.endpoint(srv)
    const isOpen = open[srv.asset_id] || autoOpen(srv)
    const disc = model.stateValue(srv, 'DISCOVERED')
    const tickCls = (t: Asset) => {
      const v = model.stateValue(t, 'EXPOSED')
      return `tick ${v === true ? '' : v === false ? 'no' : 'unk'}${(model.alertsByAsset.get(t.asset_id) ?? []).length ? ' hot' : ''}${selected === t.asset_id ? ' sel' : ''}${dim(t.asset_id) && focus ? ' dim' : ''}`
    }
    return (
      <div className={`srv${dim(srv.asset_id) ? ' dim' : ''}${selected === srv.asset_id ? ' sel' : ''}${alerts.length ? ' alerted' : ''}`}>
        <button className="srv-top" onClick={() => onSelect(srv.asset_id)}>
          <div>
            <div className="srv-name">
              <TypeIcon type="mcp_server" />{srv.name}
              {[...new Set(alerts.map(a => a.scenario_id))].map(s => <Scn key={s} id={s} />)}
            </div>
            {ep && <div className="srv-end">{ep}</div>}
          </div>
          <div className="srv-flags">
            <span className="tag">{srv.project.transport ?? '전송 미확인'}</span>
            {srv.project.declared_via_plugin && <span className="tag">플러그인 등록</span>}
          </div>
        </button>
        <div className="surface">
          {pols.length > 0 && (
            <div className="surface-row">
              <span>정책</span>
              <span className="chiprow">
                {pols.map(p => (
                  <button key={p.asset_id} className={`tag ${p.asset_subtype === 'authentication' ? '' : 'accent'}${dim(p.asset_id) ? ' dim' : ''}`}
                    onClick={() => onSelect(p.asset_id)}>
                    <TypeIcon type="permission_auth" subtype={p.asset_subtype} size={12} />
                    {p.asset_subtype === 'authentication'
                      ? (p.project.permission_auth?.credential_refs ?? []).map(c => c.reference_id).join(', ')
                      : `toolFilter ${p.project.permission_auth?.effect === 'allow' ? '허용' : '제외'} ${p.project.permission_auth?.patterns?.length ?? 0}`}
                  </button>
                ))}
              </span>
              <span />
            </div>
          )}
          <div className="surface-row">
            <span>도구</span>
            {tools.length ? (
              <span className="ticks" role="list" aria-label={`${srv.name} 도구`}>
                {tools.map(t => (
                  <button key={t.asset_id} role="listitem" className={tickCls(t)} title={`${t.name} — ${model.stateValue(t, 'EXPOSED') === true ? '노출' : model.stateValue(t, 'EXPOSED') === false ? `미노출 (${model.state(t, 'EXPOSED')?.reason})` : '노출 확인 못함'}`}
                    aria-label={t.name} onClick={() => onSelect(t.asset_id)} />
                ))}
              </span>
            ) : <span className="muted">{disc === null ? '광고 목록 미수집' : '없음'}</span>}
            <span className="surface-count">{tools.length > 0 && <><b>{exposed}</b> / {tools.length} 노출</>}</span>
          </div>
          {rps.length > 0 && (
            <div className="surface-row">
              <span>리소스</span>
              <span className="ticks">
                {rps.map(r => (
                  <button key={r.asset_id} className={`tick rp${r.asset_subtype === 'resource_template' ? ' tpl' : r.asset_subtype === 'prompt' ? ' pr' : ''}${selected === r.asset_id ? ' sel' : ''}`}
                    title={`${SUBTYPE_LABEL[r.asset_subtype ?? ''] ?? ''} ${r.name}`} aria-label={r.name} onClick={() => onSelect(r.asset_id)} />
                ))}
              </span>
              <span className="surface-count">{rps.length}</span>
            </div>
          )}
          {tools.length > 0 && <button className="expand" onClick={() => toggle(srv.asset_id)} aria-expanded={isOpen}>{isOpen ? '도구 이름 접기' : '도구 이름 보기'}</button>}
        </div>
        {isOpen && (
          <div className="tool-list">
            {tools.map(t => (
              <button key={t.asset_id} onClick={() => onSelect(t.asset_id)} style={dim(t.asset_id) && q ? { opacity: .35 } : undefined}>
                <i className={tickCls(t)} aria-hidden /><span>{t.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  const Column = ({ host }: { host: Asset }) => {
    const servers = declaredBy(host, 'mcp_server')
    const plugins = declaredBy(host, 'plugin')
    const skills = declaredBy(host, 'skill')
    const hostPols = model.policiesFor(host)
    const isGw = host.asset_type === 'gateway'
    return (
      <div className="host-col">
        <button className={`host-head${selected === host.asset_id ? ' sel' : ''}`} onClick={() => onSelect(host.asset_id)} style={dim(host.asset_id) ? { opacity: .4 } : undefined}>
          <Glyph asset={host} />
          <div>
            <div className="meta">{isGw ? 'Gateway' : 'Node'} {host.project.openclaw_version ? `OpenClaw ${host.project.openclaw_version}` : ''}</div>
            <h2>{host.name}</h2>
            <div className="meta"><code>{String(host.project.device_id ?? '').slice(0, 16)}</code>{isGw && host.project.auth_mode ? `  인증 ${host.project.auth_mode}` : ''}</div>
          </div>
          <span className="surface-count">서버 <b>{servers.length + plugins.reduce((n, p) => n + (model.out.get(p.asset_id) ?? []).filter(r => r.relation_type === 'ASSOCIATED_WITH').length, 0)}</b></span>
        </button>
        {hostPols.length > 0 && (
          <div className="chiprow" style={{ marginTop: 8 }}>
            {hostPols.map(p => (
              <button key={p.asset_id} className={`node-chip${selected === p.asset_id ? ' sel' : ''}${dim(p.asset_id) ? ' dim' : ''}`} onClick={() => onSelect(p.asset_id)}>
                <Glyph asset={p} small /><span>{p.name}</span>
              </button>
            ))}
          </div>
        )}
        <div className="lane">
          <div className="lane-title"><b>설정에 선언된 MCP 서버</b><span>{servers.length}</span></div>
          {servers.map(s => <ServerRow key={s.asset_id} srv={s} />)}
          {!servers.length && <p className="small muted">선언된 서버가 없습니다.</p>}
        </div>
        {plugins.length > 0 && (
          <div className="lane">
            <div className="lane-title"><b>플러그인</b><span>{plugins.length}</span></div>
            {plugins.map(p => {
              const regs = (model.out.get(p.asset_id) ?? []).filter(r => r.relation_type === 'ASSOCIATED_WITH').map(r => model.byId.get(r.target.asset_ref!)!).filter(x => x?.asset_type === 'mcp_server')
              return (
                <div key={p.asset_id} style={{ marginBottom: 10 }}>
                  <button className={`node-chip${selected === p.asset_id ? ' sel' : ''}${dim(p.asset_id) ? ' dim' : ''}`} onClick={() => onSelect(p.asset_id)} style={{ marginBottom: 6 }}>
                    <Glyph asset={p} small /><span>{p.name}<br /><span className="sub">{p.project.supply_chain?.package_id} {p.project.supply_chain?.version}, 출처 {p.project.supply_chain?.provider}</span></span>
                  </button>
                  <div style={{ paddingLeft: 18, borderLeft: '2px solid var(--line)' }}>
                    {regs.map(s => <ServerRow key={s.asset_id} srv={s} />)}
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {skills.length > 0 && (
          <div className="lane">
            <div className="lane-title"><b>스킬</b><span>{skills.length}</span></div>
            <div className="chiprow">
              {skills.map(sk => {
                const assoc = (model.out.get(sk.asset_id) ?? []).filter(r => r.relation_type === 'ASSOCIATED_WITH').map(r => model.byId.get(r.target.asset_ref!)?.name)
                return (
                  <button key={sk.asset_id} className={`node-chip${selected === sk.asset_id ? ' sel' : ''}${dim(sk.asset_id) ? ' dim' : ''}`} onClick={() => onSelect(sk.asset_id)}>
                    <Glyph asset={sk} small />
                    <span>{sk.name}<br /><span className="sub">{assoc.length ? `연관 서버 ${assoc.join(', ')} (추론)` : '연관 서버 없음'}</span></span>
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>
    )
  }

  const gw = hosts.find(h => h.asset_type === 'gateway')
  const node = hosts.find(h => h.asset_type === 'node')

  return (
    <div className="map-wrap">
      <div className="toolbar">
        <label className="field" style={{ width: 280 }}>
          <Search size={15} />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="자산 이름, ID, 시나리오(S1)" aria-label="자산 검색" />
        </label>
        <div className="seg" role="group" aria-label="강조">
          <button aria-pressed={!onlyAlerts} onClick={() => setOnlyAlerts(false)}>전체</button>
          <button aria-pressed={onlyAlerts} onClick={() => setOnlyAlerts(true)}>경고 관련만</button>
        </div>
        {(selected || q) && <button className="btn btn-ghost" onClick={() => { setQ(''); onSelect('') }}>강조 해제</button>}
      </div>
      <div className="map-legend">
        <span><i className="tick" />에이전트에 노출</span>
        <span><i className="tick no" />미노출(필터 등)</span>
        <span><i className="tick unk" />노출 확인 못함</span>
        <span><i className="tick hot" style={{ margin: 3 }} />경고 대상</span>
        <span><i className="tick rp" />리소스</span>
        <span><i className="tick rp tpl" />템플릿</span>
        <span><i className="tick rp pr" />프롬프트</span>
      </div>
      <div className="map">
        {gw ? <Column host={gw} /> : <div />}
        <div className="pair" aria-label={paired ? 'Gateway와 Node 페어링 확인' : '페어링 근거 없음'}>
          <span className={`pair-line${paired ? '' : ' off'}`} />
          <span className="pair-label">{paired ? '페어링 확인' : '페어링 근거 없음'}</span>
          <span className={`pair-line${paired ? '' : ' off'}`} />
        </div>
        {node ? <Column host={node} /> : <div className="empty">Node 자산이 없습니다.</div>}
      </div>
      {orphans.length > 0 && (
        <div className="lane">
          <div className="lane-title"><b>선언 주체를 확인하지 못한 서버</b><span>{orphans.length}</span></div>
          {orphans.map(s => <ServerRow key={s.asset_id} srv={s} />)}
        </div>
      )}
    </div>
  )
}
