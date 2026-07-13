# Chrome Web Store 發佈 readiness 稽核

稽核更新：2026-07-14；live private-beta 證據日期：2026-07-13

結論：**正式 Item ID 已固定；`0.1.2` engineering／live-service／Dashboard基線均已完成，operator也明確確認先前曝光的Groq／Gemini keys全部撤銷。2026-07-14 在Submit dialog取消「通過審查後自動發布」後成功提交；Status reload顯示「這個草稿尚待審查」。** 現在是Private／deferred／pending review，不是approved或published；review期間仍須維持backend與reviewer credential可用。

本稽核以 2026-07 可取得的 Chrome 官方文件為準；provider data gate 另只引用 Groq／Google 官方文件。

## Current review state

| 項目 | 已確認狀態 | 邊界 |
| --- | --- | --- |
| Provider secrets | Operator明確確認先前曝光的Groq／Gemini keys均已撤銷；replacement Groq key與ZDR維持active。撤銷後reviewer smoke再次成功。 | Evidence不得包含raw key、token、digest、email或測試文字。 |
| CWS submission | Private item已提交；success modal明示submission成功，Status reload為「這個草稿尚待審查」。 | Pending review不等於approved。 |
| Publishing | Submit dialog已取消「通過審查後自動發布」；success modal提示通過後有30天publish window。 | Deferred不會自動發布；目前也尚未published。 |
| Gemini Free guardrail | 推薦endpoint仍使用Groq；Gemini只保留self-hosted optional adapter。 | 未來若公開採用Gemini unpaid quota，必須重做terms／privacy／Limited Use review。 |

