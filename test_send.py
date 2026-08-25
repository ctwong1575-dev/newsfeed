import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def test_telegram():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "🎉 測試成功！您的 Telegram Bot 已成功連結，每日 8:00 AM 將在此發送財經新聞與 5 大投資建議。",
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Telegram 測試訊息發送成功！請檢查手機。")
        else:
            print(f"❌ 發送失敗，錯誤代碼: {response.status_code}, 內容: {response.text}")
    except Exception as e:
        print(f"❌ 連線異常: {e}")

if __name__ == "__main__":
    test_telegram()
