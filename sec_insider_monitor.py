import argparse
import os
import time
import xml.etree.ElementTree as ET
import requests
from config import SEC_HEADERS, SEC_FEED_URL, MIN_TRANSACTION_VALUE, POLL_INTERVAL_SECONDS, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

seen_filings = set()

def send_telegram(text: str):
    """發送 Markdown 格式訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Console Log Only]\n" + text + "\n" + "="*40)
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram 推送出錯: {e}")

def parse_sec_feed():
    """獲取並過濾 SEC 即時申報"""
    try:
        resp = requests.get(SEC_FEED_URL, headers=SEC_HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"SEC 回應狀態碼異常: {resp.status_code}")
            return []

        root = ET.fromstring(resp.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        alerts = []

        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text or ""
            link = entry.find('atom:link', ns).attrib.get('href', "")
            doc_id = link.split('/')[-1]

            if doc_id in seen_filings:
                continue

            # 鎖定關鍵申報：Form 4 (內部人) 與 Schedule 13D (5%+ 大股東主動介入)
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
        return alerts
    except Exception as e:
        print(f"解析 Feed 出現異常: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="SEC Edgar Premarket Monitor")
    parser.add_argument("--duration", type=int, default=180, help="運行時長 (分鐘)")
    args = parser.parse_args()

    print(f"🚀 啟動美股盤前 SEC 股權異動監控 (預計執行 {args.duration} 分鐘)...")
    end_time = time.time() + (args.duration * 60)

    while time.time() < end_time:
        new_alerts = parse_sec_feed()
        for alert in new_alerts:
            send_telegram(alert)
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
