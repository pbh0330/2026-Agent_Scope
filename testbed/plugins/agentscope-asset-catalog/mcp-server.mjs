#!/usr/bin/env node
// asset-catalog: 플러그인이 manifest mcpServers로 등록하는 stdio MCP 서버 (테스트베드 P2).
// 설치 단순화를 위해 외부 의존성 없이 JSON-RPC를 직접 처리한다.
// 도구 2종만 광고하며, 데이터는 가상의 정적 값이다.

import { createInterface } from "node:readline";

const PROTOCOL_VERSION = "2025-11-25";
const CATALOG = [
  { id: "cat-001", name: "billing-api", kind: "service", tier: "gold" },
  { id: "cat-002", name: "audit-log-store", kind: "datastore", tier: "silver" },
];

const TOOLS = [
  {
    name: "catalog_search",
    title: "Search asset catalog",
    description: "Search the fictional asset catalog by name substring.",
    inputSchema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "catalog_get_entry",
    title: "Get catalog entry",
    description: "Get one fictional catalog entry by ID.",
    inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
];

function callTool(name, args = {}) {
  if (name === "catalog_search") {
    const hits = CATALOG.filter((e) => e.name.includes(String(args.query ?? "")));
    return { content: [{ type: "text", text: JSON.stringify(hits) }] };
  }
  if (name === "catalog_get_entry") {
    const entry = CATALOG.find((e) => e.id === args.id);
    return entry
      ? { content: [{ type: "text", text: JSON.stringify(entry) }] }
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
        serverInfo: { name: "agentscope-asset-catalog", version: "0.1.0" },
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
