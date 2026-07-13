const { normalizeText } = require("./chunk");

const NOISE_SELECTOR = [
  "script", "style", "noscript", "template", "svg", "canvas", "nav", "aside", "footer", "form",
  "[hidden]", "[aria-hidden='true']", ".advertisement", ".advert", ".ads", ".social", ".share",
  ".related", ".recommend", ".comments", "#comments"
].join(",");

function visibleText(element) {
  return normalizeText(element?.innerText || element?.textContent || "");
}

function linkDensity(element) {
  const textLength = visibleText(element).length || 1;
  const linkLength = [...element.querySelectorAll("a")]
    .reduce((sum, link) => sum + visibleText(link).length, 0);
  return linkLength / textLength;
}

function candidateScore(element) {
  const paragraphs = [...element.querySelectorAll("p")];
  const paragraphScore = paragraphs.reduce((sum, paragraph) => {
    const length = visibleText(paragraph).length;
    return length >= 25 ? sum + Math.min(length, 500) : sum;
  }, 0);
  const textLength = visibleText(element).length;
  const semanticBonus = element.matches("article, main, [role='main']") ? 450 : 0;
  const headingBonus = element.querySelector("h1") ? 150 : 0;
  return (paragraphScore + Math.min(textLength, 1600) * 0.15 + semanticBonus + headingBonus)
    * Math.max(0.05, 1 - linkDensity(element));
}

function bestCandidate(document) {
  const explicit = [
    ...document.querySelectorAll("article, main, [role='main'], [itemprop='articleBody'], .article-body, .article-content, .story-body, .post-content")
  ];
  const generic = [...document.querySelectorAll("body div, body section")]
    .filter((element) => element.querySelectorAll("p").length >= 2);
  const candidates = [...new Set([...explicit, ...generic])];
  return candidates.sort((a, b) => candidateScore(b) - candidateScore(a))[0] || document.body;
}

function extractCandidateText(element) {
  const clone = element.cloneNode(true);
  clone.querySelectorAll(NOISE_SELECTOR).forEach((node) => node.remove());
  const paragraphs = [...clone.querySelectorAll("p")]
    .map(visibleText)
    .filter((text) => text.length >= 20);
  if (paragraphs.join("").length >= 120) return normalizeText(paragraphs.join("\n\n"));
  return visibleText(clone);
}

function extractTitle(document) {
  const values = [
    document.querySelector("meta[property='og:title']")?.content,
    document.querySelector("meta[name='twitter:title']")?.content,
    visibleText(document.querySelector("article h1, main h1, h1")),
    document.title
  ];
  return normalizeText(values.find((value) => normalizeText(value)) || "未命名新聞").slice(0, 200);
}

function extractFromDocument(document, selectedText = "") {
  const selection = normalizeText(selectedText);
  const body = extractCandidateText(bestCandidate(document));
  const useSelection = body.length < 120 && selection.length >= 20;
  return {
    title: extractTitle(document),
    body: useSelection ? selection : body,
    selectedText: selection.length >= 20 ? selection : "",
    source: useSelection ? "selection" : "article",
    url: document.location?.href || ""
  };
}

module.exports = { candidateScore, extractFromDocument, extractTitle, linkDensity };
