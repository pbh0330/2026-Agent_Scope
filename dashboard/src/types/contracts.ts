// 공통 스키마 v0.6.0-draft (docs/mcp-attack-surface-definition/schema-design-draft.md) 중
// 대시보드가 읽는 필드만 옮긴 타입. 생산자가 필드를 추가해도 깨지지 않도록 선택 필드를 넉넉히 둔다.

export type AssetType =
  | 'gateway' | 'node' | 'mcp_server' | 'tool' | 'resource_prompt' | 'skill' | 'plugin' | 'permission_auth'

export type StateName = 'DECLARED' | 'DISCOVERED' | 'EXPOSED' | 'POTENTIALLY_CALLABLE' | 'CALLABLE' | 'USED'

export interface TargetRef { kind: string; asset_ref?: string; profile_id?: string; agent_key?: string; gateway_ref?: string }

export interface StateAssessment {
  state: StateName
  value: boolean | null
  evidence_refs: string[]
  reason?: string
  subject_ref?: TargetRef
  policy_ref?: string
  inference_rule?: string
}

export interface CredentialRef {
  reference_id: string | null
  namespace: string
  source_field: string
  kind: string
  presence: boolean | null
  evidence_refs: string[]
  reason?: string
}

export interface PermissionAuth {
  source_ref: string
  source_field: string
  target_refs: string[]
  assessment_status: string
  effect?: string
  patterns?: string[]
  credential_refs?: CredentialRef[]
  access_scope?: Record<string, unknown>
  reason?: string
}

export interface Asset {
  asset_id: string
  asset_type: AssetType
  asset_subtype?: string
  name: string
  owner_ref?: string
  context: { profile_id: string; gateway_ref?: string; host?: string }
  evidence_refs: string[]
  mcp?: { protocol_version: string | null; version_note?: string; definition?: Record<string, any>; discovery?: Record<string, any> }
  product?: { name: string; source_ref: string; config_path: string; config?: Record<string, any> }
  project: {
    canonical_key?: string
    state_assessments: StateAssessment[]
    permission_auth?: PermissionAuth
    credential_refs?: CredentialRef[]
    supply_chain?: Record<string, any>
    description?: string
    declared_by?: string
    transport?: string | null
    [k: string]: any
  }
}

export interface Relation {
  relation_id: string
  relation_type: string
  source_asset_ref: string
  target: TargetRef
  evidence_refs: string[]
  confidence: 'confirmed' | 'high' | 'medium' | 'low'
  basis_kind?: string
  inference_rule?: string
}

export interface Evidence {
  evidence_id: string
  evidence_type: string
  source_ref: string
  observed_at: string
  collection_ref: string
  redaction_status: string
  field_path?: string
  redacted_fields?: string[]
  note?: string
}

export interface CollectionResult {
  collection_id: string
  source_ref: string
  scope: string
  target_ref: string | null
  mode: string
  status: 'success' | 'partial' | 'failed' | 'not_attempted'
  collected_at: string
  reason?: string
  protocol_version?: string | null
  auth_context_ref?: string | null
  details?: Record<string, any>
}

export interface InventorySnapshot {
  schema_version: string
  snapshot_id: string
  environment_id: string
  profile_id: string
  context: { gateway_ref?: string }
  environment: { openclaw_version: string | null; openclaw_commit: string | null; version_note?: string }
  producer: { name: string; version: string; upstream?: { name: string; version: string }[] }
  generated_at: string
  scan: { started_at: string; finished_at: string; status: 'success' | 'partial' | 'failed' }
  testbed_context?: {
    configuration_id?: string; scenario_id?: string | null; vm_snapshot_label?: string | null
    label?: string; kind?: string; captured_at?: string; notes?: string[]
  }
  assets: Asset[]
  relations: Relation[]
  evidence: Evidence[]
  collection_results: CollectionResult[]
}

export type EvalResult = 'detected' | 'not_detected' | 'unknown' | 'not_applicable' | 'not_evaluated' | 'error'

export interface DetectionEvaluation {
  evaluation_id: string
  scenario_id: string
  rule_id: string
  rule_version: string
  rule_name?: string
  asset_ids: string[]
  relation_ids: string[]
  evidence_refs: string[]
  policy_refs: { id: string; version: string; source_ref: string }[]
  result: EvalResult
  reason: string
  evaluated_at: string
  details?: Record<string, any>
}

