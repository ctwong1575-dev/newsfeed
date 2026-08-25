import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Telegram message length limit is 4096 characters
    max_len = 4000
    messages = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    
    success = True
    for msg in messages:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload)
            res_data = response.json()
            if not res_data.get("ok"):
                payload.pop("parse_mode", None)
                requests.post(url, json=payload)
                print("⚠️ Markdown 發送失敗，已降級為純文本發送。")
        except Exception as e:
            print(f"❌ Telegram 發送失敗: {e}")
            success = False
            
    if success:
        print("✅ Telegram 訊息發送成功！")
    return success
