// agentscope-token-guard 핵심 로직. OpenClaw에 의존하지 않아 단독으로 테스트할 수 있다.
//
// 1) 결과 기록: tool_result_persist에서 도구 결과의 크기·특징값을 재고(내용은 저장 안 함),
//    토큰 계산 API로 결과마다 토큰 수를 세어 JSONL에 남긴다. agentscope-usage --tool-results가
//    이 기록으로 병렬·배치 구간 증가분을 결과별 토큰 수 비율로 나눈다(정확도 개선 방안 B).
// 2) 소비 브레이크: before_tool_call에서 run·일 단위 누적 소비를 기준과 비교해
//    경고(기록만) / 승인 요구 / 차단을 결정한다. mode=warn이면 기록만 하고 실행에는 개입하지 않는다.
// 3) 실시간 반영: otlpEndpoint를 주면 결과별 토큰 수를 OTLP 스팬으로 Collector에 보내,
//    tokenattribution 커넥터가 병렬·배치 구간 배분을 대시보드에 바로 반영하게 한다.

import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { contentOf, measureContent } from "./measure.ts";
import { TokenCounter, type TokenCountConfig } from "./counter.ts";
import { CountSpanExporter, normalizeSpanId, normalizeTraceId } from "./otlp.ts";

export const RECORD_VERSION = 1;

export type Limits = { resultBytes?: number; countedTokens?: number; toolCalls?: number; sameToolStreak?: number };
export type Levels = { warn?: Limits; approve?: Limits; block?: Limits };
export type BrakeMode = "off" | "warn" | "enforce";

export type GuardConfig = {
  outputPath: string;
  tokenCount: TokenCountConfig;
  brake: { mode: BrakeMode; approvalTimeoutMs: number; run: Levels; day: Levels };
  // otlp.endpoint: Collector OTLP/HTTP 주소(예: http://localhost:4318). 없으면 보내지 않는다(JSONL 기록만).
  otlp: { endpoint?: string; timeoutMs: number };
};

export function resolveConfig(raw: unknown): GuardConfig {
  const r = (raw ?? {}) as Record<string, any>;
  const tc = (r.tokenCount ?? {}) as Record<string, any>;
  const br = (r.brake ?? {}) as Record<string, any>;
  const mode: BrakeMode = br.mode === "off" || br.mode === "enforce" ? br.mode : "warn";
  return {
    outputPath: typeof r.outputPath === "string" && r.outputPath
      ? r.outputPath.replace(/^~(?=$|[\\/])/, homedir())
      : join(homedir(), ".openclaw", "agentscope", "agentscope-tool-results.jsonl"),
    tokenCount: {
      enabled: tc.enabled === true,
      api: tc.api === "openai-usage" ? "openai-usage" : "anthropic-count-tokens",
      baseUrl: typeof tc.baseUrl === "string" ? tc.baseUrl : "https://api.anthropic.com",
      apiKeyEnv: typeof tc.apiKeyEnv === "string" ? tc.apiKeyEnv : "ANTHROPIC_API_KEY",
      model: typeof tc.model === "string" ? tc.model : undefined,
      anthropicVersion: typeof tc.anthropicVersion === "string" ? tc.anthropicVersion : "2023-06-01",
      timeoutMs: Number.isInteger(tc.timeoutMs) ? tc.timeoutMs : 10000,
      maxConcurrent: Number.isInteger(tc.maxConcurrent) && tc.maxConcurrent > 0 ? tc.maxConcurrent : 2,
      maxResultChars: Number.isInteger(tc.maxResultChars) ? tc.maxResultChars : undefined,
    },
    brake: {
      mode,
      approvalTimeoutMs: Number.isInteger(br.approvalTimeoutMs) ? br.approvalTimeoutMs : 60000,
      run: (br.run ?? {}) as Levels,
      day: (br.day ?? {}) as Levels,
    },
    otlp: {
      endpoint: typeof r.otlpEndpoint === "string" && r.otlpEndpoint.trim() ? r.otlpEndpoint.trim() : undefined,
      timeoutMs: Number.isInteger(r.otlpTimeoutMs) && r.otlpTimeoutMs > 0 ? r.otlpTimeoutMs : 5000,
    },
  };
}

