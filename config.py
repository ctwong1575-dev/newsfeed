import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "615899930")

# 已替換為最新且每日高頻更新的財經 RSS 來源
NEWS_FEEDS = {
    "CNBC Top News": "https://search.cnbc.com/rs/search/combinedrender.view?partnerId=wrss01&id=100003114&profile=rss&wants=news",
    "CNBC Finance": "https://search.cnbc.com/rs/search/combinedrender.view?partnerId=wrss01&id=10000664&profile=rss&wants=news",
    "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "MarketWatch Top Stories": "http://feeds.marketwatch.com/marketwatch/topstories/",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Sky News Business": "https://feeds.skynews.com/feeds/rss/business.rss"
}
