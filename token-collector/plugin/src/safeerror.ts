// 기록에 남기는 오류 문자열을 안전한 메타데이터로만 만든다.
//
// 외부 API 오류 응답 본문이나 JSON 파싱 오류 메시지에는 요청에 담았던 도구 결과 내용이 그대로 섞여 돌아올 수 있다.
// "결과 내용을 저장하지 않는다"를 지키기 위해, 기록에는 HTTP 상태·허용된 형식의 오류 코드·우리가 정한 문구만 남긴다.

// SafeError는 메시지에 외부 입력이 들어가지 않은 오류다(그대로 기록해도 됨).
export class SafeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SafeError";
  }
}

const CODE = /^[A-Za-z0-9_.-]{1,64}$/;

// errorCode는 오류 응답 본문에서 오류 코드만 꺼낸다(Anthropic error.type, OpenAI error.code/error.type).
// 영문·숫자·_.- 64자 이하만 허용하고, message 등 나머지는 버린다.
export function errorCode(text: string): string | undefined {
  let j: unknown;
  try {
    j = JSON.parse(text);
  } catch {
    return undefined;
  }
  const e = (j as { error?: unknown })?.error;
  const cands: unknown[] = [];
  if (e && typeof e === "object") cands.push((e as { code?: unknown }).code, (e as { type?: unknown }).type);
  else cands.push(e);
  cands.push((j as { type?: unknown })?.type);
  for (const c of cands) {
    if (typeof c === "string" && CODE.test(c)) return c;
  }
  return undefined;
}

// httpError는 상태 코드와 안전한 오류 코드만 담은 오류를 만든다(본문은 읽어서 코드만 확인하고 버림).
export async function httpError(label: string, res: { status: number; text(): Promise<string> }): Promise<SafeError> {
  const code = errorCode(await res.text().catch(() => ""));
  return new SafeError(`${label} HTTP ${res.status}${code ? ` (${code})` : ""}`);
}

// safeErrorText는 기록용 문자열이다. SafeError면 메시지, 아니면 오류 종류 이름만(TimeoutError, TypeError 등).
export function safeErrorText(e: unknown): string {
  if (e instanceof SafeError) return e.message.slice(0, 200);
  const name = (e as { name?: unknown } | null)?.name;
  return `오류(${typeof name === "string" && CODE.test(name) ? name : "unknown"})`;
}
