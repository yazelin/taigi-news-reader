# Chrome Web Store 發佈 readiness 稽核

稽核日期：2026-07-13

結論：**正式 Item ID 已固定，`0.1.1` 是已驗證／已上傳的歷史工程基線；`0.1.2` source 已實作 private-test authentication／quota，但尚未完成 exact ZIP、外部 endpoint 與 live deployment 證據，因此仍不可按 Submit for Review。** Dashboard 提供的 public key 已放入 manifest，Chrome 實際載入也確認為同一個正式 ID；更新草稿不等於送審或發佈。下列人工／營運 blockers 完成前，不應提交審查。

本稽核以 2026-07 可取得的 Chrome 官方文件為準；provider data gate 另只引用 Groq／Google 官方文件。

## Release blockers

| 優先級 | Blocker | 完成條件 |
| --- | --- | --- |
| P0 | 推薦 backend 的資料處理尚未完成 release attestation | 正式 extension ID 已由 Dashboard public key 固定為 `nejhlfbnjkbdjcaaklaofggkikdlpakn`，並以過渡期 dual allowlist 部署到 edge／backend。仍須在 Groq Console 對 production project 啟用 ZDR、輪替曾曝光的 key、確認不用 batch／fine-tuning／retention feature，並保存不含內容的設定截圖／日期作 release evidence。 |
| P0 | Gemini Free 與 CWS Limited Use 風險 | 公開推薦 endpoint 不得使用 Gemini unpaid quota。Gemini 保留為 self-hosted optional adapter；若未來要公開採用，只能在重新做 provider terms／privacy review、更新 UI／listing／policy 後切換。Google 官方條款明載 unpaid inputs／outputs 可用於改善產品且可能由 human reviewers 處理。 |
| P0 | `0.1.2` exact release 尚未驗證 | Source 已實作逐人 invite token、origin binding、`/v1/access`、job ownership、durable quota 與 capacity caps，但不能把 code presence 當成 release 完成。須跑 backend／extension 全套、package checks、secret scan，以及 fresh-profile exact ZIP 的正確 token、錯誤／撤銷 token、origin switch、401／429、one-shot terminal result、STOP／DELETE、replay zero-request E2E；記錄新的 ZIP bytes／SHA-256／commit。 |
| P0 | Dashboard privacy／listing 必須同步 `0.1.2` | 既有 `0.1.1` listing 素材與草稿不能取代新資料流揭露。Dashboard 必須同時勾 **Website content** 與 **Authentication information**，更新 `storage` justification、詳細描述及 test instructions；raw invite token 只在 Chrome local storage、綁 configured origin、只送同 origin `/v1/`，server 只有 SHA-256 digest＋stable subject。Remote code 維持 No，Limited Use certifications 需再人工核對。 |
| P0 | Reviewer 可用性／live production service | **2026-07-13 LAN root deployment 是歷史基線：** `https://ching-tech.ddns.net/taigi-tts/health` 只在允許網段完成 Groq＋MMS WAV／cleanup。現有 endpoint 仍刻意只允許 `192.168.11.0/24`，外部 CWS reviewer 無法重現；`0.1.2` auth／quota 也尚未 live 部署。須提供安全外網路徑、逐 reviewer 高熵可撤銷 token、per-IP nginx limits、single-worker durable quota volume、監控與 rollback，並從 operator LAN 外實測。 |
| P0 | Private distribution／reviewer credential | Publisher 聯絡信箱已由操作者回報完成驗證，但仍須在 Dashboard 選 Private trusted testers、加入實際 tester account，並只透過 Dashboard 安全 reviewer credential 欄提供一組有期限／足額 quota 的個別 token。不得把共用 token 放進 extension、listing、repo、screenshot 或公開 issue。 |

