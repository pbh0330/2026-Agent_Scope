import {
  AlertTriangle, ArrowLeftRight, Coins, DatabaseZap, FolderOpen, LayoutDashboard, List, Map as MapIcon, Moon, Sun, SunMoon,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AssetDrawer } from './components/AssetDrawer'
import { BrandMark } from './components/ui'
import { type Bundle, loadBundle, loadManifest, registerImported, sniff } from './data/load'
import { Model, fmtTime } from './data/model'
import { ChangesPage } from './pages/ChangesPage'
import { CollectionPage } from './pages/CollectionPage'
import { InventoryPage } from './pages/InventoryPage'
import { MapPage } from './pages/MapPage'
import { Overview } from './pages/Overview'
import { SecurityPage } from './pages/SecurityPage'
import { UsagePage } from './pages/UsagePage'
import type { DetectionReport, InventorySnapshot, Manifest, ManifestSnapshot } from './types/contracts'

export type PageKey = 'overview' | 'map' | 'inventory' | 'security' | 'changes' | 'collection' | 'usage'

const PAGES: { key: PageKey; label: string; icon: typeof MapIcon; group: string; title: string; desc: string }[] = [
  { key: 'overview', label: '개요', icon: LayoutDashboard, group: '현황', title: '개요', desc: '선택한 구성에서 무엇이 선언·발견·노출되었고 어떤 위협이 확인되었는지 봅니다.' },
  { key: 'map', label: '자산 지도', icon: MapIcon, group: '현황', title: '자산 지도', desc: '호스트별로 선언된 서버와 서버가 광고한 도구를 펼쳐 봅니다. 눈금 하나가 도구 하나입니다.' },
  { key: 'inventory', label: '자산 목록', icon: List, group: '현황', title: '자산 목록', desc: '8종 자산을 유형·상태·보안 판정·시나리오로 걸러 봅니다.' },
  { key: 'security', label: '보안 경고', icon: AlertTriangle, group: '분석', title: '보안 경고', desc: 'S1~S5 정적 탐지 결과입니다. 경고마다 관련 자산·관계·근거를 함께 보여줍니다.' },
  { key: 'changes', label: '변경 비교', icon: ArrowLeftRight, group: '분석', title: '변경 비교', desc: '두 스냅샷 사이에 추가·변경된 자산과 새로 열리거나 해결된 경고를 비교합니다.' },
  { key: 'collection', label: '수집과 검증', icon: DatabaseZap, group: '데이터', title: '수집과 검증', desc: '어떤 원본을 어떤 방식으로 읽었는지, 테스트베드 정답 목록과 얼마나 맞는지 확인합니다.' },
  { key: 'usage', label: '토큰 사용', icon: Coins, group: '데이터', title: '토큰 사용', desc: '토큰 수집기가 귀속한 도구 호출별 추정 입력 토큰과 비용입니다.' },
]

