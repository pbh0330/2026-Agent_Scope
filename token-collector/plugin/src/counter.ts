// 도구 결과 하나의 토큰 수를 센다(정확도 개선 방안 B).
//
//   T_i = 결과 i 하나만 담은 최소 요청의 입력 토큰 수
//   T_0 = 같은 형식에 결과 내용을 비운 요청의 입력 토큰 수(한 번만 세고 재사용)
//   c_i = T_i − T_0   → 결과를 감싸는 도구 결과 형식 토큰까지 포함한 결과 몫
//
// 두 가지 방식(api)을 지원한다.
//   "anthropic-count-tokens": POST {baseUrl}/v1/messages/count_tokens → { input_tokens }
//       Anthropic API 직접 연결용. 요청을 실행하지 않고 토큰 수만 센다.
//   "openai-usage": POST {baseUrl}/chat/completions (max_tokens=1) → usage.prompt_tokens
//       OpenAI 호환 게이트웨이(예: 학교 게이트웨이)용. 토큰 계산 API가 없는 대신 아주 짧은 요청을 실제로 보내
//       응답의 입력 토큰 수를 읽는다. OpenClaw가 같은 게이트웨이로 보내는 형식(tool 역할 메시지)과 같은 모양으로 센다.
//       이미지 블록은 이 형식의 tool 메시지에 넣을 수 없어 세지 않는다(skippedBlocks로 기록).
//
// API 키는 설정 파일에 두지 않고 환경 변수(apiKeyEnv)에서 읽는다. 결과 내용은 계산에만 쓰고 저장하지 않는다.

import type { ContentBlock } from "./measure.ts";

export type CountApi = "anthropic-count-tokens" | "openai-usage";

export type TokenCountConfig = {
  enabled: boolean;
  api: CountApi;
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
const PROBE_NAME = "agentscope_probe";
const ANTHROPIC_TOOL = { name: PROBE_NAME, description: "token count probe", input_schema: { type: "object", properties: {} } };
const OPENAI_TOOL = { type: "function", function: { name: PROBE_NAME, description: "token count probe", parameters: { type: "object", properties: {} } } };

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

  get source(): string {
    return this.cfg.api;
  }

  // countResult는 결과 블록의 토큰 수(c_i)를 돌려준다. 실패하면 예외.
  async countResult(blocks: ContentBlock[]): Promise<{ tokens: number; total: number; baseline: number; skippedBlocks: number }> {
    const baseline = await this.baseline();
    if (this.cfg.api === "openai-usage") {
      const { text, skipped } = toOpenAIText(blocks, this.cfg.maxResultChars);
      const total = await this.countOpenAI(text);
      return { tokens: Math.max(0, total - baseline + 1), total, baseline, skippedBlocks: skipped };
    }
    const { converted, skipped } = toAnthropicBlocks(blocks, this.cfg.maxResultChars);
    const total = await this.countAnthropic(converted);
    return { tokens: Math.max(0, total - baseline), total, baseline, skippedBlocks: skipped };
  }

  private baseline(): Promise<number> {
    if (!this.baselinePromise) {
      // openai-usage: 게이트웨이가 빈 tool 메시지를 따로 채워 넣어 오히려 더 크게 세는 것이 확인됨(10.12, 빈 내용 615 > 17바이트 결과 603).
      // 그래서 기준 요청은 "." 한 글자로 세고, 그 한 글자 몫(1토큰)을 결과 쪽에 되돌려 준다(countResult).
      const p = this.cfg.api === "openai-usage" ? this.countOpenAI(".") : this.countAnthropic(undefined);
      this.baselinePromise = p.catch((e) => {
        this.baselinePromise = undefined; // 다음에 다시 시도
        throw e;
      });
    }
    return this.baselinePromise;
  }

  private async countAnthropic(content: unknown[] | undefined): Promise<number> {
    const toolResult: Record<string, unknown> = { type: "tool_result", tool_use_id: PROBE_ID };
    if (content !== undefined) toolResult.content = content;
    const body = {
      model: this.cfg.model,
      tools: [ANTHROPIC_TOOL],
      messages: [
        { role: "user", content: "agentscope token probe" },
        { role: "assistant", content: [{ type: "tool_use", id: PROBE_ID, name: PROBE_NAME, input: {} }] },
        { role: "user", content: [toolResult] },
      ],
    };
    const j = (await this.post("/v1/messages/count_tokens",
      { "x-api-key": this.apiKey ?? "", "anthropic-version": this.cfg.anthropicVersion }, body)) as { input_tokens?: unknown };
    if (typeof j.input_tokens !== "number") throw new Error("count_tokens 응답에 input_tokens 없음");
    return j.input_tokens;
  }

  private async countOpenAI(text: string): Promise<number> {
    const body = {
      model: this.cfg.model,
      max_tokens: 1,
      tools: [OPENAI_TOOL],
      messages: [
        { role: "user", content: "agentscope token probe" },
        { role: "assistant", content: null, tool_calls: [{ id: PROBE_ID, type: "function", function: { name: PROBE_NAME, arguments: "{}" } }] },
        { role: "tool", tool_call_id: PROBE_ID, content: text },
      ],
    };
    const j = (await this.post("/chat/completions", { authorization: `Bearer ${this.apiKey ?? ""}` }, body)) as {
      usage?: { prompt_tokens?: unknown };
    };
    if (typeof j.usage?.prompt_tokens !== "number") throw new Error("응답에 usage.prompt_tokens 없음");
    return j.usage.prompt_tokens;
  }

  private async post(path: string, headers: Record<string, string>, body: unknown): Promise<unknown> {
    await this.acquire();
    try {
      const res = await this.fetchImpl(`${this.cfg.baseUrl.replace(/\/+$/, "")}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json", ...headers },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(this.cfg.timeoutMs),
      });
      if (!res.ok) {
        const t = (await res.text().catch(() => "")).slice(0, 200);
        throw new Error(`${path} HTTP ${res.status}: ${t}`);
      }
      return await res.json();
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

// OpenClaw 결과 블록 → OpenAI tool 메시지 문자열. 텍스트 블록만 이어 붙이고(OpenClaw와 같게 줄바꿈으로 구분),
// 이미지·기타 블록은 세지 않고 개수만 센다.
export function toOpenAIText(blocks: ContentBlock[], maxChars?: number): { text: string; skipped: number } {
  const parts: string[] = [];
  let skipped = 0;
  for (const b of blocks) {
    if (b.type === "text" && typeof b.text === "string") parts.push(b.text);
    else skipped++;
  }
  let text = parts.join("\n");
  if (maxChars !== undefined && text.length > maxChars) text = text.slice(0, maxChars);
  return { text, skipped };
}
