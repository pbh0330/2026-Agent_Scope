// 런타임 기능은 없다. 이 플러그인의 역할은 manifest(openclaw.plugin.json)의
// mcpServers로 asset-catalog MCP 서버를 등록하는 것뿐이다.
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

export default definePluginEntry({
  id: "agentscope-asset-catalog",
  name: "Agent Scope Asset Catalog",
  description: "Contributes the asset-catalog MCP server (testbed P2).",
  register() {},
});
