import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { resolveConfig, TokenGuard } from "../src/core.ts";
import { TokenCounter } from "../src/counter.ts";
import { buildCountPayload, COUNT_SPAN_NAME, CountSpanExporter } from "../src/otlp.ts";
import { MemorySink, startMockOpenAI } from "./helpers.ts";

const fixedNow = () => new Date("2026-10-28T03:00:00Z");
const toolMsg = (text: string) => ({ role: "toolResult", content: [{ type: "text", text }], isError: false });
const TRACE = "0af7651916cd43dd8448eb211c80319c";
const SPAN = "b7ad6b7169203331";

// 가짜 Collector(OTLP/HTTP): 받은 요청 본문을 모은다.
async function startMockCollector(status = 200) {
  const bodies: any[] = [];
  const urls: string[] = [];
  const server: Server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      urls.push(req.url ?? "");
      bodies.push(JSON.parse(raw));
      res.writeHead(status, { "content-type": "application/json" }).end("{}");
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const { port } = server.address() as AddressInfo;
  return { endpoint: `http://127.0.0.1:${port}`, bodies, urls, close: () => new Promise<void>((r) => server.close(() => r())) };
}

const attrsOf = (span: any) => Object.fromEntries(span.attributes.map((a: any) => [a.key, a.value.stringValue ?? a.value.intValue]));

test("OTLP 본문: 원래 trace id·부모 span id, 토큰 수 속성, 결과 내용 없음", () => {
  const body = buildCountPayload({
    traceId: TRACE.toUpperCase(), parentSpanId: SPAN, toolCallId: "c1", toolName: "read",
    countedTokens: 270, skippedBlocks: 0, source: "openai-usage", startMs: 1_700_000_000_000, endMs: 1_700_000_001_500,
  }) as any;
  const rs = body.resourceSpans[0];
  assert.equal(rs.resource.attributes[0].value.stringValue, "agentscope-token-guard");
  const span = rs.scopeSpans[0].spans[0];
  assert.equal(span.name, COUNT_SPAN_NAME);
  assert.equal(span.traceId, TRACE, "대문자도 소문자로 맞춤");
  assert.equal(span.parentSpanId, SPAN);
  assert.match(span.spanId, /^[0-9a-f]{16}$/);
  assert.equal(span.startTimeUnixNano, "1700000000000000000");
  assert.equal(span.endTimeUnixNano, "1700000001500000000");
  assert.deepEqual(attrsOf(span), {
    "gen_ai.tool.call.id": "c1", "openclaw.toolName": "read", "agentscope.counted_tokens": "270",
    "agentscope.count.skipped_blocks": "0", "agentscope.count.source": "openai-usage",
  });
});

test("OTLP 본문: trace id가 없거나 틀리면 새로 만들고, 부모는 넣지 않는다", () => {
  const span = (buildCountPayload({
    traceId: "not-a-trace", parentSpanId: "0000000000000000", toolCallId: "c1", toolName: "t",
    countedTokens: 1, skippedBlocks: 0, source: "x", startMs: 0, endMs: 0,
  }) as any).resourceSpans[0].scopeSpans[0].spans[0];
  assert.match(span.traceId, /^[0-9a-f]{32}$/);
  assert.notEqual(span.traceId, "not-a-trace");
  assert.equal(span.parentSpanId, undefined);
});

test("exporter 주소: /v1/traces를 붙이고, 이미 있으면 그대로", () => {
  assert.equal(new CountSpanExporter("http://localhost:4318/", 1000).target, "http://localhost:4318/v1/traces");
  assert.equal(new CountSpanExporter("http://c:4318/v1/traces", 1000).target, "http://c:4318/v1/traces");
});

test("토큰 계산이 끝나면 결과별 토큰 수 스팬을 Collector로 보낸다(before_tool_call의 trace id 사용)", async () => {
  const gw = await startMockOpenAI();
  const col = await startMockCollector();
  try {
    const cfg = resolveConfig({
      tokenCount: { enabled: true, api: "openai-usage", baseUrl: gw.baseUrl, model: "m", apiKeyEnv: "K" },
      brake: { mode: "off" }, otlpEndpoint: col.endpoint,
    });
    const sink = new MemorySink();
    const g = new TokenGuard(cfg, sink, new TokenCounter(cfg.tokenCount, undefined, { K: "k" }), fixedNow, undefined,
      new CountSpanExporter(cfg.otlp.endpoint!, cfg.otlp.timeoutMs));
    g.beforeToolCall({ toolName: "read", toolCallId: "a", runId: "r1" }, { trace: { traceId: TRACE, spanId: SPAN } });
    g.toolResultPersist({ toolName: "read", toolCallId: "a", message: toolMsg("x".repeat(400)) }, {});
    await g.flush();

    assert.equal(col.bodies.length, 1);
    assert.equal(col.urls[0], "/v1/traces");
    const span = col.bodies[0].resourceSpans[0].scopeSpans[0].spans[0];
    assert.equal(span.traceId, TRACE);
    assert.equal(span.parentSpanId, SPAN);
    const tc = sink.of("token_count")[0];
    assert.equal(attrsOf(span)["agentscope.counted_tokens"], String(tc.countedTokens));
    assert.equal(tc.traceId, TRACE, "JSONL에도 trace id를 남김");
    assert.ok(!JSON.stringify(col.bodies).includes("xxxx"), "결과 내용은 보내지 않음");
    assert.equal(sink.of("count_export_error").length, 0);
  } finally {
    await gw.close();
    await col.close();
  }
});

test("Collector 전송 실패는 count_export_error로 남기고 JSONL 기록은 그대로", async () => {
  const gw = await startMockOpenAI();
  const col = await startMockCollector(503);
  try {
    const cfg = resolveConfig({
      tokenCount: { enabled: true, api: "openai-usage", baseUrl: gw.baseUrl, model: "m", apiKeyEnv: "K" },
      brake: { mode: "off" }, otlpEndpoint: col.endpoint,
    });
    const sink = new MemorySink();
    const g = new TokenGuard(cfg, sink, new TokenCounter(cfg.tokenCount, undefined, { K: "k" }), fixedNow, undefined,
      new CountSpanExporter(cfg.otlp.endpoint!, cfg.otlp.timeoutMs));
    g.beforeToolCall({ toolName: "read", toolCallId: "a", runId: "r1" }, {});
    g.toolResultPersist({ toolName: "read", toolCallId: "a", message: toolMsg("hello") }, {});
    await g.flush();
    assert.equal(sink.of("token_count").length, 1);
    const [err] = sink.of("count_export_error");
    assert.match(err.error, /503/);
  } finally {
    await gw.close();
    await col.close();
  }
});

test("otlpEndpoint가 없으면 보내지 않는다(기본값)", () => {
  assert.equal(resolveConfig({}).otlp.endpoint, undefined);
  assert.equal(resolveConfig({ otlpEndpoint: "  " }).otlp.endpoint, undefined);
  assert.equal(resolveConfig({ otlpEndpoint: "http://localhost:4318" }).otlp.timeoutMs, 5000);
});
