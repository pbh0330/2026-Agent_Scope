import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { dayKey, DEFAULT_DAY_TIME_ZONE, FileDayStore, resolveConfig, TokenGuard, type DayState, type DayStore } from "../src/core.ts";
import { MemorySink } from "./helpers.ts";

class MemoryDayStore implements DayStore {
  saved?: DayState;
  saves = 0;
  load() { return this.saved ? structuredClone(this.saved) : undefined; }
  save(s: DayState) { this.saved = structuredClone(s); this.saves++; }
}

const at = (iso: string) => () => new Date(iso);

test("일 단위 날짜는 기본 한국 시간 자정에 바뀐다(UTC 자정 아님)", () => {
  assert.equal(DEFAULT_DAY_TIME_ZONE, "Asia/Seoul");
  assert.equal(dayKey(new Date("2026-11-09T14:59:59Z"), "Asia/Seoul"), "2026-11-09"); // KST 23:59:59
  assert.equal(dayKey(new Date("2026-11-09T15:00:00Z"), "Asia/Seoul"), "2026-11-10"); // KST 00:00
  assert.equal(dayKey(new Date("2026-11-09T15:00:00Z"), "UTC"), "2026-11-09");

  // 한도 판정도 같은 기준: KST 23:59에 2번, KST 00:00에는 새 날이라 0부터.
  const cfg = resolveConfig({ brake: { mode: "enforce", day: { block: { toolCalls: 3 } }, dayStatePath: "" } });
  let now = "2026-11-09T14:59:00Z";
  const g = new TokenGuard(cfg, new MemorySink(), undefined, () => new Date(now));
  g.beforeToolCall({ toolName: "a", toolCallId: "1", runId: "r1" }, {});
  g.beforeToolCall({ toolName: "a", toolCallId: "2", runId: "r2" }, {});
  now = "2026-11-09T15:00:00Z";
  assert.equal(g.beforeToolCall({ toolName: "a", toolCallId: "3", runId: "r3" }, {}), undefined);
  assert.deepEqual(g.dayUsageSnapshot(), { day: "2026-11-10", usage: { resultBytes: 0, countedTokens: 0, toolCalls: 1 } });
});

test("게이트웨이를 다시 시작해도 같은 날이면 일 누적을 이어서 센다", () => {
  const store = new MemoryDayStore();
  const cfg = resolveConfig({ brake: { mode: "enforce", day: { block: { toolCalls: 3 } } } });
  const now = at("2026-11-09T03:00:00Z");
  const g1 = new TokenGuard(cfg, new MemorySink(), undefined, now, undefined, undefined, store);
  g1.beforeToolCall({ toolName: "a", toolCallId: "1", runId: "r1" }, {});
  g1.beforeToolCall({ toolName: "a", toolCallId: "2", runId: "r1" }, {});
  assert.equal(store.saved?.usage.toolCalls, 2);
  assert.equal(store.saved?.day, "2026-11-09");

  // 재시작: 새 객체(메모리 상태 없음) + 같은 저장소 → 세 번째 호출에서 일 한도 차단.
  const g2 = new TokenGuard(cfg, new MemorySink(), undefined, now, undefined, undefined, store);
  assert.equal(g2.beforeToolCall({ toolName: "a", toolCallId: "3", runId: "r2" }, {})?.block, true);
});

test("저장된 누적이 다른 날짜이거나 다른 시간대 기준이면 0부터 센다", () => {
  const cfg = resolveConfig({ brake: { mode: "warn" } });
  const old = new MemoryDayStore();
  old.saved = { day: "2026-11-08", timeZone: "Asia/Seoul", usage: { resultBytes: 9, countedTokens: 9, toolCalls: 9 } };
  const g = new TokenGuard(cfg, new MemorySink(), undefined, at("2026-11-09T03:00:00Z"), undefined, undefined, old);
  assert.equal(g.dayUsageSnapshot().usage.toolCalls, 0);

  const utc = new MemoryDayStore();
  utc.saved = { day: "2026-11-09", timeZone: "UTC", usage: { resultBytes: 9, countedTokens: 9, toolCalls: 9 } };
  const g2 = new TokenGuard(cfg, new MemorySink(), undefined, at("2026-11-09T03:00:00Z"), undefined, undefined, utc);
  assert.equal(g2.dayUsageSnapshot().usage.toolCalls, 0);
});

test("결과 크기와 토큰 수도 저장된다(숫자만)", () => {
  const store = new MemoryDayStore();
  const cfg = resolveConfig({ brake: { mode: "warn" } });
  const g = new TokenGuard(cfg, new MemorySink(), undefined, at("2026-11-09T03:00:00Z"), undefined, undefined, store);
  g.beforeToolCall({ toolName: "read", toolCallId: "c", runId: "r" }, {});
  g.toolResultPersist({ toolName: "read", toolCallId: "c", message: { role: "toolResult", content: [{ type: "text", text: "비밀 secret" }] } }, {});
  assert.equal(store.saved?.usage.resultBytes, Buffer.byteLength("비밀 secret"));
  assert.ok(!JSON.stringify(store.saved).includes("secret"), "결과 내용이 저장되면 안 됨");
});

test("파일 저장소: 저장·읽기, 깨진 파일은 무시", () => {
  const dir = mkdtempSync(join(tmpdir(), "guard-day-"));
  const p = join(dir, "sub", "day.json");
  const fs = new FileDayStore(p);
  assert.equal(fs.load(), undefined, "파일 없으면 undefined");
  fs.save({ day: "2026-11-09", timeZone: "Asia/Seoul", usage: { resultBytes: 1, countedTokens: 2, toolCalls: 3 } });
  assert.deepEqual(fs.load(), { day: "2026-11-09", timeZone: "Asia/Seoul", usage: { resultBytes: 1, countedTokens: 2, toolCalls: 3 } });
  assert.equal(JSON.parse(readFileSync(p, "utf8")).v, 1);
  writeFileSync(p, "{깨짐");
  assert.equal(fs.load(), undefined);
  writeFileSync(p, JSON.stringify({ day: "2026-11-09", timeZone: "Asia/Seoul", usage: { toolCalls: -5, countedTokens: "x" } }));
  assert.deepEqual(fs.load()?.usage, { resultBytes: 0, countedTokens: 0, toolCalls: 0 }, "이상한 값은 0으로");
});

test("설정: 잘못된 시간대는 기본값, 빈 저장 경로는 저장 안 함", () => {
  const c = resolveConfig({ brake: { dayTimeZone: "Not/AZone", dayStatePath: "" } });
  assert.equal(c.brake.dayTimeZone, "Asia/Seoul");
  assert.equal(c.brake.dayStatePath, "");
  const d = resolveConfig({});
  assert.match(d.brake.dayStatePath, /agentscope-day-usage\.json$/);
  assert.equal(resolveConfig({ brake: { dayTimeZone: "UTC" } }).brake.dayTimeZone, "UTC");
});
