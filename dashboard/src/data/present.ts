// 사용자 화면에 보이는 이름·문구를 만든다.
// 원칙
// - 설정에 적힌 이름(서버·플러그인·장치 이름)은 사용자가 임의로 붙인 값이라 뜻을 짐작하지 않는다.
//   화면에는 자산 종류 + 수집된 속성(연결 방식, 등록 경로, 승인 여부) + 번호로 부르고,
//   설정 이름은 '세부 정보 보기' 안에서만 보여 준다.
// - 판정 결과는 사용자 용어 세 가지로만 보여 준다: 위협 / 안전 / 확인 못 함.
import type { Asset, AssetType, DetectionEvaluation, SecurityAlert } from '../types/contracts'
import type { Model } from './model'

export const TYPE_KO: Record<AssetType, string> = {
  gateway: '게이트웨이', node: '노드', mcp_server: 'MCP 서버', tool: '도구', resource_prompt: '리소스·프롬프트',
  skill: '스킬', plugin: '플러그인', permission_auth: '권한·인증',
}
/** 자산 사이 관계. 화살표 방향은 저장된 관계의 source → target 그대로다. */
export const REL_KO: Record<string, string> = {
  ADVERTISES: '도구·리소스 제공', DECLARES: '설정에 등록', APPLIES_TO: '권한 적용', AUTHENTICATES: '접속 인증',
  ASSOCIATED_WITH: '함께 쓰임', PAIRED_WITH: '기기 연결',
}
export const TYPE_DESC: Record<AssetType, string> = {
  gateway: 'AI 에이전트가 실행되는 본체', node: '게이트웨이에 연결된 장치', mcp_server: '도구를 주는 서버', tool: '에이전트가 하는 일',
  resource_prompt: '서버가 주는 자료', skill: '작업 지침', plugin: '기능 추가 묶음', permission_auth: '토큰·접근 규칙',
}
export const TYPES_8: AssetType[] = ['gateway', 'node', 'mcp_server', 'tool', 'resource_prompt', 'skill', 'plugin', 'permission_auth']

/** 위협 시나리오: 사용자에게 보이는 이름과 무엇을 보는지 */
export const SCENARIO_KO: { id: string; name: string; what: string }[] = [
  { id: 'S1', name: '승인 안 된 서버', what: '서버·플러그인 승인 여부' },
  { id: 'S2', name: '도구 권한 과다', what: '에이전트에 보이는 도구 범위' },
  { id: 'S4', name: '토큰 공유', what: '서버끼리 같은 토큰 사용' },
  { id: 'S3', name: '도구 이름 겹침', what: '서로 다른 서버의 같은 도구 이름' },
  { id: 'S5', name: '약한 연결 보안', what: '암호화·인증서 확인' },
]

interface ThreatCopy { title: string; why: string; steps: string[]; phrase: (n: number) => string }

