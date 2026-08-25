import feedparser
from typing import List, Dict
from config import NEWS_FEEDS

def fetch_daily_news(max_articles_per_source: int = 5) -> List[Dict[str, str]]:
    all_articles = []
    
    for source_name, url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                if count >= max_articles_per_source:
                    break
                
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                
                all_articles.append({
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "link": link
                })
                count += 1
            print(f"✅ 成功抓取 {source_name} 的新聞 ({count} 則)")
        except Exception as e:
            print(f"❌ 抓取 {source_name} 失敗: {e}")
            
    return all_articles
