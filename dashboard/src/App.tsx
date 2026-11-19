import { House, Network, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { BrandMark } from './components/ui'
import { type Bundle, loadBundle, loadManifest } from './data/load'
import { Model } from './data/model'
import { makePresent } from './data/present'
import { type UsageBundle, loadUsageBundle } from './data/usage'
import { AssetMapPage } from './pages/AssetMapPage'
import { HomePage } from './pages/HomePage'
import { ThreatsPage } from './pages/ThreatsPage'
import type { Manifest } from './types/contracts'
import { type ContractError, validateBundle } from './data/validate'

export type PageKey = 'home' | 'map' | 'threats'

// 화면마다 답하는 질문이 하나씩 있다.
const PAGES: { key: PageKey; label: string; icon: typeof House; title: string }[] = [
  { key: 'home', label: '자산 현황', icon: House, title: '에이전트 자산 현황' },
  { key: 'map', label: '자산 지도', icon: Network, title: '자산 지도' },
  { key: 'threats', label: '위협과 조치', icon: TriangleAlert, title: '위협과 조치' },
]

/**
 * 보여 줄 점검 결과. 화면에는 고르는 메뉴를 두지 않는다(실제 사용자는 자기 환경 하나만 본다).
 * 시연·캡처할 때는 주소 끝에 #S1, #P2처럼 테스트베드 구성 키를 붙여 바꾼다.
 */
const DEFAULT_KEY = 'S1'
const keyFromHash = () => decodeURIComponent(window.location.hash.replace(/^#/, '')) || null

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [key, setKey] = useState<string | null>(keyFromHash)
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [usage, setUsage] = useState<UsageBundle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [contract, setContract] = useState<ContractError[] | null>(null)
  const [page, setPage] = useState<PageKey>('home')
  const [focus, setFocus] = useState<{ scenario?: string; alert?: string; asset?: string }>({})

  useEffect(() => {
    loadManifest().then(setManifest).catch(e => setError(`점검 결과를 읽지 못했어요 (${e.message}). pipeline/build_data.py로 public/data를 만들어 주세요.`))
    const onHash = () => setKey(keyFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const entry = manifest?.snapshots.find(s => s.key === key) ?? manifest?.snapshots.find(s => s.key === DEFAULT_KEY) ?? manifest?.snapshots[0]
  useEffect(() => {
    if (!entry) return
    setBundle(null); setContract(null)
    loadBundle(entry.files).then(b => {
      // 형식이 틀린 입력은 화면을 그리지 않고 위치와 원인을 보여 준다.
      const errs = validateBundle(entry.files.snapshot, b.snapshot, entry.files.detections, b.detections)
      if (errs.length) { setContract(errs); return }
      setBundle(b); setError(null)
    }).catch(e => setError(String(e)))
  }, [entry?.key, entry?.snapshot_id])
  useEffect(() => { if (manifest) loadUsageBundle(manifest).then(setUsage) }, [manifest])

  const model = useMemo(() => (bundle ? new Model(bundle) : null), [bundle])
  const present = useMemo(() => (model ? makePresent(model) : null), [model])

  const go = (p: PageKey, opts: { scenario?: string; alert?: string; asset?: string } = {}) => { setFocus(opts); setPage(p); window.scrollTo({ top: 0 }) }
  const info = PAGES.find(p => p.key === page)!
  const alerts = model?.detections.alerts.length ?? 0

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand"><span className="brand-mark"><BrandMark size={22} /></span><div className="brand-name">AgentScope</div></div>
        <nav className="nav" aria-label="화면">
          {PAGES.map(p => {
            const Icon = p.icon
            return (
              <button key={p.key} aria-current={page === p.key ? 'page' : undefined} onClick={() => go(p.key)}>
                <Icon size={18} strokeWidth={1.9} />{p.label}
                {p.key === 'threats' && alerts > 0 && <span className="count hot">{alerts}</span>}
              </button>
            )
          })}
        </nav>
      </aside>

      <main className="page">
        <header className="page-head"><h1>{info.title}</h1></header>
        {error && <div className="err" role="alert">{error}</div>}
        {contract && (
          <section className="card contract" role="alert">
            <h2>점검 결과 파일의 형식이 맞지 않아요</h2>
            <p>잘못된 결과를 보여 주지 않도록 화면을 그리지 않았어요. 아래 위치를 고친 뒤 다시 만들어 주세요.</p>
            <ul>{contract.map((c, i) => <li key={i}><code>{c.file} · {c.where}</code><span>{c.message}</span></li>)}</ul>
            {contract.length >= 50 && <p className="muted">처음 50건만 보여 줘요.</p>}
          </section>
        )}
        {!model && !error && !contract && <div className="empty">불러오는 중</div>}
        {model && present && (
          <>
            {page === 'home' && <HomePage model={model} present={present} usage={usage} go={go} />}
            {page === 'map' && <AssetMapPage model={model} present={present} usage={usage} onThreat={id => go('threats', { alert: id })} initial={focus.asset} />}
            {page === 'threats' && <ThreatsPage model={model} present={present} scenario={focus.scenario} alertId={focus.alert}
              onScenario={id => setFocus({ scenario: id })} onShowMap={id => go('map', { asset: id })} />}
          </>
        )}
      </main>
    </div>
  )
}