/** 판정 조건(S#-C#)별 사용자 문구. 조건 정의는 docs/threat-scenarios v2.1 */
export const THREAT_COPY: Record<string, ThreatCopy> = {
  'S1-C1': {
    title: '승인하지 않은 서버가 연결됐어요',
    why: '관리자가 승인한 목록에 없는 MCP 서버가 에이전트 설정에 들어 있어요. 에이전트가 이 서버의 도구를 바로 쓸 수 있어서, 누가 왜 넣었는지 모르면 정보가 밖으로 새거나 원치 않는 동작이 일어날 수 있어요.',
    steps: ['이 서버를 추가한 사람이 있는지 팀에 확인하세요.', '쓰지 않는 서버면 설정에서 지우세요.', '쓰는 서버면 승인 목록에 올리세요.'],
    phrase: n => `승인하지 않은 서버 ${n}개가 연결됐어요`,
  },
  'S1-C2': {
    title: '서버 주소가 바뀌었어요',
    why: '승인할 때와 다른 주소로 연결되고 있어요. 누군가 연결 대상을 바꿨다면 에이전트가 주고받는 내용이 다른 곳으로 갈 수 있어요.',
    steps: ['바뀐 주소가 맞는지 설정을 바꾼 사람에게 확인하세요.', '의도하지 않은 변경이면 승인된 주소로 되돌리세요.', '맞는 변경이면 승인 목록의 주소를 갱신하세요.'],
    phrase: n => `승인된 서버 ${n}개의 연결 설정이 바뀌었어요`,
  },
  'S1-C3': {
    title: '승인하지 않은 플러그인이 서버를 추가했어요',
    why: '승인 목록에 없는 플러그인이 MCP 서버를 함께 등록했어요. 플러그인을 설치하는 것만으로 에이전트가 쓸 수 있는 도구가 늘어나요.',
    steps: ['이 플러그인을 설치한 적이 있는지 확인하세요.', '필요 없으면 플러그인을 삭제하세요.', '필요하면 플러그인을 승인 목록에 올리세요.'],
    phrase: n => `승인하지 않은 플러그인이 서버 ${n}개를 추가했어요`,
  },
  'S1-C4': {
    title: '승인된 서버가 다른 곳에 등록됐어요',
    why: '승인할 때와 다른 장치나 다른 등록 경로에서 같은 서버가 선언됐어요. 설정이 옮겨지면서 승인 범위를 벗어났을 수 있어요.',
    steps: ['서버를 옮긴 이유가 있는지 확인하세요.', '의도한 변경이면 승인 목록의 등록 위치를 갱신하세요.', '아니면 원래 위치로 되돌리세요.'],
    phrase: n => `승인된 서버 ${n}개가 다른 곳에 등록됐어요`,
  },
  'S2-C1': {
    title: '막아 둔 도구가 에이전트에 열렸어요',
    why: '정책상 막아야 하는 도구가 에이전트에 보이고 있어요. 도구 필터가 지워지거나 약해지면 파일 쓰기나 환경 정보 읽기 같은 위험한 동작을 에이전트가 할 수 있어요.',
    steps: ['서버 설정의 도구 필터가 지워지거나 바뀌었는지 확인하세요.', '필요 없는 도구는 도구 필터로 다시 막으세요.'],
    phrase: n => `막아 둔 도구가 열린 서버 ${n}개`,
  },
  'S2-C2': {
    title: '파일 접근 범위가 너무 넓어요',
    why: '파일 서버가 작업 폴더보다 넓은 범위(예: 홈 폴더 전체)를 읽을 수 있어요. 개인 파일이나 설정 파일까지 에이전트에 보일 수 있어요.',
    steps: ['서버에 열어 둔 폴더를 작업 폴더로 줄이세요.', '꼭 필요한 폴더만 따로 추가하세요.'],
    phrase: n => `파일 접근 범위가 넓은 서버 ${n}개`,
  },
  'S2-C3': {
    title: '명령 실행이나 네트워크 요청 도구가 열려 있어요',
    why: '시스템 명령을 실행하거나 외부로 요청을 보내는 도구를 에이전트가 쓸 수 있어요. 잘못된 지시 하나로 장치를 바꾸거나 정보를 밖으로 보낼 수 있어요.',
    steps: ['이 도구가 꼭 필요한지 확인하세요.', '필요 없으면 도구 필터로 막으세요.'],
    phrase: n => `명령·네트워크 도구가 열린 서버 ${n}개`,
  },
  'S2-C4': {
    title: '비밀번호·토큰을 입력받는 도구가 열려 있어요',
    why: '비밀번호나 토큰 같은 인증 정보를 입력값으로 받는 도구가 에이전트에 보여요. 에이전트가 인증 정보를 다루게 되면 기록이나 다른 도구로 새어 나갈 수 있어요.',
    steps: ['이 도구가 꼭 필요한지 확인하세요.', '필요 없으면 도구 필터로 막으세요.'],
    phrase: n => `인증 정보를 받는 도구가 열린 서버 ${n}개`,
  },
  'S3-C1': {
    title: '서로 다른 서버에 같은 이름의 도구가 있어요',
    why: '이름은 같은데 하는 일이 달라요. 에이전트가 엉뚱한 서버의 도구를 부를 수 있어요.',
    steps: ['두 도구 중 필요 없는 쪽을 도구 필터로 막으세요.', '둘 다 필요하면 서버 쪽에서 도구 이름을 구분되게 바꾸세요.'],
    phrase: n => `이름이 겹치는 도구 ${n}건`,
  },
  'S3-C2': {
    title: '같은 도구가 두 서버에 겹쳐 있어요',
    why: '하는 일은 같지만, 에이전트의 요청이 어느 서버로 갈지 정해져 있지 않아요.',
    steps: ['둘 중 한 서버의 도구를 도구 필터로 막으세요.'],
    phrase: n => `겹쳐 있는 도구 ${n}건`,
  },
  'S4-C1': {
    title: '서버 여러 개가 같은 토큰을 써요',
    why: '하나의 인증 토큰을 여러 서버가 같이 쓰고 있어요. 한 서버에서 토큰이 새면 다른 서버까지 함께 뚫려요.',
    steps: ['서버마다 따로 토큰을 발급하세요.', '함께 쓰던 토큰은 교체하세요.'],
    phrase: n => `같은 토큰을 쓰는 곳 ${n}건`,
  },
  'S4-C3': {
    title: '토큰이 바뀐 주소로 보내지고 있어요',
    why: '인증 토큰이 승인되지 않은 주소로 함께 전송돼요. 그 주소가 다른 사람의 서버라면 토큰이 그대로 넘어가요.',
    steps: ['서버 주소가 왜 바뀌었는지 먼저 확인하세요.', '의도하지 않은 변경이면 토큰을 바로 새로 발급하세요.', '주소를 승인된 곳으로 되돌리세요.'],
    phrase: n => `토큰 ${n}개가 바뀐 주소로 보내지고 있어요`,
  },
  'S5-C1': {
    title: '암호화되지 않은 연결이에요',
    why: 'http로 연결돼서 주고받는 내용과 인증 토큰이 그대로 보일 수 있어요.',
    steps: ['서버 주소를 https로 바꾸세요.'],
    phrase: n => `암호화되지 않은 연결 ${n}개`,
  },
  'S5-C2': {
    title: '인증서 확인을 꺼 뒀어요',
    why: '연결 상대가 진짜 서버인지 확인하지 않아요. 중간에서 가로채는 공격을 막을 수 없어요.',
    steps: ['설정에서 인증서 확인을 다시 켜세요.', '테스트용으로 껐다면 운영 환경에서는 꼭 켜세요.'],
    phrase: n => `인증서 확인을 끈 연결 ${n}개`,
  },
}

