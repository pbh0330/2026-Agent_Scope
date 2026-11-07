// 대시보드 입력 로더. 기본은 public/data(파이프라인 출력)를 fetch로 읽는다.
// 단일 HTML로 묶어 배포할 때는 window.__AGENTSCOPE_DATA__에 같은 경로의 JSON을 넣어 둔다.
import type { DetectionReport, InventorySnapshot, Manifest, OpenClawAudit, QAResult, SnapshotDiff, UsageReport } from '../types/contracts'

declare global {
  interface Window { __AGENTSCOPE_DATA__?: Record<string, unknown> }
}

const cache = new Map<string, Promise<unknown>>()
const imported = new Map<string, unknown>()

export function base(): string {
  const b = (import.meta as any).env?.BASE_URL ?? './'
  return b.endsWith('/') ? b : b + '/'
}

export function getJSON<T>(path: string): Promise<T> {
  if (imported.has(path)) return Promise.resolve(imported.get(path) as T)
  const inline = window.__AGENTSCOPE_DATA__?.[path]
  if (inline !== undefined) return Promise.resolve(inline as T)
  if (!cache.has(path)) {
    cache.set(path, fetch(`${base()}data/${path}`).then(r => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
      return r.json()
    }))
  }
  return cache.get(path) as Promise<T>
}

export function registerImported(path: string, data: unknown) {
  imported.set(path, data)
}

export interface Bundle {
  snapshot: InventorySnapshot
  detections: DetectionReport
  audit: OpenClawAudit | null
  qa: QAResult | null
}

export async function loadBundle(files: { snapshot: string; detections: string; audit?: string; qa?: string }): Promise<Bundle> {
  const [snapshot, detections, audit, qa] = await Promise.all([
    getJSON<InventorySnapshot>(files.snapshot),
    getJSON<DetectionReport>(files.detections),
    files.audit ? getJSON<OpenClawAudit>(files.audit) : Promise.resolve(null),
    files.qa ? getJSON<QAResult>(files.qa) : Promise.resolve(null),
  ])
  return { snapshot, detections, audit, qa }
}

export const loadManifest = () => getJSON<Manifest>('manifest.json')
export const loadDiff = (file: string) => getJSON<SnapshotDiff>(file)
export const loadUsage = (file: string) => getJSON<UsageReport>(file)

/** 사용자가 고른 JSON 파일을 형식으로 구분한다(스키마 필드 기준). */
export function sniff(obj: any): 'snapshot' | 'detections' | 'usage' | 'scanner' | 'unknown' {
  if (obj && Array.isArray(obj.assets) && Array.isArray(obj.relations) && obj.snapshot_id) return 'snapshot'
  if (obj && Array.isArray(obj.evaluations) && Array.isArray(obj.alerts)) return 'detections'
  if (obj && Array.isArray(obj.records) && obj.usage_report_id) return 'usage'
  if (obj && typeof obj.format === 'string' && obj.format.startsWith('agent-scope.scanner')) return 'scanner'
  return 'unknown'
}
