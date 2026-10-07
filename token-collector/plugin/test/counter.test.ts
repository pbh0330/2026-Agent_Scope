import { test } from "node:test";
import assert from "node:assert/strict";
import { TokenCounter, toAnthropicBlocks } from "../src/counter.ts";
import { resolveConfig } from "../src/core.ts";
import { startMockCountTokens } from "./helpers.ts";

const cfg = (baseUrl: string, extra: Record<string, unknown> = {}) =>
  resolveConfig({ tokenCount: { enabled: true, baseUrl, model: "claude-haiku-4-5", apiKeyEnv: "TEST_KEY", ...extra } }).tokenCount;

test("결과 토큰 = 결과 요청 − 기준 요청, 기준은 한 번만 센다", async () => {
  const srv = await startMockCountTokens();
  try {
    const c = new TokenCounter(cfg(srv.baseUrl), undefined, { TEST_KEY: "k-test" });
    assert.equal(c.usable, true);
    const a = await c.countResult([{ type: "text", text: "x".repeat(400) }]);
    const b = await c.countResult([{ type: "text", text: "y".repeat(40) }]);
    assert.deepEqual([a.tokens, b.tokens], [100, 10]);
    assert.equal(srv.calls.length, 3, "기준 1회 + 결과 2회");
    const req = srv.calls[1];
    assert.equal(req.headers["x-api-key"], "k-test");
    assert.equal(req.headers["anthropic-version"], "2023-06-01");
    assert.equal(req.body.model, "claude-haiku-4-5");
    assert.equal(req.body.tools[0].name, "agentscope_probe");
    assert.equal(req.body.messages[1].content[0].type, "tool_use");
    assert.equal(req.body.messages[2].content[0].tool_use_id, req.body.messages[1].content[0].id);
  } finally {
    await srv.close();
  }
});

test("이미지 블록은 Anthropic base64 이미지로 바꿔 함께 센다", async () => {
  const srv = await startMockCountTokens();
  try {
    const c = new TokenCounter(cfg(srv.baseUrl), undefined, { TEST_KEY: "k" });
    const r = await c.countResult([{ type: "text", text: "abcd" }, { type: "image", data: "AAAA", mimeType: "image/png" }, { type: "audio" }]);
    assert.equal(r.tokens, 101);
    assert.equal(r.skippedBlocks, 1);
    const sent = srv.calls.at(-1)!.body.messages[2].content[0].content;
    assert.deepEqual(sent[1], { type: "image", source: { type: "base64", media_type: "image/png", data: "AAAA" } });
  } finally {
    await srv.close();
  }
});

test("HTTP 오류는 예외로 알리고, 다음 호출에서 기준을 다시 센다", async () => {
  const srv = await startMockCountTokens({ failWith: 429 });
  try {
    const c = new TokenCounter(cfg(srv.baseUrl), undefined, { TEST_KEY: "k" });
    await assert.rejects(c.countResult([{ type: "text", text: "a" }]), /HTTP 429/);
    await assert.rejects(c.countResult([{ type: "text", text: "a" }]), /HTTP 429/);
    assert.equal(srv.calls.length, 2, "실패한 기준 요청은 캐시하지 않음");
  } finally {
    await srv.close();
  }
});

test("키·모델이 없으면 사용하지 않는다", () => {
  assert.equal(new TokenCounter(cfg("http://x"), undefined, {}).usable, false);
  assert.match(new TokenCounter(cfg("http://x", { model: undefined }), undefined, { TEST_KEY: "k" }).reasonUnusable!, /model/);
});

test("maxResultChars로 OpenClaw 결과 길이 제한과 맞춘다", () => {
  const { converted } = toAnthropicBlocks([{ type: "text", text: "abcdef" }, { type: "text", text: "ghij" }], 8);
  assert.deepEqual(converted, [{ type: "text", text: "abcdef" }, { type: "text", text: "gh" }]);
});
