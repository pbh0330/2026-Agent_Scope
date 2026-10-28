// 결과별 토큰 수를 OTLP 스팬(agentscope.tool_result.count)으로 Collector에 보낸다.
//
// Collector의 tokenattribution 커넥터는 이 스팬을 tool_call_id로 모아 두었다가, 병렬·배치 구간을 닫는
// model.call이 오면 구간 증가분을 결과별 토큰 수 비율로 나눠 실시간 메트릭에 반영한다.
// 같은 스팬이 Tempo와 원본 스팬 파일에도 저장되므로 usage.json 생성기도 이 값을 쓸 수 있다.
//
// 외부 라이브러리 없이 OTLP/HTTP JSON(POST {endpoint}/v1/traces)으로 보낸다. 결과 내용은 담지 않는다(토큰 수만).

import { randomBytes } from "node:crypto";

export const COUNT_SPAN_NAME = "agentscope.tool_result.count";
export const SERVICE_NAME = "agentscope-token-guard";

const TRACE_ID_RE = /^[0-9a-f]{32}$/;
const SPAN_ID_RE = /^[0-9a-f]{16}$/;

export type CountSpan = {
  traceId?: string; // 원래 요청의 trace id(before_tool_call의 ctx.trace.traceId). 없거나 형식이 틀리면 새로 만든다
  parentSpanId?: string; // ctx.trace.spanId. Tempo에서 같은 요청 아래에 보이게 한다
  toolCallId: string;
  toolName: string;
  countedTokens: number;
  skippedBlocks: number;
  source: string;
  startMs: number;
  endMs: number;
};

type FetchLike = (url: string, init: { method: string; headers: Record<string, string>; body: string; signal?: AbortSignal }) =>
  Promise<{ ok: boolean; status: number; text(): Promise<string> }>;

function validHex(v: unknown, re: RegExp): string | undefined {
  if (typeof v !== "string") return undefined;
  const s = v.toLowerCase();
  return re.test(s) && !/^0+$/.test(s) ? s : undefined;
}

export function normalizeTraceId(v: unknown): string | undefined {
  return validHex(v, TRACE_ID_RE);
}

export function normalizeSpanId(v: unknown): string | undefined {
  return validHex(v, SPAN_ID_RE);
}

function nonZeroHex(bytes: number): string {
  let s = randomBytes(bytes).toString("hex");
  while (/^0+$/.test(s)) s = randomBytes(bytes).toString("hex");
  return s;
}

const nanos = (ms: number) => (BigInt(Math.round(ms)) * 1_000_000n).toString();

// buildCountPayload는 OTLP/HTTP JSON 요청 본문을 만든다(테스트에서도 사용).
export function buildCountPayload(s: CountSpan): Record<string, unknown> {
  const traceId = normalizeTraceId(s.traceId) ?? nonZeroHex(16);
  const parentSpanId = normalizeSpanId(s.parentSpanId);
  const span: Record<string, unknown> = {
    traceId,
    spanId: nonZeroHex(8),
    name: COUNT_SPAN_NAME,
    kind: 1, // SPAN_KIND_INTERNAL
    startTimeUnixNano: nanos(s.startMs),
    endTimeUnixNano: nanos(Math.max(s.endMs, s.startMs)),
    attributes: [
      { key: "gen_ai.tool.call.id", value: { stringValue: s.toolCallId } },
      { key: "openclaw.toolName", value: { stringValue: s.toolName } },
      { key: "agentscope.counted_tokens", value: { intValue: String(Math.max(0, Math.round(s.countedTokens))) } },
      { key: "agentscope.count.skipped_blocks", value: { intValue: String(s.skippedBlocks) } },
      { key: "agentscope.count.source", value: { stringValue: s.source } },
    ],
    status: {},
  };
  if (parentSpanId) span.parentSpanId = parentSpanId;
  return {
    resourceSpans: [{
      resource: { attributes: [{ key: "service.name", value: { stringValue: SERVICE_NAME } }] },
      scopeSpans: [{ scope: { name: SERVICE_NAME }, spans: [span] }],
    }],
  };
}

export class CountSpanExporter {
  private readonly url: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchLike;

  constructor(endpoint: string, timeoutMs: number, fetchImpl?: FetchLike) {
    // endpoint는 Collector OTLP/HTTP 주소(예: http://localhost:4318). /v1/traces까지 적어도 된다.
    const base = endpoint.replace(/\/+$/, "");
    this.url = base.endsWith("/v1/traces") ? base : `${base}/v1/traces`;
    this.timeoutMs = timeoutMs;
    this.fetchImpl = fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
  }

  get target(): string {
    return this.url;
  }

  // send는 스팬 하나를 보낸다. 실패하면 예외(호출하는 쪽이 기록만 하고 실행에는 영향 없음).
  async send(s: CountSpan): Promise<void> {
    const res = await this.fetchImpl(this.url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(buildCountPayload(s)),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!res.ok) {
      const t = (await res.text().catch(() => "")).slice(0, 200);
      throw new Error(`OTLP HTTP ${res.status}: ${t}`);
    }
  }
}
