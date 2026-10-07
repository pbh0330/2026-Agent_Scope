// AgentScope Token Guard — OpenClaw 플러그인 진입점.
// 설치: openclaw plugins install --link ./plugin --force && openclaw plugins enable agentscope-token-guard
// 설정: openclaw.json의 plugins.entries["agentscope-token-guard"].config (README 참고)
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { createTokenGuard } from "./src/core.ts";

export default definePluginEntry({
  id: "agentscope-token-guard",
  name: "AgentScope Token Guard",
  description: "도구 결과 크기·토큰 수 기록(병렬·배치 구간 배분용)과 토큰 소비 브레이크",
  register(api) {
    const log = (msg: string) => api.logger?.info?.(`[agentscope-token-guard] ${msg}`);
    const guard = createTokenGuard(api.pluginConfig, log);
    // 모든 도구에 적용(matcher 없음). 메모리 안에서만 판정하므로 제한 시간(15초)에 걸리지 않는다.
    api.on("before_tool_call", (event, ctx) => guard.beforeToolCall(event, ctx), { priority: 10 });
    // 동기 훅: 결과 메시지를 바꾸지 않고(undefined 반환) 크기만 기록, 토큰 계산은 비동기로 진행.
    api.on("tool_result_persist", (event, ctx) => {
      guard.toolResultPersist(event, ctx);
      return undefined;
    });
  },
});
