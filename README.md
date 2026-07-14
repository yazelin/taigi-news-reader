# 台語新聞朗讀器（Chrome 擴充套件）

讓長輩在 Chrome 瀏覽新聞時，選取文字或擷取文章正文，將繁體中文新聞先轉寫成待驗收的台語文字，再用真正的台語語音朗讀。擴充套件不綁定單一服務：可以使用專案提供的免費私人測試，也可以填入自己的後端網址，私有獨立架設。

- 公開介紹與分享頁：<https://yazelin.github.io/taigi-news-reader/>
- 原始碼與自架文件：本 repo
- 目前發佈狀態：Chrome Web Store `0.1.2` 私人版已送審，採審核通過後手動發佈；尚未公開上架。

這個專案目前定位為**非商用**、可驗證技術路徑的 MVP，不宣稱已經達到播音員等級，也不會以華語語音替換文字後冒充台語。repo 內提供 [`facebook/mms-tts-nan`](https://huggingface.co/facebook/mms-tts-nan) 的實際 TTS reference；它是南閩語（`nan`）模型，但音色、腔口、字詞與長輩可懂度仍須由台語母語使用者試聽驗收。

## 先選擇使用方式

| 使用方式 | 適合誰 | 需要準備什麼 | 新聞文字會去哪裡 |
| --- | --- | --- | --- |
| **免費私人測試** | 想先試用、沒有伺服器的一般使用者 | 私人版擴充套件、專案方逐人提供的邀請碼 | 專案 HTTPS 後端，再送到目前設定的翻譯 provider；台語 TTS 在專案伺服器執行 |
| **完全私有／本機自架** | 家庭、社群或組織希望讓資料留在自己的主機 | 自己的後端、HTTPS 網址或同機 localhost、Ollama＋本機 MMS | 新聞、翻譯與音訊都留在自有主機；模型首次下載仍需連到模型來源 |
| **自行託管＋雲端翻譯** | 想自己管理服務與金鑰，但不想在本機跑翻譯模型 | 自架後端、Groq／Gemini／其他 OpenAI-compatible key、本機或 remote TTS | 先到自架後端，再送到部署者選擇的翻譯服務 |
| **本機開發／mock** | 開發者驗證 UI 與資料流 | Chrome、Node.js、Python；mock 不需模型 | 只到 `127.0.0.1`；mock 音訊不是台語 TTS |

一般使用者不必安裝 Ollama、Python 或模型；這些只由自架後端的部署者處理。免費私人測試也不要求使用者提供 Groq／Gemini key。反過來說，「自架」不一定等於「完全離線」：若自架後端仍選 Groq、Gemini 或 remote TTS，文字仍會送到該 provider；只有選擇本機翻譯與本機 TTS，資料邊界才完全留在自己的主機。

## 文件導覽

- 只想了解、分享給朋友：看[公開介紹頁](https://yazelin.github.io/taigi-news-reader/)與下方[免費私人測試](#hosted-private-beta)。
- 要在自己電腦快速看介面：從 [mock mode](#開發快速開始mock-mode) 開始；mock 不會產生真正台語語音。
- 要驗證不經雲端 provider 的實際語音：看[本機 Ollama＋MMS](#開發自架參考ollama-mms-台語-tts)。
- 要部署到家中伺服器／NAS：依 [`deploy/lan/README.md`](deploy/lan/README.md) 的 Docker、nginx、TLS、token 與配額 runbook 操作。
- 要提供 Internet 私人測試：先完成 LAN 安全基線，再看 [`deploy/private-beta/README.md`](deploy/private-beta/README.md)；這是 hardening 範本，不是公開服務的一鍵安裝器。
- 要理解 API 與元件邊界：看 [`backend/README.md`](backend/README.md)及 [`docs/architecture.md`](docs/architecture.md)。
- 要驗收功能與台語品質：看 [`docs/manual-test.md`](docs/manual-test.md)與 [`docs/validation.md`](docs/validation.md)。
- 要確認資料處理、授權與商店發佈：看 [`PRIVACY.md`](PRIVACY.md)、[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)、[`docs/chrome-web-store-readiness.md`](docs/chrome-web-store-readiness.md)及 [`docs/chrome-web-store-listing.md`](docs/chrome-web-store-listing.md)。

## 最簡架構

```text
新聞頁面
  ↓ 使用者主動選取／按下朗讀
Chrome 擴充套件（只傳純文字）
  ↓ HTTPS + 邀請碼；localhost 開發可用 HTTP
自己或專案方營運的後端
  ├─ 驗證、配額與工作隔離
  ├─ 翻譯：繁中新聞 → 台語羅馬字候選
  └─ TTS：台語文字 → 音訊
  ↓
Chrome 播放、暫停、停止與選用的本機重播
```

瀏覽器不能單靠 Web Speech API 保證每台電腦都有台語聲音，所以語言轉換與合成放在後端。擴充套件只認識本 repo 的 HTTP API，不直接持有任何翻譯或 TTS provider key；換 provider 不需要重新把金鑰包進擴充套件。

### 可組合的 provider

| 翻譯 | 台語 TTS | 特性 |
| --- | --- | --- |
| Ollama（Qwen reference） | 本機 `facebook/mms-tts-nan` | 不需雲端 API key，可完全留在自有主機；需要下載模型與足夠 CPU／RAM |
| Groq 或其他 OpenAI-compatible API | 本機 `facebook/mms-tts-nan` | 翻譯在雲端、語音在自有主機；provider key 只放後端 |
| Gemini | 本機 `facebook/mms-tts-nan` | 翻譯在 Gemini、語音在自有主機；使用 Free tier 前須確認資料政策 |
| 任一支援的翻譯器 | remote TTS adapter | 可接另一個真正台語語音服務；API 不同時需新增 adapter／受控轉接層 |

Qwen 不是必要條件，Groq 或 Gemini 也不是擴充套件的硬性依賴。`facebook/mms-tts-nan` 的模型授權是 **CC BY-NC 4.0**，本 repo 目前只把它用於非商業用途；若要商用，必須更換授權合適的 TTS 或另行取得授權。

Chrome 路徑不再用一個可能持續數十秒的 `POST /v1/synthesize`，也不讓 offscreen document 負責網路請求。MV3 可能在約 30 秒後終止長時間 fetch；實測舊流程曾在約 39 秒失敗。現在由 service worker 建立非同步工作：`POST /v1/synthesis-jobs` 取得 UUID4 job id，以短 `GET /v1/synthesis-jobs/{job_id}` 輪詢，拿到完成音訊後立即 `DELETE`；offscreen 只把完成資料轉成 Blob 並控制 audio 播放。使用者按 STOP 時也會 `DELETE`。如果 provider 仍在不能安全中斷的 thread 中工作，DELETE 會立即對該 owner 隱藏並冪等確認 job，但 active／outstanding capacity 仍計到 provider 真正結束，避免用 create/delete loop 製造額外推論容量。

`POST /v1/synthesize` 只保留給預設開放的 local development／診斷；Chrome 正常流程不依賴它。Strict invite-token mode 若同時設定 `TAIGI_ALLOW_DIRECT_SYNTHESIS=true` 會在啟動時 fail closed，private-beta ingress 也固定讓 direct route 回 404。

這條 async-job 路徑已完成 Chromium 150 final：37.01 秒 fixture 合成期間 UI 仍是 `preparing`、service worker 全程存活，完成 37 次短 GET 且 backend 維持 1 個 active job；按 STOP 後 DELETE 回報 `found=true`，active job 歸零且 session 中的 active job id 已清除。真實 Gemini 3.5 Flash + 本機 MMS 的 116 字新聞也從 START 在 50.25 秒進入 `playing`，完成 job 隨即 DELETE，offscreen 成功播放音訊；PAUSE／RESUME／STOP 狀態與 backend cleanup 均通過。

`0.1.2` 已通過 extension 的 `npm run check`、backend 測試、private-beta ingress、非 LAN 完整工作及 exact-package fresh-profile Chromium E2E。可重現的 CWS artifact 是 `extension/release/taigi-news-reader-0.1.2.zip`：50,789 bytes，SHA-256 `5639d9b33090a50470dd800ce03c2c620d55fbadea3b4f821c1ab119b6e012e6`。2026-07-14 已把同一 ZIP 提交 CWS；目前是 Private／deferred／pending review，不是 approved 或 published。測試數量會隨程式演進，不在這裡硬編會過時的計數；以 CI 與 [驗證紀錄](docs/validation.md) 為準。

更完整的元件邊界與正式環境方向見 [docs/architecture.md](docs/architecture.md)。
目前已實際驗證到哪裡、哪些仍待真人測試，見 [docs/validation.md](docs/validation.md)。

<a id="hosted-private-beta"></a>

## 免費私人測試：使用專案託管服務

擴充套件目前內建的建議 URL 是 `https://ching-tech.ddns.net/taigi-tts`。`0.1.2` source 已實作每位測試者各自的邀請碼、配額與工作隔離。邀請碼不是 Groq／Gemini provider key：明碼只存在該 Chrome profile 的 `chrome.storage.local`，綁定設定的 backend origin，並只以 `Authorization: Bearer …` 送到同 origin 的 `/v1/`。Server 只設定 SHA-256 digest 與穩定假名 subject；任何把共用 provider key 或共用邀請碼包進 extension ZIP 的作法都會讓安裝者取得它，禁止採用。

「免費私人測試」代表目前不向受邀測試者收費，不代表永久免費、公開註冊或 SLA。每位測試者應取得不同邀請碼；共用同一邀請碼也會共用同一份個人配額。現行 beta 限制如下：

| 限制 | 現行值 |
| --- | ---: |
| 每個邀請碼 subject 每日工作數 | 20 jobs |
| 每個邀請碼 subject 每日原文字元 | 12,000 字元 |
| 所有測試者合計每日工作數／原文字元 | 100 jobs／60,000 字元 |
| 擴充套件每個文字區塊 | 最多 500 字元 |
| 後端單一工作 | 600 原文字元、6,000 翻譯字元、16 MiB WAV |
| MMS 單次模型推論 | 最多 200 POJ 字元；逐段合成為單一 WAV |
| MMS 整份工作期限 | 480 秒 |
| 配額重置 | UTC 00:00；台灣時間 08:00 |

20 jobs 與 500 字元分段會讓單一 subject 的實際上限通常先落在約 10,000 原文字元。工作被接受時就保留配額；後續 provider 失敗或使用者取消不退回。本機重播若已命中 cache，不會再次傳送新聞或扣 backend 配額；重播規則見[本機重播記錄](#本機重播記錄選用)。

以上是專案方目前部署的 **demo profile**，不是寫死在 Chrome 擴充套件裡的永久上限。自架者可以依硬體、成本和使用人數調整 server-side 配額；擴充套件會顯示後端 `/v1/access` 回報的該使用者剩餘額度。

2026-07-13 已把 [`deploy/private-beta/`](deploy/private-beta/README.md) profile 套用到 `192.168.11.11`。推薦 HTTPS endpoint 現在由 strict invite-token Groq＋MMS backend 提供服務；backend 維持單一 worker、沒有 host publish port，使用 durable quota database，container 限 2 GiB memory、沒有額外 swap、4 CPUs。Server 已載入多個彼此獨立的假名 subject，不在 repo 或證據中保存 raw token／digest。開發包仍不會自動選用推薦服務；使用者必須在設定頁主動選擇服務、輸入管理者個別提供的邀請碼並通過 `/v1/access` 驗證。

Live edge／backend 已驗證正式 extension ID 與 CORS pinning、缺少／錯誤 credential 的 401、cross-subject ownership 404、實際每日配額 429、direct synthesis 404，以及 600 source characters／6,000 translated characters／16 MiB audio 的 request caps。從 operator LAN 外經 Tor 出口完成 TLS、`/v1/access` 與完整 Groq＋MMS job，證明不再只是 LAN pilot。Exact `0.1.2` ZIP 也已在 fresh Chromium profile 以正式 ID 通過原生 optional permission、quota 顯示、真實播放、history 與 replay zero-backend-request；完整證據見 [驗證紀錄](docs/validation.md)。

Operator 已在 Groq Console 人工確認 production project 啟用 ZDR，並於 2026-07-14 明確確認先前曝光的 Groq／Gemini keys 均已撤銷；replacement Groq key 正在供應成功請求。撤銷後以同一 reviewer credential 重跑 live Groq→MMS job，完成 POST 202→completed、`audio/wav`、DELETE 204，個人 quota 由 19 jobs／11,993 characters 變成 18／11,986；文件不保存 raw key、token、digest、email 或測試文字。

CWS Dashboard 已完成並重載確認 `0.1.2` package、616-character 詳細描述、Remote code=No、Website content＋Authentication information、certifications、privacy URL 與 reviewer test instructions；Distribution 維持 Private。Submit dialog 已取消「通過審查後自動發布」後送出，成功 modal 明示 submission 成功並提示通過審查後有 30 天 publish window。Status 頁目前仍是待審查；deferred publishing 表示即使未來通過也不會自動發佈。

私人測試者安裝後，在設定頁填入營運方提供的 HTTPS URL 與自己的邀請碼；之後開啟新聞、選取文字或讓套件擷取正文，再按朗讀即可。若未設定、邀請碼被撤銷、配額已滿或後端無法連線，套件必須明確提示對應問題，不得默默改接不明遠端服務或華語 voice。

<a id="self-hosting"></a>

## 私有自架：完全本機或自選 provider

同一套擴充套件可以連到使用者自己架設的相容後端，不必經過 `ching-tech.ddns.net`，也不使用專案免費 beta 的 provider key 或配額。擴充套件設定頁只填「後端 URL＋invite token」，**不能直接填 Groq、Gemini 或 TTS key**；要用自己的 provider 帳號，必須在自己的 backend 環境變數設定。設定頁只會在使用者確認後，向 Chrome 請求所填網址的 **exact origin** optional permission；換回另一個服務時也不會因此取得其他網站的讀取權限。

### URL 與 HTTPS 規則

| 後端網址 | 擴充套件是否接受 | 用途／注意事項 |
| --- | --- | --- |
| `http://127.0.0.1:8765` | 是 | 同一台 Chrome 電腦上的本機開發／自架 |
| `http://localhost:8765` | 是 | 同上；`localhost` 永遠指使用者正在操作的那台電腦 |
| `http://192.168.11.11:8765` | 否 | 一般非 localhost HTTP 會被拒絕，不能只因為在家中 LAN 就省略 TLS |
| `https://taigi.example.net/taigi-tts` | 是 | 建議的 LAN／遠端形式；憑證必須由 Chrome 正常信任 |
| `https://192.168.11.11/...` | 條件式 | 憑證必須有該 IP 的 SAN，且每台裝置都信任簽發它的 CA；通常使用可信 hostname 較簡單 |

若後端在 NAS、家用伺服器或 `192.168.11.11`，最實用的作法是讓 nginx／Caddy 等 reverse proxy 提供受信任的 HTTPS hostname，再把流量轉到未公開的 backend container。不要把 Uvicorn 的 `8765` port 直接 publish 到網際網路，也不要以略過憑證檢查的方式測試。

### 自架的六個步驟

1. 決定資料邊界：完全本機選 Ollama＋MMS；可接受雲端翻譯則選 Groq、Gemini 或其他 OpenAI-compatible provider。
2. 複製 [`backend/.env.example`](backend/.env.example) 為不追蹤的環境設定，填入選定的 provider；不要修改範例檔來保存真實 key。
3. 依[本機 Ollama＋MMS](#開發自架參考ollama-mms-台語-tts)或 [`deploy/lan/README.md`](deploy/lan/README.md) 啟動單一 backend worker，先確認 `/health` 回報預期的 concrete translator 與 synthesizer，而不是 mock。
4. 若不是單人 localhost 開發，固定 extension ID、開啟 origin gate、為每位使用者產生不同 invite token，並設定每 subject／全域日配額與 process capacity caps。
5. LAN／Internet 服務放在受信任的 HTTPS reverse proxy 後；Internet-facing 服務另加每 IP rate／connection limits、request size、監控與清楚的隱私政策。
6. 在擴充套件設定頁填入自己的服務 URL 與自己的邀請碼，接受 exact-origin 權限，儲存並測試後再用短新聞做真人試聽。

### 自架安全底線

- Groq、Gemini、remote TTS 等 **provider key 只放後端**的未追蹤 `.env` 或 secret manager；不能放入擴充套件、Pages、GitHub issue、URL 或前端 log。
- Invite token 是使用者登入自架後端的憑證，不是 provider key。每人一組高熵 token；server 只存 SHA-256 digest 與不含個資的 subject，遺失時可單獨撤銷。
- Extension ID header 與 Chrome Origin 都是公開、可偽造的 client identity，只能當 defense in depth；真正的存取控制仍需 Bearer token、quota、job ownership 及 edge limits。
- 配額數值可以自行調整，但不建議直接關閉。已接受工作在 provider 失敗／取消後不退款；quota SQLite 不保存新聞、翻譯或音訊。
- 目前 job registry 在單一 process 記憶體內；除非先改成共享 queue／store，production 必須維持一個 replica／worker。
- 使用 MMS 時須遵守 CC BY-NC 4.0 與 attribution；非商用自架不會自動解除第三方 provider 的條款與資料政策。

### 營運方部署骨架

repo 後端提供第一級 Gemini translator、generic OpenAI-compatible translator 與 remote 台語 TTS adapters；它們是接線介面，不等於已替營運方完成台語品質或商用授權驗收。建立 `backend/.env.production`（不要 commit）並填入實際 provider：

```dotenv
TAIGI_PROVIDER_MODE=concrete
TAIGI_TRANSLATOR_PROVIDER=openai_compatible
TAIGI_OPENAI_BASE_URL=https://llm.example.com/v1
TAIGI_OPENAI_API_KEY=replace-me
TAIGI_OPENAI_MODEL=replace-me

TAIGI_TTS_PROVIDER=remote
TAIGI_REMOTE_TTS_URL=https://tts.example.com/synthesize
TAIGI_REMOTE_TTS_API_KEY=replace-me

TAIGI_EXTENSION_IDS=abcdefghijklmnopabcdefghijklmnop
TAIGI_ALLOW_LOCALHOST_ORIGINS=false
TAIGI_REQUIRE_ALLOWED_ORIGIN=true

# 私人測試：每位使用者各一個高熵 token，server 只存 SHA-256。
TAIGI_REQUIRE_ACCESS_TOKEN=true
TAIGI_ACCESS_TOKEN_HASHES=tester-001=replace-with-lowercase-sha256
TAIGI_QUOTA_DATABASE_PATH=/var/lib/taigi/quota.sqlite3
TAIGI_DAILY_SUBJECT_JOB_LIMIT=20
TAIGI_DAILY_SUBJECT_CHARACTER_LIMIT=50000
TAIGI_DAILY_GLOBAL_JOB_LIMIT=100
TAIGI_DAILY_GLOBAL_CHARACTER_LIMIT=250000
```

擴充套件對 `/health`、job POST、每次 GET poll 與 DELETE 都會帶 `X-Taigi-Extension-Id: chrome.runtime.id`。Chrome 的部分簡單 GET 可能不帶 Origin，因此 strict backend 以固定 header 為 `/v1/` client gate，Origin 存在時再核對同一 ID；CORS preflight 仍以 exact extension Origin 協商。Extension ID header 與 Origin 都是公開且可被非瀏覽器偽造的識別，不是 API key 或 authentication。Private beta 的 `/v1/` 另要求逐人 bearer invite token，並把工作綁到該 token 的 subject；`/health` 明確不帶 bearer token。Edge 保留每 IP rate／connection limit、request size 與 HTTPS，不能只依賴 bearer token。

每日配額以 SQLite transaction 原子保留：每個 subject 與全域分別限制已接受工作數及 `text` 字元數，UTC 午夜重置。接受後即計費，後續 provider failure 或取消不退回；SQLite 只有 `utc_date/subject/jobs/characters`，不含新聞、翻譯、音訊、raw token 或 token digest。Job result 仍只在單一 process memory，跨 subject 不能讀取／刪除。Terminal GET 會先取得 one-shot delivery lease，payload 與 retained-byte accounting 一直保留到 ASGI response 成功送完或傳輸失敗後的 finalizer 才釋放；同時 DELETE 只做隱藏／ack，不能提早釋放正在傳送的 bytes。全域與每 subject 的 outstanding jobs／retained bytes caps 及 TTL 限制暫存量。這個 beta 架構不得水平擴充 worker，除非 job registry 改為共享 queue／store。

remote TTS endpoint 接收 `{"text":"...","language":"nan-TW","rate":1.0}`，回傳 `{"audio_base64":"...","mime_type":"audio/wav"}`。若供應商 API 不同，應在後端新增 adapter 或部署轉接服務，不能把金鑰或轉接邏輯塞進擴充套件。

目前的非商用目標也可以把 MMS 直接跑在 hosted backend：將 `TAIGI_TTS_PROVIDER=mms`、`TAIGI_MMS_MODEL=facebook/mms-tts-nan`，並以 `docker build --build-arg INSTALL_LOCAL_MMS=1 ...` 建置。這樣一般使用者仍不需安裝模型；模型只存在營運方 server。翻譯端可接 OpenAI-compatible provider，或在同一個私有網路中使用 Ollama。

本機 MMS adapter 會先把已驗證的 POJ 切成最多 200 字元的模型推論段：優先在空白邊界切分，沒有空白時改在連字號後切分，兩者都沒有時才使用不會讓下一段以 Unicode 組合符號開頭的 hard boundary。各段逐一使用同一個 single-flight worker，再把 bounded mono PCM 合成只有一個 RIFF header 的 WAV；不會截斷翻譯，也不會把多個完整 WAV 直接相接。`TAIGI_MAX_AUDIO_BYTES` 仍換算成整份音訊共用的 sample cap，每段只取得剩餘額度且 sample rate 必須一致。Transformers tokenizer 對這些已驗證文字停用二次 normalization，避免交界的空白被逐段剝除；forward 回傳 waveform tensor 後，先用 `numel()` 檢查，再呼叫 `.cpu().flatten().tolist()`，避免超大 tensor 額外膨脹成無界 Python list，WAV encoder 也再次驗證 finite samples／總 bytes。這些是 **pre-`.tolist()` 與 bounded-input controls**，不是完整 pre-forward 保證：每次 model forward 仍會先配置內部 tensor。Private beta 因此同時保留 600／6,000／16 MiB request limits、整份工作 480 秒 timeout、MMS single-flight gate、2 GiB container memory/no-swap cap 與 4-CPU quota。

例如 [Groq 已提供 OpenAI-compatible Chat Completions](https://console.groq.com/docs/openai)，可直接使用現有 adapter：`TAIGI_OPENAI_BASE_URL=https://api.groq.com/openai/v1`，API key 只放 server，模型可先以 `openai/gpt-oss-120b` 做 POJ 品質測試。接得上 API 不等於台語品質已通過；輸出仍須經 MMS 字元 gate、新聞測試集與母語者驗收。

Gemini 是後端已實作的第一級 translation provider；它透過 Google 官方 OpenAI-compatible HTTPS endpoint 接線，但有自己的 provider 選項與環境變數：

```dotenv
TAIGI_TRANSLATOR_PROVIDER=gemini
TAIGI_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
TAIGI_GEMINI_API_KEY=replace-with-server-side-key
TAIGI_GEMINI_MODEL=gemini-3.5-flash
TAIGI_GEMINI_TIMEOUT_SECONDS=45
```

Gemini 已用實際 key 完成 direct API smoke：短句與 116 字新聞請求皆回 200、通過 POJ gate，並由本機 `facebook/mms-tts-nan` 產生 WAV。Chromium 150 的 async-job 完整 E2E 也已通過：live health 確認 `concrete` Gemini 3.5 Flash + MMS，116 字新聞從 START 到 `playing` 為 50.25 秒，service worker 全程存活，完成後 DELETE job，再由 offscreen 播放；PAUSE、RESUME、STOP 及零 active job cleanup 均符合預期。工程流程通過仍不等於台語自然，輸出須用固定新聞測試集反覆測試並交由台語母語者／長輩聽測。

API key 只能放在 backend 的未追蹤環境設定或 secret manager，絕不可提交到 repo、放進 extension 或寫入前端 log。

選用 Gemini API Free tier 前也要先評估資料政策：送出的新聞內容可能被用於改善 Google 產品。營運方必須把這項資料流清楚告知使用者，確認內容是否適合傳送；不能把 Free tier 當成與本機推論相同的隱私邊界。若採其他付費方案，也應依當時適用條款重新確認資料使用與保存政策。

```bash
docker build -t taigi-news-reader-backend backend
docker run --rm --env-file backend/.env.production \
  -p 127.0.0.1:8765:8765 taigi-news-reader-backend
```

再由同機 HTTPS reverse proxy 或受管理平台提供服務。外部 reviewer endpoint 必須維持逐人 authentication、每日與 process caps、每 IP edge limits、監控與明確隱私政策；不要直接把開發用 Uvicorn port 暴露到公網。`deploy/private-beta/` 的 fail-closed ingress／resource-limit profile 已套用到 `.11`，並已從非 LAN Tor 路徑通過 TLS、access 與完整 job smoke；這是 2026-07-13 的 operational evidence，不代表後續監控或 reviewer credential 可以省略。

### 從私人測試升級為公開版

Private trusted testers 與 Public 可以使用同一個 Chrome Web Store item；不需建立另一個 extension ID。Dashboard 已儲存 Private distribution、publisher trusted tester、exact `0.1.2` ZIP、Privacy disclosures 與 test instructions；live ingress、operator-confirmed ZDR、舊 Groq／Gemini keys 撤銷、非 LAN job 與 exact-package E2E 也已完成。Reviewer raw token 只存在 Dashboard password 欄，不在 repo、listing 或 evidence 中。`0.1.2` 現已用 deferred publishing 提交並等待 Private review；尚未核准或發佈。

公開升版時維持同一 item ID，再將 manifest／package 版本提升（例如 `0.1.3`），上傳新 ZIP、更新 privacy／listing／review notes 並重新送審，之後才把 distribution 改成 Public。相同 item ID 讓已安裝的私人版可正常自動更新；本機設定與重播資料也保留，但若公開版更換 authentication 模式，必須提供明確 migration／sign-out 並安全清除舊 invite token。

公開版不能把 CWS trusted-testers 名單誤當成 API authorization，也不能把一組共用 token 烘焙進 extension。上線前要決定可擴充的個別帳號／憑證發放、撤銷與遺失復原流程，重新做容量與成本模型、隱私告知、provider terms、濫用申訴／支援、備份／復原及多使用者負載測試。若仍採 invite token，也必須維持逐人、可撤銷與有限配額，而不是公開共用 secret。

## 開發快速開始：mock mode

需求：

- Python 3.12
- Node.js 20
- 最新穩定版 Chrome

```bash
git clone https://github.com/yazelin/taigi-news-reader.git
cd taigi-news-reader
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e 'backend[dev]'
TAIGI_PROVIDER_MODE=mock \
  uvicorn taigi_news_reader_backend.app:app --host 127.0.0.1 --port 8765
```

另開終端機確認服務：

```bash
curl http://127.0.0.1:8765/health
```

### 以開發模式載入 Chrome 擴充套件

1. 開啟 `chrome://extensions`。
2. 啟用右上角「開發人員模式」。
3. 執行 `cd extension && npm ci && npm run build`。
4. 按「載入未封裝項目」，選擇本 repo 的 `extension/dist/`。
5. 開啟套件的選項頁，在「台語語音服務網址」填入 `http://127.0.0.1:8765`。本機 mock 若未啟用 strict access-token 驗證，可在邀請碼欄輸入只供本機測試的非空 placeholder；它仍只送到 `127.0.0.1` 的 `/v1/`。正式／私人測試環境必須使用管理者逐人提供的高熵邀請碼。按下儲存與測試；預設服務網址刻意留空，不會偷偷連到任何服務。
6. 開一篇新聞，選取一段文字，再由工具列開啟擴充套件並按朗讀。

修改擴充套件後，重新執行 `npm run build`，再到 `chrome://extensions` 按該套件的重新載入按鈕；修改後端後需重啟 `uvicorn`。

## 開發／自架參考：Ollama + MMS 台語 TTS

這一節提供開發者驗證實際台語資料流，**不是要求一般長輩自行安裝**。除了上面的需求，還需要 [Ollama](https://ollama.com/)；第一次使用也需要網路下載 Ollama 語言模型、Transformers 與 `facebook/mms-tts-nan` 權重。模型名稱與環境變數以 `backend/.env.example` 為準。

這條自架路徑中的 Qwen 翻譯器是實驗性 reference，不是台語翻譯品質保證。後端會依 `mms-tts-nan` 的實際 POJ 字元表檢查輸出；若模型產生漢字、阿拉伯數字、華語拼音或不支援的字母，只允許一次修復，仍不合格就回傳明確錯誤，不會把錯誤文字送進 TTS 假裝成功。正式服務應換成經母語者驗收的翻譯 provider。

```bash
ollama serve
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

另開終端機：

```bash
source .venv/bin/activate
python -m pip install -e 'backend[tts]'
export TAIGI_PROVIDER_MODE=concrete
export TAIGI_OLLAMA_BASE_URL=http://127.0.0.1:11434
export TAIGI_OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
export TAIGI_MMS_MODEL=facebook/mms-tts-nan
export TAIGI_MMS_DEVICE=cpu
uvicorn taigi_news_reader_backend.app:app --host 127.0.0.1 --port 8765
```

第一次合成會比後續慢，因為後端會延遲載入 TTS 模型。若機器記憶體不足、模型下載失敗，或 Ollama 沒有啟動，後端應回傳明確錯誤；不應偷偷改用華語 voice。

手動驗收步驟與台語品質檢查表見 [docs/manual-test.md](docs/manual-test.md)。

## 本機重播記錄（選用）

側邊欄的「在這台電腦保留朗讀音訊」**預設關閉**。只有使用者主動開啟後，完整朗讀完一篇新聞，Chrome 才會保存本機重播資料；STOP、錯誤、取消或未完成的 queue 都不會留下 partial history。儲存失敗也不會讓當次播放失敗，只會清楚提示本次未保存。

重播資料有三道上限，任一超過都依 least-recently-used（LRU）順序移除舊項目：

- 最多 5 篇。
- 音訊合計最多 50 MiB；單篇超過 50 MiB 仍可播放，但不保存。
- 每筆從最後播放時間起最多 7 天。

本機重播在 `chrome.storage.local` 使用 `taigiReplayPreferences`、`taigiReplayHistory` 與 `taigiReplayBackendIdentity`（使用者選定的服務網址另由既有 `taigiSettings` 管理）。history 每筆只有 `id`、標題、建立／最後播放時間、語速、段數、音訊 bytes，以及經過長度限制的 `service.mode/translator/synthesizer`；不保存新聞全文、台語翻譯、來源 URL、raw backend URL 或 API key。`taigiReplayBackendIdentity` 只在 opt-in 開啟時保存目前 backend URL、由 `/health` 的 mode／translator／synthesizer 組成的 canonical identity、同一組 sanitized service labels 與檢查時間，不含新聞內容；關閉功能或啟動時發現功能未開啟就會清除。

Cache schema v2 的 `id` 是以 normalized 文字 chunks、語速、目前 backend URL 與上述 provider fingerprint 計算的 SHA-256 hash，原始輸入不會放進 metadata。START 先以目前 URL 加上 stored identity 查 cache，命中時完全不打 `/health` 或 synthesis；miss 才 probe `/health`，同一 URL 背後更換 translator／synthesizer 會得到新 fingerprint 並 miss。Backend 暫時離線時可退回 stored identity；若從未取得可驗證 identity，仍可嘗試當次 synthesis，但不保存成可重播 cache。音訊各段以 ArrayBuffer 存在 extension-origin IndexedDB `taigi-news-reader-replay` 的 `audioEntries` store，不使用 `unlimitedStorage`，也不會同步到其他裝置。

同一組 chunks、語速、backend URL 與 provider fingerprint 再次 START，或從「重播記錄」按重播時，命中 cache 便直接交給 offscreen 播放，不再呼叫 synthesis API。History 會顯示服務 identity；mock 必須明確標成「測試音訊（不是台語 TTS）」。若同一 cache key 已有 history metadata，但音訊遺失或損毀，無論再次 START 或從 history 重播都會以 `REPLAY_CACHE_CORRUPT` 明確失敗、移除壞項目，而且 synthesis request 為零，**不會偷偷重新上傳新聞**；只有尚無對應 metadata 的新 START 才依使用者這次確認的內容走正常 synthesis。每筆可單獨刪除，也可一鍵清除全部；storage 刪除失敗會回報 UI，不會顯示假成功。關閉此功能會在確認後立即刪除所有 history metadata、backend identity 與 cached audio。「清除本次內容」不等於清除重播記錄。

## 隱私與資料流

擴充套件只應在使用者操作後擷取選取文字或文章純文字，不送整頁 HTML、cookie 或瀏覽紀錄。實際資料去向取決於設定的後端：

- **正式託管**：文字離開使用者裝置，送到設定頁顯示的營運方 HTTPS 後端；若後端再呼叫 provider，營運方必須揭露目的地、保存期、是否用於訓練及刪除方式。
- **開發／本機自架**：文字送到 `127.0.0.1`，Ollama 與 MMS 在本機處理，音訊回到 Chrome 播放。

預設關閉本機重播時，擴充套件不持久保存新聞文字或生成音訊；只有上述 explicit opt-in 才會在 Chrome profile 保存 bounded title metadata 與 audio。私人測試邀請碼是另一類本機設定：raw token 只存在 `taigiSettings`、綁定 backend origin，且只以 Authorization 送到該 origin 的 `/v1/`；它屬於 Authentication information，不進入 replay／player／active-job records，也不是 provider key。

Browser-local cache、server quota 與後端 job 是三個不同生命週期。Quota SQLite 只持久保存目前 UTC 日的假名 subject、工作數與字元數，不保存新聞、音訊或 token。非同步 job 全部只存在單一 backend process 的記憶體，依 subject 隔離；原文只活在 active synthesis task 的參數中，從不放入 job registry 或磁碟。Terminal result 只能 claim 一次，payload 保留到 response send／failure finalizer釋放delivery lease後才只留DELETE tombstone；傳送中DELETE不會提早釋放bytes。未被取走／刪除的terminal record或stale lease最多保留600秒。Process關閉會要求取消active jobs，並等待無法立即停止的MMS worker實際結束。

本機重播 metadata 只開放給 extension trusted contexts；一般新聞頁與 content script 不應讀到它。它仍是使用者 Chrome profile 中的本機資料，標題與音訊可能透露閱讀內容，不應視為加密保管。使用者可逐筆刪除、清除全部或關閉功能立即刪除；瀏覽器／作業系統層級的 profile 存取風險仍由裝置安全負責。

本機模型第一次下載時會連到模型發佈平台；這與合成時上傳新聞內容不同。設定頁必須讓使用者看得出目前服務 URL，未設定時不得猜測或自動選擇服務。若託管後端使用 Gemini API Free tier，新聞文字可能被用於改善 Google 產品；部署者須在啟用前揭露並重新核對當時條款。

## 授權與商用限制

repo 內自行撰寫的程式碼採 [MIT License](LICENSE)。模型權重不包含在 MIT 授權內。

`facebook/mms-tts-nan` 模型頁標示為 **CC BY-NC 4.0**；`NC` 代表非商業用途限制。目前專案已確認不作商用，因此可把它當實際 reference TTS，但仍須保留 attribution、遵守完整授權，且不能因為本 repo 是 MIT 就把模型權重視為 MIT。第三方資訊見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。若未來改為商用，必須換成授權合適的 provider 或另行取得模型授權。

後端刻意以 translator / synthesizer adapter 隔開實作。正式 provider 應實作相同介面，並補上：

- 金鑰只能留在後端，不能放進擴充套件。
- timeout、重試、速率限制與可理解的錯誤訊息。
- 使用者可見的資料傳輸與保存說明。
- 母語者試聽、長輩理解度及指定腔口的驗收。

在尚未取得真正台語 provider 時，系統應顯示「目前無可用台語語音」，而不是用華語 voice 冒充。

## 開發

```bash
# 後端
python -m pytest -q backend/tests

# 擴充套件
cd extension
npm ci
npm run check
```

CI 會執行相同層級的測試。更多協作與安全要求見 [AGENTS.md](AGENTS.md)。

### GitHub Pages 與社群分享圖

公開 Pages 使用 `main` branch 的 repo root，來源是 [`index.html`](index.html)，正式 canonical 是 <https://yazelin.github.io/taigi-news-reader/>。社群分享圖保留可維護的 [`assets/og-image.svg`](assets/og-image.svg) 與供 Open Graph／Twitter 使用的 1200×630 [`assets/og-image.png`](assets/og-image.png)。修改 SVG 後可用 Chromium 重產固定尺寸 PNG：

```bash
chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=1 --window-size=1200,630 \
  --screenshot="$PWD/assets/og-image.png" \
  "file://$PWD/assets/og-image.svg"
```

發佈後應檢查 Pages、`robots.txt`、`sitemap.xml`、canonical、OG／Twitter meta 及分享圖都能由未登入瀏覽器取得，再把 Pages URL 貼到社群平台。