/** '확인 못 함'의 이유. 조건별로 사람이 읽는 문장 */
export const UNKNOWN_REASON: Record<string, string> = {
  'S1-C0': '승인 목록이 없어서 서버가 승인됐는지 판단할 수 없어요.',
  'S2-C0': '서버의 도구 목록을 받지 못했거나 비교할 정책이 없어서 판단할 수 없어요.',
  'S3-C3': '한쪽 서버의 도구 정의를 받지 못해서 같은 도구인지 판단할 수 없어요.',
  'S4-C2': '토큰 값은 보안상 읽지 않아서, 이름이 같은 두 토큰이 같은 토큰인지 알 수 없어요.',
  'S4-C4': '토큰이 가진 권한 범위는 설정 파일만으로는 알 수 없어요.',
  'S5-C3': 'https 연결인데 인증서 확인 설정이 적혀 있지 않아요. 프로그램 기본값에 따라 달라져요.',
  'S5-C4': '서버 인증서가 진짜 그 서버 것인지는 실제로 연결해 봐야 알 수 있어요.',
  'S5-C5': '보안 설정이 어떤 연결까지 적용되는지는 실행 중인 동작을 봐야 알 수 있어요.',
  'S4-C1': '설정에 인증 토큰이 하나도 없어서 공유 여부를 따질 대상이 없어요.',
}

/** 같은 조건이라도 자산 성격에 맞게 문구를 고른다. 로컬 실행 서버는 '주소'가 아니라 '실행 설정'이 바뀐다 */
export function copyForAsset(ruleId: string, a?: Asset): ThreatCopy {
  const c = copyFor(ruleId)
  if (ruleId === 'S1-C2' && a?.asset_type === 'mcp_server' && (a.project.transport ?? 'stdio') === 'stdio') {
    return {
      ...c,
      title: '서버 실행 설정이 바뀌었어요',
      why: '승인할 때와 다른 실행 명령이나 인자로 서버가 실행되고 있어요. 다른 프로그램이 실행되거나 서버가 열어 두는 범위가 달라졌을 수 있어요.',
      steps: ['바뀐 실행 설정이 맞는지 설정을 바꾼 사람에게 확인하세요.', '의도하지 않은 변경이면 승인된 설정으로 되돌리세요.', '맞는 변경이면 승인 목록을 갱신하세요.'],
    }
  }
  return c
}

export function copyFor(ruleId: string): ThreatCopy {
  return THREAT_COPY[ruleId] ?? {
    title: '확인이 필요한 위협이 있어요', why: '자동 점검에서 위협 조건에 맞는 설정이 발견됐어요.',
    steps: ['세부 정보를 보고 설정을 확인하세요.'], phrase: (n: number) => `확인이 필요한 위협 ${n}건`,
  }
}
export function reasonFor(ev: DetectionEvaluation): string {
  return UNKNOWN_REASON[ev.rule_id] ?? (ev.result === 'not_evaluated' ? '이번 점검에서는 검사하지 않은 항목이에요.' : '정보가 부족해 판단하지 못했어요.')
}

export const SEVERITY_KO: Record<string, string> = { critical: '매우 높음', high: '높음', medium: '보통', low: '낮음', info: '참고' }
const SEV_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }
export const bySeverity = (a: SecurityAlert, b: SecurityAlert) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9)

