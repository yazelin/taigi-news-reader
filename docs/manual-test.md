# 手動驗收

自動測試負責 API contract 與狀態轉換；手動測試負責真實網頁擷取、Chrome 播放、錯誤引導與台語可懂度。每次修改權限、正文擷取、播放器或 provider 時，至少重跑相關案例。

## 準備

1. 在 `extension/` 執行 `npm ci && npm run build`，使用最新穩定版 Chrome，以「載入未封裝項目」載入 `extension/dist/`。
2. 在設定頁明確填入測試 backend URL。開發時可用 `http://127.0.0.1:8765`；正式情境必須用營運方 HTTPS URL。
3. 先以 `TAIGI_PROVIDER_MODE=mock` 啟動開發後端，確認 `http://127.0.0.1:8765/health` 正常。
4. 準備三種頁面：一般新聞、動態載入新聞、非新聞頁。
5. 準備短句、含數字／姓名／地名的段落，以及接近最大允許長度的文字。

## A. 擴充套件與 mock 資料流

- [ ] 選取一段文字後按朗讀，UI 顯示處理中，最後可播放 mock 音訊。
- [ ] 有選取時只送選取文字，不誤送整篇文章。
- [ ] 無選取時能擷取合理正文；導覽、廣告、留言不應成為主要內容。
- [ ] 無可讀文字時顯示清楚中文提示，不送空 request。
- [ ] 播放、暫停、繼續與停止都可用；連按朗讀不會疊播。
- [ ] 鍵盤可聚焦並操作主要控制項，狀態不是只靠顏色表達。
- [ ] 重新整理或切換分頁時，不會朗讀另一頁或保留過期選取內容。

在 Chrome DevTools Network 檢查：

- [ ] request 只到 `127.0.0.1:8765`。
- [ ] `/health`、synthesis POST、每次 GET poll 及完成／STOP 後 DELETE 都帶 `X-Taigi-Extension-Id`，值等於 `chrome.runtime.id`；它是固定公開識別，不是使用者 token，也沒有被 caller-supplied header 覆寫。
- [ ] payload 沒有 cookie、token、完整 HTML 或瀏覽紀錄。
- [ ] 本機重播預設關閉；未 opt-in 時完整朗讀後，`taigiReplayHistory` 與 IndexedDB `audioEntries` 沒有新增資料。
- [ ] Replay metadata／audio 沒有新聞原文、來源 URL、raw backend URL 或 provider secret；語音服務 URL 只存在既有 `taigiSettings.backendUrl`，不被複製進 history。

## B. 失敗與安全

- [ ] backend URL 未設定時，提示設定服務；已設定但無法連線時顯示服務無法使用，不顯示模糊的「播放失敗」。
- [ ] 設定頁拒絕一般 `http://` URL，只允許 HTTPS；`localhost` / `127.0.0.1` 的 HTTP 僅供開發。
- [ ] Ollama 未啟動、模型不存在與 TTS 載入失敗時，錯誤可區分且可採取行動。
- [ ] 翻譯器輸出漢字、阿拉伯數字、華語拼音或 MMS 不支援字母時，後端在 TTS 前拒絕，且不產生假成功音訊。
- [ ] 過長文字被安全拒絕或分段，不凍結 Chrome。
- [ ] 特殊字元、emoji、HTML 標籤文字不造成 script injection 或 shell execution。
- [ ] 原文包含「忽略前面指令」等 prompt injection 時，只被當成待轉換內容。
- [ ] 設定的 provider 不可用時，不會偷偷呼叫另一個遠端服務或改用華語 Web Speech voice。

正式託管測試另確認：

