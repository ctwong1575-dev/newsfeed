import os
import re
import time
import requests
import xml.etree.ElementTree as ET

# 1. 讀取環境變數
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEC_HEADERS = {
    "User-Agent": "ChunTingWong MarketResearch/1.0 (wongct.research@gmail.com)",
    "Accept-Encoding": "gzip, deflate"
}

# 2. 實盤重要訊號過濾門檻 (USD)
MIN_BUY_ALERT_USD = 100_000     # 主動增持 > 10 萬美元
MIN_SELL_ALERT_USD = 500_000    # 主動拋售 > 50 萬美元

def send_telegram(text: str):
    """發送訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ [錯誤] 缺少 Telegram 環境變數")
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
        return resp.status_code == 200 and resp.json().get("ok")
    except Exception as e:
        print(f"❌ [Telegram 發送失敗]: {e}")
        return False

def get_xml_content(index_url: str):
    """提取 Form 4 的 XML 原生內容"""
    try:
        time.sleep(0.1) # 遵守 SEC 限速規定
        r = requests.get(index_url, headers=SEC_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        
        xml_matches = re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', r.text, re.IGNORECASE)
        target_xml = None
        for path in xml_matches:
            if not path.lower().endswith(".xsd"):
                target_xml = f"https://www.sec.gov{path}"
                break
                
        if target_xml:
            time.sleep(0.1)
            xml_resp = requests.get(target_xml, headers=SEC_HEADERS, timeout=10)
            if xml_resp.status_code == 200:
                return xml_resp.content
    except Exception:
        pass
    return None

def process_form4(title: str, link: str):
    """解析並判斷重大訊號"""
    xml_content = get_xml_content(link)
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

        is_officer = root.find(".//isOfficer") is not None and root.find(".//isOfficer").text == "1"
        is_director = root.find(".//isDirector") is not None and root.find(".//isDirector").text == "1"
        officer_title = root.find(".//officerTitle").text if root.find(".//officerTitle") is not None else ""
        role = officer_title if officer_title else ("高管" if is_officer else "董事" if is_director else "大股東")

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

            # 實盤門檻判斷
            if (is_buy and total_usd >= MIN_BUY_ALERT_USD) or (is_sell and not is_10b5 and total_usd >= MIN_SELL_ALERT_USD):
                header = "🟢 <b>【美股盤前・內部人強力買入】</b>" if is_buy else "🔴 <b>【美股盤前・內部人大額拋售】</b>"
                action_text = "🔥 公開市場增持 (Code P)" if is_buy else "⚠️ 主動減持 (Code S)"
                plan_tag = "（⚡ 非 10b5-1 預設計劃）" if not is_10b5 else ""

                msg = (
                    f"{header}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 <b>標的代號</b>: <code>${ticker}</code>\n"
                    f"🏢 <b>公司名稱</b>: {company}\n"
                    f"👤 <b>申報主體</b>: <b>{owner}</b> ({role})\n"
                    f"📊 <b>交易動作</b>: {action_text} {plan_tag}\n"
                    f"💰 <b>異動金額</b>: <b>${total_usd:,.0f} USD</b> ({int(shares):,} 股 @ ${price:.2f})\n"
                    f"🔗 <a href='{link}'>SEC 申報原文</a>"
                )

                print(f"🔥 [觸發警報] ${ticker} | {owner} | ${total_usd:,.0f} USD")
                send_telegram(msg)
                return True

    except Exception as e:
        pass

    return False

def main():
    print("🚀 開始執行美股盤前 SEC 申報掃描...")
    # 每次掃描最近 80 筆最新披露
    feed_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&company=&dateb=&owner=include&start=0&count=80&output=atom"
    
    try:
        resp = requests.get(feed_url, headers=SEC_HEADERS, timeout=15)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)
            print(f"📡 成功獲取 SEC 最新 {len(entries)} 筆 Form 4 申報，開始分析...")

            alert_count = 0
            for entry in entries:
                link = entry.find('atom:link', ns).attrib.get('href', '')
                title = entry.find('atom:title', ns).text
                if process_form4(title, link):
                    alert_count += 1
            
            print(f"✅ 盤前掃描完成，共發出 {alert_count} 則重大訊號推播。")
        else:
            print(f"❌ SEC 響應狀態異常: {resp.status_code}")
    except Exception as e:
        print(f"⚠️ 網絡或解析錯誤: {e}")

if __name__ == "__main__":
    main()
