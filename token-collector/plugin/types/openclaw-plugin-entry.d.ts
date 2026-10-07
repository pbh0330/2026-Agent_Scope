// 타입 검사용 최소 선언. 실제 구현은 OpenClaw가 플러그인을 불러올 때 제공한다
// (openclaw/plugin-sdk/plugin-entry, OpenClaw 문서 docs/plugins/hooks.md 기준).
declare module "openclaw/plugin-sdk/plugin-entry" {
  type HookEvent = Record<string, any>;
  type HookCtx = Record<string, any> | undefined;
  export interface PluginApi {
    pluginConfig?: unknown;
    logger?: { info?: (msg: string) => void; warn?: (msg: string) => void };
    on(
      name: string,
      handler: (event: HookEvent, ctx: HookCtx) => unknown,
      opts?: { matcher?: string[]; priority?: number; timeoutMs?: number },
    ): void;
  }
  export function definePluginEntry(entry: {
    id: string;
    name: string;
    description?: string;
    register(api: PluginApi): void;
  }): unknown;
}
