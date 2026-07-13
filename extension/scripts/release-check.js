const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const sourceManifestPath = path.join(root, "src", "manifest.json");
const dist = path.join(root, "dist");
const distManifestPath = path.join(dist, "manifest.json");
const packagePath = path.join(root, "package.json");
const packageLockPath = path.join(root, "package-lock.json");

const errors = [];
const warnings = [];

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    errors.push(`${path.relative(root, file)} 無法讀取或不是有效 JSON：${error.message}`);
    return {};
  }
}

function requireCondition(condition, message) {
  if (!condition) errors.push(message);
}

function validVersion(version) {
  if (typeof version !== "string") return false;
  const parts = version.split(".");
  return parts.length >= 1 && parts.length <= 4 && parts.every((part) =>
    /^(0|[1-9]\d*)$/.test(part) && Number(part) <= 65535);
}

function extensionIdFromManifestKey(value) {
  if (typeof value !== "string" || !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) {
    throw new Error("manifest key 必須是無換行的 Base64 SPKI public key");
  }
  const der = Buffer.from(value, "base64");
  if (!der.length || der.toString("base64") !== value) {
    throw new Error("manifest key 必須是 canonical Base64");
  }
  const publicKey = crypto.createPublicKey({ key: der, format: "der", type: "spki" });
  if (publicKey.asymmetricKeyType !== "rsa") {
    throw new Error("manifest key 必須是 RSA public key");
  }
  const canonicalDer = publicKey.export({ format: "der", type: "spki" });
  if (!canonicalDer.equals(der)) {
    throw new Error("manifest key 必須是 canonical SPKI DER");
  }
  const prefix = crypto.createHash("sha256").update(der).digest("hex").slice(0, 32);
  return [...prefix]
    .map((nibble) => String.fromCharCode("a".charCodeAt(0) + Number.parseInt(nibble, 16)))
    .join("");
}

function walk(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) {
      errors.push(`release package 不可包含 symlink：${path.relative(dist, file)}`);
      return [];
    }
    return entry.isDirectory() ? walk(file) : [file];
  });
}

function localPath(value) {
  return typeof value === "string" && value && !/^(?:[a-z]+:|\/\/|\/)/i.test(value) && !value.split(/[\\/]/).includes("..");
}

function checkPackagedReference(value, label) {
  requireCondition(localPath(value), `${label} 必須是 package 內的相對路徑`);
  if (localPath(value)) {
    requireCondition(fs.existsSync(path.join(dist, value)), `${label} 指向不存在的檔案：${value}`);
  }
}

function pngDimensions(file) {
  try {
    const data = fs.readFileSync(file);
    const signature = "89504e470d0a1a0a";
    if (data.length < 24 || data.subarray(0, 8).toString("hex") !== signature) return null;
    return { width: data.readUInt32BE(16), height: data.readUInt32BE(20) };
  } catch {
    return null;
  }
}

function checkPngIcon(value, label, size) {
  checkPackagedReference(value, label);
  if (!localPath(value) || !fs.existsSync(path.join(dist, value))) return;
  const dimensions = pngDimensions(path.join(dist, value));
  requireCondition(dimensions?.width === size && dimensions?.height === size,
    `${label} 必須是實際 ${size}x${size} PNG`);
}

const sourceManifest = readJson(sourceManifestPath);
const manifest = readJson(distManifestPath);
const packageJson = readJson(packagePath);
const packageLock = readJson(packageLockPath);

let derivedCwsItemId = null;
try {
  derivedCwsItemId = extensionIdFromManifestKey(manifest.key);
} catch (error) {
  errors.push(`manifest key 無法推導 Chrome extension ID：${error.message}`);
}

requireCondition(fs.existsSync(dist), "缺少 dist；請先執行 npm run build");
requireCondition(manifest.manifest_version === 3, "Chrome Web Store package 必須使用 Manifest V3");
requireCondition(typeof manifest.name === "string" && manifest.name.length > 0 && [...manifest.name].length <= 75,
  "manifest name 必須為 1–75 字元");
requireCondition(typeof manifest.description === "string" && manifest.description.length > 0 && [...manifest.description].length <= 132,
  "manifest description 必須為 1–132 字元");
requireCondition(validVersion(manifest.version), "manifest version 必須是 1–4 段、每段 0–65535 的整數");
requireCondition(manifest.version === packageJson.version, "manifest.json 與 package.json version 必須一致");
requireCondition(packageLock.version === packageJson.version, "package-lock.json root version 必須與 package.json 一致");
requireCondition(packageLock.packages?.[""]?.version === packageJson.version,
  "package-lock.json packages root version 必須與 package.json 一致");
requireCondition(JSON.stringify(manifest) === JSON.stringify(sourceManifest), "dist/manifest.json 必須與 src/manifest.json 完全一致");
requireCondition(/^[a-p]{32}$/.test(packageJson.cwsItemId || ""), "package.json cwsItemId 必須是 32 字元 Chrome Item ID");
requireCondition(derivedCwsItemId === packageJson.cwsItemId,
  `manifest key 推導的 ID ${derivedCwsItemId || "<invalid>"} 與 cwsItemId ${packageJson.cwsItemId || "<missing>"} 不一致`);

