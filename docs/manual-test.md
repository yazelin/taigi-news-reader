# 手動驗收

自動測試負責 API contract 與狀態轉換；手動測試負責真實網頁擷取、Chrome 播放、錯誤引導與台語可懂度。每次修改權限、正文擷取、播放器或 provider 時，至少重跑相關案例。

## 準備

1. Repo 開發測試可在 `extension/` 執行 `npm ci && npm run build` 後載入 `extension/dist/`。已提交商店的回歸基線仍是 exact `extension/release/taigi-news-reader-0.1.2.zip`（50,789 bytes；SHA-256 `5639d9b33090a50470dd800ce03c2c620d55fbadea3b4f821c1ab119b6e012e6`）；下一版 action／換頁流程則使用 exact `extension/release/taigi-news-reader-0.1.3.zip`（52,670 bytes；SHA-256 `8ad5e78ec202524db1912d7e0148aeb05f4085eb437626b842581ea52a072e71`）解壓到另一個空目錄，以最新穩定版 Chrome 的 fresh profile 載入。這個exact-package流程已完成一輪，但仍不得把尚未上傳的`0.1.3`說成已更新商店。
2. 在設定頁明確填入測試 backend URL 與該環境專用的邀請碼。開發時可用 `http://127.0.0.1:8765`；正式情境必須用營運方 HTTPS URL。若 local backend 未啟用 strict token auth，可輸入只供本機的非空 placeholder；不可拿 production／reviewer token做 local test。
3. 先以 `TAIGI_PROVIDER_MODE=mock` 啟動開發後端，確認 `http://127.0.0.1:8765/health` 正常。測 strict auth／quota 時另用測試專用的高熵 tokens 與暫存 SQLite，不讀取或輸出 production secrets。
4. 準備三種頁面：一般新聞、動態載入新聞、非新聞頁。
5. 準備短句、含數字／姓名／地名的段落，以及接近最大允許長度的文字。

2026-07-14 已用原生 Chrome、exact `0.1.3` ZIP、正式 ID、fresh profile 與 repo 自有 fixture 實際通過首次 action、自動擷取、跨 origin 清除舊預覽，以及側欄保持開啟後重新授權；尚未把新分頁、切換分頁與重新整理的每一種組合都做成原生 UI 證據，所以清單不預先整批勾選。

## A. 擴充套件與 mock 資料流

- [ ] 選取一段文字後按朗讀，UI 顯示處理中，最後可播放 mock 音訊。
- [ ] 有選取時只送選取文字，不誤送整篇文章。
- [ ] 無選取時能擷取合理正文；導覽、廣告、留言不應成為主要內容。
- [ ] 無可讀文字時顯示清楚中文提示，不送空 request。
- [ ] 播放、暫停、繼續與停止都可用；連按朗讀不會疊播。
- [ ] 鍵盤可聚焦並操作主要控制項，狀態不是只靠顏色表達。
- [ ] 按工具列 action 會以同一次使用者操作開啟 side panel 並自動讀取 exact active tab；首次開啟不會因 panel 尚未載入而漏掉讀取。
- [ ] 重新整理、導頁或切換分頁時會清除過期預覽，不會朗讀另一頁或保留過期選取內容。
- [ ] 新分頁或跨 origin 導頁後，side panel 的「重新讀取這一頁」會提示再按工具列圖示授權；按圖示後不必關閉 side panel 即可自動讀取新頁面。

在 Chrome DevTools Network 檢查：

