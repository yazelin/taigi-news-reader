const esbuild = require("esbuild");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const source = path.join(root, "src");
const destination = path.join(root, "dist");

fs.rmSync(destination, { recursive: true, force: true });
fs.mkdirSync(destination, { recursive: true });

for (const file of [
  "manifest.json",
  "sidepanel.html",
  "sidepanel.css",
  "options.html",
  "options.css",
  "offscreen.html"
]) {
  fs.copyFileSync(path.join(source, file), path.join(destination, file));
}

esbuild.buildSync({
  entryPoints: {
    sidepanel: path.join(source, "sidepanel.js"),
    options: path.join(source, "options.js"),
    service_worker: path.join(source, "service-worker.js"),
    offscreen: path.join(source, "offscreen.js"),
    extractor: path.join(source, "content", "extractor.js")
  },
  bundle: true,
  outdir: destination,
  platform: "browser",
  target: "chrome116",
  format: "iife",
  sourcemap: false,
  legalComments: "none"
});