const requiredPermissions = ["activeTab", "scripting", "sidePanel", "offscreen", "storage"];
const permissions = Array.isArray(manifest.permissions) ? manifest.permissions : [];
for (const permission of requiredPermissions) {
  requireCondition(permissions.includes(permission), `目前功能需要 manifest permission：${permission}`);
}
for (const permission of permissions) {
  requireCondition(requiredPermissions.includes(permission), `未經 release audit 的 permission：${permission}`);
}
requireCondition(!permissions.includes("unlimitedStorage"), "不得加入 unlimitedStorage");
requireCondition(!Array.isArray(manifest.host_permissions) || manifest.host_permissions.length === 0,
  "新聞頁存取應使用 activeTab；不可加入持久 host_permissions");

const optionalHosts = Array.isArray(manifest.optional_host_permissions) ? manifest.optional_host_permissions : [];
requireCondition(optionalHosts.length > 0, "語音服務連線需要 optional_host_permissions");
for (const pattern of optionalHosts) {
  requireCondition(!["<all_urls>", "*://*/*", "http://*/*"].includes(pattern),
    `optional host pattern 過寬或允許一般明文 HTTP：${pattern}`);
}

const extensionCsp = manifest.content_security_policy?.extension_pages || "";
requireCondition(extensionCsp.includes("script-src 'self'"), "extension CSP 必須把 script-src 限制為 'self'");
requireCondition(!/(?:unsafe-eval|https?:|data:|blob:)/i.test(extensionCsp), "extension CSP 不可允許遠端或動態程式碼來源");

checkPackagedReference(manifest.background?.service_worker, "background.service_worker");
checkPackagedReference(manifest.side_panel?.default_path, "side_panel.default_path");
checkPackagedReference(manifest.options_page, "options_page");

requireCondition(manifest.icons && typeof manifest.icons === "object", "Chrome Web Store package 缺少 manifest icons");
for (const size of [16, 32, 48, 128]) {
  const icon = manifest.icons?.[String(size)];
  if (!icon) {
    if (size === 128) errors.push("Chrome Web Store package 缺少 128x128 manifest icon");
    else warnings.push(`建議補上 ${size}x${size} manifest icon`);
  } else {
    checkPngIcon(icon, `icons.${size}`, size);
  }
}

if (manifest.action?.default_icon && typeof manifest.action.default_icon === "object") {
  for (const [sizeText, icon] of Object.entries(manifest.action.default_icon)) {
    const size = Number(sizeText);
    requireCondition(Number.isInteger(size) && size > 0, `action.default_icon size 無效：${sizeText}`);
    if (Number.isInteger(size) && size > 0) checkPngIcon(icon, `action.default_icon.${sizeText}`, size);
  }
}

const files = walk(dist);
let totalBytes = 0;
for (const file of files) {
  const relative = path.relative(dist, file).replaceAll(path.sep, "/");
  const stat = fs.statSync(file);
  totalBytes += stat.size;
  requireCondition(!/(?:^|\/)(?:\.env(?:\.|$)|node_modules|test|tests)(?:\/|$)/i.test(relative),
    `package 含有不應發佈的檔案：${relative}`);
  requireCondition(!/\.(?:map|pem|key|p12|log)$/i.test(relative), `package 含有不應發佈的檔案：${relative}`);
  requireCondition(!/\.wasm$/i.test(relative), `新增 WASM 前必須重新做 remote-code／CSP 稽核：${relative}`);

  if (/\.(?:js|html|css|json)$/i.test(relative)) {
    const text = fs.readFileSync(file, "utf8");
    requireCondition(!/(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z_-]{20,}|gsk_[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,})/.test(text),
      `package 疑似含有 secret：${relative}`);
    if (/\.js$/i.test(relative)) {
      requireCondition(!/(?:\beval\s*\(|\bnew\s+Function\s*\(|\bimportScripts\s*\(\s*["']https?:|\bimport\s*\(\s*["']https?:)/.test(text),
        `package 疑似執行遠端或動態程式碼：${relative}`);
    }
    if (/\.html$/i.test(relative)) {
      for (const match of text.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
        const attributes = match[1];
        const body = match[2].trim();
        const source = attributes.match(/\bsrc=["']([^"']+)["']/i)?.[1];
        requireCondition(Boolean(source) && localPath(source), `${relative} 的 script 必須引用 package 內檔案`);
        requireCondition(!body, `${relative} 不可包含 inline script`);
        if (source && localPath(source)) checkPackagedReference(source, `${relative} script src`);
      }
      requireCondition(!/<(?:script|link)\b[^>]+(?:src|href)=["']https?:/i.test(text),
        `${relative} 不可載入遠端 script／stylesheet`);
    }
  }
}

requireCondition(files.length > 0, "dist 是空的");
requireCondition(totalBytes < 2 * 1024 * 1024 * 1024, "package 超過 Chrome Web Store 2 GB 上限");

for (const warning of warnings) console.warn(`WARN: ${warning}`);
if (errors.length) {
  for (const error of errors) console.error(`ERROR: ${error}`);
  console.error(`Chrome Web Store package audit failed with ${errors.length} error(s).`);
  process.exitCode = 1;
} else {
  console.log(`Chrome Web Store package audit passed: ${files.length} files, ${totalBytes} bytes, version ${manifest.version}.`);
  console.log(`CWS Item ID verified from manifest public key: ${derivedCwsItemId}.`);
  console.log("Dashboard listing, privacy policy URL, screenshots, promo image, reviewer backend, and account checks remain manual release gates.");
}
