import argparse
import os
import time
import re
import xml.etree.ElementTree as ET
import requests

# 讀取設定
try:
    import config
    TELEGRAM_BOT_TOKEN = getattr(config, "TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", ""))
    TELEGRAM_CHAT_ID = getattr(config, "TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))
    SEC_HEADERS = getattr(config, "SEC_HEADERS", {
        "User-Agent": "MarketIntelligenceBot/2.0 (research@marketresearch.com)",
        "Accept-Encoding": "gzip, deflate"
    })
    SEC_FEED_URL = getattr(config, "SEC_FEED_URL", (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcurrent&type=&company=&dateb=&owner=include&count=40&output=atom"
    ))
    POLL_INTERVAL_SECONDS = getattr(config, "POLL_INTERVAL_SECONDS", 20)
    MIN_BUY_VALUE = getattr(config, "MIN_BUY_VALUE", 50000.0)      # 買入門檻 ($50K)
    MIN_SELL_VALUE = getattr(config, "MIN_SELL_VALUE", 500000.0)  # 賣出門檻 ($500K)
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    SEC_HEADERS = {
        "User-Agent": "MarketIntelligenceBot/2.0 (research@marketresearch.com)",
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
        print("\n[⚠️ Telegram Token/ChatID 未配置，僅輸出至 Console]\n" + text)
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
        if resp.status_code == 200:
            print("  └─ 🚀 [Telegram 推送成功]")
        else:
            print(f"  └─ ❌ [Telegram 發送失敗 {resp.status_code}]: {resp.text}")
    except Exception as e:
        print(f"  └─ ❌ [Telegram 連線異常]: {e}")

def get_xml_url_from_entry_link(entry_link: str) -> str:
    """解析目錄以取得 Form 4 原始 XML 檔案鏈接"""
    if not entry_link.startswith("http"):
        entry_link = f"https://www.sec.gov{entry_link}"
    
    time.sleep(0.15)  # 遵守 SEC 請求速率保護 (避免 429)
    try:
        resp = requests.get(entry_link, headers=SEC_HEADERS, timeout=8)
        if resp.status_code == 200:
            base_dir = entry_link.rsplit('/', 1)[0]
            # 尋找 xml 檔案名稱
            xml_matches = re.findall(r'href="([^"]+\.xml)"', resp.text)
            for m in xml_matches:
                if 'xsl' not in m:
                    return m if m.startswith("http") else f"https://www.sec.gov{m}" if m.startswith("/") else f"{base_dir}/{m}"
    except Exception:
        pass
    return ""

def parse_form4_xml(xml_url: str, ignore_threshold=False):
    """下載並深度解析 Form 4 XML"""
    if not xml_url:
        return None
    time.sleep(0.15)
    try:
        resp = requests.get(xml_url, headers=SEC_HEADERS, timeout=8)
        if resp.status_code != 200:
            return None

        root = ET.fromstring(resp.content)

        # 1. 公司與代號
        issuer = root.find("issuer")
        ticker = issuer.findtext("issuerTradingSymbol", default="UNKNOWN").upper() if issuer is not None else "UNKNOWN"
        company_name = issuer.findtext("issuerName", default="").strip() if issuer is not None else ""

        # 2. 內部人與職位
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
                if rel.findtext("isDirector") in ["1", "true"]: roles.append("董事")
                if rel.findtext("isOfficer") in ["1", "true"]:
                    title = rel.findtext("officerTitle", default="高管")
                    roles.append(title if title else "高管")
                if rel.findtext("isTenPercentOwner") in ["1", "true"]: roles.append("10%+大股東")
                if roles:
                    owner_role = "/".join(roles)

        # 3. 10b5-1 標籤
        is_10b51 = root.findtext("affirmative10b5OneFlag", default="0") in ["1", "true"]

        # 4. 交易明細
        total_p_val, total_p_shares = 0.0, 0
        total_s_val, total_s_shares = 0.0, 0
        latest_owned_shares = "N/A"

        for trans in root.findall(".//nonDerivativeTransaction"):
            code = trans.findtext(".//transactionCoding/transactionCode", default="")
            shares_text = trans.findtext(".//transactionAmounts/transactionShares/value", default="0")
            price_text = trans.findtext(".//transactionAmounts/transactionPricePerShare/value", default="0")
            post_shares = trans.findtext(".//postTransactionAmounts/sharesOwnedFollowingTransaction/value", default="")
            
            if post_shares:
                try:
                    latest_owned_shares = f"{float(post_shares):,.0f}"
                except ValueError:
                    latest_owned_shares = post_shares

            try:
                shares = float(shares_text)
                price = float(price_text)
                val = shares * price
            except ValueError:
                continue

            if code == "P":
                total_p_shares += int(shares)
                total_p_val += val
            elif code == "S":
                total_s_shares += int(shares)
                total_s_val += val

        # 測試模式下若無 P/S 則抓取第一筆做示範
        if ignore_threshold:
            trans_type = "BUY" if total_p_val >= total_s_val else "SELL"
            val = total_p_val if trans_type == "BUY" else total_s_val
            shares = total_p_shares if trans_type == "BUY" else total_s_shares
            avg_p = val / shares if shares > 0 else 0
            return {
                "type": trans_type, "ticker": ticker, "company": company_name,
                "owner": owner_name, "role": owner_role, "shares": f"{shares:,}",
                "price": f"${avg_p:.2f}", "total_val": f"${val:,.0f}",
                "post_shares": latest_owned_shares, "is_10b51": is_10b51, "code": "P" if trans_type == "BUY" else "S"
            }

        # 正常門檻判定
        if total_p_val >= MIN_BUY_VALUE:
            avg_p = total_p_val / total_p_shares if total_p_shares > 0 else 0
            return {
                "type": "BUY", "ticker": ticker, "company": company_name,
                "owner": owner_name, "role": owner_role, "shares": f"{total_p_shares:,}",
                "price": f"${avg_p:.2f}", "total_val": f"${total_p_val:,.0f}",
                "post_shares": latest_owned_shares, "is_10b51": is_10b51, "code": "P"
            }
        elif total_s_val >= MIN_SELL_VALUE:
            avg_p = total_s_val / total_s_shares if total_s_shares > 0 else 0
            return {
                "type": "SELL", "ticker": ticker, "company": company_name,
                "owner": owner_name, "role": owner_role, "shares": f"{total_s_shares:,}",
                "price": f"${avg_p:.2f}", "total_val": f"${total_s_val:,.0f}",
                "post_shares": latest_owned_shares, "is_10b51": is_10b51, "code": "S"
            }
            
        print(f"  └─ ℹ️ [過濾] {ticker} ({owner_name}) 交易金額未達門檻 (買入: ${total_p_val:,.0f}, 賣出: ${total_s_val:,.0f})")
        return None
    except Exception as e:
        return None

def process_feed(test_mode=False):
    """處理 SEC Feed 並輸出進度日誌"""
    print(f"[{time.strftime('%H:%M:%S')}] 📡 正在請求 SEC 最新申報...")
    try:
        resp = requests.get(SEC_FEED_URL, headers=SEC_HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"[❌ SEC 請求異常 HTTP {resp.status_code}]")
            return

        root = ET.fromstring(resp.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('atom:entry', ns)
        print(f"[{time.strftime('%H:%M:%S')}] 成功獲取 {len(entries)} 筆申報，開始掃描重要異動...")

        for entry in entries:
            title = entry.find('atom:title', ns).text or ""
            link = entry.find('atom:link', ns).attrib.get('href', "")
            doc_id = link.split('/')[-1]

            if not test_mode and doc_id in seen_filings:
                continue

            seen_filings.add(doc_id)
            full_link = link if link.startswith("http") else f"https://www.sec.gov{link}"
            curr_time = time.strftime('%H:%M:%S')

            # Form 4 深度處理
            if "4 - " in title or "4/A - " in title:
                print(f"🔍 發現 Form 4: {title[:65]}...")
                xml_target = get_xml_url_from_entry_link(full_link)
                data = parse_form4_xml(xml_target, ignore_threshold=test_mode)

                if data:
                    is_buy = data["type"] == "BUY"
                    plan_tag = "⚠️ 10b5-1預設計劃" if data["is_10b51"] else "🔥 自主主動交易 (非預設)"
                    action_tag = "【內部人主動增持】" if is_buy else "【內部人大額減持】"
                    icon = "🚨" if is_buy else "⚠️"
                    
                    msg = (
                        f"{icon} *{action_tag}{data['ticker']}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🏢 *公司*：`{data['company']}`\n"
                        f"👤 *高管/股東*：`{data['owner']}` ({data['role']})\n"
                        f"💰 *異動規模*：`{data['shares']} 股 @ {data['price']}`\n"
                        f"💵 *交易總額*：`{data['total_val']}` (Code {data['code']})\n"
                        f"📊 *最新持股*：`{data['post_shares']} 股`\n"
                        f"🏷️ *交易屬性*：`{plan_tag}`\n"
                        f"🕒 *申報時間*：`{curr_time}`\n\n"
                        f"🔗 *【來源文件查核】*\n"
                        f"• 📄 [點此開啟 SEC 官方原檔]({full_link})"
                    )
                    send_telegram(msg)
                    if test_mode:
                        print("✅ 測試模式：已成功發送 1 筆申報樣板至 Telegram。")
                        return

            # 13D 處理
            elif "SC 13D" in title:
                print(f"🔥 發現 13D 大股東申報: {title}...")
                company = title.split(" - ")[1] if " - " in title else title
                msg = (
                    f"🔥 *【5%+ 激進大股東主動介入 (13D)】*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏢 *標的企業*：`{company}`\n"
                    f"📌 *申報類型*：`Schedule 13D (主動控股/併購/重組意圖)`\n"
                    f"🕒 *申報時間*：`{curr_time}`\n\n"
                    f"🔍 *【盤前簡評】*\n"
                    f"• 機構跨越 5% 股權線且具主動經營意圖，注意盤前量能變化。\n\n"
                    f"🔗 *【來源文件查核】*\n"
                    f"• 📄 [點此開啟 SEC 13D 原檔]({full_link})"
                )
                send_telegram(msg)
                if test_mode:
                    return

    except Exception as e:
        print(f"[❌ 輪詢出錯]: {e}")

def main():
    parser = argparse.ArgumentParser(description="SEC Edgar Premarket Monitor")
    parser.add_argument("--duration", type=int, default=180, help="運行時長 (分鐘)")
    parser.add_argument("--test", action="store_true", help="強制發送最新 1 筆申報進行測試")
    args = parser.parse_args()

    if args.test:
        print("🧪 啟動【測試模式】：忽略金額門檻，立即解析並推送最新 1 筆申報...")
        process_feed(test_mode=True)
        return

    print(f"🚀 啟動美股盤前重大股權異動監控 (買入門檻: ${MIN_BUY_VALUE:,.0f}, 賣出門檻: ${MIN_SELL_VALUE:,.0f})...")
    end_time = time.time() + (args.duration * 60)
    while time.time() < end_time:
        process_feed(test_mode=False)
        print(f"⏳ 等待 {POLL_INTERVAL_SECONDS} 秒後進行下一次檢查...")
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
