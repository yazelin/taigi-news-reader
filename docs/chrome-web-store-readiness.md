# Chrome Web Store 發佈 readiness 稽核

稽核日期：2026-07-13

結論：**package 工程基線接近完成，但目前仍不可提交公開審查。** 下列人工／營運 blockers 完成前，不應登入 Dashboard 上傳或按 Submit for Review。

本稽核以 2026-07 可取得的 Chrome 官方文件為準；provider data gate 另只引用 Groq／Google 官方文件。

## Release blockers

| 優先級 | Blocker | 完成條件 |
| --- | --- | --- |
| P0 | 推薦 backend 的資料處理尚未完成 release attestation | Groq Console 對 production project 啟用 ZDR；輪替未曝光的新 key；確認不用 batch／fine-tuning／retention feature；把 production extension ID 精確放入 edge／backend allowlist，以正式套件實測 health、固定 ID header、Groq translation、真正台語 TTS、rate limit、錯誤及 DELETE cleanup。保存不含內容的設定截圖／日期作 release evidence。 |
| P0 | Gemini Free 與 CWS Limited Use 風險 | 公開推薦 endpoint 不得使用 Gemini unpaid quota。Gemini 保留為 self-hosted optional adapter；若未來要公開採用，只能在重新做 provider terms／privacy review、更新 UI／listing／policy 後切換。Google 官方條款明載 unpaid inputs／outputs 可用於改善產品且可能由 human reviewers 處理。 |
| P0 | 公開 privacy policy／Dashboard disclosures 尚未人工確認 | 逐字核對 [PRIVACY.md](../PRIVACY.md)、套件內告知、listing 與實際 production provider/logging；用未登入瀏覽器確認 policy URL 公開；在 Dashboard 填 Website content、single purpose、permission justifications、remote code=No、Limited Use certifications。 |
| P0 | Store listing graphics／metadata 上傳 | Repo 已有 128 icon、`extension/store-assets/screenshot-reader-1280x800.png` 真實 Chrome UI 截圖與 `extension/store-assets/promo-440x280.png`；仍須在 Dashboard 上傳這些素材，並填詳細描述、語言、分類與 support。缺 screenshot 或必填欄位會被拒絕。 |
| P0 | Reviewer 可用性／production service | **2026-07-13 root deployment 尚未完成：** 設計 URL 仍是 `https://ching-tech.ddns.net/taigi-tts`，但目前 `/health` 回 301，導向 `https://www.ching-tech.com/taigi-tts/health` 後回公司首頁 `text/html`，不是 health JSON；這是待修的 reverse-proxy／部署狀態，不表示應改套件 URL。完成 root 部署後，推薦 endpoint 必須在 review 期間穩定且不是 mock。若 production 只允許 LAN，外部 CWS reviewer 無法重現；送審前須決定安全且可供 reviewer 存取的方式並寫入 notes。固定 extension header／Origin 都可偽造，不能單獨作為公網 authentication。 |
| P0 | Publisher account 外部作業 | 以長期維護信箱註冊並付一次性費用、啟用 Google Account 2-Step Verification、確認聯絡資訊；選 Private trusted testers 或其他 distribution。這些無法由 repo 自動驗證。 |

