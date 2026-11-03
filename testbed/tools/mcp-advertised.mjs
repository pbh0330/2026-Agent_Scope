#!/usr/bin/env node
// 정답 목록(ground truth)의 광고 계층(advertised)을 만들기 위한 보조 도구.
// OpenClaw를 거치지 않고 MCP 서버에 직접 붙어 initialize 후
// tools/list, resources/list, resources/templates/list, prompts/list 결과를 JSON으로 출력한다.
//
// 사용법:
//   stdio : node mcp-advertised.mjs -- <command> [args...]
//   HTTP  : node mcp-advertised.mjs --url https://host:port/mcp [--header "Authorization: Bearer x"] [--ca ca.pem]
//
// 의존성 없음(Node.js 24 내장 기능만 사용).

import { spawn } from "node:child_process";

const PROTOCOL_VERSION = process.env.MCP_PROTOCOL_VERSION ?? "2026-07-28";
const LIST_METHODS = [
  ["tools/list", "tools"],
  ["resources/list", "resources"],
  ["resources/templates/list", "resourceTemplates"],
  ["prompts/list", "prompts"],
];

function parseArgs(argv) {
  const opts = { headers: {} };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--") { opts.command = argv.slice(i + 1); break; }
    else if (a === "--url") opts.url = argv[++i];
    else if (a === "--header") {
      const [k, ...v] = argv[++i].split(":");
      opts.headers[k.trim()] = v.join(":").trim();
    } else if (a === "--ca") opts.ca = argv[++i];
    else throw new Error(`unknown option: ${a}`);
  }
  if (!opts.command && !opts.url) throw new Error("give -- <command> or --url <url>");
  return opts;
}

function stdioClient(command) {
  const child = spawn(command[0], command.slice(1), { stdio: ["pipe", "pipe", "ignore"] });
  const pending = new Map();
  let buf = "";
  child.stdout.on("data", (chunk) => {
    buf += chunk;
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      const msg = JSON.parse(line);
      if (msg.id !== undefined && pending.has(msg.id)) {
        pending.get(msg.id)(msg);
        pending.delete(msg.id);
      }
    }
  });
  return {
    request(id, method, params) {
      return new Promise((resolve) => {
        pending.set(id, resolve);
        child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
      });
    },
    notify(method, params) {
      child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n");
    },
    close() { child.kill(); },
  };
}

function httpClient(url, headers) {
  let sessionId;
  let negotiated;
  async function post(body) {
    const h = {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      ...headers,
    };
    if (sessionId) h["mcp-session-id"] = sessionId;
    if (negotiated) h["mcp-protocol-version"] = negotiated;
    const res = await fetch(url, { method: "POST", headers: h, body: JSON.stringify(body) });
    sessionId = res.headers.get("mcp-session-id") ?? sessionId;
    const text = await res.text();
    if (!text) return undefined;
    if ((res.headers.get("content-type") ?? "").includes("text/event-stream")) {
      const data = text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim());
      return JSON.parse(data[data.length - 1]);
    }
    return JSON.parse(text);
  }
  return {
    async request(id, method, params) {
      const msg = await post({ jsonrpc: "2.0", id, method, params });
      if (method === "initialize") negotiated = msg?.result?.protocolVersion;
      return msg;
    },
    notify(method, params) { return post({ jsonrpc: "2.0", method, params }); },
    close() {},
  };
}

async function listAll(client, method, key, nextId) {
  const items = [];
  let cursor;
  do {
    const res = await client.request(nextId(), method, cursor ? { cursor } : {});
    if (res.error) return { error: res.error };
    items.push(...(res.result?.[key] ?? []));
    cursor = res.result?.nextCursor;
  } while (cursor);
  return { items };
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.ca) process.env.NODE_EXTRA_CA_CERTS = opts.ca;
  const client = opts.url ? httpClient(opts.url, opts.headers) : stdioClient(opts.command);
  let id = 0;
  const nextId = () => ++id;

  const init = await client.request(nextId(), "initialize", {
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {},
    clientInfo: { name: "agentscope-testbed-ground-truth", version: "0.1.0" },
  });
  if (init.error) throw new Error(`initialize failed: ${JSON.stringify(init.error)}`);
  await client.notify("notifications/initialized", {});

  const caps = init.result.capabilities ?? {};
  const out = {
    requestedProtocolVersion: PROTOCOL_VERSION,
    negotiatedProtocolVersion: init.result.protocolVersion,
    serverInfo: init.result.serverInfo,
    capabilities: caps,
  };
  for (const [method, key] of LIST_METHODS) {
    const family = method.split("/")[0];
    if (!caps[family]) { out[key] = { notAdvertised: true }; continue; }
    const r = await listAll(client, method, key, nextId);
    out[key] = r.error ? { error: r.error } : r.items;
  }
  client.close();
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
}

main().catch((e) => { console.error(e.message); process.exit(1); });