- [ ] backend URL 是 HTTPS，設定頁可清楚看見目前目的地。
- [ ] 每個非-preflight `/v1/` request 缺少或帶錯 `X-Taigi-Extension-Id` 都回 403；正確 header 的 GET poll 即使沒有 `Origin` 仍可通過，以涵蓋 Chrome 可能省略 Origin 的行為。
- [ ] 正確 header 搭配另一個 extension ID 的 Origin，或任意網站 Origin，仍回 403；allowed preflight 的 exact extension Origin 可協商 `content-type,x-taigi-extension-id`。
- [ ] `/health` 不以 extension header 當授權條件，但仍受 LAN allowlist、health rate limit／connection limit 保護，且 response 不含新聞內容或 secret。
- [ ] 從不在允許網段的 client 測試會被 edge 拒絕；在允許 LAN 中逐步觸發每 IP rate／connection limit，確認 429／拒絕不洩漏內部秘密。只有偽造正確 header／Origin 不能繞過網段邊界。
- [ ] 明確記錄 extension header 與 Origin 都可被非瀏覽器 client 偽造，不把它們列為 authentication；若服務要開放公網，另驗真正 authentication／abuse controls。
- [ ] 過大 request、provider timeout 都回傳可理解且不洩漏內部秘密的錯誤。

## C. 本機重播與隱私

在 service worker DevTools 的 Application 面板檢查 extension origin storage。先保持「在這台電腦保留朗讀音訊」關閉完成一次朗讀，再開啟功能測試：

2026-07-13 已以 Chromium `150.0.7871.46` isolated profile 完成下列 E2E（為繞過原生 prompt，只在 production `dist/` 的 test-only manifest copy 額外授予 localhost host permission；正式 manifest 未加入 required host permissions）：

- [x] Fresh `GET_REPLAY_HISTORY` 回 `enabled=false/history=[]`。
- [x] Strict backend 精確 pin 該 test copy 的 extension ID；真實 Chrome client 依序完成 job POST 202、GET 200、DELETE 204，證明固定 `X-Taigi-Extension-Id` 路徑能通過 strict gate。
- [x] Opt-in 後首次 mock START 為 `cacheHit=false`，恰有一次 POST、GET、DELETE；完成後保存 8,044-byte、1-chunk IndexedDB entry。
- [x] 關掉 strict backend 後，相同 START 與 explicit REPLAY 都為 `cacheHit=true/completed`，沒有 `/health` 或 synthesis request。
- [x] `CLEAR_REPLAY_HISTORY` 回 `[]`，其後 IndexedDB `getAllKeys()` 也是 `[]`。

以下完整 UI、隱私、邊界與 fault matrix 仍須逐項驗收：

