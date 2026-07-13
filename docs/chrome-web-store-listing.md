# Chrome Web Store listing 與 Privacy practices 草稿

稽核日期：2026-07-13

這份文件是可貼入 Developer Dashboard 的 release copy。送審前仍須逐項核對實際 package、推薦 endpoint、Groq ZDR 與 [PRIVACY.md](../PRIVACY.md)，不可把草稿直接視為已完成的 Dashboard 設定。

## Store listing

### 名稱

台語新聞朗讀

### Manifest 短描述建議

把你確認的繁體中文新聞文字送到已設定的台語語音服務，並在 Chrome 播放。

目前 manifest 已改用上面較保守的文字；母語者／長輩品質驗收完成前，不可改回「自然台語」或其他超出證據的宣稱。Chrome 要求 listing metadata 準確且不得誤導；description 上限為 132 characters。

### 詳細描述

台語新聞朗讀讓你在 Chrome 瀏覽新聞時，主動擷取文章正文或選取文字，確認內容後轉成台語並播放。

使用流程：

1. 開啟新聞頁，按擴充套件圖示。
2. 按「讀取這一頁」，檢查標題與朗讀內容。
3. 選擇速度，按「確認並開始朗讀」。
4. 使用暫停、繼續、停止與重新播放。

新聞文字只有在你確認後才送到設定頁顯示的語音服務。套件不送出 Cookie、登入資訊、完整 HTML、新聞網址或瀏覽紀錄。推薦的非商用服務使用 Groq inference 做翻譯，再由伺服器上的真正台語 TTS 產生音訊；mock 音訊會明確標示「測試音訊（不是台語 TTS）」。也可以改用你信任的 HTTPS 自架服務。

本機重播預設關閉。主動開啟後，最多保留最近 5 篇、合計 50 MiB、最後播放後 7 天的音訊；可逐筆刪除、清除全部，或關閉功能立即清除。詳細資料處理方式請看隱私政策。

這是非商用 MVP。台語翻譯、用詞、腔口與發音仍可能不準確，不應用於緊急、醫療、法律或其他需要逐字正確的內容。

### Dashboard 基本欄位

- Primary language：Chinese (Traditional)。
- Category：Accessibility；若 Dashboard 當下分類名稱不同，選最接近輔助閱讀／生產力的單一分類。
- Homepage URL：`https://github.com/yazelin/taigi-news-reader`。
- Support URL：`https://github.com/yazelin/taigi-news-reader/issues`。
- Privacy policy URL：`https://github.com/yazelin/taigi-news-reader/blob/main/PRIVACY.md`，送審前以未登入視窗確認可公開讀取。
- Mature content：No。
- Payments／in-app purchases：No。
- 建議 first release 先用 Private trusted testers；Private、Unlisted、Public 仍接受相同 policy review。

### 圖像

- Package／store icon：128x128 PNG；package 另含 16／32／48 px icons。
- 真實 Chrome UI screenshot：`extension/store-assets/screenshot-reader-1280x800.png`（1280x800），涵蓋新聞頁、side panel 與送出前內容確認。
- Small promo：`extension/store-assets/promo-440x280.png`（440x280 PNG）。
- 1400x560 marquee image 可選。
- 圖像不可宣稱「完全準確」、「播音員等級」或顯示 repo 尚未實作的功能。

