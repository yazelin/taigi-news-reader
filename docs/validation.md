# 驗證紀錄

日期：2026-07-13

這份紀錄刻意區分「程式與音訊管線能運作」和「台語品質已適合長輩」。前者已有自動與實際模型驗證；後者仍需正式 provider、母語者與目標使用者驗收。

## 已通過

- Backend：`91 passed`，涵蓋 API schema、CORS、provider 錯誤、hosted adapters、Gemini、GPT-OSS reasoning、POJ repair、MMS WAV，以及 async job 的 UUID4、狀態轉換、TTL、active cap、DELETE／shutdown cancellation 與不保存原文。Strict request tests 另驗證 `/v1/` missing／wrong extension header 為 403、正確 header 可接受沒有 Origin 的 GET poll、存在時 header／Origin 必須同一 ID，以及 preflight 可協商 `x-taigi-extension-id`。
- Extension：`npm test` 為 `71/71`，ESLint 與 production build 通過；共用 backend fetch wrapper 會保留 caller headers、強制覆寫固定 `X-Taigi-Extension-Id: chrome.runtime.id` 且不 mutate caller，並已驗證 `/health`、synthesis POST、兩次 GET poll、DELETE 及各 composition root 都有接線。除 async job、cleanup 與 offscreen 邊界外，replay cache 測試涵蓋 default-off、disable-and-clear、bounded metadata、schema-v2 SHA-256 identity、count/bytes LRU、7-day expiry、corruption/orphan cleanup、大音訊轉換，以及 cached START/history replay 不受 backend health gate 影響。新增 identity tests 驗證 `/health` mode／translator／synthesizer fingerprint、stored-identity-first 零 health cache hit、provider switch miss、offline stored fallback、unknown 不寫 cache，以及 mock「不是台語 TTS」標示。P1 unit／fault-injection 另驗證同一文章的 corrupt START 以 `REPLAY_CACHE_CORRUPT` 失敗且零 synthesis request、explicit deletion error 不會假報成功、metadata write failure 不會先 evict 舊 audio，以及 post-commit cleanup failure 會回傳 warning。
- Mock API：保留的 `POST /v1/synthesize` 回 200；`POST /v1/synthesis-jobs` → `GET` → `DELETE` 的狀態與音訊 contract 自動測試通過。
- Chromium 150 async-job fixture：37.01 秒時 UI 仍是 `preparing`，service worker 全程存活，已完成 37 次短 GET，backend 維持 1 個 active job。按 STOP 後 DELETE 記錄 `found=true`，active job 變 0，session 中的 active job id 清除。
- Chromium 150 live E2E：`/health` 確認 `concrete` Gemini 3.5 Flash + MMS；116 字新聞由 START 在 50.25 秒進入 `playing`，service worker 全程存活，job 完成即 DELETE，再由 offscreen 建立／播放音訊。PAUSE 到 `paused`、RESUME 回 `playing`、STOP 到 `stopped`，最後沒有 active job。
- Chromium `150.0.7871.46` strict-header／replay-cache E2E（isolated profile）：strict backend 精確 pin test copy 的 extension ID，真實 Chrome client 完成 POST 202 → GET 200 → DELETE 204；fresh `GET_REPLAY_HISTORY` 為 `enabled=false/history=[]`，opt-in 後第一次 mock START 為 `cacheHit=false`，播放完成並保存 8,044-byte、1-chunk IndexedDB entry。關掉 backend 後，相同 START 與 explicit REPLAY 都回 `cacheHit=true/completed`，沒有 `/health` 或 synthesis request；`CLEAR_REPLAY_HISTORY` 回空 history，隨後直接 `getAllKeys()` 也是 `[]`。測試從 production `dist/` 建 copy，只為繞過原生 optional-permission prompt 而額外授予 localhost host permission；正式 manifest 未加入 required host permissions。
- Chromium `149.0.7827.55` corrupt-cache E2E（isolated profile）：先由真實 side panel 建立一筆完整 8,044-byte cache，再只刪除 IndexedDB audio、保留 history metadata，並完全停止 mock backend。對相同文章再次 START 時畫面明確顯示「本機重播音訊已損毀或遺失，不會自動重新呼叫語音服務。」；CDP 觀察到零 `/health` 或 synthesis request，隨後 history 與 IndexedDB keys 都變成空陣列。建檔階段同一組 Network instrumentation 曾實際捕捉 `/health`、POST、GET poll、DELETE，排除監測未啟用造成的假陰性。測試 copy 同樣只增加 test-only localhost host permission，正式 manifest 未改。
- 舊 direct/offscreen network 架構的短句曾完成播放與控制，但較長的實際 synthesis fetch 在約 39 秒遭 MV3 終止。這是已重現的失敗，也是改成 service-worker job protocol 的原因；舊結果不可當成新架構 E2E 證據。
- 真實 MMS：已下載並載入 `facebook/mms-tts-nan`，以合法 POJ 短句產生 54,316-byte、16 kHz、mono、1.696 秒 PCM WAV。
- Groq hosted 端到端 smoke：已用 OpenAI-compatible adapter 呼叫 Groq 的 `openai/gpt-oss-120b`，模型輸出通過 POJ 字元 gate，並由 `facebook/mms-tts-nan` 完成實際音訊合成。這不是 mock，也沒有降級使用華語 voice。
  - 短句 smoke 產生約 1.81 秒、16 kHz、mono PCM WAV。
  - 新聞句 smoke 產生 16 kHz、mono PCM WAV；最新保存的 artifact 為 8.544 秒。
