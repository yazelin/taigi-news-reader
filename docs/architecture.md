# 架構與資料流

## 設計目標

MVP 解決一個窄而具體的情境：使用者在 Chrome 主動要求朗讀目前新聞的選取段落或正文，系統把繁體中文新聞轉寫成多數台灣長輩可理解的自然台語，再交給真正的台語語音模型合成。

「翻成台語」和「用台語發音」是兩個不同問題。只把華語原文交給華語 TTS，不會變成台語；只改寫成台語文字再用華語 voice 朗讀，也不符合本專案目標。

## 元件

```text
┌─────────────────────────────────────────────┐
│ Chrome                                      │
│  新聞頁 → side panel → service worker       │
│  offscreen：只做 Blob / audio playback       │
└──────────────────┬──────────────────────────┘
                   │ /health + POST job / short GET polls / DELETE
                   │ X-Taigi-Extension-Id: chrome.runtime.id
                   ▼
┌─────────────────────────────────────────────┐
│ Backend API                                 │
│  production: operator HTTPS                 │
│  development: FastAPI on 127.0.0.1:8765     │
│  schema/長度驗證 → Translator → Synthesizer │
└──────────────────────┬──────────────────────┘
                       │ WAV / 明確錯誤
                       ▼
                 Chrome audio player
```

### Chrome 擴充套件

- 在明確使用者操作後讀取選取文字；沒有選取時才嘗試擷取文章正文。
- 只送純文字與必要播放選項，不送 DOM、cookie、local storage 或瀏覽歷史。
- 顯示擷取、轉換、合成、播放與失敗狀態，並提供播放／暫停／停止。
- 不保存 provider secret，不自行假設作業系統提供台語 Web Speech voice。
- service worker 擁有 synthesis job protocol；offscreen document 不發 backend request，只在工作完成後建立 Blob 並控制 audio。

### Backend API

- `GET /health`：讓擴充套件區分「後端無法連線」與合成失敗。
- `POST /v1/synthesis-jobs`：驗證輸入、建立 UUID4 工作並立即回 202 `pending`；active jobs 上限為 4，滿載回 429。
- `GET /v1/synthesis-jobs/{job_id}`：短輪詢 `pending`、`completed` 或 `failed`。
- `DELETE /v1/synthesis-jobs/{job_id}`：完成後移除 result；若仍 active 則取消 task。Chrome 的 STOP 使用相同操作。
- `POST /v1/synthesize`：保留給直接 API 整合與診斷；Chrome 正常路徑不維持這個長請求。
- 正式環境由營運方以 HTTPS 部署並接上合法 providers；開發參考實作只綁 loopback。
- Extension 的共用 backend fetch wrapper 會複製既有 headers，再強制覆寫 `X-Taigi-Extension-Id: chrome.runtime.id`；`/health`、建立 job、每次 poll、完成／STOP／orphan DELETE 都走同一規則，caller 不能換成其他 ID。
- Strict backend 對每個非-preflight `/v1/` request 要求 header 精確命中 extension ID allowlist。Chrome 的簡單 GET 可能省略 `Origin`，所以缺 Origin 本身不拒絕；若 Origin 存在，`chrome-extension://` ID 必須與 header 相同，其他 Origin 也必須符合 allowlist。CORS preflight 尚未帶實際自訂 header 值，故以 exact allowed Origin 及 `Access-Control-Request-Headers` 是否包含 `x-taigi-extension-id` 協商。
- `X-Taigi-Extension-Id` 與 Origin 都是公開、可由非瀏覽器 client 偽造的識別，不是 authentication。LAN deployment 的真正濫用邊界仍是來源網段 allowlist、每 IP rate／connection limit、request size／active-job cap 及 HTTPS；`/health` 不用 header 授權，只套 LAN 與 health rate limit。若改成公網服務，必須另加適合公網的 authentication／abuse controls。
- 預設不將原文與音訊寫入永久儲存。

實際 request / response schema 以後端 OpenAPI 為單一真源；修改契約時 extension 與測試必須在同一個變更內更新。

### 為何使用 job protocol

舊 Chrome 架構把整個翻譯與 TTS 放在一個長 `POST`，而且由 offscreen document 持有 network fetch。MV3 約 30 秒的 fetch／執行生命週期會讓慢模型不可靠；實際長請求曾在約 39 秒遭終止。新流程把網路 ownership 移到 service worker，並只使用很快結束的 request：