// --- 기록 파일 ---

export interface Sink { write(rec: Record<string, unknown>): void }

export class JsonlSink implements Sink {
  private ready = false;
  private readonly path: string;
  private readonly onError?: (e: unknown) => void;
  constructor(path: string, onError?: (e: unknown) => void) {
    this.path = path;
    this.onError = onError;
  }
  write(rec: Record<string, unknown>): void {
    try {
      if (!this.ready) {
        mkdirSync(dirname(this.path), { recursive: true });
        this.ready = true;
      }
      appendFileSync(this.path, JSON.stringify({ v: RECORD_VERSION, ...rec }) + "\n");
    } catch (e) {
      this.onError?.(e); // 기록 실패가 에이전트 실행을 막지 않게 한다
    }
  }
}

// --- 상태 ---

type Usage = { resultBytes: number; countedTokens: number; toolCalls: number };
// before_tool_call에서 기억해 두는 호출 정보. traceId·spanId는 OpenClaw 진단 trace(ctx.trace)에서 온다.
type CallMeta = { runId?: string; toolName?: string; traceId?: string; spanId?: string };
type RunState = Usage & { lastTool?: string; streak: number; approved: boolean };

const MAX_RUNS = 500;
const MAX_CALLS = 5000;

type Event = Record<string, any>;
type Ctx = Record<string, any> | undefined;

export type BeforeToolCallResult = {
  block?: boolean;
  blockReason?: string;
  requireApproval?: {
    title: string;
    description: string;
    severity?: "info" | "warning" | "critical";
    timeoutMs?: number;
    onResolution?: (decision: string) => void;
  };
};

type Level = "warn" | "approve" | "block";
const LEVELS: Level[] = ["block", "approve", "warn"];
type Breach = { scope: "run" | "day"; metric: keyof Limits; value: number; limit: number };

export class TokenGuard {
  private readonly runs = new Map<string, RunState>();
  private readonly calls = new Map<string, CallMeta>();
  private day = { key: "", usage: { resultBytes: 0, countedTokens: 0, toolCalls: 0 } as Usage };
  readonly pending = new Set<Promise<void>>();

  readonly cfg: GuardConfig;
  private readonly sink: Sink;
  private readonly counter?: TokenCounter;
  private readonly now: () => Date;
  private readonly exporter?: CountSpanExporter;

  constructor(cfg: GuardConfig, sink: Sink, counter?: TokenCounter, now: () => Date = () => new Date(), log?: (msg: string) => void,
    exporter?: CountSpanExporter) {
    this.cfg = cfg;
    this.sink = sink;
    this.counter = counter;
    this.now = now;
    this.exporter = exporter;
    if (counter && !counter.usable && cfg.tokenCount.enabled) log?.(`토큰 계산 비활성: ${counter.reasonUnusable}`);
  }

