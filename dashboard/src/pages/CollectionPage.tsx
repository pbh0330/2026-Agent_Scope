import { Fragment } from 'react'
import type { Model } from '../data/model'
import { fmtTime } from '../data/model'
import type { Manifest } from '../types/contracts'
import { Panel } from '../components/ui'

const STATUS: Record<string, [string, string]> = {
  success: ['normal', '성공'], partial: ['warning', '부분'], failed: ['high', '실패'], not_attempted: ['unknown', '미수행'],
}
const SCOPE: Record<string, string> = {
  gateway_config: 'Gateway 설정', node_config: 'Node 설정', gateway_identity: 'Gateway 식별', node_identity: 'Node 식별',
  gateway_pairing: '페어링 기록', plugin_manifest: '플러그인 manifest', skill_files: '스킬 파일', tools_list: '도구 목록',
  resources_list: '리소스 목록', resource_templates_list: '템플릿 목록', prompts_list: '프롬프트 목록', agent_exposure: '에이전트 노출',
  adapter_supplement: '어댑터 보강',
}

export function CollectionPage({ model, manifest, onSelect }: { model: Model; manifest: Manifest; onSelect: (id: string) => void }) {
  const s = model.snapshot
  const qa = model.bundle.qa
  const expo = qa?.checks.filter(c => c.condition_id === 'EXPOSED') ?? []
  return (
    <>
      <div className="grid-2" style={{ marginBottom: 18 }}>
        <Panel title="이 데이터가 나온 곳">
          <dl className="kv">
            {Object.entries(manifest.sources).filter(([, v]) => v).map(([k, v]) => (
              <Fragment key={k}><dt>{{ scanner: '자산 스캐너', testbed: '테스트베드', threat_rules: '탐지 규칙', schema: '공통 스키마', usage: '토큰 수집기' }[k] ?? k}</dt><dd>{v}</dd></Fragment>
            ))}
            <dt>스냅샷 ID</dt><dd><code>{s.snapshot_id}</code></dd>
            <dt>스캔 시각</dt><dd>{fmtTime(s.scan.started_at)}</dd>
            <dt>스키마</dt><dd>{s.schema_version}</dd>
          </dl>
        </Panel>
        {qa ? (
          <Panel title="정답 목록 비교" note={`${qa.ground_truth_id}, ${qa.ground_truth_version}`}>
            {qa.metrics.map(m => (
              <div className="meter" key={m.name}>
                <span>{m.name === 'declared_asset_recall' ? '선언 자산 수집률' : m.name === 'advertised_asset_recall' ? '광고 자산 수집률' : '관계 일치율'}</span>
                <b>{m.value !== null ? `${Math.round(m.value * 100)}%` : '—'} <span className="muted small">{m.numerator}/{m.denominator}</span></b>
                <div className="track-bar"><span style={{ width: `${(m.value ?? 0) * 100}%` }} /></div>
              </div>
            ))}
            <p className="small" style={{ marginTop: 8 }}>노출 판정 일치 {expo.filter(c => c.result === 'PASS').length} / {expo.length}</p>
            {qa.missing_relations.length > 0 && (
              <p className="small muted" style={{ marginTop: 6 }}>정답에만 있는 관계: {qa.missing_relations.map(r => `${r.type} ${r.source} → ${r.target}`).join(', ')}</p>
            )}
            <p className="tiny muted" style={{ marginTop: 6 }}>{qa.limitations.join(' ')}</p>
          </Panel>
        ) : (
          <Panel title="정답 목록 비교"><p className="small muted">위험 구성에는 정답 목록이 없습니다.</p></Panel>
        )}
      </div>
      <Panel title="수집 작업" note="대상과 범위별로 성공·부분·미수행을 나눠 기록합니다. 빈 목록과 수집 실패를 구분합니다" pad={false}>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>범위</th><th>대상</th><th>상태</th><th>방식</th><th>MCP 버전</th><th>내용</th></tr></thead>
            <tbody>
              {s.collection_results.map(c => {
                const t = c.target_ref ? model.byId.get(c.target_ref) : undefined
                const [cls, label] = STATUS[c.status]
                return (
                  <tr key={c.collection_id} onClick={() => t && onSelect(t.asset_id)} style={{ cursor: t ? 'pointer' : 'default' }}>
                    <td className="name">{SCOPE[c.scope] ?? c.scope}</td>
                    <td className="small">{t?.name ?? <span className="muted">파일 단위</span>}</td>
                    <td><span className={`sev ${cls}`}>{label}</span></td>
                    <td className="small muted">{c.mode}</td>
                    <td className="small">{c.protocol_version ?? '—'}</td>
                    <td className="small muted">
                      {c.details?.reported_count !== undefined && c.details.reported_count !== null && <>항목 {c.details.reported_count}개. </>}
                      {c.details?.capabilities_not_advertised?.length ? <>미광고 {c.details.capabilities_not_advertised.join(', ')}. </> : null}
                      {c.reason}
                      {c.details?.synthetic && <span className="tag risk" style={{ marginLeft: 6 }}>합성 원본</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  )
}
