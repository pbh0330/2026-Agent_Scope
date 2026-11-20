import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { resolveConfig, TokenGuard } from "../src/core.ts";
import { TokenCounter } from "../src/counter.ts";
import { CountSpanExporter } from "../src/otlp.ts";
import { errorCode, safeErrorText, SafeError } from "../src/safeerror.ts";
import { MemorySink } from "./helpers.ts";

const SECRET = "SECRET-tool-result-7f3a";
const fixedNow = () => new Date("2026-11-03T03:00:00Z");
const toolMsg = (text: string) => ({ role: "toolResult", content: [{ type: "text", text }], isError: false });

// 요청 본문을 그대로 되돌려주는 서버(오류 응답에 요청 내용이 섞이는 경우를 흉내 냄).
async function startEchoServer(status: number, shape: "echo-json" | "echo-text") {
  const server: Server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      if (shape === "echo-json") {
        res.writeHead(status, { "content-type": "application/json" })
          .end(JSON.stringify({ error: { type: "invalid_request_error", message: `bad request: ${raw}` } }));
      } else {
        res.writeHead(status, { "content-type": "text/plain" }).end(`echo ${raw}`);
      }
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const { port } = server.address() as AddressInfo;
  return { baseUrl: `http://127.0.0.1:${port}`, close: () => new Promise<void>((r) => server.close(() => r())) };
}

for (const api of ["anthropic-count-tokens", "openai-usage"] as const) {
  for (const [status, shape] of [[400, "echo-json"], [500, "echo-text"], [200, "echo-text"]] as const) {
    test(`오류 응답에 요청 내용이 섞여도 기록에 남지 않는다(${api}, HTTP ${status}, ${shape})`, async () => {
      const srv = await startEchoServer(status, shape);
      try {
        const cfg = resolveConfig({ tokenCount: { enabled: true, api, baseUrl: srv.baseUrl, model: "m", apiKeyEnv: "K" }, brake: { mode: "off" } });
        const sink = new MemorySink();
        const g = new TokenGuard(cfg, sink, new TokenCounter(cfg.tokenCount, undefined, { K: "k" }), fixedNow);
        g.toolResultPersist({ toolName: "read", toolCallId: "a", message: toolMsg(`내용 ${SECRET}`) }, {});
        await g.flush();
        const [err] = sink.of("token_count_error");
        assert.ok(err, "token_count_error가 기록되어야 함");
        assert.ok(!JSON.stringify(sink.records).includes(SECRET), `기록에 결과 내용이 남음: ${err.error}`);
        if (status !== 200) assert.match(err.error, new RegExp(`HTTP ${status}`));
        if (shape === "echo-json") assert.match(err.error, /invalid_request_error/, "허용된 형식의 오류 코드는 남김");
        if (status === 200) assert.match(err.error, /JSON이 아님/);
      } finally {
        await srv.close();
      }
    });
  }
}

test("Collector 오류 응답 본문도 count_export_error에 남기지 않는다", async () => {
  const srv = await startEchoServer(400, "echo-text");
  try {
    const exp = new CountSpanExporter(srv.baseUrl, 2000);
    const err = await exp.send({ traceId: "", toolCallId: "a", toolName: "read", countedTokens: 1, skippedBlocks: 0,
      source: "x", startMs: 0, endMs: 0 }).then(() => undefined, (e) => e);
    assert.ok(err instanceof SafeError);
    assert.equal(safeErrorText(err), "OTLP HTTP 400");
  } finally {
    await srv.close();
  }
});

test("errorCode: 형식이 맞는 코드만, 메시지는 버림", () => {
  assert.equal(errorCode('{"error":{"type":"rate_limit_error","message":"x"}}'), "rate_limit_error");
  assert.equal(errorCode('{"error":{"code":"context_length_exceeded","message":"x"}}'), "context_length_exceeded");
  assert.equal(errorCode(`{"error":{"type":"${SECRET} with spaces"}}`), undefined);
  assert.equal(errorCode("not json " + SECRET), undefined);
  assert.equal(safeErrorText(new Error(`boom ${SECRET}`)), "오류(Error)");
});
