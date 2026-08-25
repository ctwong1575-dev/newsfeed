import datetime
from fetcher import fetch_daily_news
from ai_analyzer import generate_investment_insights
from telegram_notifier import send_telegram_message

def run_daily_pipeline():
    print(f"🚀 開始執行每日財經新聞匯總任務: {datetime.datetime.now()}")
    
    articles = fetch_daily_news(max_articles_per_source=4)
    if not articles:
        print("未抓取到任何新聞，終止任務。")
        return

    print("🧠 正在使用 Gemini 生成 AI 投資建議與新聞摘要...")
    report = generate_investment_insights(articles)

    print("📤 正在發送至 Telegram...")
    header = f"📊 **【每日全球財經總覽 & 5大實質股票投資建議】**\n📅 {datetime.date.today().strftime('%Y-%m-%d')}\n\n"
    full_message = header + report
    
    send_telegram_message(full_message)

if __name__ == "__main__":
    run_daily_pipeline()
