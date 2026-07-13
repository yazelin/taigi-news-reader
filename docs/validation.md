# 驗證紀錄

日期：2026-07-13

這份紀錄刻意區分「程式與音訊管線能運作」和「台語品質已適合長輩」。前者已有自動與實際模型驗證；後者仍需正式 provider、母語者與目標使用者驗收。

## 已通過

- Backend：`48 passed`，涵蓋 API schema、CORS、provider 錯誤、hosted adapters、MMS WAV 封裝、POJ 字元 gate 與 HTTPS 設定。
- Extension：ESLint、`12 passed`、production build 全數通過。
- Mock API：`GET /health` 與 `POST /v1/synthesize` 均回 200，回傳可解碼 WAV。
- Chrome 149 headless 能以 `--load-extension` 接受 build 後的 MV3 manifest；side panel 與權限互動仍需有介面的手動測試。
- 真實 MMS：已下載並載入 `facebook/mms-tts-nan`，以合法 POJ 短句產生 54,316-byte、16 kHz、mono、1.696 秒 PCM WAV。
- 真實 Ollama 防線：本機 `qwen3:4b-instruct-2507-q4_K_M` 對測試新聞未能穩定產生符合 MMS 字表的 POJ；後端在一次修復仍失敗後，於 TTS 前明確拒絕，沒有用華語或無效輸出假裝成功。

## 尚未通過／上線前必做

- 選定可呼叫且經母語者驗收的繁中新聞轉自然台語 provider；本機 qwen reference 尚未達標。
- 將已驗證可合成的 MMS reference 部署到非商用 hosted backend，保留 attribution 與 CC BY-NC 4.0 限制；若未來改成商用才需換 provider／授權。
- 部署 HTTPS backend，加入身分驗證、rate limit、監控與正式隱私政策。
- 在有介面的 Chrome 完成設定、權限、正文擷取、side panel 與 offscreen 連續播放手測。
- 由台語母語者與長輩測試新聞、人名、地名、日期、數字、英文縮寫及長文分段。

在這些項目完成前，repo 是可載入、可測試且包含真實 TTS reference 的 MVP，不應宣稱為可直接公開營運的完成品。
