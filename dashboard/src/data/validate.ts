// 계약 검사: 화면을 그리기 전에 입력이 공통 스키마 0.7.0-draft의 형식·참조 규칙을 지키는지 본다.
// 계약 오류(형식 자체가 틀림)는 위치와 원인을 보여 주고 화면을 그리지 않는다(스키마 문서 10절, QA-SCHEMA-02·04).
// 수집 실패·부분 수집(형식은 맞고 결과 안에 실패가 기록된 경우)은 오류가 아니다. 화면이 받아서 범위를 표시한다.
import type { DetectionReport, InventorySnapshot } from '../types/contracts'

export const SUPPORTED_SCHEMA = ['0.7.0-draft']

export interface ContractError { file: string; where: string; message: string }

const TYPES = new Set(['gateway', 'node', 'mcp_server', 'tool', 'resource_prompt', 'skill', 'plugin', 'permission_auth'])
const TARGET_KINDS: Record<string, string[]> = {
  asset: ['asset_ref'], agent: ['profile_id', 'agent_key'], host: ['profile_id', 'gateway_ref'],
  backend_resource: ['resource_kind'], external_destination: ['destination_kind'],
}
const RESULTS = new Set(['detected', 'not_detected', 'unknown', 'not_applicable', 'not_evaluated', 'error'])

