const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.join(__dirname, "..");
const dist = path.join(root, "dist");
const release = path.join(root, "release");
const manifest = JSON.parse(fs.readFileSync(path.join(dist, "manifest.json"), "utf8"));
const artifact = path.join(release, `taigi-news-reader-${manifest.version}.zip`);
const reproducibilityArtifact = path.join(release, `.taigi-news-reader-${manifest.version}.reproducibility.zip`);
const normalizedTimestamp = new Date("2000-01-01T00:00:00.000Z");
const expectedFileCount = 15;

fs.mkdirSync(release, { recursive: true });
fs.rmSync(artifact, { force: true });
fs.rmSync(reproducibilityArtifact, { force: true });

function packagedFiles(directory = dist) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) {
      throw new Error(`release package 不可包含 symlink：${path.relative(dist, file)}`);
    }
    if (entry.isDirectory()) return packagedFiles(file);
    if (!entry.isFile()) throw new Error(`release package 含有不支援的檔案類型：${path.relative(dist, file)}`);
    return [path.relative(dist, file).replaceAll(path.sep, "/")];
  });
}

const files = packagedFiles().sort();
if (files.length !== expectedFileCount) {
  throw new Error(`ZIP 預期包含 ${expectedFileCount} 個檔案，實際為 ${files.length}；若 package layout 有意變更，請同步更新 release audit。`);
}
if (!files.includes("manifest.json")) throw new Error("待包內容 root 缺少 manifest.json。");
if (files.some((entry) => entry.startsWith("dist/") || entry.startsWith("/") || entry.split("/").includes(".."))) {
  throw new Error("待包內容不可多包一層 dist 或包含不安全路徑。");
}
for (const file of files) {
  fs.utimesSync(path.join(dist, file), normalizedTimestamp, normalizedTimestamp);
}

function createZip(destination) {
  const zipped = spawnSync("zip", ["-X", "-q", destination, ...files], {
    cwd: dist,
    encoding: "utf8",
    env: { ...process.env, TZ: "UTC" }
  });
  if (zipped.error?.code === "ENOENT") {
    throw new Error("找不到 zip 指令；請先安裝 Info-ZIP，再執行 npm run package:store。");
  }
  if (zipped.status !== 0) {
    throw new Error(`建立 ZIP 失敗：${zipped.stderr || zipped.stdout || `exit ${zipped.status}`}`);
  }
}

function auditZip(file) {
  const listed = spawnSync("unzip", ["-Z1", file], {
    encoding: "utf8",
    env: { ...process.env, TZ: "UTC" }
  });
  if (listed.error?.code === "ENOENT") {
    throw new Error("找不到 unzip 指令，無法驗證 release artifact。");
  }
  if (listed.status !== 0) throw new Error(`驗證 ZIP 失敗：${listed.stderr || listed.stdout}`);
  const entries = listed.stdout.trim().split(/\r?\n/).filter(Boolean);
  if (!entries.includes("manifest.json")) throw new Error("ZIP root 缺少 manifest.json。");
  if (entries.some((entry) => entry.startsWith("dist/") || entry.startsWith("/") || entry.split("/").includes(".."))) {
    throw new Error("ZIP 必須直接包含 dist 內容，不可多包一層目錄或包含不安全路徑。");
  }
  if (entries.length !== expectedFileCount || entries.some((entry, index) => entry !== files[index])) {
    throw new Error("ZIP entries 必須與排序後的 explicit file list 完全一致。");
  }
  return entries;
}

function digest(file) {
  const bytes = fs.readFileSync(file);
  return {
    bytes: bytes.length,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex")
  };
}

createZip(artifact);
const entries = auditZip(artifact);
const packaged = digest(artifact);

try {
  createZip(reproducibilityArtifact);
  auditZip(reproducibilityArtifact);
  const reproduced = digest(reproducibilityArtifact);
  if (packaged.sha256 !== reproduced.sha256 || packaged.bytes !== reproduced.bytes) {
    throw new Error(`連續兩次 package 不可重現：${packaged.sha256} != ${reproduced.sha256}`);
  }
} finally {
  fs.rmSync(reproducibilityArtifact, { force: true });
}

console.log(`${path.relative(root, artifact)} ${packaged.bytes} bytes, ${entries.length} files`);
console.log(`sha256 ${packaged.sha256}`);
console.log(`reproducibility passed: 2 identical packages, root manifest.json, ${entries.length} sorted files`);