/** 판정 결과를 사용자 용어로 */
export type Verdict = 'threat' | 'safe' | 'unknown'
/** 판단할 정보가 없어서 결론을 못 낸 것 */
export const isUnknown = (r: string) => r === 'unknown' || r === 'error'
/** 이번 버전에서 아예 검사하지 않는 조건(어느 환경에서나 같음). 사용자 판정 수에 넣지 않는다 */
export const isOutOfScope = (r: string) => r === 'not_evaluated'

// ── 이름 붙이기 ────────────────────────────────────────────────

export interface Present {
  name: (a: Asset) => string
  /** 서버·플러그인 한 줄 설명: 등록 경로 · 승인 여부 */
  sub: (a: Asset) => string
  approval: (a: Asset) => '승인됨' | '승인 안 됨' | '주소 바뀜' | '등록 위치 바뀜' | '승인 확인 못 함' | null
  where: (a: Asset) => string
  /** 자산이 놓인 게이트웨이/노드 */
  hostAsset: (a: Asset) => Asset | undefined
  /** 플러그인이 추가한 서버라면 그 플러그인 */
  addedBy: (a: Asset) => Asset | undefined
  servers: Asset[]
}

const isLocal = (a: Asset) => (a.project.transport ?? 'stdio') === 'stdio'

/** 받침에 맞는 조사: 숫자로 끝나는 이름(플러그인 2)도 읽는 소리 기준으로 고른다 */
export function josa(word: string, withFinal: string, withoutFinal: string): string {
  const last = word.trim().slice(-1)
  if (/[0-9]/.test(last)) return '2459'.includes(last) ? withoutFinal : withFinal
  const code = last.charCodeAt(0) - 0xac00
  if (code < 0 || code > 11171) return withFinal
  return code % 28 ? withFinal : withoutFinal
}

export function makePresent(m: Model): Present {
  const hosts = [...m.ofType('gateway'), ...m.ofType('node')]
  const hostByName = new Map(hosts.map(h => [h.name, h]))
  const hostAsset = (a: Asset) => {
    if (a.asset_type === 'gateway' || a.asset_type === 'node') return a
    const h = m.host(a)
    return hostByName.get(h)
  }
  const hostRank = (a: Asset) => { const h = hostAsset(a); return h?.asset_type === 'gateway' ? 0 : h ? 1 : 2 }
  const addedBy = (a: Asset) => {
    if (a.asset_type !== 'mcp_server' || a.project.declared_by !== 'plugin') return undefined
    const rel = (m.inn.get(a.asset_id) ?? []).find(r => r.relation_type === 'ASSOCIATED_WITH' && m.byId.get(r.source_asset_ref)?.asset_type === 'plugin')
    return rel ? m.byId.get(rel.source_asset_ref) : undefined
  }
  const declRank = (a: Asset) => a.project.declared_by === 'plugin' ? 1 : 0
  const servers = m.ofType('mcp_server').slice().sort((a, b) => hostRank(a) - hostRank(b) || declRank(a) - declRank(b))
  const names = new Map<string, string>()
  let local = 0, remote = 0
  for (const s of servers) names.set(s.asset_id, isLocal(s) ? `로컬 MCP 서버 ${++local}` : `원격 MCP 서버 ${++remote}`)
  const numbered = (t: AssetType, label: string) => {
    const list = m.ofType(t).slice().sort((a, b) => hostRank(a) - hostRank(b))
    list.forEach((a, i) => names.set(a.asset_id, list.length > 1 ? `${label} ${i + 1}` : label))
  }
  numbered('gateway', '게이트웨이'); numbered('node', '노드'); numbered('plugin', '플러그인'); numbered('skill', '스킬')

  const s1 = (a: Asset) => (m.evalsByAsset.get(a.asset_id) ?? []).filter(e => e.scenario_id === 'S1')
  const approval: Present['approval'] = a => {
    if (a.asset_type !== 'mcp_server' && a.asset_type !== 'plugin') return null
    const ev = s1(a)
    const hit = (id: string) => ev.some(e => e.rule_id === id && e.result === 'detected')
    if (hit('S1-C1') || hit('S1-C3')) return '승인 안 됨'
    if (hit('S1-C2')) return '주소 바뀜'
    if (hit('S1-C4')) return '등록 위치 바뀜'
    if (ev.some(e => e.result === 'not_detected')) return '승인됨'
    return '승인 확인 못 함'
  }
  const name = (a: Asset): string => {
    const n = names.get(a.asset_id)
    if (n) return n
    if (a.asset_type === 'permission_auth') {
      const targets = (m.out.get(a.asset_id) ?? []).map(r => r.target.asset_ref && m.byId.get(r.target.asset_ref)).filter(Boolean) as Asset[]
      const srv = targets.find(t => t.asset_type === 'mcp_server')
      if (srv) return a.asset_subtype === 'authentication' ? `인증 토큰 · ${name(srv)}` : `도구 필터 · ${name(srv)}`
      return a.asset_subtype === 'authentication' ? '접속 인증' : '도구 정책'
    }
    // 도구 이름은 사용자가 붙인 값이 아니라 서버가 정한 기능 이름이라 그대로 보여 준다(이름 겹침 위협의 핵심 정보)
    if (a.asset_type === 'tool') return `도구 ${a.name}`
    if (a.asset_type === 'resource_prompt') return a.asset_subtype === 'prompt' ? '프롬프트' : '리소스'
    return TYPE_KO[a.asset_type]
  }
  const where = (a: Asset) => { const h = hostAsset(a); return h ? name(h) : '확인 못 함' }
  const sub = (a: Asset): string => {
    if (a.asset_type === 'plugin') {
      const added = servers.filter(s => addedBy(s)?.asset_id === a.asset_id).length
      return [approval(a), added ? `서버 ${added}개 추가` : null].filter(Boolean).join(' · ')
    }
    if (a.asset_type !== 'mcp_server') return TYPE_DESC[a.asset_type]
    const p = addedBy(a)
    const h = hostAsset(a)
    const route = p ? `${name(p)}${josa(name(p), '이', '가')} 추가` : h?.asset_type === 'node' ? `${name(h)}에 등록` : '설정에 직접 등록'
    return `${route} · ${approval(a)}`
  }
  return { name, sub, approval, where, hostAsset, addedBy, servers }
}

