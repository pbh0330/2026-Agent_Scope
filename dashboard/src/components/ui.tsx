import {
  Boxes, Command, Database, FileText, KeyRound, Puzzle, Server, ShieldCheck, Sparkles, TerminalSquare, Waypoints,
} from 'lucide-react'
import type { ReactNode } from 'react'
import type { Asset, AssetType } from '../types/contracts'
import { RESULT_LABEL, STATUS_LABEL, type SecurityStatus, type Tri } from '../data/model'

export function TypeIcon({ type, subtype, size = 15 }: { type: AssetType; subtype?: string; size?: number }) {
  const p = { size, strokeWidth: 1.8 }
  switch (type) {
    case 'gateway': return <Command {...p} />
    case 'node': return <Waypoints {...p} />
    case 'mcp_server': return <Server {...p} />
    case 'tool': return <TerminalSquare {...p} />
    case 'resource_prompt': return subtype === 'prompt' ? <FileText {...p} /> : <Database {...p} />
    case 'skill': return <Sparkles {...p} />
    case 'plugin': return <Puzzle {...p} />
    case 'permission_auth': return subtype === 'authentication' ? <KeyRound {...p} /> : <ShieldCheck {...p} />
    default: return <Boxes {...p} />
  }
}

export function Glyph({ asset, small }: { asset: Asset; small?: boolean }) {
  return <span className={`glyph${small ? ' sm' : ''}`} aria-hidden><TypeIcon type={asset.asset_type} subtype={asset.asset_subtype} size={small ? 14 : 17} /></span>
}

export function Sev({ status }: { status: SecurityStatus | 'medium' }) {
  const label = status === 'medium' ? '보통' : STATUS_LABEL[status]
  return <span className={`sev ${status}`}>{label}</span>
}

export function SeverityTag({ severity }: { severity: string }) {
  const map: Record<string, ['high' | 'medium', string]> = {
    critical: ['high', '심각'], high: ['high', '높음'], medium: ['medium', '보통'], low: ['medium', '낮음'], info: ['medium', '정보'],
  }
  const [cls, label] = map[severity] ?? ['medium', severity]
  return <span className={`sev ${cls}`}>{label}</span>
}

export function TriMark({ value, yes = '예', no = '아니오', unk = '확인 못함', na = '해당 없음' }: { value: Tri; yes?: string; no?: string; unk?: string; na?: string }) {
  const cls = value === true ? 'yes' : value === false ? 'no' : value === null ? 'unk' : 'na'
  const label = value === true ? yes : value === false ? no : value === null ? unk : na
  return <span className={`tri ${cls}`}><i aria-hidden />{label}</span>
}

export function ResultMark({ result }: { result: string }) {
  const cls = result === 'detected' ? 'high' : result === 'not_detected' ? 'normal' : result === 'not_applicable' ? 'none' : 'unknown'
  return <span className={`sev ${cls}`}>{RESULT_LABEL[result] ?? result}</span>
}

export function Scn({ id }: { id: string }) {
  return <span className="scn">{id}</span>
}

export function Panel({ title, note, action, children, pad = true, className = '' }: {
  title?: ReactNode; note?: ReactNode; action?: ReactNode; children: ReactNode; pad?: boolean; className?: string
}) {
  return (
    <section className={`panel ${pad ? 'panel-pad' : ''} ${className}`}>
      {(title || action) && (
        <div className="panel-head">
          <div>{title && <h2>{title}</h2>}{note && <p>{note}</p>}</div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function BrandMark({ size = 30 }: { size?: number }) {
  // 측량 표식: 자산을 찾는 조준선 + 노출된 도구 눈금
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect x="1.5" y="1.5" width="29" height="29" rx="5" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="16" cy="16" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M16 3.5v6M16 22.5v6M3.5 16h6M22.5 16h6" stroke="currentColor" strokeWidth="2" />
      <circle cx="16" cy="16" r="2.4" fill="currentColor" />
    </svg>
  )
}
