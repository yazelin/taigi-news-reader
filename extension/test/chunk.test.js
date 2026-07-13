const test = require("node:test");
const assert = require("node:assert/strict");
const { chunkText, normalizeText } = require("../src/lib/chunk");

test("normalizes whitespace while retaining paragraph boundaries", () => {
  assert.equal(normalizeText("  第一段。\r\n\r\n\r\n 第二段。  "), "第一段。\n\n第二段。");
});

test("chunks at paragraph boundaries and respects maximum length", () => {
  const chunks = chunkText(`${"甲".repeat(80)}\n\n${"乙".repeat(80)}`, 100);
  assert.deepEqual(chunks, ["甲".repeat(80), "乙".repeat(80)]);
  assert.ok(chunks.every((chunk) => chunk.length <= 100));
});

test("splits a long paragraph near punctuation", () => {
  const chunks = chunkText(`${"甲".repeat(55)}。${"乙".repeat(55)}。`, 70);
  assert.equal(chunks.length, 2);
  assert.ok(chunks[0].endsWith("。"));
});
