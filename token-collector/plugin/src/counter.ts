// 토큰 계산 API(Anthropic Messages count_tokens)로 도구 결과 하나의 토큰 수를 센다(정확도 개선 방안 B).
//
//   T_i = 결과 i 하나만 담은 최소 요청의 입력 토큰 수
//   T_0 = 같은 형식에 결과 내용을 비운 요청의 입력 토큰 수(모델별로 한 번만 세고 재사용)
//   c_i = T_i − T_0   → 결과를 감싸는 tool_result 형식 토큰까지 포함한 결과 몫
//
// 요청은 POST {baseUrl}/v1/messages/count_tokens, 응답은 { input_tokens }.
// API 키는 설정 파일에 두지 않고 환경 변수(apiKeyEnv)에서 읽는다. 결과 내용은 계산에만 쓰고 저장하지 않는다.

import type { ContentBlock } from "./measure.ts";

export type TokenCountConfig = {
  enabled: boolean;
  baseUrl: string;
  apiKeyEnv: string;
  model?: string;
  anthropicVersion: string;
  timeoutMs: number;
  maxConcurrent: number;
  maxResultChars?: number;
};

type FetchLike = (url: string, init: { method: string; headers: Record<string, string>; body: string; signal?: AbortSignal }) =>
  Promise<{ ok: boolean; status: number; json(): Promise<unknown>; text(): Promise<string> }>;

const PROBE_ID = "toolu_agentscope_probe";
const PROBE_TOOL = { name: "agentscope_probe", description: "token count probe", input_schema: { type: "object", properties: {} } };

export class TokenCounter {
  private readonly cfg: TokenCountConfig;
  private readonly fetchImpl: FetchLike;
  private readonly apiKey: string | undefined;
  private baselinePromise: Promise<number> | undefined;
  private active = 0;
  private readonly waiting: Array<() => void> = [];

  constructor(cfg: TokenCountConfig, fetchImpl?: FetchLike, env: NodeJS.ProcessEnv = process.env) {
    this.cfg = cfg;
    this.fetchImpl = fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
    this.apiKey = env[cfg.apiKeyEnv];
  }

  // usable이 false면 호출하지 않는다(설정 꺼짐, 모델·키 없음).
  get usable(): boolean {
    return this.cfg.enabled && !!this.cfg.model && !!this.apiKey;
  }

  get reasonUnusable(): string | undefined {
    if (!this.cfg.enabled) return "tokenCount.enabled=false";
    if (!this.cfg.model) return "tokenCount.model 없음";
    if (!this.apiKey) return `환경 변수 ${this.cfg.apiKeyEnv} 없음`;
    return undefined;
  }

  // countResult는 결과 블록의 토큰 수(c_i)를 돌려준다. 실패하면 예외.
  async countResult(blocks: ContentBlock[]): Promise<{ tokens: number; total: number; baseline: number; skippedBlocks: number }> {
    const { converted, skipped } = toAnthropicBlocks(blocks, this.cfg.maxResultChars);
    const baseline = await this.baseline();
    const total = await this.count(converted);
    return { tokens: Math.max(0, total - baseline), total, baseline, skippedBlocks: skipped };
  }

  private baseline(): Promise<number> {
    if (!this.baselinePromise) {
      this.baselinePromise = this.count(undefined).catch((e) => {
        this.baselinePromise = undefined; // 다음에 다시 시도
        throw e;
      });
    }
    return this.baselinePromise;
  }

  private async count(content: unknown[] | undefined): Promise<number> {
    const toolResult: Record<string, unknown> = { type: "tool_result", tool_use_id: PROBE_ID };
    if (content !== undefined) toolResult.content = content;
    const body = {
      model: this.cfg.model,
      tools: [PROBE_TOOL],
      messages: [
        { role: "user", content: "agentscope token probe" },
        { role: "assistant", content: [{ type: "tool_use", id: PROBE_ID, name: PROBE_TOOL.name, input: {} }] },
        { role: "user", content: [toolResult] },
      ],
    };
    await this.acquire();
    try {
      const res = await this.fetchImpl(`${this.cfg.baseUrl.replace(/\/+$/, "")}/v1/messages/count_tokens`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": this.apiKey ?? "", "anthropic-version": this.cfg.anthropicVersion },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(this.cfg.timeoutMs),
      });
      if (!res.ok) {
        const text = (await res.text().catch(() => "")).slice(0, 200);
        throw new Error(`count_tokens HTTP ${res.status}: ${text}`);
      }
      const j = (await res.json()) as { input_tokens?: unknown };
      if (typeof j.input_tokens !== "number") throw new Error("count_tokens 응답에 input_tokens 없음");
      return j.input_tokens;
    } finally {
      this.release();
    }
  }

  private acquire(): Promise<void> {
    if (this.active < this.cfg.maxConcurrent) {
      this.active++;
      return Promise.resolve();
    }
    return new Promise((resolve) => this.waiting.push(() => { this.active++; resolve(); }));
  }

  private release(): void {
    this.active--;
    this.waiting.shift()?.();
  }
}

// OpenClaw 결과 블록 → Anthropic tool_result content 블록. 알 수 없는 블록은 빼고 개수를 센다.
export function toAnthropicBlocks(blocks: ContentBlock[], maxChars?: number): { converted: unknown[]; skipped: number } {
  const converted: unknown[] = [];
  let skipped = 0;
  let budget = maxChars ?? Infinity;
  for (const b of blocks) {
    if (b.type === "text" && typeof b.text === "string") {
      let text = b.text;
      if (text.length > budget) text = text.slice(0, Math.max(0, budget));
      budget -= text.length;
      converted.push({ type: "text", text });
    } else if (b.type === "image" && typeof b.data === "string" && b.mimeType) {
      converted.push({ type: "image", source: { type: "base64", media_type: b.mimeType, data: b.data } });
    } else {
      skipped++;
    }
  }
  return { converted, skipped };
}
