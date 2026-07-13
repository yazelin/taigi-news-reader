# 台語新聞朗讀隱私政策

生效日：2026-07-13

本政策適用於「台語新聞朗讀」Chrome 擴充套件、專案提供的推薦非商用語音服務，以及本專案的參考後端。問題或刪除請求可透過 [GitHub Issues](https://github.com/yazelin/taigi-news-reader/issues) 聯絡維護者；Issue 是公開頁面，請勿貼新聞全文、API key、個人資料或其他機密內容。

## 我們處理哪些資料

擴充套件只在使用者主動按下「讀取這一頁」後，暫時讀取目前分頁中選取的文字、新聞標題或文章正文，並先在側邊欄顯示預覽。只有使用者檢查內容並按下「確認並開始朗讀」後，套件才把確認過的純文字、分段與朗讀速度送到使用者選定的語音服務。

套件不會把新聞網址、完整 HTML、Cookie、登入資訊、API key 或瀏覽紀錄送到語音服務。設定完成後，側邊欄可能獨立呼叫該服務的 `/health`，用來顯示連線及 translator／TTS identity；這個 health request 不含新聞文字。

套件對語音服務的 `/health` 與 synthesis job requests 都會帶 `X-Taigi-Extension-Id`，值是 Chrome 指派給這個套件的固定 extension ID。正式商店版本的所有安裝使用相同 ID；它辨識套件，不是單一使用者或單一裝置，也不是密碼、token 或其他祕密。推薦後端以這個值比對允許的 `/v1/` client；如果 request 另有 `Origin`，兩者也必須一致。Chrome 的部分簡單 GET 可能不帶 `Origin`，因此合法 request 不能只靠 `Origin` 是否存在判定。

## 推薦語音服務與第三方處理

公開版的推薦服務是設定頁明確顯示的 `https://ching-tech.ddns.net/taigi-tts`。它接收使用者確認的新聞純文字，透過 Groq inference 產生台語翻譯，再由伺服器上的台語 TTS 產生音訊。Groq 是此流程中接收新聞文字的外部處理者；TTS 在推薦服務的伺服器執行，不把新聞文字交給另一個 TTS API。Provider identity 會由 `/health` 回傳並顯示於本機重播記錄，若實際 provider 改變，本政策也必須先更新。

公開發佈前，營運方必須在 Groq Console 對推薦服務所用 organization／project 啟用 Zero Data Retention（ZDR）、輪替成未曾暴露的新 API key，並重新實測推薦 endpoint。Groq 的官方資料說明指出，inference 預設不保留 customer inputs／outputs，但可靠性或 abuse 調查在未啟用 ZDR 時仍可能暫存最多 30 天；啟用 ZDR 後不會為這些目的保留 customer data。Groq 仍保存不含 customer inputs／outputs 的 usage metadata。Groq 的服務協議另明定，除非客戶明確授權，Inputs／Outputs 不用於訓練或 fine-tuning 模型。詳見 [Groq 資料控制說明](https://console.groq.com/docs/your-data) 與 [Groq Services Agreement](https://console.groq.com/docs/legal/services-agreement)。若上述 ZDR、key rotation 與 endpoint 驗證尚未完成，本專案不應把推薦服務提交為可公開使用的 Chrome Web Store 版本。

Repo 仍保留 Gemini adapter 供自行架設後端的人選用，但 Chrome Web Store 公開版不以 Gemini unpaid quota 作為推薦服務。Google 的 Gemini API 條款說明，Unpaid Services 的 inputs／outputs可能被用於改善 Google 產品，且可能由 human reviewers 處理；這與本專案的公開版資料最小化目標及 Chrome Web Store Limited Use 審查有額外風險。自行改用 Gemini 或其他 provider 的後端營運方，必須另行揭露實際接收者、方案、保存、人工存取及刪除政策，並在傳送前取得適用的同意。詳見 [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms)。

若使用者自行輸入其他 HTTPS 或 localhost 後端，資料會改送到該使用者選定的服務；該服務的營運方與下游 provider 不由本專案控制。使用者應先確認其隱私及保存政策。

## 瀏覽器本機資料

擴充套件會在 Chrome profile 保存下列資料：

- `taigiSettings`：使用者選定的 backend URL，直到使用者在設定頁清除。
- `chrome.storage.session`：播放狀態與尚待清理的 backend job identity；瀏覽器 session 結束後消失。
- 本機重播預設關閉。使用者明確開啟後，`taigiReplayPreferences` 保存開關；`taigiReplayHistory` 最多保存 5 筆標題、時間、語速、音訊大小／段數及 sanitized service identity；`taigiReplayBackendIdentity` 保存 backend URL、provider fingerprint 與檢查時間，但不含新聞內容。
- 重播音訊存在 extension-origin IndexedDB `taigi-news-reader-replay`；總量最多 50 MiB，每筆最多保留到最後播放後 7 天，並依 LRU 移除。它不會同步到其他裝置。

本機重播不保存新聞全文、翻譯文字、新聞 URL、backend API key 或 provider key。標題與生成音訊仍可能透露閱讀內容，且不是由擴充套件另行加密；能存取作業系統帳號或 Chrome profile 的人可能讀取這些資料。使用者可逐筆刪除、清除全部，或關閉重播功能以清除 history、provider identity 與 cached audio。移除擴充套件也會由 Chrome 移除其 extension storage。

## 推薦後端的保存時間

參考後端不把新聞原文寫入 job registry、application log 或磁碟。原文只在 active translation／synthesis task 的記憶體參數中存在；完成後釋放。完成音訊或安全錯誤只存在單一 backend process 的記憶體，正常情況下 Chrome 取得結果後立即 DELETE；若沒有成功刪除，terminal result 最多保留 600 秒並在後續 job API 操作時清理。Process 關閉也會取消 active jobs 並清空這些記憶體資料。

伺服器及 reverse proxy 仍可能為可靠性、安全與濫用防護保存不含 request body 的一般 access metadata，例如時間、狀態碼、來源 IP 及 user agent。正式發佈前，營運方必須確認 production logging 沒有 request／response body、設定明確保存期限，並在政策有變更時先更新本頁。

## 資料用途、分享與安全

資料只用於使用者要求的單一目的：把其確認的新聞文字轉成台語並播放，及提供使用者明確開啟的本機重播。不用於廣告、建立瀏覽画像、信用評估或出售資料，也沒有 analytics／telemetry。除提供此功能所必要的推薦服務與 Groq inference、法律要求或必要安全調查外，不分享資料。

公開推薦服務使用 HTTPS；擴充套件拒絕一般明文 HTTP，只允許使用者為同機開發目的選擇 `localhost`／`127.0.0.1`。Provider keys 只存在 backend secret，不會包進擴充套件或送到 Chrome。

`X-Taigi-Extension-Id` 與瀏覽器可能送出的 `Origin` 都是公開識別資料，非瀏覽器 client 可以偽造，不能視為使用者驗證或安全祕密。LAN 部署仍以來源網段 allowlist、每 IP rate／connection limit、request size／active-job 上限及 HTTPS 作為主要濫用邊界；`/health` 只受 LAN allowlist 與 health rate limit 保護，不以 extension header 當授權條件。若未來把服務開放到公網，營運方必須加入適合公網的 authentication／abuse controls，並在上線前同步更新本政策及套件告知。

本專案對從 Chrome APIs 取得資訊的使用遵守 Chrome Web Store User Data Policy，包括 Limited Use requirements。詳見 [Chrome Web Store Limited Use](https://developer.chrome.com/docs/webstore/program-policies/limited-use)。

## 政策更新

若資料類型、推薦 endpoint、translator／TTS provider、保存方式或分享對象改變，必須先更新本政策、擴充套件內告知及 Chrome Web Store Privacy practices，再推出新版。政策上方的生效日會同步更新。
