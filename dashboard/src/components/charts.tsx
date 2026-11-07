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
            <text x={padL - 8} y={y(t) + 4} textAnchor="end" className="axis">{t}</text>
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
              <text x={cx} y={H - 12} textAnchor="middle" className="axis xl">{g.label}</text>
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
  const W = 1100, H = 280, padL = 44, padR = 16, padT = 16, padB = 32
  const vals = points.map(p => p.value ?? 0)
  const max = Math.max(1, ...vals)
  const step = max <= 50 ? 10 : max <= 200 ? 50 : max <= 500 ? 100 : 200
  const top = Math.ceil(max / step) * step
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step)
  const n = Math.max(points.length - 1, 1)
  const x = (i: number) => padL + (i / n) * (W - padL - padR)
  const y = (v: number) => padT + (H - padT - padB) - (v / top) * (H - padT - padB)
  const known = points.map((p, i) => ({ ...p, i })).filter(p => p.value !== null)
  const line = known.map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(1)},${y(p.value!).toFixed(1)}`).join(' ')
  const area = known.length ? `${line} L${x(known[known.length - 1].i)},${y(0)} L${x(known[0].i)},${y(0)} Z` : ''
  return (
    <div className="area">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="호출 순서별 추정 입력 토큰 영역 차트">
        <defs>
          <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--c5)" stopOpacity=".55" />
            <stop offset="100%" stopColor="var(--c1)" stopOpacity=".05" />
          </linearGradient>
          <linearGradient id="area-line" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--c1)" />
            <stop offset="100%" stopColor="var(--c5)" />
          </linearGradient>
        </defs>
        {ticks.map(t => (
          <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeDasharray={t ? '3 4' : undefined} />
            <text x={padL - 8} y={y(t) + 4} textAnchor="end" className="axis">{t}</text>
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
            <text x={x(i)} y={H - 10} textAnchor="middle" className="axis">{p.label}</text>
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
