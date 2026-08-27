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
    MIN_BUY_VALUE = getattr(config, "MIN_BUY_VALUE", 50000.0)      # 內部人主動買入門檻 ($50K)
    MIN_SELL_VALUE = getattr(config, "MIN_SELL_VALUE", 500000.0)  # 內部人大額賣出門檻 ($500K)
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
    MIN_BUY_VALUE = 50000.0
    MIN_SELL_VALUE = 500000.0

seen_filings = set()

def send_telegram(text: str):
    """發送 Markdown 格式訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n[Console Log]\n" + text + "\n" + "="*50)
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
        print(f"[❌ Telegram 推送失敗]: {e}")

def get_xml_url_from_entry_link(entry_link: str) -> str:
    """將 SEC filing 網頁鏈接轉換為原始 XML 數據鏈接"""
    if not entry_link.startswith("http"):
        entry_link = f"https://www.sec.gov{entry_link}"
    
    if entry_link.endswith(".xml") or entry_link.endswith(".txt"):
        return entry_link

    # 取得目錄路徑
    base_dir = entry_link.rsplit('/', 1)[0]
    accession_no = entry_link.split('/')[-1].replace('-index.htm', '').replace('-index.html', '').replace('-', '')
    
    try:
        resp = requests.get(entry_link, headers=SEC_HEADERS, timeout=10)
        if resp.status_code == 200:
            import re
            # 優先匹配 form4 的 xml 檔案
            xml_matches = re.findall(r'href="([^"]+\.xml)"', resp.text)
            for m in xml_matches:
                if not m.endswith('xslF345X01/primary_doc.xml') and not m.endswith('xslF345X02/primary_doc.xml'):
                    if m.startswith('/'):
                        return f"https://www.sec.gov{m}"
                    elif m.startswith('http'):
                        return m
                    else:
                        return f"{base_dir}/{m}"
    except Exception:
        pass
    return entry_link

def parse_form4_xml(xml_url: str):
    """下載並深度解析 Form 4 XML，提取具體交易明細"""
    try:
        resp = requests.get(xml_url, headers=SEC_HEADERS, timeout=10)
        if resp.status_code != 200 or not resp.content.strip().startswith(b"<?xml") and b"<ownershipDocument>" not in resp.content:
            return None

        root = ET.fromstring(resp.content)

        # 1. 公司與股票代號
        issuer = root.find("issuer")
        ticker = issuer.findtext("issuerTradingSymbol", default="UNKNOWN").upper() if issuer is not None else "UNKNOWN"
        company_name = issuer.findtext("issuerName", default="").strip() if issuer is not None else ""

        # 2. 申報人身分與職位
        rpt_owner = root.find("reportingOwner")
        owner_name = "內部人士"
        owner_role = "高管/董事"
        if rpt_owner is not None:
            id_tag = rpt_owner.find("reportingOwnerId")
            if id_tag is not None:
                owner_name = id_tag.findtext("rptOwnerName", default="內部人士").strip()
            
            rel = rpt_owner.find("reportingOwnerRelationship")
            if rel is not None:
                roles = []
                if rel.findtext("isDirector") == "1" or rel.findtext("isDirector") == "true": roles.append("董事")
                if rel.findtext("isOfficer") == "1" or rel.findtext("isOfficer") == "true":
                    title = rel.findtext("officerTitle", default="高管")
                    roles.append(title if title else "高管")
                if rel.findtext("isTenPercentOwner") == "1" or rel.findtext("isTenPercentOwner") == "true": roles.append("10%+大股東")
                if roles:
                    owner_role = "/".join(roles)

        # 3. 檢查是否為 10b5-1 計畫
        is_10b51 = root.findtext("affirmative10b5OneFlag", default="0") in ["1", "true"]

        # 4. 解析二級市場交易 (非衍生品 nonDerivativeTransaction)
        transactions = []
        total_p_val, total_p_shares = 0.0, 0
        total_s_val, total_s_shares = 0.0, 0
        weighted_p_price, weighted_s_price = 0.0, 0.0
        latest_owned_shares = "N/A"

        for trans in root.findall(".//nonDerivativeTransaction"):
            code = trans.findtext(".//transactionCoding/transactionCode", default="")
            shares_text = trans.findtext(".//transactionAmounts/transactionShares/value", default="0")
            price_text = trans.findtext(".//transactionAmounts/transactionPricePerShare/value", default="0")
            acq_disp = trans.findtext(".//transactionAmounts/transactionAcquiredDisposedCode/value", default="")
            post_shares = trans.findtext(".//postTransactionAmounts/sharesOwnedFollowingTransaction/value", default="")
            
            if post_shares:
                latest_owned_shares = f"{float(post_shares):,.0f}"

            try:
                shares = float(shares_text)
                price = float(price_text)
                val = shares * price
            except ValueError:
                continue

            # Code P: 二級市場主動買入
            if code == "P":
                total_p_shares += int(shares)
                total_p_val += val
            # Code S: 二級市場主動賣出
            elif code == "S":
                total_s_shares += int(shares)
                total_s_val += val

        # 5. 重大性過濾與評定
        if total_p_val >= MIN_BUY_VALUE:
            avg_price = total_p_val / total_p_shares if total_p_shares > 0 else 0
            return {
                "type": "BUY",
                "ticker": ticker,
                "company": company_name,
                "owner": owner_name,
                "role": owner_role,
                "shares": f"{total_p_shares:,}",
                "price": f"${avg_price:.2f}",
                "total_val": f"${total_p_val:,.0f}",
                "post_shares": latest_owned_shares,
                "is_10b51": is_10b51
            }
        elif total_s_val >= MIN_SELL_VALUE:
            avg_price = total_s_val / total_s_shares if total_s_shares > 0 else 0
            return {
                "type": "SELL",
                "ticker": ticker,
                "company": company_name,
                "owner": owner_name,
                "role": owner_role,
                "shares": f"{total_s_shares:,}",
                "price": f"${avg_price:.2f}",
                "total_val": f"${total_s_val:,.0f}",
                "post_shares": latest_owned_shares,
                "is_10b51": is_10b51
            }
            
        return None # 未達重大性門檻，直接忽略
    except Exception as e:
        return None

def parse_sec_feed(is_first_run=False):
    """獲取並精準過濾 SEC 即時申報"""
    try:
        resp = requests.get(SEC_FEED_URL, headers=SEC_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('atom:entry', ns)
        alerts = []

        for entry in entries:
            title = entry.find('atom:title', ns).text or ""
            link = entry.find('atom:link', ns).attrib.get('href', "")
            doc_id = link.split('/')[-1]

            if doc_id in seen_filings:
                continue

            seen_filings.add(doc_id)
            full_link = link if link.startswith("http") else f"https://www.sec.gov{link}"
            curr_time = time.strftime('%H:%M:%S', time.localtime())

            # 1. 處理 Form 4 申報
            if "4 - " in title or "4/A - " in title:
                xml_target = get_xml_url_from_entry_link(full_link)
                data = parse_form4_xml(xml_target)
                
                # 若未達重大買入/賣出門檻，則跳過不推送
                if not data:
                    continue

                if data["type"] == "BUY":
                    plan_tag = "⚠️ 10b5-1預設計劃" if data["is_10b51"] else "🔥 自主主動增持 (非預設)"
                    msg = (
                        f"🚨 *【內部人主動增持】{data['ticker']}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🏢 *公司*：`{data['company']}`\n"
                        f"👤 *高管/股東*：`{data['owner']}` ({data['role']})\n"
                        f"💰 *增持規模*：`{data['shares']} 股 @ {data['price']}`\n"
                        f"💵 *投入總額*：`{data['total_val']}` (Code P 主動買入)\n"
                        f"📊 *最新持股*：`{data['post_shares']} 股`\n"
                        f"🏷️ *交易屬性*：`{plan_tag}`\n"
                        f"🕒 *申報時間*：`{curr_time}`\n\n"
                        f"🔗 *【來源文件查核】*\n"
                        f"• 📄 [點此開啟 SEC 官方原檔]({full_link})"
                    )
                else:
                    plan_tag = "10b5-1預設計劃" if data["is_10b51"] else "自主主動減持"
                    msg = (
                        f"⚠️ *【內部人大額減持】{data['ticker']}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🏢 *公司*：`{data['company']}`\n"
                        f"👤 *高管/股東*：`{data['owner']}` ({data['role']})\n"
                        f"🔻 *減持規模*：`{data['shares']} 股 @ {data['price']}`\n"
                        f"💵 *套現總額*：`{data['total_val']}` (Code S 賣出)\n"
                        f"📊 *剩餘持股*：`{data['post_shares']} 股`\n"
                        f"🏷️ *交易屬性*：`{plan_tag}`\n"
                        f"🕒 *申報時間*：`{curr_time}`\n\n"
                        f"🔗 *【來源文件查核】*\n"
                        f"• 📄 [點此開啟 SEC 官方原檔]({full_link})"
                    )
                alerts.append(msg)

            # 2. 處理 13D 激進大股東主動介入
            elif "SC 13D" in title:
                company = title.split(" - ")[1] if " - " in title else title
                msg = (
                    f"🔥 *【5%+ 激進大股東主動介入 (13D)】*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏢 *標的企業*：`{company}`\n"
                    f"📌 *申報類型*：`Schedule 13D (主動控股/併購/重組意圖)`\n"
                    f"🕒 *申報時間*：`{curr_time}`\n\n"
                    f"🔍 *【盤前簡評】*\n"
                    f"• 機構跨越 5% 股權線且具主動經營意圖，注意開盤量能催化。\n\n"
                    f"🔗 *【來源文件查核】*\n"
                    f"• 📄 [點此開啟 SEC 13D 原檔]({full_link})"
                )
                alerts.append(msg)

            if is_first_run and len(alerts) >= 2:
                break

        return alerts
    except Exception as e:
        print(f"[❌ 解析出錯]: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="SEC Edgar Premarket Monitor")
    parser.add_argument("--duration", type=int, default=180, help="運行時長 (分鐘)")
    parser.add_argument("--test", action="store_true", help="測試模式")
    args = parser.parse_args()

    print(f"🚀 啟動美股盤前重大股權異動監控 (買入門檻: ${MIN_BUY_VALUE:,.0f}, 賣出門檻: ${MIN_SELL_VALUE:,.0f})...")
    
    end_time = time.time() + (args.duration * 60)
    while time.time() < end_time:
        new_alerts = parse_sec_feed(is_first_run=False)
        for alert in new_alerts:
            send_telegram(alert)
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