export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical'

export interface SecurityAlert {
  alert_id: string
  evaluation_id: string
  finding_key: string
  scenario_id: string
  rule_id: string
  rule_version: string
  severity: Severity
  confidence: 'high' | 'medium' | 'low'
  title?: string
  message: string
  asset_ids: string[]
  relation_ids: string[]
  evidence_refs: string[]
  detected_at: string
  recommendation?: string
}

export interface DetectionReport {
  schema_version: string
  report_id: string
  snapshot_id: string
  generated_at: string
  ruleset: { id: string; version: string }
  evaluations: DetectionEvaluation[]
  alerts: SecurityAlert[]
}

export interface SnapshotDiff {
  diff_id: string
  previous_snapshot_id: string
  current_snapshot_id: string
  comparison_status: 'complete' | 'partial' | 'not_comparable'
  changes: { asset_id: string; change_type: string; changed_fields: string[]; reason: string; previous?: { name: string; asset_type: string } }[]
  relation_changes: { relation_id: string; change_type: string; reason: string; previous?: { relation_type: string } }[]
  alert_changes: { finding_key: string; change_type: string; previous_alert_id: string | null; current_alert_id: string | null; reason: string }[]
  limitations: string[]
}

export interface UsageRecord {
  usage_id: string
  trace_id: string
  run_id: string
  tool_name: string
  tool_source: string
  asset_ref: string | null
  mapping_status: 'matched' | 'ambiguous' | 'unmatched'
  mapping_reason: string
  pattern: 'sequential' | 'parallel' | 'batch' | 'unattributed'
  duration_ms: number | null
  approx_input_tokens: number | null
  negative_delta: boolean
  model: string | null
  provider: string | null
  attribution_method: string
  estimated_cost_usd: number | null
  pricing: { source: string; version: string | null; currency: string; input_per_million: number | null }
  note: string
}

export interface UsageReport {
  usage_report_id: string
  environment_id: string
  profile_id: string
  generated_at: string
  producer: { name: string; version: string }
  window: { start: string; end: string }
  inventory_snapshot_id: string | null
  records: UsageRecord[]
  limitations: string[]
}

export interface QAResult {
  ground_truth_id: string
  ground_truth_version: string
  metrics: { name: string; scope: string; numerator: number; denominator: number; value: number | null }[]
  checks: { check_id: string; condition_id: string; result: 'PASS' | 'FAIL' | 'PARTIAL'; expected: any; actual: any; reason: string }[]
  id_mappings: { gt_asset_id: string; asset_id: string | null; asset_type: string; layer: string; status: string }[]
  extra_assets: { asset_id: string; canonical_key: string; asset_type: string }[]
  missing_relations: { type: string; source: string; target: string }[]
  limitations: string[]
}

export interface OpenClawAudit {
  ts: number
  summary: Record<string, number>
  findings: { checkId: string; severity: string; title: string; detail: string; remediation?: string }[]
}

export interface ManifestSnapshot {
  key: string
  label: string
  kind: 'normal' | 'scenario' | 'imported'
  scenario_id: string | null
  synthetic: boolean
  test_case_ids?: string[]
  snapshot_id: string
  files: { snapshot: string; detections: string; audit?: string; qa?: string; expected?: string }
  counts: { assets: number; relations: number; alerts: number }
  expected?: { verdict: 'PASS' | 'PARTIAL' | 'FAIL'; counts: Record<string, number> }
}

// ---- 기대 결과 대조 (docs/threat-scenarios expected-results.md ↔ detections, QAResult 16.2 checks 형식) ----
export type ExpectedKind = 'required' | 'optional' | 'no_alert' | 'unknown' | 'extra'
export interface ExpectedCheck {
  check_id: string
  kind: ExpectedKind
  condition_id: string | null
  scenario_id: string
  target: string | null
  asset_id: string | null
  result: 'PASS' | 'PARTIAL' | 'FAIL' | 'SKIP' | 'INFO'
  expected: Record<string, any>
  actual: Record<string, any>
  evidence_refs: string[]
  reason: string
}
export interface ExpectedReport {
  qa_run_id: string
  snapshot_id: string
  expected_profile: string
  expected_source: string
  expected_version: string
  generated_at: string
  detection_report_id: string
  verdict: 'PASS' | 'PARTIAL' | 'FAIL'
  checks: ExpectedCheck[]
  metrics: { name: string; scope: string; numerator: number; denominator: number; value: number | null }[]
  limitations: string[]
}
export interface ScenarioCatalog {
  catalog_id: string
  catalog_version: string
  scenarios: { scenario_id: string; name: string; priority: number; conditions: { condition_id: string; name: string; severity: string | null; confidence: string | null }[] }[]
}