- [ ] request 只到 `127.0.0.1:8765`。
- [ ] `/health`、synthesis POST、每次 GET poll 及完成／STOP 後 DELETE 都帶 `X-Taigi-Extension-Id`，值等於 `chrome.runtime.id`；它是固定公開識別，不是使用者 token，也沒有被 caller-supplied header 覆寫。
- [ ] `/health` 不帶 `Authorization`。每個 `/v1/` request 都由共用 wrapper 強制帶 `Authorization: Bearer <configured invite>`；caller 不能覆寫，fetch 使用 `credentials: omit`、`redirect: error`。
- [ ] Request body 沒有 cookie、invite token、完整 HTML 或瀏覽紀錄；raw token 只在 Authorization header，不進 JSON、URL、console 或 error message。
- [ ] 本機重播預設關閉；未 opt-in 時完整朗讀後，`taigiReplayHistory` 與 IndexedDB `audioEntries` 沒有新增資料。
- [ ] Replay metadata／audio 沒有新聞原文、來源 URL、raw backend URL 或 provider secret；語音服務 URL 只存在既有 `taigiSettings.backendUrl`，不被複製進 history。
- [ ] `taigiSettings` 只有 `backendUrl/accessToken/accessTokenOrigin`；raw invite token 綁定 URL origin，只供 trusted extension contexts 讀取，不出現在 player state、active-job store、replay history、IndexedDB 或新聞頁。

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
- [ ] 正確 invite token 可通過 `/v1/access`；missing、malformed、wrong 與 revoked token 都回相同 generic 401＋`WWW-Authenticate`／`Cache-Control: no-store`，不洩漏 subject、digest 或哪一部分不符。
- [ ] 設定頁 password 欄不顯示明碼；只有 `/v1/access` 成功後才保存新設定。拒絕／逾時不破壞先前設定，新增但未使用成功的 exact-origin permission 會盡力撤回。
- [ ] 修改 backend origin 會立即清空邀請碼欄；舊 token 不送新 origin。直接竄改 storage 讓 `accessTokenOrigin` 不符時，任何 request 都 fail closed，並要求重新設定。
- [ ] 清除設定會移除 `taigiSettings` 與舊 origin permission；切換成功也會移除舊 origin permission。Network 確認 token 從未送到 redirect、`/health` 或其他網域。
- [ ] 每個非-preflight `/v1/` request 缺少或帶錯 `X-Taigi-Extension-Id` 都回 403；正確 header 的 GET poll 即使沒有 `Origin` 仍可通過，以涵蓋 Chrome 可能省略 Origin 的行為。
- [ ] 正確 header 搭配另一個 extension ID 的 Origin，或任意網站 Origin，仍回 403；allowed preflight 的 exact extension Origin 可協商 `content-type,x-taigi-extension-id`。
- [ ] `/health` 不以 extension header／invite token 當授權條件，且 response 不含新聞內容或 secret。LAN profile仍受subnet allowlist；private-beta profile對外公開health但套獨立的direct-IP rate／connection limits並移除Authorization。
- [ ] LAN profile從不在允許網段的client會被拒絕。Private-beta profile則從外網逐步觸發每IP rate／connection limit與host-wide connection cap，確認429／拒絕不洩漏內部秘密；不得把LAN allowlist誤寫成Internet beta控制。
- [ ] 明確記錄 extension header 與 Origin 都可被非瀏覽器 client 偽造，不把它們列為 authentication；真正 authentication 是逐人 invite bearer token，但仍須搭配 quota 與 edge controls。
- [ ] 過大 request、provider timeout 都回傳可理解且不洩漏內部秘密的錯誤。
- [ ] Strict invite-token backend 在 `TAIGI_ALLOW_DIRECT_SYNTHESIS=true` 時啟動 fail closed；private-beta edge 的 `POST /v1/synthesize` 固定 404，只有 local/default development可保留direct diagnostic route。
- [ ] Private-beta effective container顯示600 source characters、6,000 translated characters、16 MiB audio、480秒MMS整份timeout、2 GiB hard memory/no-swap與4-CPU quota；程式常數另固定每個MMS inference chunk最多200字元。不要把16 MiB描述成固定音訊秒數。

## C. 驗證、配額與工作隔離

只使用測試 tokens／subjects；不要顯示 production token、digest、個人信箱或新聞全文。

