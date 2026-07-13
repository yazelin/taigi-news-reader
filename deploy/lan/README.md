# 安全 LAN backend 部署準備

這份範本的目標主機是 `192.168.11.11/24`，但 **backend 不 publish 任何
host port**。backend 與既有 nginx container 只共用 dedicated external Docker
network `taigi_news_reader_edge`；nginx 透過該 network 的 Docker DNS
`http://taigi-news-reader:8765` 連 backend，再由既有 HTTPS virtual host 對
LAN 提供服務。不得新增 `0.0.0.0:8765` mapping，也不得在路由器做 port
forwarding。

## 先決條件與已知邊界

- 在真正執行前，先由主機管理者確認 `192.168.11.11` 是該主機的固定／保留
  位址、Docker Compose 可用，而且現有 nginx Compose 與設定都有備份。先依
  下節建立 `taigi_news_reader_edge`，再把 nginx **持久**加入該 network；不能
  只靠一次性的 `docker network connect`，否則 container recreate 後會消失。
- `taigi_news_reader_edge` 只能有 nginx 與本 backend 兩個 application
  container。每次部署與更新都檢查成員，不能把其他 workload 接入後再把
  extension header 當 authentication。
- 使用 Chrome 信任、且涵蓋實際 hostname 的憑證。一般公開 CA 不會為
  `192.168.11.11` 這類私有 IP 簽憑證，因此 extension 應填
  `https://<trusted-hostname>/taigi-tts`，不是裸 IP。若一定要用 IP，只能使用
  含 `IP:192.168.11.11` SAN 的私有 CA 憑證，並先在每台 Chrome 裝置信任該
  CA；測試時也不可用 `-k` 掩蓋錯誤。
- nginx 的 `allow 192.168.11.0/24; deny all;` 只適合可信家用 LAN。若有訪客
  Wi-Fi、不可信 IoT、上游 proxy 或不同 subnet，需先調整網路分段／真實 client
  IP 設定。Extension ID header 與 Origin 都能被非瀏覽器 client 偽造，不能當
  完整身分驗證；此方案依靠 LAN allowlist、固定 extension ID、兩者交叉驗證、
  rate limit 與 backend active-job cap 做最小防護，不適合直接公開到 Internet。
- `facebook/mms-tts-nan` 是 CC BY-NC 4.0 reference model；只有非商用情境才
  可照預設 `TAIGI_INSTALL_LOCAL_MMS=1` 使用。

## 1. 準備不追蹤的設定

在目標主機的 repo checkout 中執行：

```bash
cd deploy/lan
cp lan.env.example lan.env
cp backend.env.example backend.env
chmod 600 lan.env backend.env
```

在 `backend.env` 填入 Groq server-side key 與
`chrome://extensions` 顯示的固定 32 字元 extension ID。key 只能留在目標
主機的未追蹤檔案或 secret manager；不要貼進 issue、shell history、nginx
設定、extension 或 container image。Docker daemon 管理者仍能查看 container
環境，因此主機管理權也必須受控。

部署範例刻意設定：

```text
TAIGI_EXTENSION_IDS=<fixed-id>
TAIGI_ALLOW_LOCALHOST_ORIGINS=false
TAIGI_REQUIRE_ALLOWED_ORIGIN=true
```

strict mode 若沒有固定 ID 會拒絕啟動。每個實際 `/v1/` request 都必須帶
`X-Taigi-Extension-Id: <fixed-id>`；Chrome 有送 Origin 時，Origin 還必須是
同一 ID。Chrome 的 GET polling 實測可能沒有 Origin，因此只要固定 ID header
正確就能通過。CORS preflight 尚不能攜帶它正在申請的自訂 header，該 OPTIONS
改以 exact Origin 驗證。任一檢查不符都回 403；`/health` 不觸發模型下載或
付費請求，仍可供同 LAN readiness check。

公開版本預設走 Groq OpenAI-compatible chat completions，不使用 Gemini Free。
正式處理新聞前，organization admin 必須在 Groq Data Controls 實際啟用並
確認 ZDR；Groq 官方說明指出 ZDR 會關閉 inference customer-data retention，
但不會停止不含 input/output 的 usage metadata。CWS privacy disclosure 仍須
誠實列出新聞文字會送到自架 backend，再由 backend 送到 Groq：

