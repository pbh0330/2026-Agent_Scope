import { useState, type ReactNode } from 'react'

/** 도넛 차트 — 유형 구성 */
export function Donut({ data, size = 168, thickness = 22, center }: {
  data: { label: string; value: number; color: string }[]; size?: number; thickness?: number; center?: ReactNode
}) {
  const [hover, setHover] = useState<number | null>(null)
  const total = data.reduce((n, d) => n + d.value, 0) || 1
  const r = (size - thickness) / 2
  const c = 2 * Math.PI * r
  const gap = data.filter(d => d.value > 0).length > 1 ? 2.5 : 0
  let acc = 0
  return (
    <div className="donut" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label="유형별 구성 도넛 차트">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--sunken)" strokeWidth={thickness} />
        {data.map((d, i) => {
          if (!d.value) return null
          const len = (d.value / total) * c
          const seg = (
            <circle key={d.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={d.color}
              strokeWidth={hover === i ? thickness + 6 : thickness} strokeLinecap="butt"
              strokeDasharray={`${Math.max(len - gap, 0.5)} ${c}`} strokeDashoffset={-acc}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} style={{ transition: 'stroke-width .15s' }}>
              <title>{`${d.label} ${d.value}`}</title>
            </circle>
          )
          acc += len
          return seg
        })}
      </svg>
      <div className="donut-center">
        {hover !== null ? <><b>{data[hover].value}</b><span>{data[hover].label}</span></> : center}
      </div>
    </div>
  )
}

/** 원형 게이지 — 진행률 */
export function Ring({ value, label, color, sub, size = 92 }: { value: number | null; label: string; color: string; sub?: string; size?: number }) {
  const stroke = 8
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value))
  return (
    <div className="ring">
      <div className="ring-svg" style={{ width: size, height: size }}>
        <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--sunken)" strokeWidth={stroke} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
            strokeDasharray={`${pct * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        </svg>
        <span className="ring-val" style={{ color }}>{value === null ? '—' : `${Math.round(pct * 100)}`}<small>%</small></span>
      </div>
      <b>{label}</b>
      {sub && <span className="ring-sub">{sub}</span>}
    </div>
  )
}

/** 묶음 막대 — 서버별 광고·노출 도구 수 */
export function GroupedBars({ groups, series }: {
  groups: { label: string; values: number[]; note?: string }[]
  series: { name: string; color: string }[]
}) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 640, H = 240, padL = 34, padB = 34, padT = 12, padR = 8
  const max = Math.max(1, ...groups.flatMap(g => g.values))
  const step = max <= 5 ? 1 : max <= 20 ? 5 : 10
  const top = Math.ceil(max / step) * step
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step)
  const plotW = W - padL - padR
  const plotH = H - padT - padB
  const gw = plotW / Math.max(groups.length, 1)
  const bw = Math.min(26, (gw * 0.62) / series.length)
  const y = (v: number) => padT + plotH - (v / top) * plotH
  return (
    <div className="bars">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="서버별 도구 수 막대 그래프" preserveAspectRatio="xMidYMid meet">
        <defs>
          {series.map((s, i) => (
            <linearGradient key={i} id={`bar-g${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity="1" />
              <stop offset="100%" stopColor={s.color} stopOpacity=".55" />
            </linearGradient>
          ))}
        </defs>
        {ticks.map(t => (
          <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeDasharray={t ? '3 4' : undefined} />
            <text x={padL - 10} y={y(t) + 6} textAnchor="end" className="axis">{t.toLocaleString('ko-KR')}</text>
          </g>
        ))}
        {groups.map((g, gi) => {
          const cx = padL + gw * gi + gw / 2
          const start = cx - (bw * series.length + 4 * (series.length - 1)) / 2
          return (
            <g key={g.label} onMouseEnter={() => setHover(gi)} onMouseLeave={() => setHover(null)}>
              <rect x={padL + gw * gi} y={padT} width={gw} height={plotH} fill={hover === gi ? 'var(--hover-col)' : 'transparent'} rx="8" />
              {g.values.map((v, si) => {
                const h = Math.max(v ? 3 : 0, (v / top) * plotH)
                return <rect key={si} x={start + si * (bw + 4)} y={padT + plotH - h} width={bw} height={h} rx={Math.min(6, bw / 2)} fill={`url(#bar-g${si})`} />
              })}
              {gw >= 84 || !g.label.includes('-')
                ? <text x={cx} y={H - 12} textAnchor="middle" className="axis xl">{g.label}</text>
                : <text x={cx} y={H - 19} textAnchor="middle" className="axis xl">
                    <tspan x={cx}>{g.label.slice(0, g.label.indexOf('-'))}</tspan>
                    <tspan x={cx} dy="1.15em">{g.label.slice(g.label.indexOf('-'))}</tspan>
                  </text>}
            </g>
          )
        })}
      </svg>
      {hover !== null && (
        <div className="bars-tip" style={{ left: `${((padL + gw * hover + gw / 2) / W) * 100}%` }}>
          <b>{groups[hover].label}</b>
          {series.map((s, i) => <span key={s.name}><i style={{ background: s.color }} />{s.name} {groups[hover].values[i]}</span>)}
          {groups[hover].note && <em>{groups[hover].note}</em>}
        </div>
      )}
      <div className="legend">{series.map(s => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
    </div>
  )
}

