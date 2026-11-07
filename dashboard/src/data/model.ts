// 스냅샷 + 탐지 결과에서 화면이 쓰는 색인과 판정 요약을 만든다.
// 규칙: unknown/not_evaluated를 정상으로 표시하지 않는다(스키마 12.8).
import type { Asset, AssetType, DetectionEvaluation, Relation, SecurityAlert, StateAssessment, StateName } from '../types/contracts'
import type { Bundle } from './load'

export const TYPE_ORDER: AssetType[] = ['gateway', 'node', 'mcp_server', 'tool', 'resource_prompt', 'skill', 'plugin', 'permission_auth']

export const TYPE_LABEL: Record<AssetType, string> = {
  gateway: 'Gateway',
  node: 'Node',
  mcp_server: 'MCP 서버',
  tool: 'Tool',
  resource_prompt: 'Resource / Prompt',
  skill: 'Skill',
  plugin: 'Plugin',
  permission_auth: '권한 / 인증',
}

export const SUBTYPE_LABEL: Record<string, string> = {
  resource: 'Resource', resource_template: 'Template', prompt: 'Prompt', permission: '권한 정책', authentication: '인증 참조',
}

export const STATE_ORDER: StateName[] = ['DECLARED', 'DISCOVERED', 'EXPOSED', 'POTENTIALLY_CALLABLE', 'CALLABLE', 'USED']
export const STATE_LABEL: Record<StateName, string> = {
  DECLARED: '선언', DISCOVERED: '발견', EXPOSED: '노출', POTENTIALLY_CALLABLE: '잠재 호출', CALLABLE: '호출 가능', USED: '사용됨',
}
export const STATE_HINT: Record<StateName, string> = {
  DECLARED: '설정에 등록되어 있음',
  DISCOVERED: '설치 파일이나 서버 목록 응답에서 확인됨',
  EXPOSED: '에이전트에 실제로 표시됨',
  POTENTIALLY_CALLABLE: '정적 조건상 호출될 수 있음',
  CALLABLE: '런타임 검증으로 호출 가능 확인',
  USED: '실행 로그에서 사용이 관찰됨',
}

export const RELATION_LABEL: Record<string, string> = {
  DECLARES: '선언', ADVERTISES: '광고', PAIRED_WITH: '페어링', ASSOCIATED_WITH: '연관', APPLIES_TO: '적용', AUTHENTICATES: '인증',
}

export const SCENARIOS: { id: string; title: string; short: string }[] = [
  { id: 'S1', title: '비인가 MCP 서버 등록', short: '비인가 서버' },
  { id: 'S2', title: '과도한 권한의 도구 광고', short: '도구 권한' },
  { id: 'S3', title: '도구 이름 충돌', short: '이름 충돌' },
  { id: 'S4', title: '자격증명 공유', short: '자격증명' },
  { id: 'S5', title: '약한 연결 보안', short: '연결 보안' },
]

export const RESULT_LABEL: Record<string, string> = {
  detected: '탐지', not_detected: '이상 없음', unknown: '판단 불가', not_applicable: '해당 없음', not_evaluated: '미평가', error: '오류',
}

export type SecurityStatus = 'high' | 'warning' | 'unknown' | 'normal' | 'none'
export const STATUS_LABEL: Record<SecurityStatus, string> = {
  high: '높음', warning: '주의', unknown: '판단 불가', normal: '이상 없음', none: '평가 대상 아님',
}

export type Tri = boolean | null | undefined

export class Model {
  readonly assets: Asset[]
  readonly byId = new Map<string, Asset>()
  readonly relations: Relation[]
  readonly relById = new Map<string, Relation>()
  readonly out = new Map<string, Relation[]>()
  readonly inn = new Map<string, Relation[]>()
  readonly children = new Map<string, Asset[]>()
  readonly alertsByAsset = new Map<string, SecurityAlert[]>()
  readonly evalsByAsset = new Map<string, DetectionEvaluation[]>()
  readonly evidence: Map<string, Bundle['snapshot']['evidence'][number]>

