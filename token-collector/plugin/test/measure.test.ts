import { test } from "node:test";
import assert from "node:assert/strict";
import { contentOf, imageSize, measureContent } from "../src/measure.ts";
import { jpegHeader, pngHeader } from "./helpers.ts";

test("텍스트 바이트·글자 수·비ASCII 비율", () => {
  const m = measureContent([{ type: "text", text: "abc" }, { type: "text", text: "가나" }]);
  assert.equal(m.textBlocks, 2);
  assert.equal(m.textBytes, 3 + 6);
  assert.equal(m.textChars, 5);
  assert.equal(m.nonAsciiRatio, 0.4);
  assert.deepEqual(m.images, []);
});

test("이미지 헤더에서 픽셀 크기 읽기(PNG·JPEG·GIF·WebP)", () => {
  assert.deepEqual(imageSize(pngHeader(1920, 1080)), { width: 1920, height: 1080 });
  assert.deepEqual(imageSize(jpegHeader(1000, 750)), { width: 1000, height: 750 });
  const gif = Buffer.concat([Buffer.from("GIF89a", "ascii"), Buffer.from([0x40, 0x01, 0xf0, 0x00])]);
  assert.deepEqual(imageSize(gif), { width: 320, height: 240 });
  const webp = Buffer.alloc(30);
  webp.write("RIFF", 0, "ascii"); webp.write("WEBP", 8, "ascii"); webp.write("VP8X", 12, "ascii");
  webp.writeUIntLE(799, 24, 3); webp.writeUIntLE(599, 27, 3);
  assert.deepEqual(imageSize(webp), { width: 800, height: 600 });
  assert.deepEqual(imageSize(Buffer.from("not an image")), {});
});

test("이미지 블록은 크기와 형식만 남긴다", () => {
  const data = pngHeader(28, 56).toString("base64");
  const m = measureContent([{ type: "image", data, mimeType: "image/png" }]);
  assert.deepEqual(m.images, [{ mimeType: "image/png", bytes: 33, width: 28, height: 56 }]);
  assert.ok(!JSON.stringify(m).includes(data), "이미지 데이터가 측정값에 들어가면 안 됨");
});

test("content가 문자열이거나 없는 메시지", () => {
  assert.deepEqual(contentOf({ content: "hi" }), [{ type: "text", text: "hi" }]);
  assert.deepEqual(contentOf(undefined), []);
});
