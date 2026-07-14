# 台語新聞朗讀隱私政策

生效日：2026-07-14

本政策適用於「台語新聞朗讀」Chrome 擴充套件、專案提供的推薦非商用語音服務，以及本專案的參考後端。問題或刪除請求可透過 [GitHub Issues](https://github.com/yazelin/taigi-news-reader/issues) 聯絡維護者；Issue 是公開頁面，請勿貼新聞全文、API key、個人資料或其他機密內容。

## 我們處理哪些資料

擴充套件只在使用者主動按下「讀取這一頁」後，暫時讀取目前分頁中選取的文字、新聞標題或文章正文，並先在側邊欄顯示預覽。只有使用者檢查內容並按下「確認並開始朗讀」後，套件才把確認過的純文字、分段與朗讀速度送到使用者選定的語音服務。

套件不會把新聞網址、完整 HTML、Cookie、網站登入資訊、provider API key 或瀏覽紀錄送到語音服務。私人測試版另需要每位測試者各自取得的邀請碼；它是用來存取推薦服務的 **Authentication information**，不是 Groq、Gemini 或 TTS provider key。設定完成後，側邊欄可能獨立呼叫該服務的 `/health`，用來顯示連線及 translator／TTS identity；這個 health request 不含新聞文字或邀請碼。

套件對語音服務的 `/health` 與 synthesis job requests 都會帶 `X-Taigi-Extension-Id`，值是 Chrome 指派給這個套件的固定 extension ID。正式商店版本的所有安裝使用相同 ID；它辨識套件，不是單一使用者或單一裝置，也不是密碼、token 或其他祕密。推薦後端以這個值比對允許的 `/v1/` client；如果 request 另有 `Origin`，兩者也必須一致。Chrome 的部分簡單 GET 可能不帶 `Origin`，因此合法 request 不能只靠 `Origin` 是否存在判定。

私人測試邀請碼的明碼只保存在該 Chrome profile 的 `chrome.storage.local` 之 `taigiSettings`，並記錄它所綁定的語音服務 origin。套件只會把它放在 `Authorization: Bearer …` header，送到同一 origin 的 `/v1/` requests；切換服務網域時會清空輸入欄位，`/health`、新聞頁、重播資料、播放狀態及其他網域都不會收到它。Chrome 本機儲存不是額外加密的密碼保管庫；能存取作業系統帳號或 Chrome profile 的人仍可能取得邀請碼。使用者可在設定頁清除服務與邀請碼並撤銷該 origin permission，營運方也可在伺服器撤銷個別邀請碼。

推薦後端不保存邀請碼明碼，只設定每一邀請碼的 SHA-256 digest 與穩定、假名化的 subject。Digest 用於核對憑證，subject 用於隔離工作與計算配額；兩者都不是 provider API key，也不應放入公開 log。SHA-256 digest 不能讓低熵密碼變安全，因此邀請碼必須由營運方產生為高熵隨機值、逐人發放，不能在擴充套件 ZIP、listing 或公開文件中放共用邀請碼。

## 推薦語音服務與第三方處理

私人測試版的推薦服務是設定頁明確顯示的 `https://ching-tech.ddns.net/taigi-tts`。它接收使用者確認的新聞純文字，透過 Groq inference 產生台語翻譯，再由伺服器上的台語 TTS 產生音訊。Groq 是此流程中接收新聞文字的外部處理者；TTS 在推薦服務的伺服器執行，不把新聞文字交給另一個 TTS API。Provider identity 會由 `/health` 回傳並顯示於本機重播記錄，若實際 provider 改變，本政策也必須先更新。

Operator 已在 Groq Console 人工確認推薦服務所用 production project 啟用 Zero Data Retention（ZDR），replacement API key 也已由成功 live job 證明正在使用。2026-07-14，operator 另明確確認先前曝光的 Groq／Gemini keys 均已撤銷，並在撤銷後重跑 live Groq→MMS job成功；文件不保存任何 raw key、token、digest、email或測試文字。Groq 的官方資料說明指出，inference 預設不保留 customer inputs／outputs，但可靠性或 abuse 調查在未啟用 ZDR 時仍可能暫存最多 30 天；啟用 ZDR 後不會為這些目的保留 customer data。Groq 仍保存不含 customer inputs／outputs 的 usage metadata。Groq 的服務協議另明定，除非客戶明確授權，Inputs／Outputs 不用於訓練或 fine-tuning 模型。詳見 [Groq 資料控制說明](https://console.groq.com/docs/your-data) 與 [Groq Services Agreement](https://console.groq.com/docs/legal/services-agreement)。

Repo 仍保留 Gemini adapter 供自行架設後端的人選用，但 Chrome Web Store 公開版不以 Gemini unpaid quota 作為推薦服務。Google 的 Gemini API 條款說明，Unpaid Services 的 inputs／outputs可能被用於改善 Google 產品，且可能由 human reviewers 處理；這與本專案的公開版資料最小化目標及 Chrome Web Store Limited Use 審查有額外風險。自行改用 Gemini 或其他 provider 的後端營運方，必須另行揭露實際接收者、方案、保存、人工存取及刪除政策，並在傳送前取得適用的同意。詳見 [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms)。

若使用者自行輸入其他 HTTPS 或 localhost 後端，資料會改送到該使用者選定的服務；該服務的營運方與下游 provider 不由本專案控制。使用者應先確認其隱私及保存政策。

## 瀏覽器本機資料

擴充套件會在 Chrome profile 保存下列資料：

- `taigiSettings`：使用者選定的 backend URL，直到使用者在設定頁清除。
- `taigiSettings` 也保存私人測試邀請碼及其綁定 origin；邀請碼以 password 欄位輸入，只供 extension trusted contexts 讀取，不進入播放、工作或重播 records。它是 Authentication information，未由擴充套件另行加密。
- `chrome.storage.session`：播放狀態與尚待清理的 backend job identity；瀏覽器 session 結束後消失。
- 本機重播預設關閉。使用者明確開啟後，`taigiReplayPreferences` 保存開關；`taigiReplayHistory` 最多保存 5 筆標題、時間、語速、音訊大小／段數及 sanitized service identity；`taigiReplayBackendIdentity` 保存 backend URL、provider fingerprint 與檢查時間，但不含新聞內容。
- 重播音訊存在 extension-origin IndexedDB `taigi-news-reader-replay`；總量最多 50 MiB，每筆最多保留到最後播放後 7 天，並依 LRU 移除。它不會同步到其他裝置。

本機重播不保存新聞全文、翻譯文字、新聞 URL、私人測試邀請碼、backend API key 或 provider key。標題與生成音訊仍可能透露閱讀內容，且不是由擴充套件另行加密；能存取作業系統帳號或 Chrome profile 的人可能讀取這些資料。使用者可逐筆刪除、清除全部，或關閉重播功能以清除 history、provider identity 與 cached audio。清除服務設定會另行移除邀請碼；移除擴充套件也會由 Chrome 移除其 extension storage。

## 推薦後端的保存時間

參考後端不把新聞原文寫入 job registry、application log、quota database 或磁碟。原文只在 active translation／synthesis task 的記憶體參數中存在；完成後釋放。工作綁定已驗證邀請碼對應的 subject，其他 subject 即使取得 job ID 也不能讀取或刪除。完成音訊或安全錯誤只存在單一 backend process 的記憶體；terminal response 只能成功取得一次。該 GET 會持有一個 delivery lease，payload 與 retained-byte 配額一直保留到 response body 成功送完或傳輸失敗後的 finalizer 才釋放，之後只留可供 Chrome DELETE 的小型 tombstone。傳送期間收到同 owner DELETE 會立即隱藏並確認 job，但不會提早釋放 payload；pending provider 若不能安全中斷，也會繼續占用 active／outstanding capacity 到真正結束。未取走的 terminal record、tombstone 或卡住的 delivery lease 最多保留 600 秒並在後續 job API 操作時清理。全域、每 subject 的 outstanding-job 與 terminal-result bytes 上限會限制記憶體與音訊流量；超過上限會明確失敗。Process 關閉會要求取消 active jobs；不能合作取消的 MMS worker thread 仍會由 service shutdown 等到實際結束。

私人測試後端使用 durable SQLite 只保存目前 UTC 日的配額列：UTC 日期、假名化 subject、已接受工作數與已接受字元數。它不保存新聞原文、翻譯、音訊、邀請碼明碼或 digest。每個 subject 與全域都有每日工作數及字元數上限，於 UTC 午夜重置；已接受的請求即使之後 provider 失敗或使用者取消，仍計入配額。舊日期列會在啟動或配額操作時刪除。這份 SQLite 可跨 backend restart 保留當日用量；job registry 仍是單一 worker 的 process-local memory，因此私人 beta 只執行一個 backend worker／replica。

伺服器及 reverse proxy 仍可能為可靠性、安全與濫用防護保存不含 request body 的一般 access metadata，例如時間、狀態碼、來源 IP 及 user agent。正式發佈前，營運方必須確認 production logging 沒有 request／response body、設定明確保存期限，並在政策有變更時先更新本頁。

## 資料用途、分享與安全

資料只用於使用者要求的單一目的：把其確認的新聞文字轉成台語並播放，及提供使用者明確開啟的本機重播。不用於廣告、建立瀏覽画像、信用評估或出售資料，也沒有 analytics／telemetry。除提供此功能所必要的推薦服務與 Groq inference、法律要求或必要安全調查外，不分享資料。

推薦服務使用 HTTPS；擴充套件拒絕一般明文 HTTP，只允許使用者為同機開發目的選擇 `localhost`／`127.0.0.1`。Provider keys 只存在 backend secret，不會包進擴充套件或送到 Chrome。私人邀請碼只能授權本服務的受限 `/v1/` 功能；它不會讓使用者取得或直接呼叫營運方的 Groq／Gemini provider key。

`X-Taigi-Extension-Id` 與瀏覽器可能送出的 `Origin` 都是公開識別資料，非瀏覽器 client 可以偽造，不能視為使用者驗證或安全祕密。私人測試的真正應用層驗證是逐人、可撤銷的邀請碼；edge 另以每 IP request／connection limits、request size limits、HTTPS，以及 backend 的每日配額、active／outstanding jobs 與 terminal bytes caps 降低濫用風險。Private-beta profile 限制 600 source characters、2,000 translated characters、16 MiB audio，每 subject 每 UTC 日 20 jobs／12,000 characters與全域100 jobs／60,000 characters，以及2 GiB container memory/no-swap與4 CPUs，並強制關閉direct synthesis；2026-07-13 已部署到`.11`，且從非LAN Tor路徑通過TLS、access與完整job smoke。`/health`不接收邀請碼，只套獨立edge limits。服務仍須持續監控；若未來改成公開onboarding／account模式，必須重新檢查本政策與安全邊界。

本專案對從 Chrome APIs 取得資訊的使用遵守 Chrome Web Store User Data Policy，包括 Limited Use requirements。詳見 [Chrome Web Store Limited Use](https://developer.chrome.com/docs/webstore/program-policies/limited-use)。

Chrome 於 2026-07-01 公布的 [Chrome Web Store policy update](https://developer.chrome.com/blog/cws-policy-updates-2026) 要求所有資料收集都向使用者顯著揭露，不再因為資料與 single purpose 密切相關而省略，並自 2026-08-01 起執行。`0.1.3` 的設計在設定頁先顯示服務目的地、Website content／Authentication information 的用途及第三方 Groq，再由使用者按「同意並儲存、測試」；新聞文字另須在 side panel 預覽後按「確認並開始朗讀」才傳送，本機音訊保存則維持 default-off explicit opt-in。2026-07-14 已在 Dashboard 儲存並重載確認 Remote code=No、Website content＋Authentication information、Limited Use certifications 與本 privacy URL，並把 exact `0.1.3` package以deferred publishing提交Private review。Status仍顯示草稿待審查；這不是approval或publication。

## 政策更新

若資料類型、推薦 endpoint、translator／TTS provider、保存方式或分享對象改變，必須先更新本政策、擴充套件內告知及 Chrome Web Store Privacy practices，再推出新版。政策上方的生效日會同步更新。
