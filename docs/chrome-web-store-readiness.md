# Chrome Web Store 發佈 readiness 稽核

稽核日期：2026-07-13

結論：**正式 Item ID 已固定，`0.1.1` package 工程基線已完成，可更新 Dashboard 草稿，但目前仍不可按 Submit for Review。** Dashboard 提供的 public key 已放入 manifest，Chrome 實際載入也確認為同一個正式 ID；更新草稿不等於送審或發佈。下列人工／營運 blockers 完成前，不應提交審查。

本稽核以 2026-07 可取得的 Chrome 官方文件為準；provider data gate 另只引用 Groq／Google 官方文件。

## Release blockers

| 優先級 | Blocker | 完成條件 |
| --- | --- | --- |
| P0 | 推薦 backend 的資料處理尚未完成 release attestation | 正式 extension ID 已由 Dashboard public key 固定為 `nejhlfbnjkbdjcaaklaofggkikdlpakn`，並以過渡期 dual allowlist 部署到 edge／backend。仍須在 Groq Console 對 production project 啟用 ZDR、輪替曾曝光的 key、確認不用 batch／fine-tuning／retention feature，並保存不含內容的設定截圖／日期作 release evidence。 |
| P0 | Gemini Free 與 CWS Limited Use 風險 | 公開推薦 endpoint 不得使用 Gemini unpaid quota。Gemini 保留為 self-hosted optional adapter；若未來要公開採用，只能在重新做 provider terms／privacy review、更新 UI／listing／policy 後切換。Google 官方條款明載 unpaid inputs／outputs 可用於改善產品且可能由 human reviewers 處理。 |
| P0 | Dashboard privacy disclosures 尚未人工確認 | `https://github.com/yazelin/taigi-news-reader/blob/main/PRIVACY.md` 已在 push 後以未登入 HTTP client 確認回 200；仍須逐字核對 policy、套件內告知、listing 與實際 production provider/logging，並在 Dashboard 填 Website content、single purpose、permission justifications、remote code=No、Limited Use certifications。 |
| P0 | Store listing graphics／metadata 上傳 | Repo 已有 128 icon、`extension/store-assets/screenshot-reader-1280x800.png` 真實 Chrome UI 截圖與 `extension/store-assets/promo-440x280.png`；仍須在 Dashboard 上傳這些素材，並填詳細描述、語言、分類與 support。缺 screenshot 或必填欄位會被拒絕。 |
| P0 | Reviewer 可用性／production service | **2026-07-13 LAN root deployment 已完成：** `https://ching-tech.ddns.net/taigi-tts/health` 在允許網段直接回 200 JSON，且實際 Groq＋MMS job 已完成 WAV 與 DELETE cleanup；不再 301 到公司首頁。但 production 刻意只允許 `192.168.11.0/24`，外部 CWS reviewer 無法重現。送審前仍須提供安全、可供 reviewer 使用且不把共用 secret 包進 extension 的路徑，並寫入 notes。固定 extension header／Origin 都可偽造，不能單獨作為公網 authentication。 |
| P0 | Publisher account 外部作業 | 以長期維護信箱註冊並付一次性費用、啟用 Google Account 2-Step Verification、確認聯絡資訊；選 Private trusted testers 或其他 distribution。這些無法由 repo 自動驗證。 |

