function normalizeText(text) {
  return String(text || "")
    .replace(/\r\n?/g, "\n")
    .replace(/[\t\u00a0 ]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function splitLongParagraph(paragraph, maxLength) {
  const result = [];
  let remaining = paragraph.trim();
  while (remaining.length > maxLength) {
    const window = remaining.slice(0, maxLength + 1);
    const candidates = ["。", "！", "？", "；", "，", " "];
    let cut = -1;
    for (const separator of candidates) {
      cut = Math.max(cut, window.lastIndexOf(separator));
    }
    if (cut < Math.floor(maxLength * 0.45)) cut = maxLength;
    else cut += 1;
    result.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) result.push(remaining);
  return result;
}

function chunkText(text, maxLength = 500) {
  if (maxLength < 50) throw new Error("maxLength must be at least 50");
  const normalized = normalizeText(text);
  if (!normalized) return [];

  const paragraphs = normalized.split(/\n+/).flatMap((part) => splitLongParagraph(part, maxLength));
  const chunks = [];
  let current = "";
  for (const paragraph of paragraphs) {
    const combined = current ? `${current}\n${paragraph}` : paragraph;
    if (combined.length <= maxLength) current = combined;
    else {
      if (current) chunks.push(current);
      current = paragraph;
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

module.exports = { normalizeText, chunkText };
