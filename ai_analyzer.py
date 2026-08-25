from typing import List, Dict
from google import genai
import os
import datetime

def generate_investment_insights(articles: List[Dict[str, str]]) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("環境變數 GEMINI_API_KEY 未設定，請檢查 GitHub Secrets。")

    client = genai.Client(api_key=api_key)

    # 取得當前真實日期（HKT / UTC+8 相當於今天）
    today_str = datetime.date.today().strftime("%Y年%m月%d日")

    news_text = ""
    for idx, art in enumerate(articles, 1):
        news_text += f"[{idx}] 來源: {art['source']} | 發佈時間: {art['published']}\n標題: {art['title']}\n摘要: {art['summary']}\n連結: {art['link']}\n\n"
        
    prompt = f"""
今天是 **{today_str}**。
你是一位頂尖的資深全球宏觀策略師與財經新聞主播。

以下是今天從 RSS 抓取到的最新國際財經新聞（請仔細核對發佈時間，並嚴格以最新的市場情報進行分析）：

---
{news_text[:15000]}
---

請進行以下分析並生成一份每日總結報告：

1. **今日全球市場核心摘要**（簡明扼要，3-4 句，請結合 **{today_str}** 最新動態）。
2. **5 個具體實質的投資建議**：
   - 必須涵蓋但不限於：**美股 (US Stocks)**、**港股 (HK Stocks)**、**黃金 (Gold)**。
   - 每個建議必須明確包含：
     - **股票/資產名稱與代號 (Ticker)**
     - **操作方向**（看漲/突破買入/逢低吸納等）
     - **建議買入價區間**
     - **止蝕價 (Stop-loss)** 與 **目標價 (Target Price)**
     - **數據與邏輯支持**（引用上方新聞中的最新數據、財報或宏觀數據）

【輸出格式需求】：
- 使用繁體中文。
- 在報告開頭標明「分析基準日期：{today_str}」。
- 使用適合 Telegram 閱讀的 Markdown 格式，適當加入 Emoji。
"""

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"Gemini API 分析生成失敗: {e}"
