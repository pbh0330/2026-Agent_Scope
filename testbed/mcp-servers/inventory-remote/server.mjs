// Agent Scope 테스트베드 P2 원격 MCP 서버 (inventory-remote)
//
// - 전송: Streamable HTTP over HTTPS (실습용 CA가 서명한 서버 인증서)
// - 인증: Authorization: Bearer <INVENTORY_MCP_TOKEN> (더미 값)
// - 광고: 도구 2종, 리소스 1종, 프롬프트 1종 — 다른 서버와 이름이 겹치지 않게 구성(S3 정상 기준)
// - 데이터는 모두 가상의 정적 값이며 외부로 전송하지 않는다.
//
// 환경변수
//   INVENTORY_MCP_TOKEN  필수. 클라이언트가 보내야 하는 Bearer 토큰
//   TLS_CERT, TLS_KEY    필수. 서버 인증서·키 경로
//   HOST (기본 0.0.0.0), PORT (기본 8443)

import https from "node:https";
import { readFileSync } from "node:fs";
import { randomUUID, timingSafeEqual } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { isInitializeRequest } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

const HOST = process.env.HOST ?? "0.0.0.0";
const PORT = Number(process.env.PORT ?? 8443);
const TOKEN = process.env.INVENTORY_MCP_TOKEN;
if (!TOKEN || !process.env.TLS_CERT || !process.env.TLS_KEY) {
  console.error("INVENTORY_MCP_TOKEN, TLS_CERT, TLS_KEY are required");
  process.exit(1);
}

const HOSTS = [
  { id: "web-01", role: "web", os: "ubuntu-24.04", owner: "team-a" },
  { id: "db-01", role: "database", os: "ubuntu-24.04", owner: "team-b" },
  { id: "build-01", role: "ci", os: "debian-12", owner: "team-a" },
];

function buildServer() {
  const server = new McpServer({ name: "agentscope-inventory-remote", version: "0.1.0" });

  server.registerTool(
    "inventory_list_hosts",
    {
      title: "List inventory hosts",
      description: "List the host IDs in the testbed's fictional inventory.",
      inputSchema: {},
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async () => ({ content: [{ type: "text", text: HOSTS.map((h) => h.id).join("\n") }] }),
  );

  server.registerTool(
    "inventory_get_host",
    {
      title: "Get inventory host",
      description: "Get one fictional inventory host record by ID.",
      inputSchema: { id: z.string().describe("Host ID, e.g. web-01") },
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async ({ id }) => {
      const host = HOSTS.find((h) => h.id === id);
      return host
        ? { content: [{ type: "text", text: JSON.stringify(host) }] }
        : { content: [{ type: "text", text: `unknown host: ${id}` }], isError: true };
    },
  );

  server.registerResource(
    "inventory-hosts",
    "inventory://hosts",
    { title: "Inventory hosts", description: "All fictional hosts as JSON", mimeType: "application/json" },
    async (uri) => ({ contents: [{ uri: uri.href, mimeType: "application/json", text: JSON.stringify(HOSTS) }] }),
  );

  server.registerPrompt(
    "inventory_owner_report",
    {
      title: "Inventory owner report",
      description: "Ask for a short report of hosts owned by one team.",
      argsSchema: { owner: z.string().describe("Owner team, e.g. team-a") },
    },
    ({ owner }) => ({
      messages: [{ role: "user", content: { type: "text", text: `List the inventory hosts owned by ${owner} and their roles.` } }],
    }),
  );

  return server;
}

function authorized(req) {
  const header = req.headers.authorization ?? "";
  const expected = Buffer.from(`Bearer ${TOKEN}`);
  const got = Buffer.from(header);
  return got.length === expected.length && timingSafeEqual(got, expected);
}

async function readJson(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : undefined;
}

const transports = new Map();

const httpsServer = https.createServer(
  { cert: readFileSync(process.env.TLS_CERT), key: readFileSync(process.env.TLS_KEY) },
  async (req, res) => {
    const url = new URL(req.url, `https://${req.headers.host}`);
    if (url.pathname !== "/mcp") {
      res.writeHead(404).end();
      return;
    }
    if (!authorized(req)) {
      res.writeHead(401, { "www-authenticate": "Bearer" }).end();
      return;
    }
    try {
      const sessionId = req.headers["mcp-session-id"];
      const body = req.method === "POST" ? await readJson(req) : undefined;
      let transport = sessionId ? transports.get(sessionId) : undefined;

      if (!transport) {
        if (req.method !== "POST" || !isInitializeRequest(body)) {
          res.writeHead(400, { "content-type": "application/json" }).end(
            JSON.stringify({ jsonrpc: "2.0", error: { code: -32000, message: "No valid session" }, id: null }),
          );
          return;
        }
        transport = new StreamableHTTPServerTransport({
          sessionIdGenerator: () => randomUUID(),
          onsessioninitialized: (id) => transports.set(id, transport),
        });
        transport.onclose = () => transport.sessionId && transports.delete(transport.sessionId);
        await buildServer().connect(transport);
      }
      await transport.handleRequest(req, res, body);
    } catch (err) {
      console.error(err);
      if (!res.headersSent) res.writeHead(500).end();
    }
  },
);

httpsServer.listen(PORT, HOST, () => console.log(`inventory-remote MCP listening on https://${HOST}:${PORT}/mcp`));
