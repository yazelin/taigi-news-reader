const { extractFromDocument } = require("../lib/extraction");

globalThis.TaigiNewsExtractor = {
  extract() {
    return extractFromDocument(document, globalThis.getSelection?.().toString() || "");
  }
};