  constructor(readonly bundle: Bundle) {
    const s = bundle.snapshot
    this.assets = s.assets
    this.relations = s.relations
    this.evidence = new Map(s.evidence.map(e => [e.evidence_id, e]))
    for (const a of s.assets) this.byId.set(a.asset_id, a)
    for (const r of s.relations) {
      this.relById.set(r.relation_id, r)
      push(this.out, r.source_asset_ref, r)
      if (r.target.asset_ref) push(this.inn, r.target.asset_ref, r)
    }
    for (const a of s.assets) if (a.owner_ref) push(this.children, a.owner_ref, a)
    for (const al of bundle.detections.alerts) for (const id of al.asset_ids) push(this.alertsByAsset, id, al)
    for (const ev of bundle.detections.evaluations) for (const id of ev.asset_ids) push(this.evalsByAsset, id, ev)
  }

  get snapshot() { return this.bundle.snapshot }
  get detections() { return this.bundle.detections }

  ofType(t: AssetType) { return this.assets.filter(a => a.asset_type === t) }

  state(a: Asset, name: StateName): StateAssessment | undefined {
    return a.project.state_assessments.find(s => s.state === name)
  }
  stateValue(a: Asset, name: StateName): Tri {
    const s = this.state(a, name)
    return s ? s.value : undefined
  }

  /** 가장 멀리 확인된 상태(true인 마지막 단계) */
  furthest(a: Asset): StateName | null {
    let last: StateName | null = null
    for (const n of STATE_ORDER) if (this.stateValue(a, n) === true) last = n
    return last
  }

  security(a: Asset): SecurityStatus {
    const al = this.alertsByAsset.get(a.asset_id) ?? []
    if (al.some(x => x.severity === 'high' || x.severity === 'critical')) return 'high'
    if (al.length) return 'warning'
    const ev = this.evalsByAsset.get(a.asset_id) ?? []
    if (!ev.length) return 'none'
    if (ev.some(e => e.result === 'unknown' || e.result === 'not_evaluated' || e.result === 'error')) return 'unknown'
    if (ev.every(e => e.result === 'not_applicable')) return 'none'
    return 'normal'
  }

  /** 소속 서버 / 선언 주체 */
  parentOf(a: Asset): Asset | undefined {
    if (a.owner_ref) return this.byId.get(a.owner_ref)
    const decl = (this.inn.get(a.asset_id) ?? []).find(r => r.relation_type === 'DECLARES' || r.relation_type === 'ASSOCIATED_WITH')
    return decl ? this.byId.get(decl.source_asset_ref) : undefined
  }

  policiesFor(a: Asset): Asset[] {
    return (this.inn.get(a.asset_id) ?? [])
      .filter(r => r.relation_type === 'APPLIES_TO' || r.relation_type === 'AUTHENTICATES')
      .map(r => this.byId.get(r.source_asset_ref)!)
      .filter(Boolean)
  }

  neighbours(id: string): Set<string> {
    const s = new Set<string>([id])
    for (const r of this.out.get(id) ?? []) if (r.target.asset_ref) s.add(r.target.asset_ref)
    for (const r of this.inn.get(id) ?? []) s.add(r.source_asset_ref)
    const a = this.byId.get(id)
    if (a?.owner_ref) s.add(a.owner_ref)
    for (const c of this.children.get(id) ?? []) s.add(c.asset_id)
    for (const al of this.alertsByAsset.get(id) ?? []) for (const x of al.asset_ids) s.add(x)
    return s
  }

  host(a: Asset): string {
    return a.context.host ?? (a.project.host as string) ?? '—'
  }

  /** 엔드포인트 요약: URL 또는 실행 명령 */
  endpoint(a: Asset): string | null {
    const c = a.product?.config
    if (!c) return null
    if (c.url) return String(c.url)
    if (c.command) return [c.command, ...(Array.isArray(c.args) ? c.args : [])].join(' ')
    return null
  }
}

function push<K, V>(m: Map<K, V[]>, k: K, v: V) {
  const arr = m.get(k)
  if (arr) arr.push(v)
  else m.set(k, [v])
}

export function fmtTime(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
}

export function shortId(id: string): string {
  return id.length > 18 ? `${id.slice(0, 16)}…` : id
}