官方依據：Chrome 要求 manifest root ZIP、name／version／icons／description，且每次更新 version 必須增加；見 [Prepare your extension](https://developer.chrome.com/docs/webstore/prepare)。Listing 缺 description、icon 或 screenshots 會被拒；圖像尺寸見 [Supplying Images](https://developer.chrome.com/docs/webstore/images)。處理 website content，即使只存在本機，也要揭露並提供 privacy policy；見 [User Data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq/) 與 [Privacy practices](https://developer.chrome.com/docs/webstore/cws-dashboard-privacy)。

Dashboard 允許先上傳 ZIP 後編輯草稿，直到按 Submit for Review 才進入審查；官方也明確說明可在未發佈前由 Package 頁取得 public key 來固定開發版 ID，見 [Publish in the Chrome Web Store](https://developer.chrome.com/docs/webstore/publish/) 與 [Manifest `key`](https://developer.chrome.com/docs/extensions/reference/manifest/key)。2026-08-01 開始施行的更新要求對所有資料處理做顯著揭露，因此本案從 first release 就以較嚴格版本填寫 UI、listing 與 Dashboard；見 [2026 policy update](https://developer.chrome.com/blog/cws-policy-updates-2026)。

Groq 官方說明指出 inference inputs／outputs 預設不保留，但 reliability／abuse logs 最多可能保留 30 天，所有客戶可啟用 ZDR；見 [Your Data in GroqCloud](https://console.groq.com/docs/your-data)。Groq 的 [Services Agreement](https://console.groq.com/docs/legal/services-agreement) 說 Inputs／Outputs 不用於 training／fine-tuning，除非 customer 明確授權。相較之下，[Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) 說 Unpaid Services 內容可用於改善產品並可能由 human reviewers 處理；Chrome [Limited Use](https://developer.chrome.com/docs/webstore/program-policies/limited-use) 對 human access／data transfer 有嚴格限制。

## 已通過的 repo 檢查

- `0.1.1` 歷史基線的 Manifest V3、`minimum_chrome_version=116`、name／version／description 格式有效；目前 source manifest、package 與 lockfile root 已改為 `0.1.2`，但本節不得視為已完成 `0.1.2` release check 或 package 驗證。
- Manifest 的 canonical RSA SPKI public key 推導出正式 CWS Item ID `nejhlfbnjkbdjcaaklaofggkikdlpakn`。`npm run release:check` 會重新解析 public key、驗證 RSA／canonical DER，並要求推導 ID 與 `package.json.cwsItemId` 完全相同；隔離 Chrome 對 `0.1.1` 已觀察到同一 service-worker origin，`0.1.2` 仍須重跑。
- Manifest 已改用不保證翻譯／發音品質的保守描述：「把你確認的繁體中文新聞文字送到已設定的台語語音服務，並在 Chrome 播放。」母語者／長輩品質驗收完成前不可改回「自然台語」或其他超出證據的宣稱；metadata 變更需 bump version 重包。
- Required permissions 都有實際用途：`activeTab` + `scripting` 只在 action／使用者操作後擷取目前頁面；`sidePanel` 提供 UI；`offscreen` 只做 Blob／audio；`storage` 保存設定、session cleanup 與 opt-in replay。
- 沒有 `tabs`、persistent `host_permissions`、`<all_urls>`、`unlimitedStorage`、cookies、history、webRequest 或 telemetry permission。
- Backend host access 是 `optional_host_permissions`；設定頁只在使用者按下同意儲存後，runtime-request 該 URL 的 exact origin。Chrome 官方也建議可行時使用 optional permission；見 [Declare permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions)。
- Extension 的共用 backend fetch wrapper 會在 `/health`、job POST、每次 GET poll 及 DELETE 強制覆寫 `X-Taigi-Extension-Id` 為 `chrome.runtime.id`；caller 不能換值。Backend／edge strict mode 對非-preflight `/v1/` 要求 ID 精確命中 allowlist，缺少／錯誤 header 或 header 與已存在 Origin 不一致都回 403。Chrome GET 可能不帶 Origin，因此正確 header 的無 Origin request 可接受；preflight 仍要求 exact extension Origin 並協商自訂 header。
- 這個 header 與 Origin 都是公開識別、可由非瀏覽器偽造，不能描述成 API key、authentication 或防止所有濫用。目標 LAN 部署仍由 subnet allowlist、per-IP rate／connection limit、request size／active-job cap 與 HTTPS 構成邊界；`/health` 不要求 header，只受 LAN／health limits 保護。若 reviewer endpoint 會暴露公網，必須另行完成適合公網的 authentication／abuse review。
- `0.1.2` 已實作的私人測試憑證是逐人 bearer invite token：extension raw token 存 `chrome.storage.local`、綁 configured origin，只送該 origin `/v1/`；server config 只有 SHA-256 digest＋stable pseudonymous subject。它是 CWS Authentication information，不是 provider key。Source implementation 不等於 exact ZIP 或 production deployment 已通過。
- Candidate 的 SQLite quota 只保存當日 UTC date、subject、jobs、characters；不存新聞、音訊、raw token 或 digest。Per-subject／global daily jobs＋characters quota、owner-bound jobs、one-shot terminal delivery、outstanding／terminal-byte caps與 nginx per-IP limits形成多層防護。Job registry 仍是 process-local，所以 private beta 部署限定單 worker／replica。
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
2. 已把 public key 放入 source manifest 的 `key`，正式 ID 也已加入 edge／backend 過渡期 allowlist。`0.1.1` ZIP 已是 Dashboard 歷史草稿；`0.1.2` source 已實作 private-test controls，但尚未形成經驗證的 release artifact。Public key 可公開，但 CWS signing private key／OAuth token 不得放進 repo。
3. 為每位 tester／reviewer離線產生不同高熵 token，只把 SHA-256 設成 `stable-subject=digest`。Raw token 不得放進 git、extension ZIP、provider env example、listing、screenshot或 release evidence；經私密管道分發，並保留個別撤銷對照。
4. 完成上表 P0：Groq ZDR 與 provider key rotation、外部 HTTPS reachability、single-worker backend＋durable quota volume、nginx per-IP limits、production logging／monitoring、rollback。從 operator LAN 外驗證；不要因 source 有 auth／quota 就宣稱 live。
5. 確認 `src/manifest.json` 與 `package.json` version 都是 `0.1.2` 且高於 Dashboard 的 `0.1.1`；執行 backend tests、`cd extension && npm ci && npm run check && npm run package:store`。
6. 記錄 tests、ZIP 路徑、size、SHA-256、git commit、Groq ZDR attestation、endpoint health identity 與 isolated-profile E2E。解壓 exact ZIP 到空目錄 load unpacked，重跑 [manual-test.md](manual-test.md) 與 [listing reviewer steps](chrome-web-store-listing.md#reviewer-test-instructions)。
7. 在 Dashboard 更新 Store listing 與 Privacy practices，尤其新增 Authentication information；Distribution 選 Private trusted testers並加入實際測試帳號。Test instructions 使用一組可撤銷 reviewer token，僅放 Dashboard 安全 credential 欄。所有 visibility 都走相同 policy review，見 [Distribution](https://developer.chrome.com/docs/webstore/cws-dashboard-distribution/)。
8. 上傳最終 `0.1.2` ZIP，重新確認 Dashboard package version／hash evidence 後才人工按 Submit for Review，並選 deferred publishing。Review 通過後再人工決定 publish。

### Private → Public 升版

1. 沿用同一 CWS item／正式 extension ID；不要另建公開 item。相同 ID 讓私人測試安裝可收到正常更新，Chrome local settings／replay 也維持同一 origin。
2. 把版本再提升為高於已發布 private build 的版本（例如 `0.1.3`），重新 build、測試、打包、上傳並送審。不能只在 Dashboard 把 visibility 切 Public 而沿用未重新稽核的 credential／privacy 流程。
3. 公開前決定可擴充的個別 onboarding／authentication、撤銷、遺失復原與支援流程。CWS trusted-testers 名單不是 API authorization；extension 裡的任何 static／shared token 都是公開資料。若保留 invite token，仍須逐人發放、可撤銷、有配額。
4. 重新核對容量／成本、provider terms、Groq ZDR／key rotation、資料保存、abuse／incident response、backup／restore、監控與多使用者負載。若 authentication 模式改變，新版 UI 必須安全清除／migration 舊 token。
5. 更新 listing、Privacy practices、policy 與 reviewer notes，重跑 exact public ZIP E2E；審查通過後才把 distribution 發布為 Public。是否採 deferred publishing 仍由操作者在 Dashboard 人工決定。

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
Invite-token digest subjects provisioned (no raw values):
Authentication information Dashboard disclosure reviewed:
Correct / wrong / revoked / cross-origin token matrix:
Per-subject/global UTC quota + restart persistence verified:
Job ownership + one-shot terminal result/caps verified:
nginx per-IP rate/connection limits verified:
Single backend worker + durable quota volume verified:
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

不要在 evidence 中貼新聞全文、raw invite token、token digest、API key、CWS token、cookie、完整 server log、個人信箱或其他使用者資料。