- [ ] Fresh install／清空 extension data 後，`taigiReplayPreferences` 未啟用，UI 清楚顯示預設關閉。
- [ ] 開啟後 `chrome.storage.local.taigiReplayPreferences` 只有 `{enabled: true}`；沒有 `unlimitedStorage` permission。
- [ ] 多段文章尚未完整跑完時，按 STOP、製造 provider error 或開始另一篇；`taigiReplayHistory` 與 IndexedDB 都不留下 partial entry／orphan audio。
- [ ] 全篇 queue 成功後才新增一筆。`taigiReplayHistory` 每筆只有 `id/title/createdAt/lastPlayedAt/rate/chunkCount/bytes/service`；`service` 只有 sanitized `mode/translator/synthesizer`，沒有全文、翻譯、URL、backend 或 key，`id` 是 64 位 hex hash。mock history 必須顯示「測試音訊（不是台語 TTS）」。
- [ ] IndexedDB `taigi-news-reader-replay` / `audioEntries` 有相同 id，chunks 依序只有 MIME type 與 ArrayBuffer audio；一般新聞頁／content script 不能讀取 trusted-context metadata。
- [ ] 關掉 backend 或在 DevTools 阻擋 synthesis API，再從 history 按「重播」；音訊與 PAUSE／RESUME／STOP 正常，Network 沒有 `POST /v1/synthesis-jobs` 或 `POST /v1/synthesize`。
- [ ] Opt-in 開啟後 `taigiReplayBackendIdentity` 只有目前 backend URL、canonical identity、sanitized service triple 與 `checkedAt`，沒有新聞內容；關閉功能及 disabled startup 都會清掉它。
- [ ] 相同 normalized chunks、語速、backend URL 與 stored provider identity 再次 START 會 cache hit，Network 沒有 `/health` 或 synthesis；改語速、文字、URL，或讓同 URL 的 `/health` 改變 mode／translator／synthesizer，都會產生不同 hash、不誤用舊音訊。
- [ ] Cache miss 時才 probe `/health`；backend 離線時沿用同 URL 的 stored identity。清掉 identity 後讓 `/health` 失敗，當次可 synthesis 但 service 為 unknown，完成後不新增 history/audio。
- [ ] 重播某筆會更新 `lastPlayedAt` 並把它變成最近使用項目；建立第 6 筆時只保留最近使用的 5 筆，evicted metadata 與 audio 都消失。
- [ ] 用 fixture 讓總音訊超過 50 MiB，確認依 LRU evict；單篇超過 50 MiB 時當次仍播放並提示不保存。
- [ ] 將測試項目的 `lastPlayedAt` 調成 7 天前並重新讀取 history，metadata 與對應 audio 都被清除。
- [ ] 刪掉某筆 IndexedDB audio、保留 metadata 後，以相同文章／語速／backend 再次 START：UI 明確回報 `REPLAY_CACHE_CORRUPT`，Network 的 synthesis request 為零，且壞 metadata 被移除；重新建立相同 fixture 後從 history 重播也得到同樣結果。
- [ ] 模擬 IndexedDB／quota write failure：當次朗讀仍完成，UI 顯示本機記錄未保存。
- [ ] 在 count／bytes eviction 時模擬 metadata write failure：新 audio 回滾，舊 metadata／audio 仍可重播；metadata 成功後再模擬舊 audio delete failure，新的 bounded history 仍成立且 UI 顯示 cleanup warning，之後可清理 orphan。
- [ ] 每筆「刪除」同步移除 metadata 與 audio；注入 audio-store delete failure 時 UI 顯示錯誤、不顯示「已刪除」，metadata 留著可重試。「清除所有重播記錄」清空兩處但維持 opt-in。
- [ ] 關閉 opt-in 時先出現確認；確認後 preference 為 disabled，所有 backend identity/history/audio 立即清空。取消確認則保留原狀；若清理失敗，錯誤須傳到 UI 且 preference 維持 enabled，不能顯示已關閉。
- [ ] 「清除本次內容」只清當前 UI／session，不會冒充或觸發「清除所有重播記錄」。

## D. 真實台語路徑

以正式台語 provider 測試；若測自架參考路徑，啟動 Ollama 與 concrete mode。先用 1–2 句短文確認端到端，再測完整段落。自架第一次執行要預留模型下載／載入時間。

- [ ] 實際使用 `facebook/mms-tts-nan`（或 UI 明確標示的另一個真正台語 provider）。
- [ ] 產生的內容是台語表達，不只是華語句子換一個聲音念。
- [ ] 人名、台灣地名、日期、金額、百分比與英文縮寫仍可理解。
- [ ] 語速調整有效，不造成嚴重失真；停止操作能中止目前播放。
- [ ] 文章分段後停頓自然，沒有漏句、重複或順序錯亂。

## E. 母語者與長輩驗收

至少邀請一位台語母語使用者與目標年齡層使用者，不先提供原文答案，試聽多個不同來源新聞：

- [ ] 能說出主要事件、人物與結果。
- [ ] 沒有會改變新聞意思的翻譯錯誤。
- [ ] 用詞自然，不是逐字華語直譯。
- [ ] 腔口雖不綁特定縣市，但多數目標使用者可懂。
- [ ] 聲音清楚、音量與語速合適，長句不過度疲勞。

記錄測試日期、Chrome／OS、Ollama 模型、TTS provider 與版本、測試文章類型和失敗案例。涉及新聞內容時只保存必要片段，避免把完整文章或個資貼進 issue。