官方依據：Chrome 要求 manifest root ZIP、name／version／icons／description，且每次更新 version 必須增加；見 [Prepare your extension](https://developer.chrome.com/docs/webstore/prepare)。Listing 缺 description、icon 或 screenshots 會被拒；圖像尺寸見 [Supplying Images](https://developer.chrome.com/docs/webstore/images)。處理 website content，即使只存在本機，也要揭露並提供 privacy policy；見 [User Data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq/) 與 [Privacy practices](https://developer.chrome.com/docs/webstore/cws-dashboard-privacy)。

Dashboard 允許先上傳 ZIP 後編輯草稿，直到按 Submit for Review 才進入審查；官方也明確說明可在未發佈前由 Package 頁取得 public key 來固定開發版 ID，見 [Publish in the Chrome Web Store](https://developer.chrome.com/docs/webstore/publish/) 與 [Manifest `key`](https://developer.chrome.com/docs/extensions/reference/manifest/key)。2026-08-01 開始施行的更新要求對所有資料處理做顯著揭露，因此本案從 first release 就以較嚴格版本填寫 UI、listing 與 Dashboard；見 [2026 policy update](https://developer.chrome.com/blog/cws-policy-updates-2026)。

Groq 官方說明指出 inference inputs／outputs 預設不保留，但 reliability／abuse logs 最多可能保留 30 天，所有客戶可啟用 ZDR；見 [Your Data in GroqCloud](https://console.groq.com/docs/your-data)。Groq 的 [Services Agreement](https://console.groq.com/docs/legal/services-agreement) 說 Inputs／Outputs 不用於 training／fine-tuning，除非 customer 明確授權。相較之下，[Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) 說 Unpaid Services 內容可用於改善產品並可能由 human reviewers 處理；Chrome [Limited Use](https://developer.chrome.com/docs/webstore/program-policies/limited-use) 對 human access／data transfer 有嚴格限制。

## 已通過的 repo 檢查

- Manifest V3、`minimum_chrome_version=116`、name／version／description 格式有效；source manifest、package 與 lockfile root version 都是 `0.1.1`，高於先前草稿的 `0.1.0`。
- Manifest 的 canonical RSA SPKI public key 推導出正式 CWS Item ID `nejhlfbnjkbdjcaaklaofggkikdlpakn`。`npm run release:check` 會重新解析 public key、驗證 RSA／canonical DER，並要求推導 ID 與 `package.json.cwsItemId` 完全相同；隔離 Chrome 實際載入 `dist/` 時也觀察到同一 service-worker origin 與 `0.1.1` registration。
- Manifest 已改用不保證翻譯／發音品質的保守描述：「把你確認的繁體中文新聞文字送到已設定的台語語音服務，並在 Chrome 播放。」母語者／長輩品質驗收完成前不可改回「自然台語」或其他超出證據的宣稱；metadata 變更需 bump version 重包。
- Required permissions 都有實際用途：`activeTab` + `scripting` 只在 action／使用者操作後擷取目前頁面；`sidePanel` 提供 UI；`offscreen` 只做 Blob／audio；`storage` 保存設定、session cleanup 與 opt-in replay。
- 沒有 `tabs`、persistent `host_permissions`、`<all_urls>`、`unlimitedStorage`、cookies、history、webRequest 或 telemetry permission。
- Backend host access 是 `optional_host_permissions`；設定頁只在使用者按下同意儲存後，runtime-request 該 URL 的 exact origin。Chrome 官方也建議可行時使用 optional permission；見 [Declare permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions)。
- Extension 的共用 backend fetch wrapper 會在 `/health`、job POST、每次 GET poll 及 DELETE 強制覆寫 `X-Taigi-Extension-Id` 為 `chrome.runtime.id`；caller 不能換值。Backend／edge strict mode 對非-preflight `/v1/` 要求 ID 精確命中 allowlist，缺少／錯誤 header 或 header 與已存在 Origin 不一致都回 403。Chrome GET 可能不帶 Origin，因此正確 header 的無 Origin request 可接受；preflight 仍要求 exact extension Origin 並協商自訂 header。
- 這個 header 與 Origin 都是公開識別、可由非瀏覽器偽造，不能描述成 API key、authentication 或防止所有濫用。目標 LAN 部署仍由 subnet allowlist、per-IP rate／connection limit、request size／active-job cap 與 HTTPS 構成邊界；`/health` 不要求 header，只受 LAN／health limits 保護。若 reviewer endpoint 會暴露公網，必須另行完成適合公網的 authentication／abuse review。
- Extension CSP 是 `script-src 'self'; object-src 'self'`。所有 HTML script 都是 package-local；source／dist scan 沒有 `eval`、`new Function`、remote script、dynamic remote import 或 WASM。Backend response 是 JSON／audio data，並非 remotely hosted code；符合 [Manifest V3 remote code policy](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code)。
- esbuild 沒有 source map、沒有 obfuscation／minification，package 不含 tests、`node_modules`、provider keys、model weights或 backend secrets。官方 review 文件指出 broad host／sensitive execution 與難讀 code 會延長審查；目前 compiled code 可讀，但 `https://*/*` 仍需 review notes 詳細解釋，見 [Review process](https://developer.chrome.com/docs/webstore/review-process)。
- Store small promo 已有實際 440x280 PNG；另已用 production `dist/` 的 isolated Chromium profile 拍攝真實 1280x800 新聞頁＋side panel 內容確認畫面 `extension/store-assets/screenshot-reader-1280x800.png`，不是 SVG 設計稿或僅截 extension page。
- `npm run release:check` 會重新 build，核對 manifest／version／permissions／CSP／icons／package references、secret／RHC signatures、symlink、source map 與 2 GB 上限。
- `npm run package:store` 只把 `dist/` 的 15 個檔案以固定時間與排序放入 ZIP root，驗證 root `manifest.json`、拒絕多一層 `dist/` 或不安全 path，並內建連續兩次包裝的 bytes／SHA-256 可重現斷言。當前正式 ID draft artifact 為 `taigi-news-reader-0.1.1.zip`，43,125 bytes，SHA-256 `978551ea279f4a8d62d5e3789954b8a0e103a0bc9f5b98ca0d16f5893ef8a40c`；官方 ZIP 上限是 2 GB，見 [Publish in the Chrome Web Store](https://developer.chrome.com/docs/webstore/publish/)。不得再上傳先前 `0.1.0` artifact。
- `.github/workflows/store-package.yml` 只有手動 `workflow_dispatch`，執行 tests／lint／build／package 並上傳短期 artifact；它沒有 CWS token、登入、upload 或 publish 步驟。
- 自動基線為 extension ESLint／production build／`71/71` tests，以及 backend `100 passed`；NGINX 1.29.3 `nginx -t` 亦通過。Backend regression 包含將 punctuation、smart apostrophe／hyphen 與 `ⁿ` 做窄幅 deterministic normalization，中文、數字、不支援拉丁字母及 symbols 仍 fail closed。
- 實際 `.11` LAN deployment 使用只含 nginx＋backend 的 dedicated external network；backend 沒有 host port、以 non-root／read-only rootfs／cap-drop 執行。CPU-only image 驗證 `torch 2.13.0+cpu`、`torch.version.cuda=None` 且沒有 `nvidia-*` packages。HTTPS health 是 concrete Groq＋MMS JSON。Edge／backend 在安裝遷移期同時 allowlist 正式 ID 與舊 unpacked ID；正式 ID 的 preflight 為 200、正確 ID／Origin POST 可通過到 schema 422、正確 header 的無 Origin GET 可通過到 backend 404、ID／Origin mismatch 為 403，舊 ID 也仍可通過。Dual allowlist 只保留後端相容性；不同 extension ID 的 Chrome storage／IndexedDB 不共用，舊設定與重播不會自動遷移。真實短句 job 為 POST 202 → completed 62,508-byte RIFF/WAVE → DELETE 204；direct `/v1/synthesize` 為 404，LAN 直連 host port 8765 失敗。
- Chromium `150.0.7871.46` isolated-profile strict mock E2E 已用 production `dist/` 的 test-only copy 通過 POST 202 → GET 200 → DELETE 204、offline START `cacheHit=true` 與 explicit REPLAY `cacheHit=true`。Test copy 只為繞過原生 prompt 額外授予 localhost host permission，正式 manifest 沒有 required host permissions。
- 正式 CWS ID 的 exact-package production E2E 已解壓 SHA-256 `978551ea279f4a8d62d5e3789954b8a0e103a0bc9f5b98ca0d16f5893ef8a40c` 的 `0.1.1` ZIP 到全新 profile，確認 runtime ID／version、原生 optional permission 與 fresh history `0 → 1`。Concrete Groq＋MMS 產生 239,660-byte `audio/wav` RIFF/WAVE，header 宣告長度相符，offscreen ended protocol 後 UI 才成為 `completed 1/1`；按可見重播按鈕後為 `playing → completed`，replay baseline 後 backend／health／job requests 全為 0。首次 START 前未啟用 Network instrumentation，因此不宣稱該輪精確 POST／GET／DELETE 次數。
- Chromium `149.0.7827.55` 曾以當時未修改的 production `dist/` 與舊 unpacked ID 實際通過 Chrome 原生 optional-permission prompt、action／activeTab、side panel 擷取、concrete Groq＋MMS job，offscreen audio `ended`後 `completed`、history 與按鈕 replay。首次播放取得 189,484-byte RIFF/WAVE；replay 新增 health、job API 及全部 backend request 均為 0。同次測試曾重現 80 字新聞被 punctuation／`ⁿ` 擋下，extension 正確 fail without fake audio；保守 normalization 修正 `253300c` 部署後，同 80 字 production job 產生 932,908-byte RIFF/WAVE 並 DELETE 204。這是舊 ID 的歷史 production 證據，不能取代外部 reviewer 可達性測試。

## Broad optional host decision

`https://*/*` 即使是 optional 仍受 minimum-permission policy 約束，且官方明列它會增加 review time。現在保留它的唯一理由是核心功能允許使用者輸入任意可信 HTTPS backend，而實際 grant 只對 exact origin。如果公開產品只打算支援推薦 endpoint，送審前應縮成該單一 origin；如果自架 endpoint 是明確 store feature，就保留 optional pattern，並使用 [listing 草稿](chrome-web-store-listing.md) 的完整理由。不要為「未來也許會用」保留權限。

## Package 與發佈程序

1. 已以 developer account 建立草稿並取得 public key；由它推導的正式 Item ID 是 `nejhlfbnjkbdjcaaklaofggkikdlpakn`。Dashboard 顯示的 Item ID 必須人工比對完全相同。
2. 已把 public key 放入 source manifest 的 `key`、把版本提升到 `0.1.1`，並將正式 ID 加入 edge／backend 過渡期 dual allowlist。Public key 可公開，但 CWS signing private key／OAuth token 不得放進 repo。
3. 把 `taigi-news-reader-0.1.1.zip` 更新到同一個 Dashboard 草稿，**不要按 Submit for Review**；完成上表其餘 P0，更新 privacy／listing copy。
4. 確認 `src/manifest.json` 與 `package.json` version 相同，而且高於 Dashboard 已上傳的版本；執行 `cd extension && npm ci && npm run check && npm run package:store`。
5. 記錄 tests、ZIP 路徑、size、SHA-256、git commit、Groq ZDR attestation、endpoint health identity 與 isolated-profile E2E。
6. 解壓 ZIP 到空目錄，從解壓後內容 load unpacked；重跑 [manual-test.md](manual-test.md) 與 [listing reviewer steps](chrome-web-store-listing.md#reviewer-test-instructions)。Chrome 官方也要求測試實際提交的 exact package；見 [Troubleshooting](https://developer.chrome.com/docs/webstore/troubleshooting/)。
7. 在 Dashboard 完成 Store listing、Privacy practices、Distribution 與 Test instructions。建議 first release 用 Private trusted testers；所有 visibility 都走相同 policy review，見 [Distribution](https://developer.chrome.com/docs/webstore/cws-dashboard-distribution/)。
8. 上傳最終 ZIP，人工按 Submit for Review 並選 deferred publishing。官方要求 developer account 2-Step Verification，見 [Chrome Web Store API prerequisites](https://developer.chrome.com/docs/webstore/using-api)。
9. Review 通過後再人工決定 publish；deferred submission 通過後有 30 天可發佈，見 [Publish](https://developer.chrome.com/docs/webstore/publish/)。

## Release evidence 範本

```text
Git commit:
Manifest/package version:
ZIP filename:
ZIP bytes:
ZIP SHA-256:
npm run check:
npm run release:check:
Exact ZIP unpacked Chrome smoke:
Recommended /health identity:
Production extension ID pinned at edge/backend:
Header / missing-Origin / mismatched-Origin matrix:
LAN allowlist + rate/connection limits verified:
Reviewer endpoint reachability verified from outside operator LAN:
Groq production project + ZDR verified at (UTC):
Groq key rotated at (UTC; never paste key):
Backend request-body logging disabled:
Rate limit / abuse control smoke:
Privacy URL checked while logged out:
Screenshot + small promo uploaded:
Dashboard data disclosure reviewed by:
Distribution / regions:
Deferred publish selected:
```

不要在 evidence 中貼新聞全文、API key、CWS token、cookie、完整 server log 或使用者資料。