- <https://console.groq.com/docs/openai>
- <https://console.groq.com/docs/your-data>

CWS ID 尚未核發時，不可把 `TAIGI_EXTENSION_IDS` 留空。受限 LAN 測試只能
暫時 pin `chrome://extensions` 顯示的 unpacked ID，並在 nginx map 加同一個
exact Origin；取得正式 CWS ID 後立即替換並移除測試 ID。

## 2. 建立 dedicated external edge network

先確認 network 尚未存在；只需建立一次，而且不要指定與現有 bridge 重疊的
subnet：

```bash
docker network inspect taigi_news_reader_edge
docker network create --driver bridge taigi_news_reader_edge
```

若第一個指令已成功，就不要再執行 create。接著編輯既有
`/home/ct/nginx/docker-compose.yml`，**保留原有 network 設定**，只替 nginx
service 與 top-level networks 各新增以下項目：

```yaml
services:
  nginx:
    networks:
      # 保留既有 bridge_network 與其固定 IP 設定。
      taigi_news_reader_edge: {}

networks:
  # 保留既有 bridge_network block。
  taigi_news_reader_edge:
    external: true
    name: taigi_news_reader_edge
```

先在維護時段解析 Compose，再讓 Compose 持久套用 network attachment。`up`
可能 recreate nginx，必須預期短暫連線中斷；不可只執行臨時
`docker network connect` 後就結束：

```bash
cd /home/ct/nginx
docker compose config
docker exec nginx nginx -t
docker compose up -d --no-deps nginx
docker exec nginx nginx -t
docker network inspect taigi_news_reader_edge
```

此時 network 應只有 nginx；backend 啟動後應剛好只有 nginx 與
`taigi-news-reader-lan-backend-1`（實際 Compose container 名可能依版本不同）。
兩份 Compose 都把 network 宣告為 external，因此任一方 `compose down` 都不會
刪除它，也不再依賴既有 nginx project 所擁有的 shared bridge lifecycle。

正常啟動順序是：確認 external network 存在 → 確認 nginx 已持久接入 → 啟動
backend → backend health/DNS 成功 → test/reload nginx edge。正常停止與回復則
相反：先撤 nginx edge 並 test/reload，再停止 backend；通常保留 nginx 的
network attachment 與 external network，避免為下次啟動 recreate nginx。

## 3. 啟動 private-network-only backend

先只解析設定，確認 Compose 最終完全沒有 `ports:`，並且 backend 只加入
dedicated external network：

```bash
docker compose --env-file lan.env -f compose.yaml config
docker compose --env-file lan.env -f compose.yaml build
docker compose --env-file lan.env -f compose.yaml up -d backend
docker compose --env-file lan.env -f compose.yaml ps
docker compose --env-file lan.env -f compose.yaml exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3).read().decode())"
docker run --rm --network taigi_news_reader_edge \
  -v "$PWD/nginx:/config:ro" nginx:1.29.3-alpine \
  nginx -t -c /config/nginx.conf.test
```

image 以非 root `taigi` user 執行；container root filesystem 為 read-only，
模型 cache 是唯一持久 volume。第一次 MMS request 仍可能下載大型模型並需要
足夠 RAM／disk；先在維護時段完成。若改用 remote TTS，把 build arg 設為 0，
並依 backend provider contract 使用 HTTPS endpoint。

## 4. 納入既有 nginx TLS server

1. 把 `nginx/00-taigi-http.conf.example` 複製到 nginx `http` context 會 include
   的位置，替換所有 exact extension ID placeholder。每個合法 ID 需要一條
   Origin map 與兩條 identity map（無 Origin、同 ID Origin）；不可讓 ID A 的
   header 搭配 ID B 的 Origin。該檔也使用 Docker embedded DNS `127.0.0.11`
   動態解析 backend；目標 nginx 必須是 1.27.3 以上，並且已連到
   `taigi_news_reader_edge`。在目標的 `conf.d/*.conf` layout 可將它複製為
   `/home/ct/nginx/00-taigi-http.conf`，讓 nginx 在 `http` context 自動載入。