```text
service worker                         backend
      │ POST /v1/synthesis-jobs            │
      │────────────────────────────────────>│ 202 pending + UUID4
      │ GET /v1/synthesis-jobs/{id}         │
      │────────────────────────────────────>│ pending
      │     …短輪詢，不持有長 fetch…         │ translate + synthesize
      │ GET /v1/synthesis-jobs/{id}         │
      │────────────────────────────────────>│ completed + WAV result
      │ DELETE /v1/synthesis-jobs/{id}      │
      │────────────────────────────────────>│ 204 / 清除 result
      │ 將音訊交給 offscreen Blob/audio      │
```

STOP 會中止 client polling 並 DELETE job；後端若仍在合成，DELETE 會取消 task。backend shutdown 也會取消所有 active tasks，再關閉 provider clients。

Chromium 150 final 已驗證這個 ownership 邊界：37.01 秒 fixture 仍停在 `preparing` 時，service worker 保持存活、已完成 37 次短 GET，backend 只有 1 個 active job；STOP 送出 DELETE（`found=true`）後 active job 歸零，extension session 中的 active job id 也已清除。真實 `concrete` Gemini 3.5 Flash + MMS 的 116 字流程則在 50.25 秒進入 `playing`，job 完成即 DELETE，再把音訊交由 offscreen 建 Blob／播放；PAUSE、RESUME、STOP 後均無遺留 active job。

固定 ID contract 另以 Chromium `150.0.7871.46` isolated profile + strict mock backend 驗證：backend 精確 pin test extension ID，client 完成 POST 202 → GET 200 → DELETE 204；關掉 backend 後 START 與 explicit REPLAY 都命中本機 cache。測試使用 production `dist/` copy，只為繞過原生 optional-permission prompt 而額外授予 localhost host permission；正式 manifest 沒有 required host permissions。

### 記憶體生命週期

- Job registry 只在單一 backend process 的記憶體內，沒有 database、disk queue 或持久化檔案；restart 後 job 會消失。
- 原文只存在 active task 的呼叫參數，合成結束即釋放；registry record 從不保存原文。
- Terminal result（完整合成結果或安全錯誤）TTL 為 600 秒；每次存取會順便清除過期資料，正常 client 讀完即 DELETE。
- Job ID 使用 UUID4，但不可把難猜的 ID 當成 authentication；extension ID header／Origin 同樣不是祕密。託管環境仍需網路 allowlist 或真正 authentication、濫用防護與 rate limit。
- 同時最多 4 個 active jobs，避免翻譯／TTS 工作無界耗盡 CPU、RAM 或 provider quota。

以上只描述 backend job registry。Chrome 的 optional replay cache 是獨立的 browser-local 儲存，啟用與否不會改變 backend 原文／job 的 memory-only 規則。

### Chrome 本機重播 cache

重播是 explicit opt-in，`taigiReplayPreferences.enabled` 預設不是 `true`。service worker 啟動時把 `chrome.storage.local` access level 限制為 `TRUSTED_CONTEXTS`，並負責 cache lookup、LRU、IndexedDB 與清除；offscreen document 仍只做 Blob／audio playback。manifest 不要求 `unlimitedStorage`。

```text
完整 synthesis queue
  │ 每段音訊暫留 service worker memory
  │ STOP / error / cancel → 丟棄，不建立 history
  ▼ 全篇成功
SHA-256(schema + chunks + rate + backend identity)
  ├─ chrome.storage.local
  │    taigiReplayPreferences: { enabled }
  │    taigiReplayHistory: bounded display metadata
  │    taigiReplayBackendIdentity: URL + provider fingerprint, no news content
  └─ IndexedDB taigi-news-reader-replay
       audioEntries: ordered MIME type + ArrayBuffer chunks
```

`taigiReplayHistory` 每筆欄位嚴格限定為：

- `id`：64-hex SHA-256 cache key。
- `title`、`createdAt`、`lastPlayedAt`、`rate`、`chunkCount`、`bytes`。
- `service`：經過長度限制的 `mode`、`translator`、`synthesizer`，只用來辨識 history 音訊來源；mock 顯示「測試音訊（不是台語 TTS）」。

history metadata 不含新聞全文、台語翻譯、來源 URL、backend URL 或 key。Cache schema v2 的 canonical hash input 包含語言、normalized 完整 chunks、語速、目前 backend URL，以及由 `/health` 的 mode／translator／synthesizer 形成的 canonical provider identity；切換語速、URL 或同 URL 背後的 provider/model 都不共用舊音訊。Hash 只是 cache identity，不是 encryption、authentication 或 provider idempotency key。

