import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

// 가짜 count_tokens 서버: 고정분 50 + tool_result 텍스트 4글자당 1토큰 + 이미지 블록당 100.
// tool_result에 content가 없으면(기준 요청) 고정분 50 + 3만 돌려준다.
export async function startMockCountTokens(opts: { failWith?: number } = {}) {
  const calls: Array<{ headers: Record<string, unknown>; body: any }> = [];
  const server: Server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      const body = JSON.parse(raw);
      calls.push({ headers: req.headers, body });
      if (req.url !== "/v1/messages/count_tokens" || req.method !== "POST") {
        res.writeHead(404).end();
        return;
      }
      if (opts.failWith) {
        res.writeHead(opts.failWith, { "content-type": "application/json" }).end('{"error":{"type":"rate_limit_error"}}');
        return;
      }
      const tr = body.messages[2].content[0];
      let tokens = 53;
      if (tr.content !== undefined) {
        tokens = 50;
        for (const b of tr.content) {
          if (b.type === "text") tokens += Math.ceil(b.text.length / 4);
          if (b.type === "image") tokens += 100;
        }
        tokens += 3;
      }
      res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ input_tokens: tokens }));
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const { port } = server.address() as AddressInfo;
  return { baseUrl: `http://127.0.0.1:${port}`, calls, close: () => new Promise<void>((r) => server.close(() => r())) };
}

export function pngHeader(w: number, h: number): Buffer {
  const b = Buffer.alloc(33);
  b.writeUInt32BE(0x89504e47, 0);
  b.writeUInt32BE(0x0d0a1a0a, 4);
  b.writeUInt32BE(13, 8);
  b.write("IHDR", 12, "ascii");
  b.writeUInt32BE(w, 16);
  b.writeUInt32BE(h, 20);
  return b;
}

export function jpegHeader(w: number, h: number): Buffer {
  // SOI, APP0(길이 16), SOF0(길이 17: 정밀도, 세로, 가로, ...)
  const app0 = Buffer.concat([Buffer.from([0xff, 0xe0, 0x00, 0x10]), Buffer.alloc(14)]);
  const sof = Buffer.alloc(19);
  sof.writeUInt16BE(0xffc0, 0);
  sof.writeUInt16BE(17, 2);
  sof[4] = 8;
  sof.writeUInt16BE(h, 5);
  sof.writeUInt16BE(w, 7);
  return Buffer.concat([Buffer.from([0xff, 0xd8]), app0, sof]);
}

export class MemorySink {
  records: Array<Record<string, any>> = [];
  write(r: Record<string, unknown>) { this.records.push(r); }
  of(kind: string) { return this.records.filter((r) => r.kind === kind); }
}
