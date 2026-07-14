const assert = require("node:assert/strict");
const { existsSync, readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const test = require("node:test");
const { JSDOM } = require("jsdom");

const repositoryRoot = resolve(__dirname, "../..");
const canonicalUrl = "https://yazelin.github.io/taigi-news-reader/";
const imageUrl = `${canonicalUrl}assets/og-image.png`;

function pageDocument() {
  const html = readFileSync(resolve(repositoryRoot, "index.html"), "utf8");
  return new JSDOM(html).window.document;
}

function content(document, selector, attribute = "content") {
  const element = document.querySelector(selector);
  assert.ok(element, `Missing ${selector}`);
  const value = element.getAttribute(attribute);
  assert.ok(value, `Empty ${selector}`);
  return value;
}

test("Pages landing exposes complete canonical, Open Graph, and Twitter metadata", () => {
  const document = pageDocument();

  assert.ok(document.title.includes("台語新聞朗讀"));
  assert.equal(document.querySelector("#hero-title").textContent, "新聞，我講給你聽");
  assert.ok(content(document, "meta[name='description']"));
  assert.equal(content(document, "link[rel='canonical']", "href"), canonicalUrl);

  assert.equal(content(document, "meta[property='og:url']"), canonicalUrl);
  assert.equal(content(document, "meta[property='og:type']"), "website");
  assert.equal(content(document, "meta[property='og:locale']"), "zh_TW");
  assert.ok(content(document, "meta[property='og:title']"));
  assert.ok(content(document, "meta[property='og:description']"));
  assert.equal(content(document, "meta[property='og:image']"), imageUrl);
  assert.equal(content(document, "meta[property='og:image:width']"), "1200");
  assert.equal(content(document, "meta[property='og:image:height']"), "630");
  assert.ok(content(document, "meta[property='og:image:alt']"));

  assert.equal(
    content(document, "meta[name='twitter:card']"),
    "summary_large_image",
  );
  assert.ok(content(document, "meta[name='twitter:title']"));
  assert.ok(content(document, "meta[name='twitter:description']"));
  assert.equal(content(document, "meta[name='twitter:image']"), imageUrl);
  assert.ok(content(document, "meta[name='twitter:image:alt']"));

  const structuredData = JSON.parse(
    document.querySelector("script[type='application/ld+json']").textContent,
  );
  assert.equal(structuredData["@type"], "SoftwareApplication");
  assert.equal(structuredData.url, canonicalUrl);
  assert.equal(structuredData.image, imageUrl);
  assert.equal("offers" in structuredData, false);
  assert.equal("isAccessibleForFree" in structuredData, false);
});

test("Pages distinguishes the hosted demo from private self-hosting", () => {
  const document = pageDocument();
  const ways = document.querySelector("#ways-to-use");
  const selfHosting = document.querySelector("#self-hosting");
  const faq = document.querySelector("#faq");

  assert.ok(ways);
  assert.match(ways.textContent, /邀請制免費私人測試/);
  assert.match(ways.textContent, /20 個工作/);
  assert.match(ways.textContent, /12,000 個原文字元/);
  assert.match(ways.textContent, /台灣時間 08:00/);
  assert.match(ways.textContent, /不代表永久免費/);
  assert.match(ways.textContent, /自架.*不一定等於.*完全不離開/s);

  assert.ok(selfHosting);
  assert.match(selfHosting.textContent, /Groq／Gemini／OpenAI-compatible／Ollama/);
  assert.match(selfHosting.textContent, /provider API key 不會寫進擴充套件/);
  assert.match(selfHosting.textContent, /localhost.*127\.0\.0\.1.*HTTP/s);
  assert.match(selfHosting.textContent, /HTTPS hostname/);
  assert.match(selfHosting.textContent, /CC BY-NC 4\.0/);

  assert.ok(faq);
  assert.match(faq.textContent, /一定要安裝 Qwen 或 Ollama 嗎/);
  assert.match(faq.textContent, /擴充套件只設定相容後端的 URL 與邀請碼/);
  assert.match(faq.textContent, /provider key 應保存在自架後端/);

  for (const link of document.querySelectorAll("a[href^='#']")) {
    const id = link.getAttribute("href").slice(1);
    assert.ok(document.getElementById(id), `Missing internal target #${id}`);
  }
});

test("README provides stable hosted and self-hosting routes", () => {
  const readme = readFileSync(resolve(repositoryRoot, "README.md"), "utf8");

  assert.match(readme, /<a id="hosted-private-beta"><\/a>/);
  assert.match(readme, /<a id="self-hosting"><\/a>/);
  assert.match(readme, /不能直接填 Groq、Gemini 或 TTS key/);
  assert.match(readme, /http:\/\/192\.168\.11\.11:8765` \| 否/);
  assert.match(readme, /demo profile.*不是寫死在 Chrome 擴充套件/s);

  const relativeLinks = readme.matchAll(/\]\((?!https?:\/\/|#)([^\s)#]+)(?:#[^)]+)?\)/g);
  for (const match of relativeLinks) {
    const target = resolve(repositoryRoot, decodeURIComponent(match[1]));
    assert.ok(existsSync(target), `Missing README link target ${match[1]}`);
  }
});

test("Open Graph PNG is present at exactly 1200 by 630 pixels", () => {
  const imagePath = resolve(repositoryRoot, "assets/og-image.png");
  const image = readFileSync(imagePath);

  assert.deepEqual(
    [...image.subarray(0, 8)],
    [137, 80, 78, 71, 13, 10, 26, 10],
  );
  assert.equal(image.readUInt32BE(16), 1200);
  assert.equal(image.readUInt32BE(20), 630);
  assert.ok(existsSync(resolve(repositoryRoot, "assets/og-image.svg")));
  assert.ok(existsSync(resolve(repositoryRoot, "assets/site.css")));
});

test("robots and sitemap point crawlers at the canonical Pages URL", () => {
  const robots = readFileSync(resolve(repositoryRoot, "robots.txt"), "utf8");
  const sitemap = readFileSync(resolve(repositoryRoot, "sitemap.xml"), "utf8");

  assert.match(robots, /User-agent: \*/);
  assert.match(robots, /Allow: \//);
  assert.match(robots, new RegExp(`${canonicalUrl}sitemap\\.xml`));
  assert.match(sitemap, new RegExp(`<loc>${canonicalUrl}</loc>`));
});
