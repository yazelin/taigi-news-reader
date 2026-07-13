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
