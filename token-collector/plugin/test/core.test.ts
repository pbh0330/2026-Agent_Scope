import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveConfig, TokenGuard } from "../src/core.ts";
import { TokenCounter } from "../src/counter.ts";
import { MemorySink, startMockCountTokens } from "./helpers.ts";

const fixedNow = () => new Date("2026-10-06T03:00:00Z");
const toolMsg = (text: string) => ({ role: "toolResult", content: [{ type: "text", text }], isError: false });

test("결과 기록: 크기만 남기고 내용은 남기지 않으며, 결과 메시지를 바꾸지 않는다", () => {
  const sink = new MemorySink();
  const g = new TokenGuard(resolveConfig({ brake: { mode: "off" } }), sink, undefined, fixedNow);
  g.beforeToolCall({ toolName: "fs__read_text_file", toolCallId: "c1", runId: "r1" }, {});
  const ret = g.toolResultPersist({ toolName: "fs__read_text_file", toolCallId: "c1", message: toolMsg("비밀 내용 secret") }, {});
  assert.equal(ret, undefined);
  const [rec] = sink.of("tool_result");
  assert.equal(rec.runId, "r1");
  assert.equal(rec.textBytes, Buffer.byteLength("비밀 내용 secret"));
  assert.ok(!JSON.stringify(sink.records).includes("secret"), "결과 내용이 기록되면 안 됨");
});

test("토큰 계산: 병렬 결과마다 token_count 기록, run 누적에 반영", async () => {
  const srv = await startMockCountTokens();
  try {
    const cfg = resolveConfig({ tokenCount: { enabled: true, baseUrl: srv.baseUrl, model: "m", apiKeyEnv: "K" }, brake: { mode: "off" } });
    const sink = new MemorySink();
    const g = new TokenGuard(cfg, sink, new TokenCounter(cfg.tokenCount, undefined, { K: "k" }), fixedNow);
    for (const [id, n] of [["a", 400], ["b", 4000]] as const) {
      g.beforeToolCall({ toolName: "fs__read_text_file", toolCallId: id, runId: "r1" }, {});
    }
    g.toolResultPersist({ toolName: "fs__read_text_file", toolCallId: "a", message: toolMsg("x".repeat(400)) }, {});
    g.toolResultPersist({ toolName: "fs__read_text_file", toolCallId: "b", message: toolMsg("x".repeat(4000)) }, {});
    g.toolResultPersist({ toolName: "fs__read_text_file", toolCallId: "s", isSynthetic: true, message: toolMsg("x") }, {});
    await g.flush();
    const counts = Object.fromEntries(sink.of("token_count").map((r) => [r.toolCallId, r.countedTokens]));
    assert.deepEqual(counts, { a: 100, b: 1000 }, "합성(복구) 결과는 세지 않음");
    assert.equal(sink.of("token_count")[0].runId, "r1");
  } finally {
    await srv.close();
  }
});

test("토큰 계산 실패는 token_count_error로 남기고 실행은 계속된다", async () => {
  const srv = await startMockCountTokens({ failWith: 500 });
  try {
    const cfg = resolveConfig({ tokenCount: { enabled: true, baseUrl: srv.baseUrl, model: "m", apiKeyEnv: "K" } });
    const sink = new MemorySink();
    const g = new TokenGuard(cfg, sink, new TokenCounter(cfg.tokenCount, undefined, { K: "k" }), fixedNow);
    g.toolResultPersist({ toolName: "t", toolCallId: "a", message: toolMsg("abc") }, {});
    await g.flush();
    assert.equal(sink.of("token_count_error").length, 1);
    assert.equal(sink.of("token_count").length, 0);
  } finally {
    await srv.close();
  }
});

const brakeCfg = (mode: string) =>
  resolveConfig({
    brake: {
      mode,
      run: { warn: { toolCalls: 3 }, approve: { resultBytes: 1000 }, block: { sameToolStreak: 4 } },
    },
  });

test("warn 모드: 기준을 넘어도 기록만 하고 실행에는 개입하지 않는다", () => {
  const sink = new MemorySink();
  const g = new TokenGuard(brakeCfg("warn"), sink, undefined, fixedNow);
  for (let i = 0; i < 5; i++) {
    assert.equal(g.beforeToolCall({ toolName: "exec", toolCallId: `c${i}`, runId: "r" }, {}), undefined);
  }
  const levels = sink.of("brake").map((r) => r.level);
  assert.deepEqual(levels, ["warn", "block", "block"], "3번째 호출 warn, 4·5번째는 같은 도구 연속 4회 이상 block");
  assert.ok(sink.of("brake").every((r) => r.enforced === false));
});

test("enforce 모드: 승인 요구 → 승인되면 그 run에서는 다시 묻지 않음, 차단은 계속", () => {
  const sink = new MemorySink();
  const g = new TokenGuard(brakeCfg("enforce"), sink, undefined, fixedNow);
  g.beforeToolCall({ toolName: "fs__read_text_file", toolCallId: "a", runId: "r" }, {});
  g.toolResultPersist({ toolName: "fs__read_text_file", toolCallId: "a", message: toolMsg("x".repeat(1200)) }, {});
  const r1 = g.beforeToolCall({ toolName: "exec", toolCallId: "b", runId: "r" }, {});
  assert.ok(r1?.requireApproval, "누적 결과 1200B ≥ 1000B → 승인 요구");
  r1!.requireApproval!.onResolution!("allow-once");
  assert.equal(sink.of("brake_resolution")[0].decision, "allow-once");
  const r2 = g.beforeToolCall({ toolName: "ls", toolCallId: "c", runId: "r" }, {});
  assert.equal(r2, undefined, "승인된 run은 approve 단계를 다시 묻지 않음(warn은 기록)");
  for (const id of ["d", "e", "f"]) g.beforeToolCall({ toolName: "exec", toolCallId: id, runId: "r" }, {});
  const r3 = g.beforeToolCall({ toolName: "exec", toolCallId: "g", runId: "r" }, {});
  assert.equal(r3?.block, true);
  assert.match(r3!.blockReason!, /sameToolStreak/);
  // 다른 run은 영향 없음
  assert.equal(g.beforeToolCall({ toolName: "exec", toolCallId: "z", runId: "other" }, {}), undefined);
});

test("일 단위 한도는 run을 넘어 누적된다", () => {
  const sink = new MemorySink();
  const g = new TokenGuard(resolveConfig({ brake: { mode: "enforce", day: { block: { toolCalls: 3 } } } }), sink, undefined, fixedNow);
  g.beforeToolCall({ toolName: "a", toolCallId: "1", runId: "r1" }, {});
  g.beforeToolCall({ toolName: "b", toolCallId: "2", runId: "r2" }, {});
  assert.equal(g.beforeToolCall({ toolName: "c", toolCallId: "3", runId: "r3" }, {})?.block, true);
});
