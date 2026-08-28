import os
import re
import time
import argparse
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

# 1. 讀取環境變數
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 2. SEC 嚴格合規標頭 (必須使用標準格式且帶有特定 Host 與壓縮聲明)
SEC_HEADERS = {
    "User-Agent": "ChunTingWong MarketResearch/1.0 (wongct.research@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov"
}

SEC_WWW_HEADERS = {
    "User-Agent": "ChunTingWong MarketResearch/1.0 (wongct.research@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov"
}

# 門檻設定 (測試模式下任何一筆都會發送)
MIN_BUY_ALERT_USD = 100_000
MIN_SELL_ALERT_USD = 500_000

def send_telegram(text: str):
    """發送訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[警告] 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram 發送失敗]: {e}")
        return False

def get_latest_sec_filings():
    """使用 SEC 官方專用 feed 抓取最新申報"""
    # 此接口響應速度快，專供實時數據串流
    feed_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&company=&dateb=&owner=include&start=0&count=20&output=atom"
    try:
        # SEC 限速規定：每秒不超過 10 次請求
        time.sleep(0.2)
        resp = requests.get(feed_url, headers=SEC_WWW_HEADERS, timeout=20)
        if resp.status_code == 200:
            return resp.content
        else:
            print(f"[SEC 響應錯誤] HTTP {resp.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[網絡重試] 請求 SEC 超時，正在重試... ({e})")
    return None

def extract_form4_xml(index_url: str):
    """從申報目錄獲取 form4.xml 內容"""
    try:
        time.sleep(0.2)
        r = requests.get(index_url, headers=SEC_WWW_HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        
        # 尋找 xml 檔案路徑
        xml_matches = re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', r.text)
        xml_url = None
        for path in xml_matches:
            if not path.endswith(".xsd"):
                xml_url = f"https://www.sec.gov{path}"
                break
        
        if not xml_url:
            return None
            
        time.sleep(0.2)
        xml_resp = requests.get(xml_url, headers=SEC_WWW_HEADERS, timeout=15)
        if xml_resp.status_code == 200:
            return xml_resp.content
    except Exception:
        pass
    return None

def parse_and_alert(title: str, link: str, force_test: bool = False):
    """解析 Form 4 並推播警報"""
    xml_content = extract_form4_xml(link)
    if not xml_content:
        return False

    try:
        root = ET.fromstring(xml_content)

        ticker_elem = root.find(".//issuerTradingSymbol")
        ticker = ticker_elem.text.upper() if ticker_elem is not None and ticker_elem.text else "N/A"
        
        company_elem = root.find(".//issuerName")
        company = company_elem.text if company_elem is not None and company_elem.text else "未知公司"

        owner_elem = root.find(".//rptOwnerName")
        owner = owner_elem.text if owner_elem is not None and owner_elem.text else "內部人士"

        # 身份識別
        is_officer = root.find(".//isOfficer") is not None and root.find(".//isOfficer").text == "1"
        is_director = root.find(".//isDirector") is not None and root.find(".//isDirector").text == "1"
        officer_title = root.find(".//officerTitle").text if root.find(".//officerTitle") is not None else ""
        role = officer_title if officer_title else ("高管" if is_officer else "董事" if is_director else "持股 >10% 股東")

        transactions = root.findall(".//nonDerivativeTransaction")
        if not transactions:
            return False

        for trans in transactions:
            code = trans.find(".//transactionCode").text if trans.find(".//transactionCode") is not None else ""
            acq_disp = trans.find(".//transactionAcquiredDisposedCode/value").text if trans.find(".//transactionAcquiredDisposedCode/value") is not None else ""
            
            try:
                shares = float(trans.find(".//transactionShares/value").text or 0)
                price = float(trans.find(".//transactionPricePerShare/value").text or 0)
            except Exception:
                shares, price = 0, 0
                
            total_usd = shares * price

            footnote = " ".join([t.text for t in root.findall(".//footnote") if t.text])
            is_10b5 = "10b5-1" in footnote.lower()

            is_buy = (code == "P" and acq_disp == "A")
            is_sell = (code == "S" and acq_disp == "D")

            if force_test or (is_buy and total_usd >= MIN_BUY_ALERT_USD) or (is_sell and not is_10b5 and total_usd >= MIN_SELL_ALERT_USD):
                header = "🧪 <b>【SEC 股權變動測試訊號】</b>" if force_test else ("🟢 <b>【強力買入訊號】</b>" if is_buy else "🔴 <b>【重要沽出訊號】</b>")
                action_text = "公開市場買入 (Code P)" if is_buy else "主動賣出 (Code S)" if is_sell else f"申報異動 (Code {code})"
                plan_tag = "（10b5-1 計劃）" if is_10b5 else "（⚡ 非排程主動交易）"

                msg = (
                    f"{header}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 <b>標的</b>: <code>${ticker}</code> - {company}\n"
                    f"👤 <b>內部人</b>: <b>{owner}</b> ({role})\n"
                    f"📊 <b>動作</b>: {action_text} {plan_tag}\n"
                    f"💰 <b>異動規模</b>: <b>${total_usd:,.0f} USD</b> ({int(shares):,} 股 @ ${price:.2f})\n"
                    f"🔗 <a href='{link}'>SEC 官方申報原件</a>"
                )

                print(f"✅ [成功推送 Telegram] {ticker} | {owner} | {action_text} | ${total_usd:,.0f}")
                send_telegram(msg)
                return True

    except Exception as e:
        # print(f"解析 XML 錯誤: {e}")
        pass

    return False

def run_monitor(duration_seconds: int):
    """主監察輪詢流程"""
    print(f"🚀 啟動美股異動監控，預計運行 {duration_seconds} 秒...")
    start_time = time.time()
    seen_entries = set()
    initial_test_sent = False

    while (time.time() - start_time) < duration_seconds:
        xml_feed = get_latest_sec_filings()
        if xml_feed:
            try:
                root = ET.fromstring(xml_feed)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('atom:entry', ns)
                
                print(f"📡 成功抓取 SEC 最新 {len(entries)} 筆申報...")

                # 第一次抓取時，強制發送 1 筆測試訊號以驗證 Telegram
                if not initial_test_sent and entries:
                    for entry in entries:
                        link = entry.find('atom:link', ns).attrib.get('href', '')
                        title = entry.find('atom:title', ns).text
                        if parse_and_alert(title, link, force_test=True):
                            initial_test_sent = True
                            break

                # 實時過濾其餘新申報
                for entry in entries:
                    eid = entry.find('atom:id', ns).text
                    if eid not in seen_entries:
                        seen_entries.add(eid)
                        title = entry.find('atom:title', ns).text
                        link = entry.find('atom:link', ns).attrib.get('href', '')
                        parse_and_alert(title, link, force_test=False)

            except Exception as e:
                print(f"[解析錯誤]: {e}")

        # SEC 請求間隔保護（避免被封鎖 IP）
        time.sleep(15)

    print(f"✅ 已達到設定運行時長 ({duration_seconds} 秒)，監控程序正常結束。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEC Insider Filings Monitor")
    parser.add_argument("--duration", type=int, default=180, help="腳本運行總秒數")
    args = parser.parse_args()

    run_monitor(args.duration)