官方依據：Chrome 要求 manifest root ZIP、name／version／icons／description，且每次更新 version 必須增加；見 [Prepare your extension](https://developer.chrome.com/docs/webstore/prepare)。Listing 缺 description、icon 或 screenshots 會被拒；圖像尺寸見 [Supplying Images](https://developer.chrome.com/docs/webstore/images)。處理 website content，即使只存在本機，也要揭露並提供 privacy policy；見 [User Data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq/) 與 [Privacy practices](https://developer.chrome.com/docs/webstore/cws-dashboard-privacy)。

Dashboard 允許先上傳 ZIP 後編輯草稿，直到按 Submit for Review 才進入審查；官方也明確說明可在未發佈前由 Package 頁取得 public key 來固定開發版 ID，見 [Publish in the Chrome Web Store](https://developer.chrome.com/docs/webstore/publish/) 與 [Manifest `key`](https://developer.chrome.com/docs/extensions/reference/manifest/key)。Chrome 在 **2026-07-01** 公布的 [2026 policy update](https://developer.chrome.com/blog/cws-policy-updates-2026) 要求所有資料收集都顯著揭露，不再因資料與 single purpose 密切相關而免除，並自 **2026-08-01** 起執行。`0.1.2` options affirmative consent、新聞 preview＋confirm、default-off replay opt-in及listing／policy文案符合目前設計方向；Remote code=No、Website content＋Authentication information、certifications及privacy URL已隨Private item提交，目前等待review。

Groq 官方說明指出 inference inputs／outputs 預設不保留，但 reliability／abuse logs 最多可能保留 30 天，所有客戶可啟用 ZDR；見 [Your Data in GroqCloud](https://console.groq.com/docs/your-data)。Groq 的 [Services Agreement](https://console.groq.com/docs/legal/services-agreement) 說 Inputs／Outputs 不用於 training／fine-tuning，除非 customer 明確授權。相較之下，[Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) 說 Unpaid Services 內容可用於改善產品並可能由 human reviewers 處理；Chrome [Limited Use](https://developer.chrome.com/docs/webstore/program-policies/limited-use) 對 human access／data transfer 有嚴格限制。

## 已通過的 repo／operational 檢查

- `0.1.2` Manifest V3、`minimum_chrome_version=116`、name／version／description、source manifest／package／lockfile root version與production build均通過 release checks。
- Manifest 的 canonical RSA SPKI public key 推導出正式 CWS Item ID `nejhlfbnjkbdjcaaklaofggkikdlpakn`。`npm run release:check` 已重新解析 public key、驗證 RSA／canonical DER，並要求推導 ID 與 `package.json.cwsItemId` 完全相同；fresh Chromium profile 從 exact `0.1.2` ZIP 註冊後也觀察到同一 service-worker origin。
- Manifest 已改用不保證翻譯／發音品質的保守描述：「把你確認的繁體中文新聞文字送到已設定的台語語音服務，並在 Chrome 播放。」母語者／長輩品質驗收完成前不可改回「自然台語」或其他超出證據的宣稱；metadata 變更需 bump version 重包。
- Required permissions 都有實際用途：`activeTab` + `scripting` 只在 action／使用者操作後擷取目前頁面；`sidePanel` 提供 UI；`offscreen` 只做 Blob／audio；`storage` 保存設定、session cleanup 與 opt-in replay。
- 沒有 `tabs`、persistent `host_permissions`、`<all_urls>`、`unlimitedStorage`、cookies、history、webRequest 或 telemetry permission。
- Backend host access 是 `optional_host_permissions`；設定頁只在使用者按下同意儲存後，runtime-request 該 URL 的 exact origin。Chrome 官方也建議可行時使用 optional permission；見 [Declare permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions)。
- Extension 的共用 backend fetch wrapper 會在 `/health`、job POST、每次 GET poll 及 DELETE 強制覆寫 `X-Taigi-Extension-Id` 為 `chrome.runtime.id`；caller 不能換值。Backend／edge strict mode 對非-preflight `/v1/` 要求 ID 精確命中 allowlist，缺少／錯誤 header 或 header 與已存在 Origin 不一致都回 403。Chrome GET 可能不帶 Origin，因此正確 header 的無 Origin request 可接受；preflight 仍要求 exact extension Origin 並協商自訂 header。
- 這個 header 與 Origin 都是公開識別、可由非瀏覽器偽造，不能描述成 API key、authentication 或防止所有濫用。Live private-beta 改由逐人 bearer token、per-IP rate／connection limits、request／process caps 與 HTTPS 構成公網邊界；`/health` 不要求 token，但套獨立 edge limits。
- `0.1.2` 的私人測試憑證是逐人 bearer invite token：extension raw token 存 `chrome.storage.local`、綁 configured origin，只送該 origin `/v1/`；server config 只有 SHA-256 digest＋stable pseudonymous subject。它是 CWS Authentication information，不是 provider key。Live server 已載入兩個不同 subjects；任何 evidence 都不得記 raw token 或 digest。
- SQLite quota 只保存當日 UTC date、subject、jobs、characters；不存新聞、音訊、raw token 或 digest。Per-subject／global daily jobs＋characters quota、owner-bound jobs、one-shot terminal delivery、outstanding／terminal-byte caps形成多層防護。Terminal GET 以 delivery lease把 payload bytes計到 response send/failure finalizer；pending DELETE 在 non-cooperative provider真正返回前仍計 active／outstanding，slow response或create/delete loop不能提早取回 capacity。
- Strict token mode 若同時設定 `TAIGI_ALLOW_DIRECT_SYNTHESIS=true`，backend 會啟動 fail closed。Live private-beta nginx 只暴露 access 與 async job routes，direct route 已驗證固定 404；另有每 IP rate／connection limits 與 global connection cap。Job registry 仍是 process-local，所以 deployment 限定單 worker／replica。
- MMS 在 Transformers forward 回傳 tensor後、呼叫 `.tolist()` 前先以 `numel()` 套 audio sample cap，WAV encoder也做 iterable／bytes cap；這避免超限 waveform再膨脹成Python list，但不能阻止 model forward本身先配置tensor。Live profile另限600 source／2,000 translated characters、16 MiB audio、2 GiB memory/no-swap及4 CPUs。
- Extension CSP 是 `script-src 'self'; object-src 'self'`。所有 HTML script 都是 package-local；source／dist scan 沒有 `eval`、`new Function`、remote script、dynamic remote import 或 WASM。Backend response 是 JSON／audio data，並非 remotely hosted code；符合 [Manifest V3 remote code policy](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code)。
- esbuild 沒有 source map、沒有 obfuscation／minification，package 不含 tests、`node_modules`、provider keys、model weights或 backend secrets。官方 review 文件指出 broad host／sensitive execution 與難讀 code 會延長審查；目前 compiled code 可讀，但 `https://*/*` 仍需 review notes 詳細解釋，見 [Review process](https://developer.chrome.com/docs/webstore/review-process)。
- Dashboard listing目前有128x128 icon、一張真實1280x800新聞頁＋side panel screenshot及440x280 promo；詳細描述已更新為616 characters。Repo對應screenshot是`extension/store-assets/screenshot-reader-1280x800.png`，不是SVG設計稿或僅截extension page。
- `npm run release:check` 會重新 build，核對 manifest／version／permissions／CSP／icons／package references、secret／RHC signatures、symlink、source map 與 2 GB 上限。
- `npm run package:store` 只把 `dist/` 的15個檔案以固定時間與排序放入ZIP root，驗證root `manifest.json`、拒絕多一層`dist/`或不安全path，並內建連續兩次包裝的bytes／SHA-256可重現斷言。`taigi-news-reader-0.1.2.zip`為**50,789 bytes**，SHA-256 **`5639d9b33090a50470dd800ce03c2c620d55fbadea3b4f821c1ab119b6e012e6`**；2026-07-14已上傳並重載確認Dashboard package version／permissions。官方ZIP上限是2 GB，見[Publish in the Chrome Web Store](https://developer.chrome.com/docs/webstore/publish/)。
- `.github/workflows/store-package.yml` 只有手動 `workflow_dispatch`，執行 tests／lint／build／package 並上傳短期 artifact；它沒有 CWS token、登入、upload 或 publish 步驟。
- 自動基線為 extension ESLint／production build／`82/82` tests，以及 backend `166 passed`。Backend新增anti-abuse regressions涵蓋send failure仍release delivery lease、concurrent DELETE retained-byte accounting、pending DELETE capacity、non-cooperative MMS timeout/cancel single-flight、pre-`.tolist()` cap、strict direct disable與private-beta ingress／resource limits；NGINX 1.29.3兩組`nginx -t` harness及edge 403／429 CORS、method gate容器行為測試通過。POJ normalization仍只處理安全 typography，中文、數字、不支援拉丁字母及symbols fail closed。
- `deploy/private-beta/` 提供Internet-facing ingress／Compose override與rollback runbook，static tests鎖定600／2,000／16 MiB、2 GiB/no-swap、4 CPU、single worker、direct 404、pinned CORS、source-IP limits及no request-body logging。2026-07-13 已將此profile套用到`.11`：backend沒有host port，durable quota database已掛載，effective resource limits與single-worker contract相符。
- Live `.11` matrix 已確認缺少／錯誤 credential 為 401、cross-subject access 為與 unknown job 相同的 404、實際 quota exhaustion 為 429、direct route 為 404，CORS pin 正式 extension ID。Operator 人工確認 Groq production project 啟用 ZDR、replacement key active，並於2026-07-14明確確認舊曝光Groq／Gemini keys均已撤銷。
- 從operator LAN外經Tor出口完成推薦endpoint TLS、`/v1/access`與完整Groq＋MMS job；外部reachability不再是未驗證項目。服務在review期間仍需維持監控、容量與個別reviewer token。
- Chromium `150.0.7871.46` isolated-profile strict mock E2E 已用 production `dist/` 的 test-only copy 通過 POST 202 → GET 200 → DELETE 204、offline START `cacheHit=true` 與 explicit REPLAY `cacheHit=true`。Test copy 只為繞過原生 prompt 額外授予 localhost host permission，正式 manifest 沒有 required host permissions。
- 正式 CWS ID 的 exact `0.1.2` ZIP 已在 fresh Chromium profile 註冊為 `nejhlfbnjkbdjcaaklaofggkikdlpakn`，通過原生 exact-origin optional permission、subject quota／UTC reset顯示、live Groq＋MMS playback與history。從history重播後，新增health及backend job requests均為0。Exact package後續已提交Private review。
- Dashboard Privacy已儲存並重載確認Remote code=No、Website content＋Authentication information、certifications及privacy URL。Test instructions於2026-07-14儲存，username為`cws-reviewer`、instructions counter為360/500；64-character raw credential只存在Dashboard password欄，repo／文件／evidence均不得保存value或digest。Distribution為Private。
- Public homepage、support及privacy URL已由未登入HTTP client確認回200。Submit dialog取消automatic publishing後已提交；success modal提示通過後30天publish window，Status reload顯示草稿尚待審查。
- 舊Groq／Gemini keys撤銷後，以同一reviewer credential重跑live Groq→MMS smoke：access ok，POST 202後completed `audio/wav`，`audio_base64`長度51,260 characters，cleanup DELETE 204；subject quota由remaining 19 jobs／11,993 characters變成18／11,986。證據不包含credential、digest、email或測試文字。
- 正式 CWS ID 的 exact-package production E2E 已解壓 SHA-256 `978551ea279f4a8d62d5e3789954b8a0e103a0bc9f5b98ca0d16f5893ef8a40c` 的 `0.1.1` ZIP 到全新 profile，確認 runtime ID／version、原生 optional permission 與 fresh history `0 → 1`。Concrete Groq＋MMS 產生 239,660-byte `audio/wav` RIFF/WAVE，header 宣告長度相符，offscreen ended protocol 後 UI 才成為 `completed 1/1`；按可見重播按鈕後為 `playing → completed`，replay baseline 後 backend／health／job requests 全為 0。首次 START 前未啟用 Network instrumentation，因此不宣稱該輪精確 POST／GET／DELETE 次數。
- Chromium `149.0.7827.55` 曾以當時未修改的 production `dist/` 與舊 unpacked ID 實際通過 Chrome 原生 optional-permission prompt、action／activeTab、side panel 擷取、concrete Groq＋MMS job，offscreen audio `ended`後 `completed`、history 與按鈕 replay。首次播放取得 189,484-byte RIFF/WAVE；replay 新增 health、job API 及全部 backend request 均為 0。同次測試曾重現 80 字新聞被 punctuation／`ⁿ` 擋下，extension 正確 fail without fake audio；保守 normalization 修正 `253300c` 部署後，同 80 字 production job 產生 932,908-byte RIFF/WAVE 並 DELETE 204。這只保留為舊 ID 的歷史 production 證據。

## Broad optional host decision

`https://*/*` 即使是 optional 仍受 minimum-permission policy 約束，且官方明列它會增加 review time。現在保留它的唯一理由是核心功能允許使用者輸入任意可信 HTTPS backend，而實際 grant 只對 exact origin。如果公開產品只打算支援推薦 endpoint，送審前應縮成該單一 origin；如果自架 endpoint 是明確 store feature，就保留 optional pattern，並使用 [listing 草稿](chrome-web-store-listing.md) 的完整理由。不要為「未來也許會用」保留權限。

## Package 與發佈程序

1. 已以 developer account 建立草稿並取得 public key；由它推導的正式 Item ID 是 `nejhlfbnjkbdjcaaklaofggkikdlpakn`。Dashboard 顯示的 Item ID 必須人工比對完全相同。
2. 已把 public key 放入 source manifest 的 `key`，正式 ID 也已 pin 到 live edge／backend。`0.1.2` exact artifact、fresh-profile／external E2E及Dashboard upload均已完成，package version／permissions已重載確認。Public key可公開，但CWS signing private key／OAuth token不得放進repo。
3. Live server已provision不同高熵token對應的stable subjects；Dashboard reviewer username為`cws-reviewer`，64-character raw credential只存在password欄。Server只保存SHA-256 mapping；raw token或digest不得放進git、extension ZIP、listing、instructions本文、screenshot或release evidence。
4. Repo 階段已確認 `src/manifest.json` 與 `package.json` version 都是 `0.1.2`，backend `166 passed`、extension `82/82`＋lint／build與`npm run package:store`通過；固定 artifact bytes／hash如上。任何後續 source改動都要bump version或至少重建、重算hash並重跑同級checks。
5. `.11` single-worker backend、durable quota volume、nginx edge、600／2,000／16 MiB、2 GiB/no-swap／4 CPU caps與非LAN smoke已完成；Groq ZDR／replacement key active與舊Groq／Gemini keys撤銷均由operator明確確認。持續保留monitoring／rollback readiness。
6. Exact ZIP的fresh-profile正式ID、native permission、quota、playback／history／zero-request replay及非LAN endpoint flow已留下證據；Dashboard同credential live smoke也已完成。
7. Dashboard已儲存Private distribution、package、616-character description、assets、Privacy practices與360/500 test instructions，並重載確認；所有visibility都走相同policy review，見[Distribution](https://developer.chrome.com/docs/webstore/cws-dashboard-distribution/)。
8. Submit dialog已取消automatic publishing checkbox後成功送出；success modal確認submission及30天publish window。Status reload為「這個草稿尚待審查」。目前是Private／deferred／pending review；等待審查期間不得宣稱approved或published。

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
Terminal delivery lease releases on send success/failure; concurrent DELETE verified:
Pending DELETE keeps active/outstanding capacity until provider return:
Strict direct synthesis disabled + ingress direct route 404 verified:
MMS pre-tolist sample cap + forward-allocation limitation reviewed:
Effective beta limits verified (600/2000/16 MiB; 2 GiB/no-swap; 4 CPU):
nginx per-IP rate/connection limits verified:
Single backend worker + durable quota volume verified:
Reviewer endpoint reachability verified from outside operator LAN:
Groq production project + ZDR verified at (UTC):
Replacement Groq key active at (UTC; never paste key):
Previously exposed Groq/Gemini keys revoked at (UTC; never paste keys):
Backend request-body logging disabled:
Rate limit / abuse control smoke:
Privacy URL checked while logged out:
Screenshot + small promo uploaded:
Dashboard data disclosure reviewed by:
Distribution / regions:
Deferred publish selected:
```

不要在 evidence 中貼新聞全文、raw invite token、token digest、API key、CWS token、cookie、完整 server log、個人信箱或其他使用者資料。
