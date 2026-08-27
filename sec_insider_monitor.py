import os
import re
import time
import requests
import xml.etree.ElementTree as ET

# ================= 1. 設定區域 =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# SEC 要求合規 User-Agent 格式：名稱 電郵/機構
HEADERS = {
    "User-Agent": "EquitySignalBot/2.0 (contact@researchlab.com)"
}

# 測試模式：True = 忽略條件，抓到任何內部人交易立刻印出/推播，驗證連線
TEST_MODE = True

# 過濾門檻（測試完成後可自行調整）
MIN_BUY_ALERT_USD = 100_000     # 主動增持警報門檻 (USD)
MIN_SELL_ALERT_USD = 500_000    # 主動拋售警報門檻 (USD)
# ===============================================

def send_telegram(text: str):
    """發送訊息至 Telegram"""
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
    """從 SEC 索引頁取得真實的 form4.xml 網址"""
    try:
        r = requests.get(index_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        # 尋找 .xml 結尾的文件連結
        xml_paths = re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', r.text)
        for path in xml_paths:
            if not path.endswith(".xsd"):
                return f"https://www.sec.gov{path}"
    except Exception:
        pass
    return None

def process_form4_filing(title: str, link: str, is_test_run: bool = False):
    """解析 Form 4 內部人交易申報"""
    xml_url = get_form4_xml_url(link)
    if not xml_url:
        return False

    try:
        r = requests.get(xml_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return False

        root = ET.fromstring(r.content)

        # 提取核心資訊
        ticker_elem = root.find(".//issuerTradingSymbol")
        ticker = ticker_elem.text.upper() if ticker_elem is not None and ticker_elem.text else "N/A"
        
        company_elem = root.find(".//issuerName")
        company = company_elem.text if company_elem is not None and company_elem.text else "未知公司"

        owner_elem = root.find(".//rptOwnerName")
        owner = owner_elem.text if owner_elem is not None and owner_elem.text else "內部人士"

        # 判斷職位
        is_officer = root.find(".//isOfficer") is not None and root.find(".//isOfficer").text == "1"
        is_director = root.find(".//isDirector") is not None and root.find(".//isDirector").text == "1"
        officer_title = root.find(".//officerTitle").text if root.find(".//officerTitle") is not None else ""
        role = officer_title if officer_title else ("高管" if is_officer else "董事" if is_director else "持股 >10% 股東")

        # 檢查非衍生品交易 (普通股買賣)
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

            # 判斷是否為 10b5-1 計畫
            footnote = " ".join([t.text for t in root.findall(".//footnote") if t.text])
            is_10b5 = "10b5-1" in footnote.lower()

            # 訊號分類
            is_buy = (code == "P" and acq_disp == "A")
            is_sell = (code == "S" and acq_disp == "D")

            # 測試模式觸發 OR 滿足實盤過濾條件
            if is_test_run or (is_buy and total_usd >= MIN_BUY_ALERT_USD) or (is_sell and not is_10b5 and total_usd >= MIN_SELL_ALERT_USD):
                
                header = "🧪 <b>【系統連線測試訊號】</b>" if is_test_run else ("🟢 <b>【強力買入訊號】</b>" if is_buy else "🔴 <b>【重要沽出訊號】</b>")
                action_text = "公開市場買入 (Code P)" if is_buy else "主動賣出 (Code S)" if is_sell else f"申報異動 (Code {code})"
                plan_tag = "（10b5-1 計畫執行）" if is_10b5 else "（⚡ 非排程主動交易）"

                msg = (
                    f"{header}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 <b>標的</b>: <code>${ticker}</code> - {company}\n"
                    f"👤 <b>內部人</b>: <b>{owner}</b> ({role})\n"
                    f"📊 <b>動作</b>: {action_text} {plan_tag}\n"
                    f"💰 <b>異動規模</b>: <b>${total_usd:,.0f} USD</b> ({int(shares):,} 股 @ ${price:.2f})\n"
                    f"🔗 <a href='{link}'>SEC 官方申報原件</a>"
                )

                print(f"\n[成功捕獲] {ticker} | {owner} | {action_text} | ${total_usd:,.0f}")
                send_telegram(msg)
                return True
                
    except Exception as e:
        # print(f"解析單一文件出錯: {e}")
        pass
        
    return False

def run_monitor():
    """主監察流程"""
    feed_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&company=&dateb=&owner=include&start=0&count=40&output=atom"
    
    print("🚀 美股股權異動監控系統啟動...")
    print("📡 正在向 SEC EDGAR 請求最新 Form 4 數據...")

    seen_ids = set()

    # 1. 啟動時先執行一次測試推播
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)
            
            print(f"✅ 成功獲取 SEC 最新 {len(entries)} 筆申報列表！")
            
            # 挑選最新一筆有效的 Form 4 發送測試
            for entry in entries:
                link = entry.find('atom:link', ns).attrib.get('href', '')
                title = entry.find('atom:title', ns).text
                if process_form4_filing(title, link, is_test_run=True):
                    print("✅ 測試訊息已成功發送至 Telegram！")
                    break
        else:
            print(f"❌ SEC 連線響應異常: {r.status_code}，請確認 User-Agent。")
    except Exception as e:
        print(f"❌ 啟動測試失敗: {e}")

    # 2. 進入盤前常規循環監測 (只抓取符合標準的大額交易)
    print("\n⏳ 進入實時監控循環 (每 30 秒輪詢一次)...")
    while True:
        try:
            r = requests.get(feed_url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                for entry in root.findall('atom:entry', ns):
                    eid = entry.find('atom:id', ns).text
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        title = entry.find('atom:title', ns).text
                        link = entry.find('atom:link', ns).attrib.get('href', '')
                        process_form4_filing(title, link, is_test_run=False)
        except Exception as err:
            print(f"[網絡警告]: {err}")

        time.sleep(30)

if __name__ == "__main__":
    run_monitor()