export function validateBundle(snapFile: string, s: InventorySnapshot, detFile: string, d: DetectionReport): ContractError[] {
  const errs: ContractError[] = []
  const add = (file: string, where: string, message: string) => { if (errs.length < 50) errs.push({ file, where, message }) }

  // 버전: 문자열만 보고 구버전을 받아들이지 않는다.
  for (const [file, v] of [[snapFile, (s as any)?.schema_version], [detFile, (d as any)?.schema_version]] as const) {
    if (!SUPPORTED_SCHEMA.includes(v)) {
      add(file, 'schema_version', v
        ? `지원하지 않는 형식 버전(${v})이에요. 이 화면은 ${SUPPORTED_SCHEMA.join(', ')}만 읽어요. 파이프라인으로 다시 만들어 주세요.`
        : '형식 버전(schema_version)이 없어요.')
    }
  }
  if (errs.length) return errs

  for (const k of ['snapshot_id', 'environment_id', 'profile_id', 'assets', 'relations', 'evidence', 'collection_results', 'scan'] as const) {
    if ((s as any)[k] === undefined) add(snapFile, k, '필수 항목이 없어요.')
  }
  for (const k of ['report_id', 'snapshot_id', 'evaluations', 'alerts'] as const) {
    if ((d as any)[k] === undefined) add(detFile, k, '필수 항목이 없어요.')
  }
  if (errs.length) return errs

  const uniq = <T,>(list: T[], id: (x: T) => string, file: string, where: string) => {
    const seen = new Set<string>()
    list.forEach((x, i) => {
      const v = id(x)
      if (!v) add(file, `${where}[${i}]`, 'ID가 비어 있어요.')
      else if (seen.has(v)) add(file, `${where}[${i}]`, `ID가 중복됐어요: ${v}`)
      seen.add(v)
    })
    return seen
  }
  const assets = uniq(s.assets, a => a.asset_id, snapFile, 'assets')
  const rels = uniq(s.relations, r => r.relation_id, snapFile, 'relations')
  const evs = uniq(s.evidence, e => e.evidence_id, snapFile, 'evidence')
  const cols = uniq(s.collection_results, c => c.collection_id, snapFile, 'collection_results')
  const typeOf = new Map(s.assets.map(a => [a.asset_id, a.asset_type]))

  const gwRef = s.context?.gateway_ref
  if (gwRef && typeOf.get(gwRef) !== 'gateway') add(snapFile, 'context.gateway_ref', `게이트웨이가 아닌 자산을 가리켜요: ${gwRef}`)

  s.assets.forEach((a, i) => {
    const w = `assets[${i}] (${a.asset_id})`
    if (!TYPES.has(a.asset_type)) add(snapFile, w, `알 수 없는 자산 종류(${a.asset_type})예요.`)
    if (a.owner_ref && !assets.has(a.owner_ref)) add(snapFile, `${w}.owner_ref`, `가리키는 자산이 없어요: ${a.owner_ref}`)
    if ((a.asset_type === 'tool' || a.asset_type === 'resource_prompt') && typeOf.get(a.owner_ref ?? '') !== 'mcp_server') {
      add(snapFile, `${w}.owner_ref`, '도구·리소스는 소속 MCP 서버를 가리켜야 해요.')
    }
    const g = a.context?.gateway_ref
    if (g && typeOf.get(g) !== 'gateway') add(snapFile, `${w}.context.gateway_ref`, `게이트웨이가 아닌 자산을 가리켜요: ${g}`)
    if (!a.evidence_refs?.length) add(snapFile, `${w}.evidence_refs`, '근거가 하나도 없어요.')
    a.evidence_refs?.forEach(e => { if (!evs.has(e)) add(snapFile, `${w}.evidence_refs`, `가리키는 근거가 없어요: ${e}`) })
    if (!Array.isArray(a.project?.state_assessments)) add(snapFile, `${w}.project.state_assessments`, '상태 목록이 없어요.')
  })

  s.relations.forEach((r, i) => {
    const w = `relations[${i}] (${r.relation_id})`
    if (!assets.has(r.source_asset_ref)) add(snapFile, `${w}.source_asset_ref`, `시작 자산이 없어요: ${r.source_asset_ref}`)
    const keys = TARGET_KINDS[r.target?.kind]
    if (!keys) add(snapFile, `${w}.target`, `알 수 없는 대상 종류(${r.target?.kind})예요.`)
    else {
      const t = r.target as unknown as Record<string, unknown>
      keys.forEach(k => { if (typeof t[k] !== 'string') add(snapFile, `${w}.target.${k}`, '대상 정보가 빠졌어요.') })
      if (r.target.kind === 'asset' && r.target.asset_ref && !assets.has(r.target.asset_ref)) add(snapFile, `${w}.target.asset_ref`, `가리키는 자산이 없어요: ${r.target.asset_ref}`)
    }
    if (!r.evidence_refs?.length) add(snapFile, `${w}.evidence_refs`, '근거가 하나도 없어요.')
    r.evidence_refs?.forEach(e => { if (!evs.has(e)) add(snapFile, `${w}.evidence_refs`, `가리키는 근거가 없어요: ${e}`) })
  })

  s.evidence.forEach((e, i) => {
    if (!cols.has(e.collection_ref)) add(snapFile, `evidence[${i}] (${e.evidence_id}).collection_ref`, `가리키는 수집 작업이 없어요: ${e.collection_ref}`)
  })
  s.collection_results.forEach((c, i) => {
    if (c.target_ref && !assets.has(c.target_ref)) add(snapFile, `collection_results[${i}] (${c.collection_id}).target_ref`, `가리키는 자산이 없어요: ${c.target_ref}`)
  })

  for (const k of ['snapshot_id', 'environment_id', 'profile_id'] as const) {
    if ((d as any)[k] !== (s as any)[k]) add(detFile, k, `점검 결과가 다른 스냅샷을 가리켜요: ${(d as any)[k]}`)
  }
  const evals = uniq(d.evaluations, v => v.evaluation_id, detFile, 'evaluations')
  const evalRule = new Map(d.evaluations.map(v => [v.evaluation_id, v]))
  d.evaluations.forEach((v, i) => {
    const w = `evaluations[${i}] (${v.evaluation_id})`
    if (!RESULTS.has(v.result)) add(detFile, `${w}.result`, `알 수 없는 판정(${v.result})이에요.`)
    v.asset_ids?.forEach(x => { if (!assets.has(x)) add(detFile, `${w}.asset_ids`, `가리키는 자산이 없어요: ${x}`) })
    v.relation_ids?.forEach(x => { if (!rels.has(x)) add(detFile, `${w}.relation_ids`, `가리키는 관계가 없어요: ${x}`) })
    v.evidence_refs?.forEach(x => { if (!evs.has(x)) add(detFile, `${w}.evidence_refs`, `가리키는 근거가 없어요: ${x}`) })
  })
  uniq(d.alerts, a => a.alert_id, detFile, 'alerts')
  d.alerts.forEach((a, i) => {
    const w = `alerts[${i}] (${a.alert_id})`
    const v = evalRule.get(a.evaluation_id)
    if (!evals.has(a.evaluation_id) || !v) add(detFile, `${w}.evaluation_id`, `가리키는 평가가 없어요: ${a.evaluation_id}`)
    else if (v.result !== 'detected') add(detFile, `${w}.evaluation_id`, '위협이 아닌 평가에서 경고가 나왔어요.')
    if (!a.asset_ids?.length) add(detFile, `${w}.asset_ids`, '경고 대상 자산이 없어요.')
    a.asset_ids?.forEach(x => { if (!assets.has(x)) add(detFile, `${w}.asset_ids`, `가리키는 자산이 없어요: ${x}`) })
  })
  return errs
}
