from typing import List, Dict
from google import genai
import os
import datetime
import time

def generate_investment_insights(articles: List[Dict[str, str]]) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("環境變數 GEMINI_API_KEY 未設定，請檢查 GitHub Secrets。")

    client = genai.Client(api_key=api_key)
    today_str = datetime.date.today().strftime("%Y年%m月%d日")

    news_text = ""
    for idx, art in enumerate(articles, 1):
        news_text += f"[{idx}] 來源: {art['source']} | 發佈時間: {art['published']}\n標題: {art['title']}\n摘要: {art['summary']}\n連結: {art['link']}\n\n"
        
    prompt = f"""
今天是 **{today_str}**。
你是一位頂尖的資深全球宏觀策略師與財經新聞主播。

以下是今天從 RSS 抓取到的最新國際財經新聞（包含原文網址）：

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
     - **數據與邏輯支持**（引用新聞數據）
3. **新聞來源與參考連結**：
   - 在報告最後，列出本次報告所參考的新聞來源。
   - **極度重要格式需求**：每則參考新聞必須使用完整可點擊的 Markdown 超連結，格式為：
     `• [新聞標題](新聞真實網址) - 來源`
   - **禁止**出現無法點擊的「新聞1」、「新聞2」或裸露文字，一定要將新聞標題與上方提供對應的真實 URL (連結) 結合！

【輸出格式需求】：
- 使用繁體中文。
- 在報告開頭標明「分析基準日期：{today_str}」。
- 使用適合 Telegram 閱讀的 Markdown 格式，適當加入 Emoji。
"""

    # 備援模型清單：優先使用 flash 次之使用其他可用模型
    models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash']

    for model_name in models_to_try:
        # 每個模型嘗試重試最多 3 次
        for attempt in range(1, 4):
            try:
                print(f"🔄 嘗試使用模型 {model_name} (第 {attempt} 次嘗試)...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response.text:
                    return response.text
            except Exception as e:
                print(f"⚠️ 模型 {model_name} 第 {attempt} 次呼叫失敗: {e}")
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    time.sleep(5 * attempt)  # 遇 503 暫停 5、10 秒後重試
                else:
                    break  # 若非 503 伺服器過載問題，直接切換下一個模型

    return "❌ Gemini API 分析生成失敗：所有備援模型與重試均告超時或繁忙，請稍後於 GitHub Actions 手動重試。"
