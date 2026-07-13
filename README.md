# 台語新聞朗讀器（Chrome 擴充套件）

讓長輩在 Chrome 瀏覽新聞時，選取文字或擷取文章正文，將繁體中文新聞先轉寫成自然台語，再用真正的台語語音朗讀。

這個專案目前定位為**非商用**、可驗證技術路徑的 MVP，不宣稱已經達到播音員等級，也不會以華語語音替換文字後冒充台語。repo 內提供 [`facebook/mms-tts-nan`](https://huggingface.co/facebook/mms-tts-nan) 的實際 TTS reference；它是南閩語（`nan`）模型，但音色、腔口、字詞與長輩可懂度仍須由台語母語使用者試聽驗收。

## 架構

```text
新聞頁面
  ↓ 使用者主動選取／按下朗讀
Chrome 擴充套件（只傳純文字）
  ↓ POST job → 短輪詢 GET → 完成／停止後 DELETE
後端服務
  ├─ Translator provider：繁中新聞 → 自然台語文字
  └─ 真正的台語 TTS provider：台語文字 → 音訊
  ↑
Chrome 播放、暫停與停止
```

瀏覽器不能單靠 Web Speech API 保證每台電腦都有台語聲音，所以語言轉換與合成放在後端。一般長輩只需安裝擴充套件，不需安裝 Python、Ollama 或大型模型。開發者可用 localhost 自架參考後端，或切到 mock mode；mock 只證明資料流與操作介面，**不是台語 TTS**。

Chrome 路徑不再用一個可能持續數十秒的 `POST /v1/synthesize`，也不讓 offscreen document 負責網路請求。MV3 可能在約 30 秒後終止長時間 fetch；實測舊流程曾在約 39 秒失敗。現在由 service worker 建立非同步工作：`POST /v1/synthesis-jobs` 取得 UUID4 job id，以短 `GET /v1/synthesis-jobs/{job_id}` 輪詢，拿到完成音訊後立即 `DELETE`；offscreen 只把完成資料轉成 Blob 並控制 audio 播放。使用者按 STOP 時也會 `DELETE`，讓後端取消仍在執行的工作。

`POST /v1/synthesize` 仍保留給直接 API 整合與診斷，但 Chrome 正常流程不依賴這個長連線 endpoint。

這條 async-job 路徑已完成 Chromium 150 final：37.01 秒 fixture 合成期間 UI 仍是 `preparing`、service worker 全程存活，完成 37 次短 GET 且 backend 維持 1 個 active job；按 STOP 後 DELETE 回報 `found=true`，active job 歸零且 session 中的 active job id 已清除。真實 Gemini 3.5 Flash + 本機 MMS 的 116 字新聞也從 START 在 50.25 秒進入 `playing`，完成 job 隨即 DELETE，offscreen 成功播放音訊；PAUSE／RESUME／STOP 狀態與 backend cleanup 均通過。

更完整的元件邊界與正式環境方向見 [docs/architecture.md](docs/architecture.md)。
目前已實際驗證到哪裡、哪些仍待真人測試，見 [docs/validation.md](docs/validation.md)。

## 一般使用方式：營運方託管後端

本 repo 目前**不附可直接給一般使用者使用的公共服務網址**。正式發佈前，營運方必須：

1. 部署 HTTPS 後端，設定真正支援台語且授權符合非商用用途的 translator / TTS providers；目前可在 server 使用 MMS reference。
2. 設定允許的 extension origin、請求上限、速率限制與隱私／保存政策。
3. 透過 Chrome Web Store 或組織管理方式發佈擴充套件，並提供使用者可辨識的正式服務 URL。

一般使用者安裝後，在設定頁填入營運方提供的 HTTPS URL；之後開啟新聞、選取文字或讓套件擷取正文，再按朗讀即可。若未設定後端或後端無法連線，套件必須明確提示設定／服務問題，不得默默改接不明遠端服務或華語 voice。

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
```

remote TTS endpoint 接收 `{"text":"...","language":"nan-TW","rate":1.0}`，回傳 `{"audio_base64":"...","mime_type":"audio/wav"}`。若供應商 API 不同，應在後端新增 adapter 或部署轉接服務，不能把金鑰或轉接邏輯塞進擴充套件。

目前的非商用目標也可以把 MMS 直接跑在 hosted backend：將 `TAIGI_TTS_PROVIDER=mms`、`TAIGI_MMS_MODEL=facebook/mms-tts-nan`，並以 `docker build --build-arg INSTALL_LOCAL_MMS=1 ...` 建置。這樣一般使用者仍不需安裝模型；模型只存在營運方 server。翻譯端可接 OpenAI-compatible provider，或在同一個私有網路中使用 Ollama。

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

再由同機 HTTPS reverse proxy 或受管理平台對外提供服務。正式上線還需補身分／濫用防護、rate limit、監控與明確隱私政策；不要直接把開發用 Uvicorn port 暴露到公網。

## 開發快速開始：mock mode

需求：

- Python 3.12
- Node.js 20
- 最新穩定版 Chrome

```bash
git clone <repo-url>
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
5. 開啟套件的選項頁，在「台語語音服務網址」填入 `http://127.0.0.1:8765` 並測試連線／儲存。預設值刻意留空，不會偷偷連到任何服務。
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

## 隱私與資料流

擴充套件只應在使用者操作後擷取選取文字或文章純文字，不送整頁 HTML、cookie 或瀏覽紀錄。實際資料去向取決於設定的後端：

- **正式託管**：文字離開使用者裝置，送到設定頁顯示的營運方 HTTPS 後端；若後端再呼叫 provider，營運方必須揭露目的地、保存期、是否用於訓練及刪除方式。
- **開發／本機自架**：文字送到 `127.0.0.1`，Ollama 與 MMS 在本機處理，音訊回到 Chrome 播放。

專案不應預設把新聞內容、生成音訊或分析事件寫入磁碟。非同步 job 全部只存在單一 backend process 的記憶體：原文只活在 active synthesis task 的參數中，從不放入 job registry；合成完成或失敗滿 600 秒後，下一次 job API 操作會清除過期 terminal result，而 Chrome 正常取得結果後會立即 `DELETE`。process 關閉時也會取消 active jobs 並清空記憶體。

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