/** 서버가 하는 일 한 줄 (이름이 아니라 수집된 속성으로) */
export function serverLead(m: Model, p: Present, a: Asset): string {
  const h = p.hostAsset(a)
  const by = p.addedBy(a)
  const route = by ? `${p.name(by)}${josa(p.name(by), '이', '가')} 추가한` : h ? `${p.name(h)} 설정에 등록된` : '설정에 등록된'
  return `${route} ${isLocal(a) ? '같은 장치에서 실행되는' : '인터넷 주소로 연결하는'} 서버예요.`
}

/** 서버의 도구·리소스 수 */
export function serverStats(m: Model, a: Asset) {
  const kids = m.children.get(a.asset_id) ?? []
  const tools = kids.filter(k => k.asset_type === 'tool')
  const usable = tools.filter(t => m.stateValue(t, 'EXPOSED') === true)
  const res = kids.filter(k => k.asset_type === 'resource_prompt').length
  return { tools, usable: usable.length, res }
}

// ── AI 사용 기록의 도구 이름 ───────────────────────────────────
// 토큰 수집기는 호출된 도구의 원래 이름을 남긴다. 화면에는 도구가 '하는 일'로 보여 준다.
// 기본 도구는 OpenClaw 문서의 정의, MCP 도구는 도구 정의(description)를 근거로 정한 이름.
const TOOL_KO: Record<string, string> = {
  read: '파일 읽기', write: '파일 쓰기', edit: '파일 고치기', apply_patch: '파일 고치기', ls: '폴더 목록 보기', find: '파일 찾기', grep: '파일 내용 검색',
  exec: '명령 실행', process: '실행 중인 작업 관리', web_search: '웹 검색', web_fetch: '웹 페이지 가져오기', browser: '브라우저 조작',
  message: '메시지 보내기', cron: '예약 작업', image: '이미지 보기', memory_search: '기억 검색', memory_get: '기억 읽기',
  read_text_file: '파일 내용 읽기', read_file: '파일 내용 읽기', read_multiple_files: '여러 파일 읽기', write_file: '파일 쓰기', edit_file: '파일 고치기',
  list_directory: '폴더 목록 보기', directory_tree: '폴더 구조 보기', search_files: '파일 찾기', get_file_info: '파일 정보 보기', create_directory: '폴더 만들기',
  move_file: '파일 옮기기', list_allowed_directories: '열린 폴더 보기',
}
export function usageToolName(label: string, source?: string): { name: string; kind: string } {
  const raw = label.includes('__') ? label.split('__').slice(1).join('__') : label
  const kind = source === 'mcp' || label.includes('__') ? 'MCP 서버 도구' : '에이전트 기본 도구'
  return { name: TOOL_KO[raw] ?? (kind === 'MCP 서버 도구' ? '이름 없는 MCP 도구' : '이름 없는 기본 도구'), kind }
}
