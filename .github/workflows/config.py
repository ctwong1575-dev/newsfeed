import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "615899930")

NEWS_FEEDS = {
    "CNBC": "https://search.cnbc.com/rs/search/combinedrender.view?partnerId=wrss01&id=10000664&profile=rss&wants=news",
    "CNN Business": "http://rss.cnn.com/rss/money_latest.rss",
    "DW Business": "https://rss.dw.com/xml/rss-en-bus",
    "Sky News Business": "https://feeds.skynews.com/feeds/rss/business.rss",
    "Al Arabiya English": "https://english.alarabiya.net/tools/rss"
}
