// 도구 결과 메시지의 크기·특징값을 잰다. 결과 내용 자체는 밖으로 내보내지 않는다.
//
// OpenClaw 도구 결과 메시지(ToolResultMessage)의 content는 텍스트 블록({type:"text", text})과
// 이미지 블록({type:"image", data: base64, mimeType})의 배열이다(packages/llm-core/src/types.ts).

export type ContentBlock = { type: string; text?: string; data?: string; mimeType?: string };

export type ImageInfo = { mimeType: string; bytes: number; width?: number; height?: number };

export type ResultMeasure = {
  textBlocks: number;
  textBytes: number; // UTF-8 바이트 수
  textChars: number; // 코드 포인트 수
  nonAsciiRatio: number; // 0~1, 한글 등 비ASCII 글자 비율
  images: ImageInfo[];
  otherBlocks: number; // 텍스트·이미지가 아닌 블록 수
};

export function contentOf(message: unknown): ContentBlock[] {
  const c = (message as { content?: unknown } | undefined)?.content;
  if (typeof c === "string") return [{ type: "text", text: c }];
  return Array.isArray(c) ? (c.filter((b) => b && typeof b === "object") as ContentBlock[]) : [];
}

export function measureContent(blocks: ContentBlock[]): ResultMeasure {
  let textBlocks = 0, textBytes = 0, textChars = 0, nonAscii = 0, otherBlocks = 0;
  const images: ImageInfo[] = [];
  for (const b of blocks) {
    if (b.type === "text" && typeof b.text === "string") {
      textBlocks++;
      textBytes += Buffer.byteLength(b.text, "utf8");
      for (const ch of b.text) {
        textChars++;
        if (ch.codePointAt(0)! > 0x7f) nonAscii++;
      }
    } else if (b.type === "image" && typeof b.data === "string") {
      const buf = Buffer.from(b.data, "base64");
      images.push({ mimeType: b.mimeType ?? "unknown", bytes: buf.length, ...imageSize(buf) });
    } else {
      otherBlocks++;
    }
  }
  return {
    textBlocks, textBytes, textChars,
    nonAsciiRatio: textChars ? Math.round((nonAscii / textChars) * 1000) / 1000 : 0,
    images, otherBlocks,
  };
}

// imageSize는 PNG·JPEG·GIF·WebP 헤더에서 가로·세로 픽셀을 읽는다. 모르면 빈 객체.
export function imageSize(b: Buffer): { width?: number; height?: number } {
  // PNG: 8바이트 시그니처 + IHDR(가로·세로 4바이트 빅엔디언)
  if (b.length >= 24 && b.readUInt32BE(0) === 0x89504e47 && b.toString("ascii", 12, 16) === "IHDR") {
    return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
  }
  // GIF: "GIF8" + 가로·세로 2바이트 리틀엔디언
  if (b.length >= 10 && b.toString("ascii", 0, 4) === "GIF8") {
    return { width: b.readUInt16LE(6), height: b.readUInt16LE(8) };
  }
  // WebP: RIFF....WEBP + VP8 / VP8L / VP8X
  if (b.length >= 30 && b.toString("ascii", 0, 4) === "RIFF" && b.toString("ascii", 8, 12) === "WEBP") {
    const kind = b.toString("ascii", 12, 16);
    if (kind === "VP8X") return { width: 1 + b.readUIntLE(24, 3), height: 1 + b.readUIntLE(27, 3) };
    if (kind === "VP8L") {
      const v = b.readUInt32LE(21);
      return { width: (v & 0x3fff) + 1, height: ((v >> 14) & 0x3fff) + 1 };
    }
    if (kind === "VP8 ") return { width: b.readUInt16LE(26) & 0x3fff, height: b.readUInt16LE(28) & 0x3fff };
  }
  // JPEG: SOFn 마커(C0~CF, 단 C4·C8·CC 제외)에서 세로·가로
  if (b.length >= 4 && b[0] === 0xff && b[1] === 0xd8) {
    let i = 2;
    while (i + 9 < b.length) {
      if (b[i] !== 0xff) { i++; continue; }
      const m = b[i + 1];
      if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) { i += 2; continue; }
      const len = b.readUInt16BE(i + 2);
      if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
        return { height: b.readUInt16BE(i + 5), width: b.readUInt16BE(i + 7) };
      }
      i += 2 + len;
    }
  }
  return {};
}
