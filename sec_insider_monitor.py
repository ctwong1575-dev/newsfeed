import argparse
import os
import time
import xml.etree.ElementTree as ET
import requests

# 讀取設定
try:
    import config
    TELEGRAM_BOT_TOKEN = getattr(config, "TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", ""))
    TELEGRAM_CHAT_ID = getattr(config, "TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))
    SEC_HEADERS = getattr(config, "SEC_HEADERS", {
        "User-Agent": "MarketIntelligenceBot/2.0 (contact@marketresearch.com)",
        "Accept-Encoding": "gzip, deflate"
    })
    SEC_FEED_URL = getattr(config, "SEC_FEED_URL", (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcurrent&type=&company=&dateb=&owner=include&count=40&output=atom"
    ))
    POLL_INTERVAL_SECONDS = getattr(config, "POLL_INTERVAL_SECONDS", 20)
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    SEC_HEADERS = {
        "User-Agent": "MarketIntelligenceBot/2.0 (contact@marketresearch.com)",
        "Accept-Encoding": "gzip, deflate"
    }
    SEC_FEED_URL = (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcurrent&type=&company=&dateb=&owner=include&count=40&output=atom"
    )
    POLL_INTERVAL_SECONDS = 20

seen_filings = set()

def send_telegram(text: str):
    """發送 Markdown 格式訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n[⚠️ Telegram Token/ChatID 未配置，僅輸出至 Console]")
        print(text)
        print("-" * 50)
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[❌ Telegram 發送失敗 {resp.status_code}]: {resp.text}")
        else:
            print(f"[✅ Telegram 推送成功]")
    except Exception as e:
        print(f"[❌ Telegram 連線異常]: {e}")

def parse_sec_feed(is_first_run=False):
    """獲取並過濾 SEC 即時申報"""
    try:
        resp = requests.get(SEC_FEED_URL, headers=SEC_HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"[⚠️ SEC 回應異常: HTTP {resp.status_code}]")
            return []

        root = ET.fromstring(resp.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('atom:entry', ns)
        print(f"[{time.strftime('%H:%M:%S')}] 成功拉取 SEC Feed，包含 {len(entries)} 筆最新申報記錄...")

        alerts = []
        for entry in entries:
            title = entry.find('atom:title', ns).text or ""
            link = entry.find('atom:link', ns).attrib.get('href', "")
            doc_id = link.split('/')[-1]

            if doc_id in seen_filings:
                continue

            # 判斷是否為 Form 4 或 Schedule 13D
            is_form4 = "4 - " in title or "4/A - " in title
            is_13d = "SC 13D" in title

            if is_form4 or is_13d:
                seen_filings.add(doc_id)
                full_link = link if link.startswith("http") else f"https://www.sec.gov{link}"
                curr_time = time.strftime('%H:%M:%S', time.localtime())

                if is_form4:
                    msg = (
                        f"🚨 *【內部人持股異動申報 (Form 4)】*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *申報標題*：`{title}`\n"
                        f"🕒 *捕獲時間*：`{curr_time}`\n\n"
                        f"🔍 *【盤前簡評】*\n"
                        f"• 內部人/大股東提交法定持股變更文件。\n"
                        f"• 請注意核對底層是否包含 Code P (市場主動買入) 或 10b5-1 計畫標註。\n\n"
                        f"🔗 *【來源文件查核】*\n"
                        f"• 📄 [點此開啟 SEC 官方原檔]({full_link})"
                    )
                else:
                    msg = (
                        f"🔥 *【5%+ 激進大股東主動介入 (13D)】*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *申報標題*：`{title}`\n"
                        f"🕒 *捕獲時間*：`{curr_time}`\n\n"
                        f"🔍 *【盤前簡評】*\n"
                        f"• 持股跨越 5% 門檻且具備主動意圖 (併購/改選/重組訴求)。\n"
                        f"• 盤前易引發股價跳空與成交量放大。\n\n"
                        f"🔗 *【來源文件查核】*\n"
                        f"• 📄 [點此開啟 SEC 13D 官方原檔]({full_link})"
                    )
                alerts.append(msg)
                
                # 如果是首次測試運行，最多推送最新 2 筆，避免被舊記錄刷屏
                if is_first_run and len(alerts) >= 2:
                    break

        return alerts
    except Exception as e:
        print(f"[❌ 解析 Feed 出錯]: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="SEC Edgar Premarket Monitor")
    parser.add_argument("--duration", type=int, default=180, help="運行時長 (分鐘)")
    parser.add_argument("--test", action="store_true", help="測試模式：立即推送當前最新申報")
    args = parser.parse_args()

    print(f"🚀 啟動 SEC 股權異動監控 (時長: {args.duration} 分鐘, 輪詢間隔: {POLL_INTERVAL_SECONDS} 秒)...")
    
    # 第一次執行時拉取現存最新記錄測試連線
    initial_alerts = parse_sec_feed(is_first_run=True)
    if initial_alerts:
        print(f"⚡ [初始化] 捕獲到 {len(initial_alerts)} 筆近期申報，正在發送測試推播...")
        for alert in initial_alerts:
            send_telegram(alert)
    else:
        print("ℹ️ 當前 Feed 中暫無未處理的 Form 4 / 13D 申報，保持監聽中...")

    end_time = time.time() + (args.duration * 60)
    while time.time() < end_time:
        time.sleep(POLL_INTERVAL_SECONDS)
        new_alerts = parse_sec_feed(is_first_run=False)
        for alert in new_alerts:
            send_telegram(alert)

if __name__ == "__main__":
    main()
