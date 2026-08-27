import argparse
import os
import time
import re
import xml.etree.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# 讀取配置
try:
    import config
    TELEGRAM_BOT_TOKEN = getattr(config, "TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", ""))
    TELEGRAM_CHAT_ID = getattr(config, "TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))
    SEC_HEADERS = getattr(config, "SEC_HEADERS", {
        "User-Agent": "MarketIntelligenceBot/2.0 (research@marketresearch.com)",
        "Accept-Encoding": "gzip, deflate"
    })
    MIN_BUY_VALUE = getattr(config, "MIN_BUY_VALUE", 50000.0)      # 內部人買入門檻 ($50K)
    MIN_SELL_VALUE = getattr(config, "MIN_SELL_VALUE", 500000.0)  # 內部人賣出門檻 ($500K)
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    SEC_HEADERS = {
        "User-Agent": "MarketIntelligenceBot/2.0 (research@marketresearch.com)",
        "Accept-Encoding": "gzip, deflate"
    }
    MIN_BUY_VALUE = 50000.0
    MIN_SELL_VALUE = 500000.0

SEC_FEED_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?"
    "action=getcurrent&type=&company=&dateb=&owner=include&count=80&output=atom"
)

# 建立具備自動重試機制的持久化 Session
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))
session.headers.update(SEC_HEADERS)

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
        resp = session.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("  └─ 🚀 [Telegram 推送成功]")
        else:
            print(f"  └─ ❌ [Telegram 發送失敗 {resp.status_code}]: {resp.text}")
    except Exception as e:
        print(f"  └─ ❌ [Telegram 連線異常]: {e}")

def parse_form4_details(doc_url: str, ignore_threshold: bool = False):
    """下載並深度解析 Form 4，提取股票代號、高管、買賣金額與 10b5-1 計劃"""
    time.sleep(0.15)  # SEC 頻率保護
    try:
        resp = session.get(doc_url, timeout=15)
        if resp.status_code != 200:
            return None

        content = resp.text
        # 若為 HTML 索引頁，自動定位具體的 xml 檔案
        if "<ownershipDocument>" not in content:
            base_dir = doc_url.rsplit('/', 1)[0]
            xml_files = re.findall(r'href="([^"]+)"', content)
            xml_target = None
            for f in xml_files:
                if f.endswith(".xml") and not f.endswith("xslF345X01/primary_doc.xml") and not f.endswith("xslF345X02/primary_doc.xml"):
                    xml_target = f if f.startswith("http") else f"https://www.sec.gov{f}" if f.startswith("/") else f"{base_dir}/{f}"
                    break
            if xml_target:
                time.sleep(0.15)
                resp = session.get(xml_target, timeout=15)
                content = resp.text
            else:
                return None

        if "<ownershipDocument>" not in content:
            return None

        xml_start = content.find("<ownershipDocument>")
        xml_end = content.find("</ownershipDocument>") + len("</ownershipDocument>")
        root = ET.fromstring(content[xml_start:xml_end])

        # 1. 公司與股票代號
        issuer = root.find("issuer")
        ticker = issuer.findtext("issuerTradingSymbol", default="UNKNOWN").upper() if issuer is not None else "UNKNOWN"
        company_name = issuer.findtext("issuerName", default="").strip() if issuer is not None else ""

        # 2. 內部人與職位
        rpt_owner = root.find("reportingOwner")
        owner_name = "內部人士"
        roles = []
        if rpt_owner is not None:
            id_tag = rpt_owner.find("reportingOwnerId")
            if id_tag is not None:
                owner_name = id_tag.findtext("rptOwnerName", default="內部人士").strip()
            rel = rpt_owner.find("reportingOwnerRelationship")
            if rel is not None:
                if rel.findtext("isDirector") in ["1", "true"]: roles.append("董事")
                if rel.findtext("isOfficer") in ["1", "true"]:
                    t = rel.findtext("officerTitle", default="高管")
                    roles.append(t if t else "高管")
                if rel.findtext("isTenPercentOwner") in ["1", "true"]: roles.append("10%+大股東")
        role_desc = "/".join(roles) if roles else "內部人"

        # 3. 10b5-1 計劃
        is_10b51 = root.findtext("affirmative10b5OneFlag", default="0") in ["1", "true"]

        # 4. 統計交易
        total_p_val, total_p_shares = 0.0, 0
        total_s_val, total_s_shares = 0.0, 0
        total_other_val, total_other_shares = 0.0, 0
        latest_shares = "N/A"

        for trans in root.findall(".//nonDerivativeTransaction"):
            code = trans.findtext(".//transactionCoding/transactionCode", default="")
            shares_txt = trans.findtext(".//transactionAmounts/transactionShares/value", default="0")
            price_txt = trans.findtext(".//transactionAmounts/transactionPricePerShare/value", default="0")
            post_txt = trans.findtext(".//postTransactionAmounts/sharesOwnedFollowingTransaction/value", default="")
            
            if post_txt:
                try: latest_shares = f"{float(post_txt):,.0f}"
                except ValueError: latest_shares = post_txt

            try:
                s = float(shares_txt)
                p = float(price_txt)
                val = s * p
            except ValueError:
                continue

            if code == "P":
                total_p_shares += int(s)
                total_p_val += val
            elif code == "S":
                total_s_shares += int(s)
                total_s_val += val
            else:
                total_other_shares += int(s)
                total_other_val += val

        # 測試模式判斷
        if ignore_threshold:
            trans_type = "BUY" if total_p_val >= total_s_val else "SELL"
            val = total_p_val if trans_type == "BUY" else total_s_val
            shares = total_p_shares if trans_type == "BUY" else total_s_shares
            if shares == 0:
                shares, val = total_other_shares, total_other_val
            avg_p = val / shares if shares > 0 else 0.0
            return {
                "type": trans_type, "ticker": ticker, "company": company_name,
                "owner": owner_name, "role": role_desc, "shares": f"{shares:,}",
                "price": f"${avg_p:.2f}", "total_val": f"${val:,.0f}",
                "post_shares": latest_shares, "is_10b51": is_10b51, "code": "P" if trans_type == "BUY" else "S"
            }

        # 門檻過濾
        if total_p_val >= MIN_BUY_VALUE:
            avg_p = total_p_val / total_p_shares if total_p_shares > 0 else 0
            return {
                "type": "BUY", "ticker": ticker, "company": company_name,
                "owner": owner_name, "role": role_desc, "shares": f"{total_p_shares:,}",
                "price": f"${avg_p:.2f}", "total_val": f"${total_p_val:,.0f}",
                "post_shares": latest_shares, "is_10b51": is_10b51, "code": "P"
            }
        elif total_s_val >= MIN_SELL_VALUE:
            avg_p = total_s_val / total_s_shares if total_s_shares > 0 else 0
            return {
                "type": "SELL", "ticker": ticker, "company": company_name,
                "owner": owner_name, "role": role_desc, "shares": f"{total_s_shares:,}",
                "price": f"${avg_p:.2f}", "total_val": f"${total_s_val:,.0f}",
                "post_shares": latest_shares, "is_10b51": is_10b51, "code": "S"
            }

        print(f"  └─ ℹ️ [未達門檻] {ticker} | {owner_name} | 買入: ${total_p_val:,.0f} | 賣出: ${total_s_val:,.0f}")
        return None
    except Exception as e:
        print(f"  └─ ⚠️ 解析單筆 Form 4 異常: {e}")
        return None

