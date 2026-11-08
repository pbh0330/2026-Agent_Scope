// 토큰 사용 데이터 원천.
// 1) 사용 현황 API(token-collector/backend/usageapi)가 떠 있으면 그 응답을 그대로 쓴다.
//    개발 서버는 vite.config.ts의 프록시로 /api → http://127.0.0.1:8088 에 붙는다.
// 2) API에 닿지 않으면 파이프라인이 저장해 둔 같은 응답의 정적 사본(public/data/usage-api)을 쓴다.
import type { BrakeEvents, Manifest, UsageByAsset, UsageHealth, UsageRecords, UsageSummary, UsageTimeseries } from '../types/contracts'
import { getJSON } from './load'

export type UsageGroup = 'asset' | 'server' | 'pattern'

export interface UsageBundle {
  source: 'live' | 'static'
  fetchedAt: string
  health: UsageHealth
  summary: UsageSummary
  byAsset: Record<UsageGroup, UsageByAsset>
  records: UsageRecords
  timeseries: UsageTimeseries
  brakes: BrakeEvents
}

const API = '/api/v1/usage'

async function api<T>(path: string, timeoutMs = 2500): Promise<T> {
  const ctl = new AbortController()
  const id = setTimeout(() => ctl.abort(), timeoutMs)
  try {
    const r = await fetch(`${API}/${path}`, { signal: ctl.signal, headers: { Accept: 'application/json' } })
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
    if (!(r.headers.get('content-type') ?? '').includes('json')) throw new Error(`${path}: JSON 응답 아님`)
    return await r.json() as T
  } finally {
    clearTimeout(id)
  }
}

async function fromApi(): Promise<UsageBundle> {
  const health = await api<UsageHealth>('health', 1500)
  const [summary, a, s, p, records, timeseries, brakes] = await Promise.all([
    api<UsageSummary>('summary'),
    api<UsageByAsset>('by-asset?group=asset'),
    api<UsageByAsset>('by-asset?group=server'),
    api<UsageByAsset>('by-asset?group=pattern'),
    api<UsageRecords>('records?limit=500'),
    api<UsageTimeseries>('timeseries'),
    api<BrakeEvents>('brake-events?limit=500'),
  ])
  return { source: 'live', fetchedAt: new Date().toISOString(), health, summary,
    byAsset: { asset: a, server: s, pattern: p }, records, timeseries, brakes }
}

async function fromStatic(dir: string, capturedAt: string): Promise<UsageBundle> {
  const f = <T,>(name: string) => getJSON<T>(`${dir}/${name}`)
  const [health, summary, a, s, p, records, timeseries, brakes] = await Promise.all([
    f<UsageHealth>('health.json'), f<UsageSummary>('summary.json'),
    f<UsageByAsset>('by-asset.asset.json'), f<UsageByAsset>('by-asset.server.json'), f<UsageByAsset>('by-asset.pattern.json'),
    f<UsageRecords>('records.json'), f<UsageTimeseries>('timeseries.json'), f<BrakeEvents>('brake-events.json'),
  ])
  return { source: 'static', fetchedAt: capturedAt, health, summary,
    byAsset: { asset: a, server: s, pattern: p }, records, timeseries, brakes }
}

let cached: Promise<UsageBundle | null> | null = null

/** API → 정적 사본 순서로 시도. 둘 다 없으면 null. force면 다시 읽는다. */
export function loadUsageBundle(manifest: Manifest, force = false): Promise<UsageBundle | null> {
  if (cached && !force) return cached
  const fallback = () => manifest.usage_api ? fromStatic(manifest.usage_api.dir, manifest.usage_api.captured_at) : Promise.resolve(null)
  cached = fromApi().catch(fallback).catch(() => null)
  return cached
}

/** 대시보드 자산과 사용 기록 연결: 사용 현황 API가 스냅샷으로 매핑한 asset_id만 쓴다(이름으로 추측하지 않음). */
export function usageForAsset(b: UsageBundle | null, assetId: string) {
  if (!b) return null
  return b.byAsset.asset.items.find(i => i.asset_id === assetId)
    ?? b.byAsset.server.items.find(i => i.asset_id === assetId)
    ?? null
}