  // before_tool_call: 이번 호출 직전까지의 누적 소비로 판정한 뒤, 호출 수를 반영한다.
  beforeToolCall(event: Event, ctx: Ctx): BeforeToolCallResult | undefined {
    const toolName: string = event.toolName ?? ctx?.toolName ?? "unknown";
    const toolCallId: string | undefined = event.toolCallId ?? ctx?.toolCallId;
    const runId: string | undefined = event.runId ?? ctx?.runId;
    if (toolCallId) {
      this.remember(toolCallId, {
        runId, toolName, traceId: normalizeTraceId(ctx?.trace?.traceId), spanId: normalizeSpanId(ctx?.trace?.spanId),
      });
    }

    const run = this.run(runId);
    const day = this.dayUsage();
    const runLimits = runId ? this.cfg.brake.run : {}; // run을 모르면 run 기준은 판정하지 않는다(일 기준만)
    const streak = run.lastTool === toolName ? run.streak + 1 : 1;
    run.lastTool = toolName;
    run.streak = streak;

    const mode = this.cfg.brake.mode;
    let result: BeforeToolCallResult | undefined;
    if (mode !== "off") {
      const breaches: Record<Level, Breach[]> = { warn: [], approve: [], block: [] };
      for (const lv of LEVELS) {
        breaches[lv].push(...check("run", { ...run, toolCalls: run.toolCalls + 1 }, streak, runLimits[lv]));
        breaches[lv].push(...check("day", { ...day, toolCalls: day.toolCalls + 1 }, undefined, this.cfg.brake.day[lv]));
      }
      let level = LEVELS.find((lv) => breaches[lv].length > 0);
      if (level === "approve" && run.approved) level = undefined; // 이 run에서 이미 승인받음
      if (level) {
        const enforced = mode === "enforce";
        this.sink.write({
          kind: "brake", ts: this.now().toISOString(), level, mode, enforced,
          runId, toolCallId, toolName, reasons: breaches[level],
          run: { resultBytes: run.resultBytes, countedTokens: run.countedTokens, toolCalls: run.toolCalls, sameToolStreak: streak },
        });
        if (enforced) result = this.decision(level, breaches[level], toolName, run, runId, toolCallId);
      }
    }
    run.toolCalls++;
    day.toolCalls++;
    return result;
  }

  // tool_result_persist(동기 훅): 크기 기록 → 토큰 계산은 비동기로 진행. 결과 메시지는 바꾸지 않는다.
  toolResultPersist(event: Event, ctx: Ctx): void {
    const toolCallId: string | undefined = event.toolCallId ?? ctx?.toolCallId;
    const toolName: string = event.toolName ?? ctx?.toolName ?? "unknown";
    const meta = toolCallId ? this.calls.get(toolCallId) : undefined;
    const runId = meta?.runId;
    const traceId = meta?.traceId;
    const blocks = contentOf(event.message);
    const m = measureContent(blocks);
    const isError = (event.message as { isError?: boolean } | undefined)?.isError === true;
    const synthetic = event.isSynthetic === true;

    this.sink.write({
      kind: "tool_result", ts: this.now().toISOString(), runId, traceId, toolCallId, toolName,
      sessionKey: ctx?.sessionKey, isError, isSynthetic: synthetic, ...m,
    });
    const run = this.run(runId);
    const day = this.dayUsage();
    run.resultBytes += m.textBytes;
    day.resultBytes += m.textBytes;

    if (!synthetic && toolCallId && this.counter?.usable) {
      const started = Date.now();
      const p = this.counter.countResult(blocks).then(
        (c) => {
          run.countedTokens += c.tokens;
          this.dayUsage().countedTokens += c.tokens;
          const ended = Date.now();
          this.sink.write({
            kind: "token_count", ts: this.now().toISOString(), runId, traceId, toolCallId, toolName,
            countedTokens: c.tokens, probeTotal: c.total, probeBaseline: c.baseline, skippedBlocks: c.skippedBlocks,
            model: this.cfg.tokenCount.model, source: this.cfg.tokenCount.api, durationMs: ended - started,
          });
          if (this.exporter) {
            this.track(this.exporter.send({
              traceId, parentSpanId: meta?.spanId, toolCallId, toolName, countedTokens: c.tokens,
              skippedBlocks: c.skippedBlocks, source: this.cfg.tokenCount.api, startMs: started, endMs: ended,
            }).catch((e: unknown) => {
              this.sink.write({
                kind: "count_export_error", ts: this.now().toISOString(), runId, traceId, toolCallId, toolName,
                error: String((e as Error)?.message ?? e).slice(0, 200),
              });
            }));
          }
        },
        (e: unknown) => {
          this.sink.write({
            kind: "token_count_error", ts: this.now().toISOString(), runId, toolCallId, toolName,
            error: String((e as Error)?.message ?? e).slice(0, 200),
          });
        },
      );
      this.track(p);
    }
  }

  // track은 진행 중인 비동기 작업(토큰 계산·전송)을 flush가 기다릴 수 있게 등록한다.
  private track(p: Promise<void>): void {
    // 예외가 새어 나가 처리되지 않은 거부(unhandled rejection)로 게이트웨이가 멈추지 않게 여기서 삼킨다.
    const q: Promise<void> = p.catch(() => undefined).finally(() => this.pending.delete(q));
    this.pending.add(q);
  }

