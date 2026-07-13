# 驗證紀錄

日期：2026-07-13

這份紀錄刻意區分「程式與音訊管線能運作」和「台語品質已適合長輩」。前者已有自動與實際模型驗證；後者仍需正式 provider、母語者與目標使用者驗收。

## 已通過

- Backend：`54 passed`，涵蓋 API schema、CORS、provider 錯誤、hosted adapters、GPT-OSS reasoning 設定與 repair、MMS WAV 封裝、POJ 字元 gate 與 HTTPS 設定。
- Extension：ESLint、`17 passed`、production build 全數通過；測試包含 action／activeTab 接線與 offscreen audio 的快速暫停競態。
- Mock API：`GET /health` 與 `POST /v1/synthesize` 均回 200，回傳可解碼 WAV。
- Chromium 150 有介面 E2E：build 後的 MV3 extension 已成功載入；設定頁可將 backend 儲存為 `http://127.0.0.1:8765` 並顯示連線正常。真實工具列 action click 會在使用者手勢內開啟 side panel 並取得當頁 `activeTab`，不需保留新聞頁的 persistent host permission。測試頁標題與兩段正文成功擷取為 116 字／1 段，且排除指定頁尾噪音。
- Chromium 真實播放控制：短句已走完 extension → Groq → POJ gate → MMS → offscreen audio，backend 回 200；自然播放可到 `completed`，真實 UI 操作也通過 `playing → paused → playing → stopped`，全程沒有 error。快速暫停不再把 `play()` 被 `pause()` 中斷的正常情境誤報為播放失敗。
- 真實 MMS：已下載並載入 `facebook/mms-tts-nan`，以合法 POJ 短句產生 54,316-byte、16 kHz、mono、1.696 秒 PCM WAV。
- Groq hosted 端到端 smoke：已用 OpenAI-compatible adapter 呼叫 Groq 的 `openai/gpt-oss-120b`，模型輸出通過 POJ 字元 gate，並由 `facebook/mms-tts-nan` 完成實際音訊合成。這不是 mock，也沒有降級使用華語 voice。
  - 短句 smoke 產生約 1.81 秒、16 kHz、mono PCM WAV。
  - 新聞句 smoke 產生 16 kHz、mono PCM WAV；最新保存的 artifact 為 8.544 秒。
- 真實 Ollama 防線：本機 `qwen3:4b-instruct-2507-q4_K_M` 對測試新聞未能穩定產生符合 MMS 字表的 POJ；後端在一次修復仍失敗後，於 TTS 前明確拒絕，沒有用華語或無效輸出假裝成功。
- 本機 `qwen3:8b` 曾產生字元表合法但語言品質不正確的 pseudo-POJ，證明字元 gate 只能防格式污染，不能取代母語者／專用翻譯模型的語意與發音驗收。

上述 Groq smoke 證明的是「OpenAI-compatible 翻譯 → gate-valid POJ → MMS TTS → 可解碼 WAV」在這兩次實際請求中完整跑通。POJ 字元 gate 與 WAV 格式檢查只能驗證輸入字表及音訊容器，**不代表翻譯內容、台語用詞、發音或長輩可懂度已通過**。LLM provider 的輸出具有非決定性；即使輸入、模型名稱與參數相同，後續請求仍可能產生不同結果，因此不能把單次 smoke 當成永久品質保證。

有介面重測也實際觀察到這項非決定性：同一則較長新聞曾成功產生 WAV，也曾在一次 strict repair 後仍無法通過 MMS 字元 gate。後端會明確回錯而不是合成不可信輸出。GPT-OSS 現已使用 low reasoning 並保留 8,192 completion tokens，避免預設 reasoning 吃完輸出額度而回傳空內容；這修正 transport reliability，但不保證每次翻譯都能成為合法、自然的 POJ。

## 尚未通過／上線前必做

- Groq `openai/gpt-oss-120b` 已證實可呼叫並能在實測中產生 gate-valid POJ，但仍須以固定新聞測試集重複測試，並由台語母語者審核語意、用詞與發音後，才能決定是否採用；本機 qwen reference 尚未達標。
- 將已驗證可合成的 MMS reference 部署到非商用 hosted backend，保留 attribution 與 CC BY-NC 4.0 限制；若未來改成商用才需換 provider／授權。
- 部署 HTTPS backend，加入身分驗證、rate limit、監控與正式隱私政策。
- 在目標長輩實際使用的 Chrome／作業系統組合再做安裝與長文連續播放驗收；Chromium 150 的設定、權限、正文擷取、實際合成、offscreen 播放與暫停／繼續／停止已通過。
- 由台語母語者與長輩測試新聞、人名、地名、日期、數字、英文縮寫及長文分段。

在這些項目完成前，repo 是可載入、可測試且包含真實 TTS reference 的 MVP，不應宣稱為可直接公開營運的完成品。