export interface Manifest {
  generated_at: string
  environment_id: string
  sources: Record<string, string | null>
  snapshots: ManifestSnapshot[]
  diffs: { from: string; to: string; file: string; counts: Record<string, number> }[]
  usage: { file: string; source: string; linked_snapshot: string | null; note: string } | null
  expected?: { source: string; version: string; profiles: string[] }
  usage_api?: { dir: string; api_base: string; captured_at: string; mode: string | null; sources: string[] | null
    records: number | null; inventory_snapshot_id: string | null; source: string }
}

// ---- 사용 현황 API (token-collector/backend/usageapi, agentscope-usage-api) ----
// 응답 모양은 usageapi README 기준. 모든 값은 추정치(estimated: true)이며 청구 금액이 아니다.
export interface UsageWindow { start: string; end: string }
export type UsageMethod = 'sequential' | 'allocated' | 'not_computed'
export type UsagePattern = 'sequential' | 'parallel' | 'batch' | 'unattributed'

export interface UsageHealth {
  status: 'ok' | 'degraded' | 'loading'
  mode: 'fixed' | 'live'
  data_window: UsageWindow | null
  records: number
  brake_events: number | null
  sources: string[]
  loaded_at: string
  last_error: string | null
  inventory_snapshot_id: string | null
  missing_counts: number
  limitations?: string[]
}

export interface UsageSummary {
  window: UsageWindow
  estimated: true
  calls: number
  attributed_tokens: number
  estimated_cost_usd: number | null
  pricing: { currency: string; sources: string[] }
  by_method: { sequential: { calls: number; tokens: number }; allocated: { calls: number; tokens: number }; not_computed: { calls: number } }
  by_mapping: { matched: number; ambiguous: number; unmatched: number }
  data_quality: { missing_counts: number; not_computed: number; negative_delta: number; calls_without_cost: number; inventory_snapshot_id: string | null }
}

export interface UsageItem {
  key: string
  label: string
  asset_id: string | null
  asset_type: string | null
  mapping_status: 'matched' | 'ambiguous' | 'unmatched' | null
  tool_source?: string
  mcp_server?: string | null
  calls: number
  calls_not_computed: number
  tokens: number
  tokens_sequential: number
  tokens_allocated: number
  estimated_cost_usd: number | null
  share: number
  relative: number
  last_used_at: string | null
  last_trace_id: string | null
}
export interface UsageByAsset { window: UsageWindow; group: 'asset' | 'tool' | 'server' | 'pattern'; total_tokens: number; inventory_snapshot_id: string | null; items: UsageItem[] }

export interface UsageApiRecord {
  usage_id: string
  time: string
  tool_name: string
  tool_source: string
  mcp_server: string | null
  asset_id: string | null
  mapping_status: string
  pattern: UsagePattern
  method: UsageMethod
  attribution_method: string
  tokens: number | null
  estimated_cost_usd: number | null
  duration_ms: number | null
  model: string | null
  trace_id: string | null
  tool_call_id?: string | null
}
export interface UsageRecords { window: UsageWindow; total: number; next_cursor: string | null; items: UsageApiRecord[] }

export interface UsagePoint { t: string; tokens: number; calls: number }
export interface UsageTimeseries { window: UsageWindow; group: string; step: string; total: { key: string; tokens: number; points: UsagePoint[] }; series: { key: string; label: string; tokens: number; points: UsagePoint[] }[] }

export interface BrakeEventItem {
  time: string
  level: 'warn' | 'approve' | 'block'
  mode: string
  enforced: boolean
  tool_name: string
  reasons: { scope: string; metric: string; value: number; limit: number }[]
  run_usage: { result_bytes: number; counted_tokens: number; tool_calls: number; same_tool_streak: number } | null
  resolution: { decision: string; time: string } | null
  trace_id: string | null
}
export interface BrakeEvents { window: UsageWindow; available: boolean; by_level: Record<'warn' | 'approve' | 'block', number>; total: number; items: BrakeEventItem[]; next_cursor: string | null }