2. 把 `nginx/taigi-locations.inc` 複製為
   `/home/ct/nginx/taigi-locations.inc`，再只 include 到持有可信憑證的 HTTPS
   `server` block。必須保留 `.inc` 副檔名；若命名為 `.conf`，既有
   `conf.d/*.conf` 會在 `http` context 自動載入 location 並使 `nginx -t`
   失敗。設定裡的 `taigi_backend` upstream 指向 dedicated network alias
   `taigi-news-reader:8765`；不可改成 container 內的 `127.0.0.1`，那會指向
   nginx 自己。若 base path 或 subnet 不同，先明確修改。
3. 上面的 disposable nginx syntax harness 通過後，仍要在真正 nginx container
   內以 `getent hosts taigi-news-reader` 確認 dedicated-network DNS，再確認
   backend health 與完整 config；成功後才 atomic reload。harness 不會驗證
   實際 certificate path 或其他 virtual host。不要由本 repo 自動改 systemd、
   服務設定或現有 TLS key。

範本只代理 `/health` 與 async synthesis jobs；保留的長連線
`POST /v1/synthesize` 明確回 404。create 與約每秒一次的 polling 使用不同
rate-limit zones，超量回 429；request body 上限為 32 KiB。nginx 與 backend
都要求 exact extension ID header，並在 Origin 存在時交叉檢查。completed
response 可能包含大型 WAV，因此 job proxy 關閉 response buffering，避免音訊
落入 nginx proxy temp file。

## 5. 從另一台 LAN Chrome 裝置驗證

將以下 `<host>` 換成憑證涵蓋的 hostname，`<id>` 換成 extension ID：

```bash
curl --fail https://<host>/taigi-tts/health
curl -i -X OPTIONS https://<host>/taigi-tts/v1/synthesis-jobs \
  -H 'Origin: chrome-extension://<id>' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-taigi-extension-id'
curl -i -X OPTIONS https://<host>/taigi-tts/v1/synthesis-jobs \
  -H 'Origin: https://not-allowed.example' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-taigi-extension-id'
```

預期 allowed preflight 為 200、帶正確 CORS origin，且允許
`X-Taigi-Extension-Id`；錯誤 Origin 為 403。實際 POST/GET/DELETE 缺少或送錯
該 header 都必須是 403；GET polling 即使沒有 Origin，正確 header 仍應進入
正常 job response。
LAN client 連 `http://192.168.11.11:8765/health` 必須失敗，而且
`docker compose config` 不得出現 backend host port，
`/taigi-tts/v1/synthesize` 必須是 404。最後才在 extension 設定
`https://<host>/taigi-tts`，依 `docs/manual-test.md` 做 async job、STOP、離線
replay 與 cache clear 測試。

## 回復與更新

回復順序要先關外部入口，再停 backend：

1. 從 HTTPS server 移除 `taigi-locations.inc` include，並移除／停用
   `00-taigi-http.conf`；還原已備份的 nginx 設定。
2. 在 running nginx container 執行 `nginx -t`。只有成功才 reload；若 test
   失敗，running master 仍使用舊設定，應先修復檔案而不是 restart container。
3. 確認原有 virtual hosts、TLS 與部署前 `/taigi-tts` 行為正常後，再執行本
   repo 的 `docker compose down`。不要刪除其他 virtual hosts 或共用憑證。
4. 保留 `taigi_news_reader_edge` 與 nginx 的 persistent Compose attachment，
   可讓重新部署不必 recreate nginx。兩邊 `compose down` 都不會刪 external
   network，也不會影響 nginx 原有的 `bridge_network`。

若確定要完整移除 dedicated network，必須先停止 backend，再從
`/home/ct/nginx/docker-compose.yml` 移除 `taigi_news_reader_edge` attachment，
用 Compose 更新 nginx 並驗證原有 routes；確認 network 沒有 endpoint 後才執行
`docker network rm taigi_news_reader_edge`。不可直接移除仍有 container 連線的
network。

更新前備份設定、閱讀 provider 與 image release notes，重新 build，通過
`/health` 與 preflight 後再恢復入口。`docker compose down` 不會刪模型 volume；
只有明確加 `--volumes` 才會刪除本專案的 model volume。
