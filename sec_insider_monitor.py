import os
import re
import time
import argparse
import requests
import xml.etree.ElementTree as ET

# 1. 讀取環境變數 (由 GitHub Secrets 傳入)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# SEC 要求合規 User-Agent 格式：名稱 電郵
HEADERS = {
    "User-Agent": "EquitySignalBot/2.0 (contact@researchlab.com)"
}

# 門檻設定
MIN_BUY_ALERT_USD = 100_000
MIN_SELL_ALERT_USD = 500_000

def send_telegram(text: str):
    """發送訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[警告] 未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")
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

def get_form4_xml_url(index_url: str):
    """從 SEC 索引頁尋找實際的 xml 文件 URL"""
    try:
        r = requests.get(index_url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return None
        xml_paths = re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', r.text)
        for path in xml_paths:
            if not path.endswith(".xsd"):
                return f"https://www.sec.gov{path}"
    except Exception:
        pass
    return None

def process_form4_filing(title: str, link: str, force_send_test: bool = False):
    """解析 Form 4 並提取交易數據"""
    xml_url = get_form4_xml_url(link)
    if not xml_url:
        return False

    try:
        r = requests.get(xml_url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return False

        root = ET.fromstring(r.content)

        ticker_elem = root.find(".//issuerTradingSymbol")
        ticker = ticker_elem.text.upper() if ticker_elem is not None and ticker_elem.text else "N/A"
        
        company_elem = root.find(".//issuerName")
        company = company_elem.text if company_elem is not None and company_elem.text else "未知公司"

        owner_elem = root.find(".//rptOwnerName")
        owner = owner_elem.text if owner_elem is not None and owner_elem.text else "內部人士"

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

            # 觸發條件：測試推播 OR 滿足實盤過濾門檻
            if force_send_test or (is_buy and total_usd >= MIN_BUY_ALERT_USD) or (is_sell and not is_10b5 and total_usd >= MIN_SELL_ALERT_USD):
                header = "🧪 <b>【SEC 股權變動測試訊號】</b>" if force_send_test else ("🟢 <b>【強力買入訊號】</b>" if is_buy else "🔴 <b>【重要沽出訊號】</b>")
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

                print(f"[已發送] {ticker} | {owner} | {action_text} | ${total_usd:,.0f}")
                send_telegram(msg)
                return True

    except Exception as e:
        pass

    return False

def run_monitor(duration_seconds: int):
    """在指定時長內運行監測"""
    parser_feed_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&company=&dateb=&owner=include&start=0&count=40&output=atom"
    
    print(f"🚀 啟動美股異動監控，預計運行 {duration_seconds} 秒...")
    start_time = time.time()
    seen_ids = set()

    # 1. 啟動先抓取 1 筆即時數據發送，確保 GitHub Actions 執行有實質產出
    try:
        r = requests.get(parser_feed_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)
            for entry in entries:
                link = entry.find('atom:link', ns).attrib.get('href', '')
                title = entry.find('atom:title', ns).text
                if process_form4_filing(title, link, force_send_test=True):
                    break
    except Exception as e:
        print(f"初始化抓取異常: {e}")

    # 2. 在限定時間內進行輪詢
    while (time.time() - start_time) < duration_seconds:
        try:
            r = requests.get(parser_feed_url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                for entry in root.findall('atom:entry', ns):
                    eid = entry.find('atom:id', ns).text
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        title = entry.find('atom:title', ns).text
                        link = entry.find('atom:link', ns).attrib.get('href', '')
                        process_form4_filing(title, link, force_send_test=False)
        except Exception as err:
            print(f"[網絡警告]: {err}")

        time.sleep(20)

    print(f"✅ 已達到設定運行時長 ({duration_seconds} 秒)，監控程序正常結束。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEC Insider Filings Monitor")
    parser.add_argument("--duration", type=int, default=180, help="腳本運行總秒數 (預設: 180)")
    args = parser.parse_args()

    run_monitor(args.duration)
