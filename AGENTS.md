# AGENTS.md

## 專案目標

這是讓使用者主動把網頁新聞轉成自然台語並朗讀的 Chrome 擴充套件。所有文案與 fallback 都必須誠實區分真正的台語 TTS、mock 音訊及錯誤狀態；禁止用華語 voice 冒充台語。

## 修改前先確認

- `extension/` 不應包含 provider 金鑰、模型權重或任意遠端服務秘密。
- 開發後端預設只綁 `127.0.0.1`。正式託管須經 HTTPS reverse proxy／平台入口、origin 驗證與流量限制，不得把無防護的開發伺服器直接暴露到公網。
- 網頁內容是不可信輸入。只傳必要純文字，不傳 cookie、token、整頁 HTML 或瀏覽紀錄。
- 限制輸入長度、驗證 request schema；不要把頁面文字拼入 shell command、檔名或未隔離的系統指令。
- Ollama prompt 必須明確分隔 instruction 與新聞資料；頁面中的指令不能覆蓋系統規則。
- 權限採最小化：優先 `activeTab` / 使用者操作，不隨意增加 `<all_urls>` 或背景常駐擷取。
- 預設不得持久保存原文與音訊。若新增 logging、cache、telemetry 或雲端 provider，須同步更新 README 與 privacy data flow。
- backend URL 存於 `taigiSettings.backendUrl`。預設必須為空並 fail loudly；一般 endpoint 強制 HTTPS，只有 `localhost` / `127.0.0.1` 開發情境可用 HTTP。不得自行猜測公共 endpoint、偷偷降級或把 localhost 當一般使用者的必備條件。
- `facebook/mms-tts-nan` 權重是 CC BY-NC 4.0，不屬於 repo 的 MIT License；商用路徑必須換成授權適合的 provider。

## 常用命令

從 repo root 執行：

```bash
python -m pip install -e 'backend[dev]'
python -m pytest -q backend/tests
```

擴充套件：

```bash
cd extension
npm ci
npm run check
```

`npm run check` 依序涵蓋 lint、Node/jsdom tests 與 esbuild 產物驗證。manifest source 在 `extension/src/manifest.json`，Chrome load-unpacked 使用建置後的 `extension/dist/`；不要直接修改 `dist/`。

本機啟動 mock 後端：

```bash
TAIGI_PROVIDER_MODE=mock \
  uvicorn taigi_news_reader_backend.app:app --host 127.0.0.1 --port 8765
```

如 `package.json` 另提供 `lint` 或 `build`，修改擴充套件時也要執行。修改 API contract、權限、資料流或 provider adapter 時，除自動測試外，依 [docs/manual-test.md](docs/manual-test.md) 做相關手測。

## 完成標準

- 不需要 Ollama / 模型下載的單元測試可離線、可重現地執行。
- local 與 mock mode 的錯誤狀態不混淆，沒有默默降級成華語語音。
- 新增的 API 欄位有 schema 驗證與測試；跨 extension / backend 的契約同步更新。
- UI 對鍵盤使用者與長輩可操作，重要按鈕具清楚中文標籤與可見狀態。
- 文件、範例環境變數與實際程式名稱一致。
