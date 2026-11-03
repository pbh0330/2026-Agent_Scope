#!/usr/bin/env node
// notes-sync: S1 위협 구성용 플러그인 agentscope-notes-sync가 manifest mcpServers로 등록하는 비인가 stdio MCP 서버.
// 원본은 testbed/mcp-servers/notes-stub/server.mjs (플러그인은 복사 설치되므로 같은 코드를 폴더 안에 둔다).
// 설치 단순화를 위해 외부 의존성 없이 JSON-RPC를 직접 처리한다(asset-catalog와 같은 방식).
// 같은 코드를 여러 서버 이름으로 띄울 수 있도록 도구 이름 접두어를 --name으로 받는다.
//   node server.mjs --name shadow-notes  → shadow_notes_list_notes, shadow_notes_get_note
// 도구는 읽기 전용 2종이고 데이터는 가상의 정적 값이다(S2·S3 판정에 영향을 주지 않도록).

import { createInterface } from "node:readline";

const PROTOCOL_VERSION = "2025-11-25";
const i = process.argv.indexOf("--name");
const NAME = i > 0 ? process.argv[i + 1] : "notes-stub";
const PREFIX = NAME.replace(/[^A-Za-z0-9]/g, "_");
const NOTES = [
  { id: "n-001", title: "weekly sync", body: "fictional note" },
  { id: "n-002", title: "todo", body: "fictional note" },
];

const TOOLS = [
  {
    name: `${PREFIX}_list_notes`,
    title: "List notes",
    description: "List the fictional note IDs and titles.",
    inputSchema: { type: "object", properties: {} },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: `${PREFIX}_get_note`,
    title: "Get note",
    description: "Get one fictional note by ID.",
    inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
];

function callTool(name, args = {}) {
  if (name === TOOLS[0].name) {
    return { content: [{ type: "text", text: JSON.stringify(NOTES.map(({ id, title }) => ({ id, title }))) }] };
  }
  if (name === TOOLS[1].name) {
    const note = NOTES.find((n) => n.id === args.id);
    return note
      ? { content: [{ type: "text", text: JSON.stringify(note) }] }
      : { content: [{ type: "text", text: `unknown id: ${args.id}` }], isError: true };
  }
  return undefined;
}

function handle(msg) {
  switch (msg.method) {
    case "initialize":
      return {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: { tools: {} },
        serverInfo: { name: `agentscope-${NAME}`, version: "0.1.0" },
      };
    case "ping":
      return {};
    case "tools/list":
      return { tools: TOOLS };
    case "tools/call": {
      const result = callTool(msg.params?.name, msg.params?.arguments);
      if (result) return result;
      throw { code: -32602, message: `unknown tool: ${msg.params?.name}` };
    }
    default:
      throw { code: -32601, message: `method not found: ${msg.method}` };
  }
}

const send = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");

createInterface({ input: process.stdin }).on("line", (line) => {
  if (!line.trim()) return;
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } });
    return;
  }
  if (msg.id === undefined) return; // notifications
  try {
    send({ jsonrpc: "2.0", id: msg.id, result: handle(msg) });
  } catch (err) {
    send({ jsonrpc: "2.0", id: msg.id, error: { code: err.code ?? -32603, message: err.message ?? String(err) } });
  }
});
