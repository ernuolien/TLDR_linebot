# TLDR_linebot

LINE 群組聊天摘要機器人。在群組輸入 `tldr` 就會摘要最近的對話（`/tldr` 也可以）。

## 使用方式

| 指令 | 說明 |
| --- | --- |
| `tldr` | 摘要最近 3 小時 |
| `tldr 6h`、`tldr 2d` | 摘要指定時間（最多 7 天） |
| `tldr 小明`、`tldr @小明` | 統整某人最近 3 小時說了什麼 |
| `tldr 小明 6h`、`tldr 6h 小明` | 人名和時間可以合用，順序不拘 |

- 只在群組／多人聊天室運作；同一群組 1 分鐘內只能觸發一次。
- 人名可以只打一部分，不分大小寫；比對到多人時會請你打完整一點。用 @ 標記最準確，同名也不會認錯。
- 人名只會比對這段時間內有發言的人。比對不到時（例如 `tldr 我覺得太長`）當作一般聊天，機器人不回應。
- 機器人只看得到「加入群組之後」的訊息。
- 訊息保留 7 天後自動刪除；把機器人移出群組會立即刪除該群組的所有紀錄。
- 貼圖、圖片等非文字訊息只記錄為「[貼圖]」「[圖片]」等佔位文字。

## 架構

```
LINE ──HTTPS──▶ Caddy (DuckDNS + Let's Encrypt) ──▶ FastAPI app ──▶ SQLite
                                                        │
                                                        └──▶ LLM（Gemini Flash，失敗時改用 Flash-Lite）
```

| 檔案 | 用途 |
| --- | --- |
| `src/tldr_linebot/app.py` | webhook 伺服器、LINE SDK 轉接、定時清除 |
| `src/tldr_linebot/bot.py` | 機器人行為（儲存、指令、冷卻、摘要），不依賴 LINE SDK |
| `src/tldr_linebot/command.py` | `tldr` 指令解析 |
| `src/tldr_linebot/store.py` | SQLite 存取 |
| `src/tldr_linebot/prompt.py` | 摘要 prompt 與聊天紀錄格式化 |
| `src/tldr_linebot/llm.py` | OpenAI 相容 API 呼叫與供應商備援 |

## 本機開發

```sh
uv sync
uv run pytest
uv run ruff format . && uv run ruff check .
```

## 部署

push 到 `main` 且 CI 通過後，GitHub Actions 會 build 映像推到 `ghcr.io/ernuolien/tldr_linebot`（tag：`latest` 與 commit SHA）。VM 上的 systemd timer 每 5 分鐘拉一次新映像。

### 1. LINE Developers 設定

1. 在 [LINE Developers Console](https://developers.line.biz/console/) 建立 Provider 與 **Messaging API** channel。
2. Basic settings：記下 **Channel secret**。
3. Messaging API：發行 **Channel access token (long-lived)**。
4. Messaging API：開啟 **Allow bot to join group chats**。
5. 在 [LINE Official Account Manager](https://manager.line.biz/) 的回應設定中，關閉「自動回應訊息」與「加入好友的歡迎訊息」，開啟 Webhook。
6. 等 VM 部署好後，把 Webhook URL 設為 `https://<你的子網域>.duckdns.org/callback`，按 Verify，並開啟 **Use webhook**。

### 2. LLM API 金鑰

- 主要：[Google AI Studio](https://aistudio.google.com/apikey) 取得 Gemini API key。免費方案的內容會被 Google 用於改進產品。
- 備援：預設用同一把金鑰的 Gemini Flash-Lite（Flash 忙碌回 503 時接手）；也可改用 [build.nvidia.com](https://build.nvidia.com) 的模型。
- 模型 ID 會隨時間變動，請到各自網站確認後填入 `.env`。

### 3. DuckDNS

到 [duckdns.org](https://www.duckdns.org) 登入，建立一個子網域，記下 token。

### 4. GCP e2-micro VM

1. 建立 VM：機型 `e2-micro`，區域 `us-west1`／`us-central1`／`us-east1`（免費額度限定），開機磁碟選 30GB 標準永久磁碟、Debian 12。
2. 防火牆勾選允許 HTTP 與 HTTPS 流量。
3. SSH 進入 VM 後安裝 Docker：
   ```sh
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER   # 重新登入後生效
   ```
4. 取得部署檔並設定：
   ```sh
   sudo git clone https://github.com/ernuolien/TLDR_linebot.git /opt/tldr_linebot
   sudo chown -R $USER /opt/tldr_linebot
   cd /opt/tldr_linebot
   cp .env.example .env && chmod 600 .env
   nano .env   # 填入所有金鑰、DOMAIN、DUCKDNS_TOKEN
   ./deploy/install.sh
   ```
5. 確認：`curl https://<你的子網域>.duckdns.org/healthz` 回傳 `{"status":"ok"}`。

> GHCR 套件在第一次 push 後預設可能是 private。到 GitHub 個人頁 → Packages → `tldr_linebot` → Package settings，把 visibility 改為 public，VM 才能免登入拉取。

### 更新與回滾

- 更新：push 到 `main`，最多約 5 分鐘後 VM 自動換版。
- 回滾：在 VM 的 `.env` 把 `IMAGE_TAG` 改成某個舊 commit SHA，然後 `docker compose up -d`。改回 `latest` 即恢復自動更新。
- 部署檔（`docker-compose.yml`、`Caddyfile`、`deploy/`）有變動時，需在 VM 上 `git pull`。
- 查看日誌：`docker compose logs -f app`

## 隱私

- 機器人加入群組時會公告記錄行為。
- 訊息只存在 VM 上的 SQLite，保留 7 天。
- `.env` 與資料庫檔永遠不進版控（`.gitignore` + CI gitleaks 掃描）。