- Gemini 第一級 provider：已用實際 API key 直連 `gemini-3.5-flash`；短句與 116 字新聞請求皆回 200、通過 POJ gate，並由本機 `facebook/mms-tts-nan` 產生 WAV。key 未寫入文件或 repo；direct backend 與上述 Chrome async-job E2E 均已有實證。
- 真實 Ollama 防線：本機 `qwen3:4b-instruct-2507-q4_K_M` 對測試新聞未能穩定產生符合 MMS 字表的 POJ；後端在一次修復仍失敗後，於 TTS 前明確拒絕，沒有用華語或無效輸出假裝成功。
- 本機 `qwen3:8b` 曾產生字元表合法但語言品質不正確的 pseudo-POJ，證明字元 gate 只能防格式污染，不能取代母語者／專用翻譯模型的語意與發音驗收。

上述 Groq smoke 證明的是「OpenAI-compatible 翻譯 → gate-valid POJ → MMS TTS → 可解碼 WAV」在這兩次實際請求中完整跑通。POJ 字元 gate 與 WAV 格式檢查只能驗證輸入字表及音訊容器，**不代表翻譯內容、台語用詞、發音或長輩可懂度已通過**。LLM provider 的輸出具有非決定性；即使輸入、模型名稱與參數相同，後續請求仍可能產生不同結果，因此不能把單次 smoke 當成永久品質保證。

有介面重測也實際觀察到這項非決定性：同一則較長新聞曾成功產生 WAV，也曾在一次 strict repair 後仍無法通過 MMS 字元 gate。後端會明確回錯而不是合成不可信輸出。GPT-OSS 現已使用 low reasoning 並保留 8,192 completion tokens；首次 translation content 為空時也會用完全相同的 provider request 自動重試一次，不會拿 reasoning、華語原文或其他 provider 冒充翻譯。這些修正改善 transport reliability，但不保證每次翻譯都能成為合法、自然的 POJ。

## 尚未通過／上線前必做

- Groq `openai/gpt-oss-120b` 已證實可呼叫並能在實測中產生 gate-valid POJ，但仍須以固定新聞測試集重複測試，並由台語母語者審核語意、用詞與發音後，才能決定是否採用；本機 qwen reference 尚未達標。
- Gemini + async job + Chrome 工程 E2E 已通過，但仍須由台語母語者與長輩聽測翻譯、用詞、發音與可懂度。若用 Free tier，須先接受並揭露送出內容可能被用於改善 Google 產品的資料政策；所有 keys 只能留在 backend secret，不可提交。
- Extension 的 71-test automated baseline，以及真實 Chromium 的 strict-header async job、default-off、opt-in／完整 queue save、離線 START／REPLAY cache hit、corrupt START 零 request／雙向清除與 clear-all IndexedDB E2E 已通過。Schema-v2 provider fingerprint 的 provider-switch、LRU／TTL、逐筆刪除、停用即清除、原生 optional-permission prompt 及完整 cached-audio controls 仍須依 [manual-test.md](manual-test.md) 在正式 manifest 與目標裝置手動驗收。
- 將已驗證可合成的 MMS reference 部署到非商用 hosted backend，保留 attribution 與 CC BY-NC 4.0 限制；若未來改成商用才需換 provider／授權。
- 把設計 URL `https://ching-tech.ddns.net/taigi-tts` 的 root reverse-proxy 實際部署完成；2026-07-13 的 `/health` 仍被導向公司首頁 HTML，這是部署未完成，不是套件 URL 設計錯誤。
- 完成 HTTPS backend 的 LAN allowlist、固定 extension ID gate、rate／connection limit、監控與正式隱私政策。Extension header／Origin 都可偽造，不是 authentication；若改開公網，必須另加真正 authentication／abuse controls。
- 在目標長輩實際使用的 Chrome／作業系統組合完成安裝、更多長文連續播放與可用性驗收；Chromium 150 的 async job、STOP cancellation 與 audio 控制結果不能取代所有目標裝置測試。
- 由台語母語者與長輩測試新聞、人名、地名、日期、數字、英文縮寫及長文分段。

在這些項目完成前，repo 是可載入、可測試且包含真實 TTS reference 的 MVP，不應宣稱為可直接公開營運的完成品。
