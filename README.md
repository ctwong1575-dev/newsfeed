# Global Financial News & Investment Insights Telegram Bot

此專案自動收集各大國際財經新聞（CNBC、CNN、DW、Sky News、Al Arabiya 等 RSS），並透過 Google **Gemini 2.5 Flash** 進行數據分析，生成包含 **買入價、止蝕價、目標價與數據支持** 的 5 大實質股票/資產投資建議，定時推送至 Telegram。

---

## 📁 檔案結構

```text
financial-news-bot/
├── .env                  # 環境變數設定檔 (已預填 TELEGRAM_CHAT_ID)
├── config.py             # 系統設定與 RSS 訂閱源
├── fetcher.py            # 新聞爬蟲與 RSS 擷取模組
├── ai_analyzer.py        # Gemini 2.5 分析與投資建議生成模組
├── telegram_notifier.py  # Telegram 訊息發送模組 (含長訊息切分與 Markdown 降級機制)
├── main.py               # 每日任務主要執行檔
├── test_send.py          # Telegram 連線測試腳本
├── requirements.txt      # Python 依賴包列表
└── README.md             # 本說明文件
```

---

## 🚀 快速開始 (Cursor Pro 使用步驟)

1. 解壓縮 `financial-news-bot.zip` 並在 **Cursor Pro** 中開啟此資料夾。
2. 補全 `.env` 檔案中的 API Key：
   ```env
   GEMINI_API_KEY=填入您的Gemini_API_Key
   TELEGRAM_BOT_TOKEN=填入您的Telegram_Bot_Token
   TELEGRAM_CHAT_ID=615899930
   ```
3. 安裝依賴包：
   ```bash
   pip install -r requirements.txt
   ```
4. 執行連線測試：
   ```bash
   python test_send.py
   ```
5. 執行全流程試運行：
   ```bash
   python main.py
   ```

---

## ⏰ 設定香港時間每日 08:00 自動觸發 (GitHub Actions)

可以在專案根目錄建立 `.github/workflows/daily_cron.yml`：

```yaml
name: Daily Financial Bot

on:
  schedule:
    # HKT 08:00 AM = UTC 00:00
    - cron: '0 0 * * *'
  workflow_dispatch:

jobs:
  run-bot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python main.py
```
> 將變數新增至 GitHub Repo -> **Settings > Secrets and variables > Actions** 即可。
