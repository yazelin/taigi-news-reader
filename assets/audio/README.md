# 公開台語語音示範檔

這個目錄保存 GitHub Pages「三段實際產生的台語語音」所使用的固定 MP3。播放這些靜態檔案不會呼叫專案後端、不會上傳文字，也不會扣私人測試邀請碼額度。

三段華語短稿皆由本專案在 2026-07-15 自行編寫，未取自第三方新聞，也不代表真實事件、即時天氣或官方通知。它們只用於展示「華語文字 → 台語羅馬字 → 台語 TTS」流程。

## 產生方式

1. 使用 `gemini:gemini-3.5-flash` 產生初始台語羅馬字。
2. 加入網站前逐字檢查，修正明顯的詞義、拼寫與歧義；這不等同台語母語者或指定腔口驗收。
3. 將下方列出的最終羅馬字送入 `huggingface:facebook/mms-tts-nan`，以 1 倍速度產生 16 kHz、單聲道 WAV。
4. 使用 FFmpeg 6.1.1 增加 6 dB 音量，轉成 16 kHz、單聲道、64 kbit/s CBR MP3，並移除來源 metadata。
5. 檔名加入最終 MP3 的 SHA-256 前 8 碼，更新內容時不覆寫舊 URL，避免 GitHub Pages／瀏覽器快取混用版本。

## 音檔清單

| 類型 | 檔案 | 長度 | 大小 | SHA-256 |
| --- | --- | ---: | ---: | --- |
| 天氣與交通 | [`sample-weather-0d6928b9.mp3`](sample-weather-0d6928b9.mp3) | 21.672 秒 | 173,664 bytes | `0d6928b9e91c3cdcbfb6988d85c9deb0631bb574277299be9040457810d95ee8` |
| 社區生活 | [`sample-community-996cb0a9.mp3`](sample-community-996cb0a9.mp3) | 18.756 秒 | 150,336 bytes | `996cb0a905226c592213cf2fab61c812ffaeaf4cb22d9a924e45257d74d2b3e6` |
| 地方文化 | [`sample-culture-6f8130db.mp3`](sample-culture-6f8130db.mp3) | 20.952 秒 | 167,904 bytes | `6f8130dbfb160cc3a7a81a2f508a5f7b1eedd0060d57e3807137ca13e56d16a5` |

### 天氣與交通

- 原始華語：清晨沿海風勢較強，白天雲量逐漸增加，部分地區偶有短暫雨。民眾外出可準備輕便雨具，騎車經過空曠路段時請減速慢行。
- 實際送入 TTS 的台語羅馬字：`tsá-khí-sî iân-hái ê hong-sè khah tōa ji̍t-sî hûn-liōng tsiām-tsiām tsing-ka pōo-hūn tē-khu ū-sî-á ē lo̍h bô-kú ê hōo tāi-ke tshut-mn̂g thang tsún-pī khing-piān ê hōo-kū khiâ-tshia king-kuè khui-khuah ê lōo-tuān ê sî-tsūn tshiánn sái khah bān`

### 社區生活

- 原始華語：社區活動中心試辦週末共餐，由志工準備家常菜，也協助行動不便的長輩登記送餐。主辦單位提醒，餐點數量有限，請有需要的居民提前預約。
- 實際送入 TTS 的台語羅馬字：`siā-khu oa̍h-tāng tiong-sim chhì-pān chiu-boa̍t chò-hóe chia̍h-pn̄g iû chì-kang chún-pī ka-siông-chhài iā pang-chān kiânn-lōo bô-hong-piān ê tióng-pòe teng-kì beh hōo lâng sàng-pn̄g chú-pān tan-ūi thê-chhenn chhan-tiám ê sòo-liōng iú-hān chhiánn ū su-iàu ê ki-bîn thê-chêng ū-iok`

### 地方文化

- 原始華語：地方文化館整理早年街景與生活照片，邀請居民分享照片背後的故事。工作人員將口述內容整理成文字，未來作為社區展覽與教育活動素材。
- 實際送入 TTS 的台語羅馬字：`tē-hng bûn-hoà-koán chíng-lí chá-nî ê ke-kíng kap seng-hoa̍h siòng-phìnn kiò ki-bîn lâi hun-hióng siòng-phìnn āu-piah ê kò͘-sū kang-chok jîn-oân chiong chhùi-kóng ê lāi-iông chíng-lí chò bûn-jī āu-lâi beh chò siā-khu tián-lám kap kàu-io̍k oa̍h-tāng ê châi-liāu`

## 授權與品質限制

語音模型由 Meta AI 發布，模型頁標示為 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)。這些音檔只隨本專案提供非商用示範，並保留模型 attribution；完整第三方說明見 [`../../THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md)。不要把 repo 的 MIT 程式碼授權誤解成模型或這批示範音檔可商用。

台語用詞、腔口與發音仍可能不準確，需由母語者與目標長輩繼續試聽。這些檔案不得作為緊急、醫療、法律或其他要求逐字正確的語音資訊。

這批固定樣本在公開前修正過明顯問題，因此適合呈現 TTS 音色與整體流程，但不是擴充套件每次即時翻譯品質的保證。實際輸出仍會隨輸入內容、翻譯 provider 與模型版本改變。