官方依據：Chrome 要求 manifest root ZIP、name／version／icons／description，且每次更新 version 必須增加；見 [Prepare your extension](https://developer.chrome.com/docs/webstore/prepare)。Listing 缺 description、icon 或 screenshots 會被拒；圖像尺寸見 [Supplying Images](https://developer.chrome.com/docs/webstore/images)。處理 website content，即使只存在本機，也要揭露並提供 privacy policy；見 [User Data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq/) 與 [Privacy practices](https://developer.chrome.com/docs/webstore/cws-dashboard-privacy)。

Groq 官方說明指出 inference inputs／outputs 預設不保留，但 reliability／abuse logs 最多可能保留 30 天，所有客戶可啟用 ZDR；見 [Your Data in GroqCloud](https://console.groq.com/docs/your-data)。Groq 的 [Services Agreement](https://console.groq.com/docs/legal/services-agreement) 說 Inputs／Outputs 不用於 training／fine-tuning，除非 customer 明確授權。相較之下，[Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) 說 Unpaid Services 內容可用於改善產品並可能由 human reviewers 處理；Chrome [Limited Use](https://developer.chrome.com/docs/webstore/program-policies/limited-use) 對 human access／data transfer 有嚴格限制。

## 已通過的 repo 檢查

- Manifest V3、`minimum_chrome_version=116`、name／version／description 格式有效；source manifest 與 package version 都是 `0.1.0`。`0.1.0` 是合法 first release version，但下次 upload 必須更大。
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
- `npm run package:store` 只把 `dist/` 內容放入 ZIP root，驗證 root `manifest.json`、拒絕多一層 `dist/` 或不安全 path，並輸出 SHA-256。官方 ZIP 上限是 2 GB；見 [Publish in the Chrome Web Store](https://developer.chrome.com/docs/webstore/publish/)。
- `.github/workflows/store-package.yml` 只有手動 `workflow_dispatch`，執行 tests／lint／build／package 並上傳短期 artifact；它沒有 CWS token、登入、upload 或 publish 步驟。
- Header fix 完成後的自動基線為 extension ESLint／production build／`71/71` tests，以及 backend `92 passed`；NGINX 1.29.3 `nginx -t` 亦通過。這只證明 repo contract，不代表上述 root endpoint 已部署。
- Chromium `150.0.7871.46` isolated-profile strict mock E2E 已用 production `dist/` 的 test-only copy 通過 POST 202 → GET 200 → DELETE 204、offline START `cacheHit=true` 與 explicit REPLAY `cacheHit=true`。Test copy 只為繞過原生 prompt 額外授予 localhost host permission，正式 manifest 沒有 required host permissions；這項 LAN/mock 證據仍不能取代 production endpoint 與 CWS reviewer 測試。

## Broad optional host decision

`https://*/*` 即使是 optional 仍受 minimum-permission policy 約束，且官方明列它會增加 review time。現在保留它的唯一理由是核心功能允許使用者輸入任意可信 HTTPS backend，而實際 grant 只對 exact origin。如果公開產品只打算支援推薦 endpoint，送審前應縮成該單一 origin；如果自架 endpoint 是明確 store feature，就保留 optional pattern，並使用 [listing 草稿](chrome-web-store-listing.md) 的完整理由。不要為「未來也許會用」保留權限。

## Package 與發佈程序

1. 完成上表所有 P0，更新 privacy／listing copy。
2. 確認 `src/manifest.json` 與 `package.json` version 相同，而且高於 Dashboard 已上傳的版本。
3. 執行 `cd extension && npm ci && npm run check && npm run package:store`。
4. 記錄 tests、ZIP 路徑、size、SHA-256、git commit、Groq ZDR attestation、endpoint health identity 與 isolated-profile E2E。
5. 解壓 ZIP 到空目錄，從解壓後內容 load unpacked；重跑 [manual-test.md](manual-test.md) 與 [listing reviewer steps](chrome-web-store-listing.md#reviewer-test-instructions)。Chrome 官方也要求測試實際提交的 exact package；見 [Troubleshooting](https://developer.chrome.com/docs/webstore/troubleshooting/)。
6. 在 Dashboard 完成 Store listing、Privacy practices、Distribution 與 Test instructions。建議 first release 用 Private trusted testers；所有 visibility 都走相同 policy review，見 [Distribution](https://developer.chrome.com/docs/webstore/cws-dashboard-distribution/)。
7. 人工上傳 ZIP 並選 deferred publishing；不要把 CWS OAuth refresh token 或 signing private key放進 repo。官方要求 developer account 2-Step Verification，見 [Chrome Web Store API prerequisites](https://developer.chrome.com/docs/webstore/using-api)。
8. Review 通過後再人工決定 publish；deferred submission 通過後有 30 天可發佈，見 [Publish](https://developer.chrome.com/docs/webstore/publish/)。

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
