import os
import re
import time
import argparse
import requests
import xml.etree.ElementTree as ET

# 1. 讀取環境變數
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEC_HEADERS = {
    "User-Agent": "ChunTingWong MarketResearch/1.0 (wongct.research@gmail.com)",
    "Accept-Encoding": "gzip, deflate"
}

MIN_BUY_ALERT_USD = 100_000
MIN_SELL_ALERT_USD = 500_000

def send_telegram(text: str):
    """發送訊息至 Telegram 並打印具體 HTTP 狀態"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ [錯誤] 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 環境變數！")
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
        res_json = resp.json()
        if resp.status_code == 200 and res_json.get("ok"):
            print("🎉 [Telegram] 訊息推送成功！")
            return True
        else:
            print(f"❌ [Telegram API 報錯] HTTP {resp.status_code}: {res_json.get('description')}")
            return False
    except Exception as e:
        print(f"❌ [Telegram 網絡請求失敗]: {e}")
        return False

def get_xml_content(index_url: str):
    """精準提取 Form 4 的 XML 原生內容"""
    try:
        # 將 -index.htm 替換為資料夾基礎路徑
        base_dir = index_url.rsplit('/', 1)[0]
        acc_num = index_url.split('/')[-1].replace('-index.htm', '').replace('-index.html', '')
        
        # 優先嘗試標準命名: {acc_num}.txt 或直接獲取目錄檔案
        r = requests.get(index_url, headers=SEC_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        
        # 提取 XML 文件路徑 (排除 .xsd schema 檔)
        xml_matches = re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', r.text)
        target_xml = None
        for path in xml_matches:
            if not path.endswith(".xsd"):
                target_xml = f"https://www.sec.gov{path}"
                break
                
        if target_xml:
            time.sleep(0.1)
            xml_resp = requests.get(target_xml, headers=SEC_HEADERS, timeout=10)
            if xml_resp.status_code == 200:
                return xml_resp.content
    except Exception as e:
        print(f"⚠️ [XML 抓取異常]: {e}")
    return None

def parse_and_alert(title: str, link: str, force_test: bool = False):
    """解析 Form 4 並判斷買賣訊號"""
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
        role = officer_title if officer_title else ("高管" if is_officer else "董事" if is_director else "持股 >10% 股東")

        transactions = root.findall(".//nonDerivativeTransaction")
        
        # 如果是強制測試模式，即使是非常規交易也構造一筆推播以測試管線
        if force_test:
            code = "P"
            acq_disp = "A"
            shares = 1000
            price = 150.0
            total_usd = 150000.0
            is_10b5 = False
            
            if transactions:
                t0 = transactions[0]
                code = t0.find(".//transactionCode").text if t0.find(".//transactionCode") is not None else "P"
                acq_disp = t0.find(".//transactionAcquiredDisposedCode/value").text if t0.find(".//transactionAcquiredDisposedCode/value") is not None else "A"
                try:
                    shares = float(t0.find(".//transactionShares/value").text or 1000)
                    price = float(t0.find(".//transactionPricePerShare/value").text or 100)
                    total_usd = shares * price
                except Exception:
                    pass

            msg = (
                f"🧪 <b>【SEC 股權變動測試訊號】</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>標的</b>: <code>${ticker}</code> - {company}\n"
                f"👤 <b>內部人</b>: <b>{owner}</b> ({role})\n"
                f"📊 <b>動作</b>: 申報異動 (Code {code})\n"
                f"💰 <b>異動規模</b>: <b>${total_usd:,.0f} USD</b> ({int(shares):,} 股 @ ${price:.2f})\n"
                f"🔗 <a href='{link}'>SEC 官方申報原件</a>"
            )
            print(f"🚀 正在推播測試卡片: ${ticker} ({owner})...")
            return send_telegram(msg)

        # 實盤監察過濾
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

            if (is_buy and total_usd >= MIN_BUY_ALERT_USD) or (is_sell and not is_10b5 and total_usd >= MIN_SELL_ALERT_USD):
                header = "🟢 <b>【強力買入訊號】</b>" if is_buy else "🔴 <b>【重要沽出訊號】</b>"
                action_text = "公開市場買入 (Code P)" if is_buy else "主動賣出 (Code S)"
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

                print(f"🔥 [觸發實盤警報] {ticker} | {owner} | ${total_usd:,.0f}")
                send_telegram(msg)
                return True

    except Exception as e:
        print(f"⚠️ [解析報錯]: {e}")

    return False

def run_monitor(duration_seconds: int):
    feed_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&company=&dateb=&owner=include&start=0&count=20&output=atom"
    
    print(f"🚀 啟動美股異動監控，預計運行 {duration_seconds} 秒...")
    start_time = time.time()
    seen_entries = set()
    initial_test_sent = False

    while (time.time() - start_time) < duration_seconds:
        try:
            resp = requests.get(feed_url, headers=SEC_HEADERS, timeout=15)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('atom:entry', ns)
                print(f"📡 成功抓取 SEC 最新 {len(entries)} 筆申報...")

                # 啟動時強制發送 1 筆測試訊號
                if not initial_test_sent and entries:
                    for entry in entries:
                        link = entry.find('atom:link', ns).attrib.get('href', '')
                        title = entry.find('atom:title', ns).text
                        if parse_and_alert(title, link, force_test=True):
                            initial_test_sent = True
                            break

                # 實時過濾其餘申報
                for entry in entries:
                    eid = entry.find('atom:id', ns).text
                    if eid not in seen_entries:
                        seen_entries.add(eid)
                        title = entry.find('atom:title', ns).text
                        link = entry.find('atom:link', ns).attrib.get('href', '')
                        parse_and_alert(title, link, force_test=False)

        except Exception as e:
            print(f"⚠️ [輪詢異常]: {e}")

        time.sleep(15)

    print(f"✅ 已達到設定運行時長 ({duration_seconds} 秒)，監控程序正常結束。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=180)
    args = parser.parse_args()
    run_monitor(args.duration)
