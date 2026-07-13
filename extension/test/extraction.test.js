const test = require("node:test");
const assert = require("node:assert/strict");
const { JSDOM } = require("jsdom");
const { extractFromDocument } = require("../src/lib/extraction");

function documentFor(html) {
  return new JSDOM(html, { url: "https://news.example/story" }).window.document;
}

test("extracts title and article paragraphs while excluding navigation", () => {
  const document = documentFor(`<!doctype html><title>網站標題</title>
    <nav>${"分類連結 ".repeat(80)}</nav>
    <article><h1>重要新聞標題</h1>
      <p>${"這是第一段新聞內容，提供事件背景與重要資訊。".repeat(5)}</p>
      <p>${"這是第二段新聞內容，說明後續影響與各方回應。".repeat(5)}</p>
      <aside><p>${"延伸閱讀".repeat(30)}</p></aside>
    </article>`);
  const result = extractFromDocument(document);
  assert.equal(result.title, "重要新聞標題");
  assert.match(result.body, /第一段新聞內容/);
  assert.match(result.body, /第二段新聞內容/);
  assert.doesNotMatch(result.body, /延伸閱讀/);
});

test("uses selected text when the page has no substantial article", () => {
  const document = documentFor("<main><p>短內容</p></main>");
  const selection = "這是使用者在新聞頁面上主動選取、希望以台語朗讀的一整段重要文字。";
  const result = extractFromDocument(document, selection);
  assert.equal(result.source, "selection");
  assert.equal(result.body, selection);
});

test("retains selection as an alternative when an article is found", () => {
  const document = documentFor(`<article><h1>標題</h1><p>${"完整新聞內容。".repeat(30)}</p></article>`);
  const selection = "使用者另外選取的這段文字內容足夠長，可以單獨朗讀。";
  const result = extractFromDocument(document, selection);
  assert.equal(result.source, "article");
  assert.equal(result.selectedText, selection);
});