type Theme = 'system' | 'light' | 'dark'
const store = {
  get(k: string) { try { return localStorage.getItem(k) } catch { return null } },
  set(k: string, v: string) { try { localStorage.setItem(k, v) } catch { /* 저장 불가 환경 */ } },
}

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [current, setCurrent] = useState<string>(() => store.get('as.snapshot') ?? 'P2')
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState<PageKey>('overview')
  const [selected, setSelected] = useState<string | null>(null)
  const [drawer, setDrawer] = useState(false)
  const [focus, setFocus] = useState<{ scenario?: string; alert?: string }>({})
  const [theme, setTheme] = useState<Theme>(() => (store.get('as.theme') as Theme) ?? 'system')
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const el = document.documentElement
    if (theme === 'system') el.removeAttribute('data-theme')
    else el.setAttribute('data-theme', theme)
    store.set('as.theme', theme)
  }, [theme])

  useEffect(() => { loadManifest().then(setManifest).catch(e => setError(`manifest.json을 읽지 못했습니다: ${e.message}. pipeline/build_data.py로 public/data를 만드세요.`)) }, [])

  const entry = manifest?.snapshots.find(s => s.key === current) ?? manifest?.snapshots.find(s => s.key === 'P2') ?? manifest?.snapshots[0]
  useEffect(() => {
    if (!entry) return
    setBundle(null)
    loadBundle(entry.files).then(b => { setBundle(b); setError(null) }).catch(e => setError(String(e)))
    store.set('as.snapshot', entry.key)
  }, [entry?.key, entry?.snapshot_id])

  const model = useMemo(() => (bundle ? new Model(bundle) : null), [bundle])

  const select = useCallback((id: string) => {
    if (!id) { setSelected(null); setDrawer(false); return }
    setSelected(id); setDrawer(true)
  }, [])
  const go = (p: PageKey, opts: { scenario?: string; alert?: string } = {}) => { setFocus(opts); setPage(p); window.scrollTo({ top: 0 }) }

  // 팀원이 만든 snapshot.json / detections.json을 끌어다 놓으면 '불러온 데이터'로 추가
  const importFiles = async (files: FileList | null) => {
    if (!files?.length || !manifest) return
    let snap: InventorySnapshot | null = null
    let det: DetectionReport | null = null
    const problems: string[] = []
    for (const f of Array.from(files)) {
      try {
        const obj = JSON.parse(await f.text())
        const kind = sniff(obj)
        if (kind === 'snapshot') snap = obj
        else if (kind === 'detections') det = obj
        else if (kind === 'scanner') problems.push(`${f.name}: 스캐너 내부 형식입니다. pipeline/build_data.py로 공통 스냅샷으로 바꿔 주세요.`)
        else problems.push(`${f.name}: InventorySnapshot이나 DetectionReport 형식이 아닙니다.`)
      } catch { problems.push(`${f.name}: JSON을 읽지 못했습니다.`) }
    }
    if (!snap) { setError(problems.join(' ') || 'snapshot.json이 필요합니다.'); return }
    const detections: DetectionReport = det ?? { schema_version: snap.schema_version, report_id: 'none', snapshot_id: snap.snapshot_id, generated_at: snap.generated_at, ruleset: { id: '없음', version: '-' }, evaluations: [], alerts: [] }
    const key = 'IMPORT'
    registerImported('import/snapshot.json', snap)
    registerImported('import/detections.json', detections)
    const imp: ManifestSnapshot = {
      key, label: '불러온 데이터', kind: 'imported', scenario_id: null, synthetic: false, snapshot_id: snap.snapshot_id + Date.now(),
      files: { snapshot: 'import/snapshot.json', detections: 'import/detections.json' },
      counts: { assets: snap.assets.length, relations: snap.relations.length, alerts: detections.alerts.length },
    }
    setManifest({ ...manifest, snapshots: [...manifest.snapshots.filter(s => s.key !== key), imp] })
    setCurrent(key)
    setError(problems.length ? problems.join(' ') : null)
  }

  const info = PAGES.find(p => p.key === page)!
  const normal = manifest?.snapshots.filter(s => s.kind === 'normal') ?? []
  const risky = manifest?.snapshots.filter(s => s.kind === 'scenario') ?? []
  const imported = manifest?.snapshots.filter(s => s.kind === 'imported') ?? []
  const nextTheme: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
  const ThemeIcon = theme === 'light' ? Sun : theme === 'dark' ? Moon : SunMoon

  return (
    <div className="shell"
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={e => { if (e.currentTarget === e.target) setDragging(false) }}
      onDrop={e => { e.preventDefault(); setDragging(false); importFiles(e.dataTransfer.files) }}>
      <aside className="rail">
        <div className="brand"><BrandMark /><div><div className="brand-name">AgentScope</div><div className="brand-sub">AI 에이전트 자산 식별과 가시화</div></div></div>
        <nav className="nav" aria-label="화면">
          {PAGES.map((p, i) => {
            const Icon = p.icon
            const showGroup = i === 0 || PAGES[i - 1].group !== p.group
            const alerts = p.key === 'security' && model ? model.detections.alerts.length : 0
            return (
              <div key={p.key} style={{ display: 'contents' }}>
                {showGroup && <div className="nav-group">{p.group}</div>}
                <button aria-current={page === p.key ? 'page' : undefined} onClick={() => go(p.key)}>
                  <Icon size={16} strokeWidth={1.8} />{p.label}
                  {p.key === 'security' && model && <span className={`count${alerts ? ' hot' : ''}`}>{alerts}</span>}
                  {p.key === 'map' && model && <span className="count">{model.assets.length}</span>}
                </button>
              </div>
            )
          })}
        </nav>
        <div className="rail-foot">
          <button className="rail-cta" onClick={() => fileRef.current?.click()}>
            <FolderOpen size={16} />스냅샷 불러오기
          </button>
          <input ref={fileRef} type="file" accept=".json,application/json" multiple hidden onChange={e => importFiles(e.target.files)} />
          <p>snapshot.json을 화면에 끌어다 놓아도 됩니다.</p>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div className="topbar-title">
            <span className="crumb">AgentScope</span>
            <b>{info.title}</b>
          </div>
          {manifest && (
            <div className="snap-tabs" role="group" aria-label="스냅샷 선택">
              <div className="snap-group" title="테스트베드 정상 구성">
                {normal.map(s => (
                  <button key={s.key} className="snap" aria-pressed={entry?.key === s.key} onClick={() => setCurrent(s.key)}>{s.key}</button>
                ))}
              </div>
              {risky.length > 0 && (
                <div className="snap-group risk" title="위험 구성: S1은 테스트베드 구성 사본, 나머지는 P2 설정을 바꾼 합성 구성">
                  {risky.map(s => (
                    <button key={s.key} className="snap" aria-pressed={entry?.key === s.key} onClick={() => setCurrent(s.key)}>
                      {s.key}{s.counts.alerts > 0 && <i className="snap-badge">{s.counts.alerts}</i>}
                    </button>
                  ))}
                </div>
              )}
              {imported.map(s => (
                <div className="snap-group" key={s.key}>
                  <button className="snap" aria-pressed={entry?.key === s.key} onClick={() => setCurrent(s.key)}>불러옴</button>
                </div>
              ))}
            </div>
          )}
          <button className="icon-btn round" onClick={() => setTheme(nextTheme[theme])} aria-label={`화면 테마: ${theme === 'system' ? '시스템' : theme === 'light' ? '밝게' : '어둡게'}`} title="테마 바꾸기"><ThemeIcon size={17} /></button>
          <span className="team-avatar" title="AgentScope 팀">AS</span>
        </div>

        <main className="page">
          <header className="page-head">
            <div>
              <p className="hello">{entry ? (entry.kind === 'scenario' ? (entry.synthetic ? 'P2 기반 합성 위험 구성' : '테스트베드 위험 구성 사본') : entry.kind === 'imported' ? '불러온 데이터' : '테스트베드 정상 구성') : ''}</p>
              <h1>{entry ? (entry.label.split(' · ')[1] ? `${entry.key} ${entry.label.split(' · ')[1]}` : entry.label) : info.title}</h1>
              <p>{info.desc}</p>
            </div>
            {model && <span className="pill-meta">스캔 {fmtTime(model.snapshot.scan.finished_at)}</span>}
          </header>

          {error && <div className="err" role="alert" style={{ marginBottom: 18 }}>{error}</div>}
          {!model && !error && <div className="empty">스냅샷을 불러오는 중</div>}
          {model && manifest && entry && (
            <div className="stack">
              {page === 'overview' && <Overview model={model} entry={entry} go={go} onSelect={select} />}
              {page === 'map' && <MapPage model={model} selected={selected} onSelect={select} />}
              {page === 'inventory' && <InventoryPage model={model} selected={selected} onSelect={select} />}
              {page === 'security' && <SecurityPage model={model} scenario={focus.scenario} alertId={focus.alert} onSelect={select}
                onMap={id => { setSelected(id); setDrawer(false); go('map') }} />}
              {page === 'changes' && <ChangesPage model={model} manifest={manifest} current={entry.key} onSelect={select} />}
              {page === 'collection' && <CollectionPage model={model} manifest={manifest} onSelect={select} />}
              {page === 'usage' && <UsagePage manifest={manifest} snapshotId={model.snapshot.snapshot_id} />}
            </div>
          )}
        </main>
      </div>

      {model && drawer && selected && (
        <AssetDrawer model={model} id={selected} onSelect={select} onClose={() => setDrawer(false)}
          onAlert={id => { setDrawer(false); go('security', { alert: id }) }} />
      )}
      {dragging && <div className="drop">snapshot.json과 detections.json을 놓으세요</div>}
    </div>
  )
}