  // 테스트·종료용: 진행 중인 토큰 계산이 끝날 때까지 기다린다.
  async flush(): Promise<void> {
    while (this.pending.size) await Promise.allSettled([...this.pending]);
  }

  private decision(level: Level, reasons: Breach[], toolName: string, run: RunState, runId?: string, toolCallId?: string): BeforeToolCallResult | undefined {
    const why = reasons.map((b) => `${b.scope}.${b.metric} ${b.value} ≥ ${b.limit}`).join(", ");
    if (level === "block") {
      return { block: true, blockReason: `토큰 소비 한도 초과로 ${toolName} 실행을 차단함 (${why})` };
    }
    if (level === "approve") {
      return {
        requireApproval: {
          title: "토큰 소비 기준 초과",
          description: `이 실행의 토큰 소비가 기준을 넘었습니다 (${why}). ${toolName}을(를) 계속 실행할까요?`,
          severity: "warning",
          timeoutMs: this.cfg.brake.approvalTimeoutMs,
          onResolution: (decision: string) => {
            if (decision === "allow-once" || decision === "allow-always") run.approved = true;
            this.sink.write({ kind: "brake_resolution", ts: this.now().toISOString(), runId, toolCallId, toolName, decision });
          },
        },
      };
    }
    return undefined;
  }

  // run을 모르면(runId 없음) 매번 새 상태를 돌려준다. 하나의 공용 버킷에 여러 run이 쌓여
  // run 기준 브레이크가 잘못 걸리는 것을 막는다(일 기준 누적에는 그대로 반영).
  private run(runId: string | undefined): RunState {
    const fresh = (): RunState => ({ resultBytes: 0, countedTokens: 0, toolCalls: 0, streak: 0, approved: false });
    if (!runId) return fresh();
    let s = this.runs.get(runId);
    if (!s) {
      s = fresh();
      this.runs.set(runId, s);
      if (this.runs.size > MAX_RUNS) this.runs.delete(this.runs.keys().next().value!);
    }
    return s;
  }

  private remember(toolCallId: string, v: CallMeta) {
    this.calls.set(toolCallId, v);
    if (this.calls.size > MAX_CALLS) this.calls.delete(this.calls.keys().next().value!);
  }

  // 일 단위 누적(UTC 날짜 기준). 날짜가 바뀌면 0부터.
  private dayUsage(): Usage {
    const key = this.now().toISOString().slice(0, 10);
    if (this.day.key !== key) this.day = { key, usage: { resultBytes: 0, countedTokens: 0, toolCalls: 0 } };
    return this.day.usage;
  }
}

function check(scope: "run" | "day", u: Usage, streak: number | undefined, lim: Limits | undefined): Breach[] {
  if (!lim) return [];
  const out: Breach[] = [];
  const add = (metric: keyof Limits, value: number | undefined) => {
    const limit = lim[metric];
    if (limit !== undefined && value !== undefined && value >= limit) out.push({ scope, metric, value, limit });
  };
  add("resultBytes", u.resultBytes);
  add("countedTokens", u.countedTokens);
  add("toolCalls", u.toolCalls);
  add("sameToolStreak", streak);
  return out;
}

export function createTokenGuard(rawConfig: unknown, log?: (msg: string) => void): TokenGuard {
  const cfg = resolveConfig(rawConfig);
  const sink = new JsonlSink(cfg.outputPath, (e) => log?.(`기록 실패: ${String(e)}`));
  const exporter = cfg.otlp.endpoint ? new CountSpanExporter(cfg.otlp.endpoint, cfg.otlp.timeoutMs) : undefined;
  if (exporter && !cfg.tokenCount.enabled) log?.("otlpEndpoint가 있지만 tokenCount.enabled=false라 보낼 토큰 수가 없음");
  return new TokenGuard(cfg, sink, new TokenCounter(cfg.tokenCount), undefined, log, exporter);
}