- [ ] Server 設定每位 tester 的 stable pseudonymous subject 與 SHA-256 digest，不保存 raw token；每位 token 不同且可個別撤銷。Extension／ZIP／public docs／logs 都找不到 raw token 或 provider key。
- [ ] `/v1/access` 回目前 subject 的 UTC date、reset timestamp 與 per-subject／global `limits/used/remaining`；response 不含 raw token、digest、新聞或其他 subject 用量明細。
- [ ] Options page儲存後與side panel啟動／每次remote job後，都顯示該subject剩餘jobs／characters及UTC reset；global額度只用於判斷服務上限，不顯示其他subject的used counts。
- [ ] 接受一個 job 後，subject／global jobs 各加 1、characters 依 request 的 stripped text 長度增加；provider 後續失敗或 STOP 取消也不退 quota。因 active／outstanding capacity 拒絕且尚未 admission 的 request 不計 quota。
- [ ] 分別觸發 subject jobs、subject characters、global jobs、global characters 上限；每次都回 generic 429，並有正確 `Retry-After`、`X-RateLimit-Reset`、`Remaining=0` 與 scope，UTC 午夜後可重新使用。
- [ ] Restart backend 後同一 UTC 日的計數仍存在；SQLite schema／rows 只有 `utc_date/subject/jobs/characters`。跨 UTC 午夜操作會移除舊日期 rows，不保留新聞、音訊、raw token 或 digest。
- [ ] Token A 建立的 pending／completed job，Token B 對同 ID 的 GET／DELETE 都得到與 unknown job 相同的 404；A 仍能完成或取消，沒有 ownership leakage。
- [ ] Terminal completed／failed result第一次GET取得one-shot delivery lease，第二次GET為404。以慢send與client disconnect fixture確認payload／retained bytes保留到body send成功或失敗finalizer才釋放；finalizer後owner DELETE tombstone仍回204，大型WAV不能靠重複GET放大egress。
- [ ] 在terminal response仍傳送時並行DELETE：DELETE立即回204並隱藏job，但replacement job仍因retained-byte cap被拒；send finalizer釋放lease後才可取得capacity，且record依delete-request完成移除。
- [ ] DELETE pending、已進入non-cooperative provider thread的job：owner立即看不到、重複DELETE維持204，但active／outstanding capacity到provider真正返回前不下降；create/delete loop不能製造平行MMS推論。
- [ ] 分別觸發每subject outstanding jobs、global outstanding jobs、active jobs、per-subject terminal bytes與global terminal bytes caps；回429或安全terminal failure，不持續增加process memory。TTL後terminal／tombstone／stale delivery lease被清除。
- [ ] Nginx 以 client IP 分別限制 health、access、create、poll／delete request rate與同時 connection；429／拒絕不回顯 Authorization 或內部設定。Backend access logs 不記 `/v1/` request body或 token。
- [ ] Private beta 只有一個 backend worker／replica，quota SQLite 位於 durable volume；effective Compose 另顯示 2 GiB memory、`memswap_limit=2 GiB`（沒有額外 swap）、4 CPUs、600 source characters、6,000 translated characters、16 MiB audio、480秒MMS整份timeout，以及每 subject 每 UTC 日 20 jobs／12,000 characters、全域 100 jobs／60,000 characters。Restart／rollback smoke 通過；未改成 shared job registry 前，不做 multi-worker deployment。
- [ ] 從 operator LAN 外以 reviewer 網路完成 `/health`、`/v1/access`、job、one-shot GET、DELETE 與 quota smoke；這項通過前不得宣稱 reviewer endpoint 可用或送審。

## D. 本機重播與隱私

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

## E. 真實台語路徑

以正式台語 provider 測試；若測自架參考路徑，啟動 Ollama 與 concrete mode。先用 1–2 句短文確認端到端，再測完整段落。自架第一次執行要預留模型下載／載入時間。

- [ ] 實際使用 `facebook/mms-tts-nan`（或 UI 明確標示的另一個真正台語 provider）。
- [ ] 產生的內容是台語表達，不只是華語句子換一個聲音念。
- [ ] 人名、台灣地名、日期、金額、百分比與英文縮寫仍可理解。
- [ ] 語速調整有效，不造成嚴重失真；停止操作能中止目前播放。
- [ ] 文章分段後停頓自然，沒有漏句、重複或順序錯亂。
- [ ] 使用超限fixture確認MMS在waveform tensor完成後、`.tolist()`前以`numel()`拒絕，WAV encoder也拒絕超限iterable／bytes；記錄這不是pre-forward guarantee，model forward仍可能先配置輸出／內部tensor，container memory cap才是額外邊界。
- [ ] 使用超過200字元的合法POJ fixtures分別覆蓋空白邊界、長連字號token與Unicode combining-safe hard boundary，確認優先順序、所有chunk可完整重組原文、每段不超過200字元且下一段不以combining mark開頭；再確認MMS逐段呼叫runtime、共用遞減sample budget與整份timeout，最後WAV只有一個RIFF header且frames為各段總和。Sample rate不一致、空段或總bytes超限都應fail closed，不回傳部分音訊。
- [ ] 在2 GiB live-equivalent container以約200字元POJ做實機RSS smoke；再以完整async job確認多段MMS完成時container沒有OOM／restart。不要把單次smoke描述成所有文字與rate的記憶體保證。

## F. 母語者與長輩驗收

至少邀請一位台語母語使用者與目標年齡層使用者，不先提供原文答案，試聽多個不同來源新聞：

- [ ] 能說出主要事件、人物與結果。
- [ ] 沒有會改變新聞意思的翻譯錯誤。
- [ ] 用詞自然，不是逐字華語直譯。
- [ ] 腔口雖不綁特定縣市，但多數目標使用者可懂。
- [ ] 聲音清楚、音量與語速合適，長句不過度疲勞。

記錄測試日期、Chrome／OS、Ollama 模型、TTS provider 與版本、測試文章類型和失敗案例。涉及新聞內容時只保存必要片段，避免把完整文章或個資貼進 issue。