`taigiReplayBackendIdentity` 保存 `{backendUrl, identity, service, checkedAt}`，只在 opt-in 開啟時存在且不含新聞內容。START 先以 current backend URL + stored identity lookup，命中便免 `/health` 與 synthesis；miss 才 probe `/health`（已有 stored identity 時 1.5 秒、第一次 4.5 秒）。Probe 失敗可退回同 URL 的 stored identity；完全沒有 identity 時使用 `unknown` 完成當次 synthesis，但不寫 replay cache。關閉 opt-in 或啟動時確認功能未開啟會清掉這筆 identity。

Cache 同時受 5 entries、50 MiB total 與 7 days since `lastPlayedAt` 約束，以 LRU 保留最近播放項目。單篇超過 50 MiB 不寫入。list/get/put 與 startup orphan cleanup 會移除過期、超額、缺 metadata 或缺 audio 的項目；replay 會更新 `lastPlayedAt`。

`put` 先暫存新 audio，再提交已完成 LRU pruning 的 metadata，metadata 成功後才刪除被 evict 的舊 audio。這個 metadata-before-eviction cleanup 順序讓 metadata write failure 可回滾新 audio、保留原本有效的 cache；若 metadata 已提交但舊 audio 清理失敗，則保留新的 authoritative history 並把 cleanup warning 回報 UI，之後可再清理 orphan。

一般 START 先用 stored identity 查同一 cache key，命中便完全跳過 health 與 synthesis；history REPLAY 也不受 backend health gate 阻擋。sidepanel 載入時仍可能獨立送出一次初始 `/health` probe，但 cache playback 本身不送 synthesis request。同一 id 已有 metadata、但 audio 遺失或損毀時，START 與 history REPLAY 都會移除壞項目、拋出 `REPLAY_CACHE_CORRUPT`，且不送任何 synthesis request；只有沒有對應 metadata 的新 START 才走正常 synthesis。使用者可逐筆 DELETE、clear all；把 opt-in 關閉時會先清空 `taigiReplayBackendIdentity`、`taigiReplayHistory` 與 `audioEntries`，再保存 disabled preference。Explicit delete／clear／disable 的 storage error 會一路傳回 UI，成功訊息只在操作 resolve 後顯示；disable 清理失敗時 preference 仍維持 enabled，方便再次清理。Cache write／quota 失敗只影響未來重播，不得逆轉已完成的當次播放。

job creation 與保留的 direct `POST /v1/synthesize` 共用以下 request：

```json
{
  "text": "欲朗讀的新聞文字",
  "source_language": "zh-TW",
  "target_language": "nan-TW",
  "rate": 1.0
}
```

`source_language` / `target_language` 是固定值，`rate` 範圍為 0.5–1.5。direct response 包含 `taigi_text`、`audio_base64`、`mime_type` 與 `provider`；job 完成時相同物件放在 `result`。音訊不得以 data URL 前綴混入 `audio_base64` 欄位。

### Provider adapters

後端把能力切成兩個介面：

1. `Translator`：繁中新聞文字 → 適合目標 TTS 的台語文字／書寫格式。
2. `TtsSynthesizer`：台語文字 → 具有 MIME type、取樣率等 metadata 的音訊。

自架參考實作為 `OllamaTranslator` 與 `MmsTtsSynthesizer`。開發實作為 deterministic `MockTranslator` / `MockTtsSynthesizer`，讓 CI 不下載大型模型。mock output 只能標示為測試資料。目前非商用託管可在 server 沿用 MMS，但翻譯端仍須換成品質合格的 provider，且整體資料政策必須適合實際使用情境。

repo 目前提供下列託管部署接點：

- `GeminiTranslator` 是第一級 provider，選擇值為 `gemini`，使用獨立的 `TAIGI_GEMINI_*` 設定與 Google 官方 OpenAI-compatible endpoint。
- `OpenAICompatibleTranslator` 呼叫 provider 的 chat-completions API；base URL、model 與 API key 只由後端環境變數提供。
- `RemoteTtsSynthesizer` 呼叫營運方選定的台語 TTS endpoint。對方接收 `text`、固定的 `nan-TW` language 與 `rate`，並回傳 base64 WAV。adapter 會拒絕非 WAV、無效 base64、空音訊或超過大小限制的 response。

