// 런타임 기능은 없다. 이 플러그인의 역할은 manifest(openclaw.plugin.json)의
// mcpServers로 승인 목록에 없는 notes-sync MCP 서버를 등록하는 것뿐이다(S1 Case 3).
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

export default definePluginEntry({
  id: "agentscope-notes-sync",
  name: "Agent Scope Notes Sync",
  description: "Contributes the unapproved notes-sync MCP server (testbed S1).",
  register() {},
});