官方規格見 [Supplying Images](https://developer.chrome.com/docs/webstore/images) 與 [Listing requirements](https://developer.chrome.com/docs/webstore/program-policies/policies)。

## Privacy practices

### Single purpose

讓使用者主動擷取或選取目前分頁的新聞文字，在確認後送到其選定的台語語音服務，並播放回傳音訊；使用者可選擇在本機保留有界限的重播音訊。

### Permission justifications

- `activeTab`：只在使用者按擴充套件 action 後，暫時取得目前分頁權限；不背景監看其他分頁。
- `scripting`：把 package 內的 `extractor.js` 注入使用者剛主動開啟的 active tab，以擷取選取文字或文章正文；搭配 `activeTab`，不使用永久新聞網站 host access。
- `sidePanel`：在 Chrome side panel 顯示內容預覽、明確送出確認、播放控制及本機重播管理。
- `offscreen`：Manifest V3 service worker 沒有 DOM audio 能力，因此以 package 內 offscreen document 建立 Blob URL 並播放使用者要求的音訊。
- `storage`：在本機保存 backend URL、session 播放／cleanup 狀態，以及使用者明確 opt-in 的 bounded replay preferences、metadata、provider fingerprint；不使用 `unlimitedStorage`。
- Optional `https://*/*`：使用者可以指定可信任的 HTTPS 語音服務。Manifest 只宣告可選能力；設定頁按下同意儲存時才用 `chrome.permissions.request()` 要求該 URL 的 exact origin，不在安裝時取得所有 HTTPS 網站權限。
- Optional `http://127.0.0.1/*`、`http://localhost/*`：只支援同機自架開發服務；一般遠端 HTTP 會被拒絕。

`https://*/*` 仍是 broad host pattern，官方文件指出可能延長審查。若 public release 決定不再支援任意自架 HTTPS backend，應改成推薦服務的單一 origin；若保留自架功能，以上 exact-origin runtime flow 必須在 review notes 說清楚。

### Remote code

選擇：**No, I am not using remote code.**

所有 JavaScript 都由 esbuild 打包在 ZIP 中，CSP 是 `script-src 'self'; object-src 'self'`。Backend 回傳的是 JSON status／provider labels 與 base64 audio data，套件不把遠端 JavaScript、WASM 或其他 response 當程式碼執行。官方定義明確區分 remote executable code 與 data；見 [Deal with remote hosted code violations](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code)。

### Data usage

- 勾選：Website content。它包含使用者主動擷取或選取的標題／正文，及由其產生的台語音訊。
- 不勾選 Web history：套件不收集或傳送新聞 URL、跨頁瀏覽紀錄或被動背景活動。
- 不勾選 authentication、personal communications、financial、health、location 等類型；但使用者可能自行選取含敏感資料的頁面，因此 UI 與 policy 應提醒不要把私人／機密內容送到不信任的服務。
- Local-only data 也必須揭露：backend setting、播放 session、opt-in replay title/service metadata、provider identity 與 audio。
- 每次 backend request 另帶固定的 `X-Taigi-Extension-Id`，只辨識商店套件而非單一安裝／使用者；它不是 secret。Browser Origin 若存在也可能由 edge 檢查，但兩者都可被非瀏覽器偽造，不應宣稱為使用者 authentication。
- 第三方：公開推薦 endpoint 的營運方及 Groq inference。公開版必須使用已啟用 ZDR 的 Groq project；Gemini Free 不得作為推薦公開後端。自訂 backend 的營運方由使用者選擇。
- Certification：資料只用於或改善上述 single purpose；不出售、不用於廣告、信用評估或 unrelated profiling；除必要服務供應商、法律要求、安全／abuse 調查外不轉移；遵守 Limited Use。

Chrome 要求 Dashboard disclosures、privacy policy 與實際行為一致；見 [Fill out the privacy fields](https://developer.chrome.com/docs/webstore/cws-dashboard-privacy)、[User Data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq/) 與 [Limited Use](https://developer.chrome.com/docs/webstore/program-policies/limited-use)。

## Reviewer test instructions

1. 使用待送審 ZIP 安裝，Chrome 116+。
2. 開啟設定，按「使用建議的非商用服務」，確認資料傳輸告知後接受 exact-origin optional permission。
3. 確認 `https://ching-tech.ddns.net/taigi-tts/health` 直接或經正確保留路徑的 redirect 回傳 JSON，且內容是 production 預期的 `mode=concrete`、Groq translator identity 與真正台語 synthesizer identity；不得回網站 HTML，也不得是 mock。
4. 開啟一篇公開繁中新聞，按 extension action，再按「讀取這一頁」。檢查預覽後按「確認並開始朗讀」。
5. 預期 UI 依序顯示 preparing／playing／completed，可暫停、繼續、停止；失敗時會顯示可理解錯誤，不會改用華語 voice。
6. 開啟本機重播，完成一篇後再次 START；預期 cache hit，不送 `/health` 或 synthesis。從 history 重播也不送 synthesis。清除全部後 history 與 IndexedDB 為空。
7. Review notes 補充：新聞頁只透過 `activeTab` 在使用者操作後讀取；任意 HTTPS pattern 是為 user-selected backend，實際只 runtime-request exact origin；所有 remote responses 都是 data，不是 executable code。套件對 `/health`、POST／GET／DELETE 都帶固定的公開 extension ID header；`/v1/` 缺少／錯誤 ID 或 header 與已存在 Origin 不一致時會拒絕，但 Chrome GET 可能不帶 Origin。Header／Origin 不是 secret 或公網 authentication，營運方另使用網路與 rate-limit controls。

送審前先用 isolated Chrome profile 重跑以上流程，並保留 `/health`、POST／GET／DELETE、cache hit 與清除證據。Reviewer backend 必須在整個 review 期間穩定可用、具 rate limit，edge／backend allowlist 與 CORS 必須包含 Dashboard 分配的正式 extension ID。若服務只允許 operator LAN，必須先解決 CWS reviewer 從外部無法重現的問題；不能只把可偽造的 extension header 當成公網保護。