def run_once(test_mode: bool = False):
    """執行單次掃描並推送"""
    print(f"[{time.strftime('%H:%M:%S')}] 📡 正在請求 SEC 最新申報...")
    try:
        resp = session.get(SEC_FEED_URL, timeout=20)
        if resp.status_code != 200:
            print(f"[❌ SEC 請求異常 HTTP {resp.status_code}]")
            return

        root = ET.fromstring(resp.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('atom:entry', ns)
        print(f"[{time.strftime('%H:%M:%S')}] 成功獲取 {len(entries)} 筆最新申報，開始掃描重大異動...")

        processed_count = 0
        for entry in entries:
            title = entry.find('atom:title', ns).text or ""
            link = entry.find('atom:link', ns).attrib.get('href', "")
            full_link = link if link.startswith("http") else f"https://www.sec.gov{link}"
            curr_time = time.strftime('%H:%M:%S')

            # 1. 處理 Form 4
            if "4 - " in title or "4/A - " in title:
                print(f"🔍 正在解析 Form 4: {title[:50]}...")
                data = parse_form4_details(full_link, ignore_threshold=test_mode)

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
                    processed_count += 1
                    if test_mode:
                        print("✅ 測試成功：已發送第一筆申報樣板至 Telegram。")
                        return

            # 2. 處理 Schedule 13D
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
                processed_count += 1
                if test_mode:
                    return

        print(f"[{time.strftime('%H:%M:%S')}] ✅ 掃描完成，共推送 {processed_count} 筆重大申報。")

    except Exception as e:
        print(f"[❌ 執行出錯]: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEC Edgar One-shot Monitor")
    parser.add_argument("--test", action="store_true", help="測試模式：忽略門檻，立即發送最新 1 筆")
    args = parser.parse_args()

    run_once(test_mode=args.test)