/** 영역 차트 — 호출 순서별 값. null은 계산하지 않은 점(빈 원)으로 표시 */
export function AreaChart({ points, unit = '' }: { points: { label: string; value: number | null; note?: string }[]; unit?: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 1100, H = 300, padL = 80, padR = 40, padT = 20, padB = 40
  const vals = points.map(p => p.value ?? 0)
  const max = Math.max(1, ...vals)
  const raw = max / 5, mag = 10 ** Math.floor(Math.log10(raw))
  const step = Math.max(1, [1, 2, 5, 10].map(m => m * mag).find(s => s >= raw) ?? 10 * mag)
  const top = Math.ceil(max / step) * step
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step)
  const n = Math.max(points.length - 1, 1)
  // 가로축 글자는 최대 8개 정도만 쓴다(점이 많으면 글자가 겹친다). 값은 점에 마우스를 올려 본다.
  const every = Math.max(1, Math.ceil(points.length / 8))
  const x = (i: number) => padL + (i / n) * (W - padL - padR)
  const y = (v: number) => padT + (H - padT - padB) - (v / top) * (H - padT - padB)
  const known = points.map((p, i) => ({ ...p, i })).filter(p => p.value !== null)
  const line = known.map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(1)},${y(p.value!).toFixed(1)}`).join(' ')
  const area = known.length ? `${line} L${x(known[known.length - 1].i)},${y(0)} L${x(known[0].i)},${y(0)} Z` : ''
  return (
    <div className="area wide">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="호출 순서별 추정 입력 토큰 영역 차트">
        <defs>
          <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5B5FEF" stopOpacity=".3" />
            <stop offset="100%" stopColor="#5B5FEF" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="area-line" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#5B5FEF" />
            <stop offset="100%" stopColor="#8B6CF6" />
          </linearGradient>
        </defs>
        {ticks.map(t => (
          <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeDasharray={t ? '3 4' : undefined} />
            <text x={padL - 10} y={y(t) + 6} textAnchor="end" className="axis">{t.toLocaleString('ko-KR')}</text>
          </g>
        ))}
        {area && <path d={area} fill="url(#area-fill)" />}
        {line && <path d={line} fill="none" stroke="url(#area-line)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />}
        {points.map((p, i) => (
          <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={x(i) - (W / n) / 2} y={padT} width={W / n} height={H - padT - padB} fill="transparent" />
            <circle cx={x(i)} cy={y(p.value ?? 0)} r={hover === i ? 6 : 4}
              fill={p.value === null ? 'var(--surface)' : 'var(--surface)'} stroke={p.value === null ? 'var(--ink-3)' : 'var(--c1)'} strokeWidth="2"
              strokeDasharray={p.value === null ? '2 2' : undefined} />
            {(i % every === 0 || (i === points.length - 1 && i % every >= every / 2)) && <text x={x(i)} y={H - 8} textAnchor="middle" className="axis">{p.label}</text>}
          </g>
        ))}
      </svg>
      {hover !== null && (
        <div className="area-tip" style={{ left: `${(x(hover) / W) * 100}%` }}>
          <b>{points[hover].value === null ? '토큰 배분 안 함' : `${points[hover].value!.toLocaleString('ko-KR')}${unit}`}</b>
          {points[hover].note && <span>{points[hover].note}</span>}
        </div>
      )}
    </div>
  )
}

/** 꺾은선 — 구성별 보안 경고 수. 점을 누르면 그 구성으로 이동 */
export function ConfigLine({ points, onPick }: {
  points: { key: string; value: number; active: boolean }[]; onPick?: (key: string) => void
}) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 520, H = 230, padL = 30, padR = 14, padT = 44, padB = 40
  const max = Math.max(2, ...points.map(p => p.value))
  const step = max <= 6 ? 2 : max <= 15 ? 5 : 10
  const top = Math.ceil(max / step) * step
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step)
  const n = Math.max(points.length - 1, 1)
  const x = (i: number) => padL + 8 + (i / n) * (W - padL - padR - 16)
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / top)
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const area = points.length ? `${line} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z` : ''
  const focus = hover ?? points.findIndex(p => p.active)
  return (
    <div className="area">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="구성별 보안 경고 수 꺾은선 그래프">
        <defs>
          <linearGradient id="cfg-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5B5FEF" stopOpacity=".26" />
            <stop offset="100%" stopColor="#5B5FEF" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map(t => (
          <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={padL - 10} y={y(t) + 6} textAnchor="end" className="axis">{t.toLocaleString('ko-KR')}</text>
          </g>
        ))}
        {area && <path d={area} fill="url(#cfg-fill)" />}
        <path d={line} fill="none" stroke="var(--indigo)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => {
          const dash = p.key.indexOf('-')
          return (
            <g key={p.key} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => onPick?.(p.key)} style={{ cursor: onPick ? 'pointer' : undefined }}>
              <rect x={x(i) - (W / n) / 2} y={padT - 30} width={W / n} height={H - padT - padB + 60} fill="transparent" />
              <circle cx={x(i)} cy={y(p.value)} r={i === focus ? 6 : 4} fill={p.active ? 'var(--indigo)' : 'var(--surface)'} stroke="var(--indigo)" strokeWidth="2" />
              {dash < 0
                ? <text x={x(i)} y={H - 20} textAnchor="middle" className="axis" fontWeight={p.active ? 700 : 400}>{p.key}</text>
                : <text x={x(i)} y={H - 24} textAnchor="middle" className="axis" fontWeight={p.active ? 700 : 400}>
                    <tspan x={x(i)}>{p.key.slice(0, dash)}</tspan><tspan x={x(i)} dy="1.2em">{p.key.slice(dash)}</tspan>
                  </text>}
            </g>
          )
        })}
        {focus >= 0 && (() => {
          const p = points[focus], label = `${p.key} · ${p.value}`, w = label.length * 7.4 + 18
          const cx = Math.min(Math.max(x(focus), padL + w / 2), W - padR - w / 2)
          return <g pointerEvents="none">
            <rect x={cx - w / 2} y={y(p.value) - 38} width={w} height={26} rx="8" fill="var(--surface)" stroke="var(--line-strong)" />
            <text x={cx} y={y(p.value) - 20.5} textAnchor="middle" fontSize="12" fontWeight="800" fill="var(--ink)">{label}</text>
          </g>
        })()}
      </svg>
    </div>
  )
}
