const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.join(__dirname, "..");
const dist = path.join(root, "dist");
const release = path.join(root, "release");
const manifest = JSON.parse(fs.readFileSync(path.join(dist, "manifest.json"), "utf8"));
const artifact = path.join(release, `taigi-news-reader-${manifest.version}.zip`);

fs.mkdirSync(release, { recursive: true });
fs.rmSync(artifact, { force: true });

const zipped = spawnSync("zip", ["-X", "-q", "-r", artifact, "."], {
  cwd: dist,
  encoding: "utf8"
});
if (zipped.error?.code === "ENOENT") {
  throw new Error("找不到 zip 指令；請先安裝 Info-ZIP，再執行 npm run package:store。");
}
if (zipped.status !== 0) {
  throw new Error(`建立 ZIP 失敗：${zipped.stderr || zipped.stdout || `exit ${zipped.status}`}`);
}

const listed = spawnSync("unzip", ["-Z1", artifact], { encoding: "utf8" });
if (listed.error?.code === "ENOENT") {
  throw new Error("找不到 unzip 指令，無法驗證 release artifact。");
}
if (listed.status !== 0) throw new Error(`驗證 ZIP 失敗：${listed.stderr || listed.stdout}`);
const entries = listed.stdout.trim().split(/\r?\n/).filter(Boolean);
if (!entries.includes("manifest.json")) throw new Error("ZIP root 缺少 manifest.json。");
if (entries.some((entry) => entry.startsWith("dist/") || entry.startsWith("/") || entry.split("/").includes(".."))) {
  throw new Error("ZIP 必須直接包含 dist 內容，不可多包一層目錄或包含不安全路徑。");
}

const bytes = fs.readFileSync(artifact);
const digest = crypto.createHash("sha256").update(bytes).digest("hex");
console.log(`${path.relative(root, artifact)} ${bytes.length} bytes`);
console.log(`sha256 ${digest}`);
