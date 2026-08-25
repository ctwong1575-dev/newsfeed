from typing import List, Dict
from google import genai
import os

def generate_investment_insights(articles: List[Dict[str, str]]) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key)

    news_text = ""
    for idx, art in enumerate(articles, 1):
        news_text += f"[{idx}] {art['source']} | 標題: {art['title']}\n摘要: {art['summary']}\n\n"
        
    prompt = f"""
你是一位頂尖的資深全球宏觀策略師與財經新聞主播。
以下是今天來自全球各大媒體（Bloomberg, CNBC, CNN, DW, Sky News, Al Arabiya 等）的最新國際財經新聞：

---
{news_text[:15000]}
---

請進行以下分析並生成一份每日總結報告：

1. **今日全球市場核心摘要**（簡明扼要，3-4 句）。
2. **5 個具體實質的投資建議**：
   - 必須涵蓋但不限於：**美股 (US Stocks)**、**港股 (HK Stocks)**、**黃金 (Gold)**。
   - 每個建議必須明確包含：
     - **股票/資產名稱與代號 (Ticker)**
     - **操作方向**（看漲/突破買入/逢低吸納等）
     - **建議買入價區間**
     - **止蝕價 (Stop-loss)** 與 **目標價 (Target Price)**
     - **數據與邏輯支持**（引用新聞中的數據、財報、成交量、CAPEX 或宏觀經濟數據）

【輸出格式需求】：
- 使用繁體中文。
- 使用適合 Telegram 閱讀的 Markdown 格式，適當加入 Emoji。
"""

    from typing import List, Dict
from google import genai
import os

def generate_investment_insights(articles: List[Dict[str, str]]) -> str:
    # 讀取環境變數中的 GEMINI_API_KEY
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("環境變數 GEMINI_API_KEY 未設定，請檢查 GitHub Secrets。")

    client = genai.Client(api_key=api_key)

    news_text = ""
    for idx, art in enumerate(articles, 1):
        news_text += f"[{idx}] {art['source']} | 標題: {art['title']}\n摘要: {art['summary']}\n\n"
        
    prompt = f"""
你是一位頂尖的資深全球宏觀策略師與財經新聞主播。
以下是今天來自全球各大媒體的最新國際財經新聞：

---
{news_text[:15000]}
---

請進行以下分析並生成一份每日總結報告：

1. **今日全球市場核心摘要**（簡明扼要，3-4 句）。
2. **5 個具體實質的投資建議**：
   - 必須涵蓋但不限於：**美股 (US Stocks)**、**港股 (HK Stocks)**、**黃金 (Gold)**。
   - 每個建議必須明確包含：
     - **股票/資產名稱與代號 (Ticker)**
     - **操作方向**（看漲/突破買入/逢低吸納等）
     - **建議買入價區間**
     - **止蝕價 (Stop-loss)** 與 **目標價 (Target Price)**
     - **數據與邏輯支持**（引用新聞中的數據、財報、成交量、CAPEX 或宏觀經濟數據）

【輸出格式需求】：
- 使用繁體中文。
- 使用適合 Telegram 閱讀的 Markdown 格式，適當加入 Emoji。
"""

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',  # 👈 已更新為 3.6 版本
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"Gemini API 分析生成失敗: {e}"
        return response.text
    except Exception as e:
        return f"Gemini API 分析生成失敗: {e}"
