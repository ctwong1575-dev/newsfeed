import requests
import os

def send_telegram_message(message: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "615899930")
    
    if not bot_token:
        print("❌ 未設定 TELEGRAM_BOT_TOKEN")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True  # 避免多個網址產生過多預覽圖庫
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ 成功發送訊息至 Telegram")
        else:
            print(f"⚠️ 發送失敗 (HTTP {response.status_code}): {response.text}")
            # 如果因為 Markdown 格式解析失敗，退回純文字發送
            payload.pop("parse_mode", None)
            requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ Telegram 發送例外: {e}")
