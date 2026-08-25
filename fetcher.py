import feedparser
import requests
import datetime
from typing import List, Dict
from config import NEWS_FEEDS

def fetch_daily_news(max_articles_per_source: int = 4) -> List[Dict[str, str]]:
    all_articles = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for source_name, url in NEWS_FEEDS.items():
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                count = 0
                for entry in feed.entries:
                    if count >= max_articles_per_source:
                        break
                    
                    title = entry.get("title", "").strip()
                    summary = entry.get("summary", entry.get("description", "")).strip()
                    link = entry.get("link", "").strip()
                    published = entry.get("published", entry.get("updated", entry.get("pubDate", "")))

                    if title:
                        all_articles.append({
                            "source": source_name,
                            "title": title,
                            "summary": summary,
                            "link": link,
                            "published": published
                        })
                        count += 1
                print(f"✅ 成功抓取 {source_name} 的新聞 ({count} 則)")
            else:
                print(f"⚠️ {source_name} 回傳狀態碼: {response.status_code}")
        except Exception as e:
            print(f"❌ 抓取 {source_name} 失敗: {e}")
            
    return all_articles