remote adapter 是一份清楚的協定，不是通用供應商名稱。若實際 provider 的 API 不同，應新增 provider-specific adapter 或受控 shim，並用契約測試確認；不能在文件中把「可接」寫成「已驗證可用」。

### 託管翻譯選項

- **Groq**：`openai/gpt-oss-120b` 已有實際端到端 smoke；目前證據與限制記錄在 [validation.md](validation.md)。
- **Gemini**：第一級 provider 使用 `TAIGI_TRANSLATOR_PROVIDER=gemini`，並讀取 `TAIGI_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`、server-side `TAIGI_GEMINI_API_KEY`、`TAIGI_GEMINI_MODEL=gemini-3.5-flash` 與 `TAIGI_GEMINI_TIMEOUT_SECONDS=45`。短句及 116 字新聞的 direct API → POJ gate → 本機 MMS smoke 皆回 200 並產生 WAV；上述 Chromium 150 async-job + offscreen audio 完整 E2E 亦已通過。

不論選哪個模型，provider output 都要先經 POJ gate 才能送入 MMS，且 gate 只能驗證字元格式，不能判定翻譯正確或台語自然。正式採用仍須固定新聞測試集、重複執行與母語者驗收。

Gemini API Free tier 會形成額外隱私邊界：送出的內容可能被用於改善 Google 產品。營運方須在 provider 選擇與隱私告知中明確標示，並避免傳送不適合此資料政策的內容；若改用付費方案，也要依實際帳戶方案與當時條款重新審查，不可只沿用 Free tier 或過往假設。

所有 Gemini keys 只能存在 backend secret manager 或未追蹤的環境設定，禁止提交到 repo、傳到 extension、包進 build artifact 或出現在 client-visible logs。

## 本機實際路徑的限制

以下是開發者／自架者的參考路徑；一般長輩使用託管服務時不需 Ollama、Python 或本機模型。

- Ollama 語言模型不是台語正確性的保證；專有名詞、數字、地名與新聞語境可能翻錯。
- 翻譯輸出必須先通過 `facebook/mms-tts-nan` 的 POJ 字元白名單；漢字、數字、華語拼音或不支援字母不得進入 TTS。Ollama 只重試修復一次，仍不合格就失敗。
- `facebook/mms-tts-nan` 是具體的南閩語 TTS 模型，但不代表所有腔口、台羅／漢字輸入與長句都同樣自然。
- 長文需要安全分段；分段不能切壞姓名、數字或句意，合併音訊時也要避免突兀停頓。
- 第一版需要網路下載模型，下載後的推論才可在本機進行。硬體需求與第一次啟動時間依裝置而異。
- 模型為 CC BY-NC 4.0，不是可直接投入商業產品的預設方案。

因此品質驗收必須包含台語母語者與實際長輩，不得只靠測試通過或語言代碼 `nan` 判定完成。

## 託管環境 provider

託管 provider 應透過 adapter 取代不可靠的本機元件，不改動 Chrome 的使用流程；非商用 server 可保留已驗證的 MMS synthesizer。建議 adapter contract 至少涵蓋：

- 可取消請求、timeout、有限次重試與 rate-limit 訊號。
- 回傳實際語言／腔口、音訊格式與 provider request id。
- 明確區分不支援、驗證失敗、provider unavailable 與內容過長。
- server-side secret 管理；extension 永遠不接觸 secret。
- 可觀測性不記錄完整新聞原文，敏感欄位預設遮蔽。

選託管 provider 前需逐項確認：授權允許目的用途、台語而非華語聲音、資料處理地域與保存期、是否用客戶資料訓練、刪除機制、可用性，以及母語者的可懂度。

## 威脅邊界

新聞頁面與頁面文字一律視為不可信：

- 不執行頁面提供的程式或指令。
- 翻譯 prompt 以資料區塊包住原文，並告訴模型忽略原文中的命令。
- 限制請求大小與同時請求數，避免頁面造成記憶體／GPU 耗盡。
- loopback 服務仍可能被其他本機網站或 client 探測；需驗證 extension header、存在時的 Origin、content type 與 schema，不能把「localhost」或可偽造的 header 當成完整身分驗證。
- hosted backend 需要 HTTPS、secret 隔離、網路 allowlist／真正 authentication、rate limit、濫用防護與明確隱私政策；endpoint 缺失或無法使用時，extension 必須明確失敗。
- Replay history 的 title、timestamps、hash 與 audio 雖然只留在本機，仍可能揭露閱讀興趣；UI 必須維持 default-off、清楚容量／期限說明與立即刪除控制。
