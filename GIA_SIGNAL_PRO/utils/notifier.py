
import requests
from datetime import datetime
from GIA_SIGNAL_PRO.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class TelegramSignalNotifier:
    """
    🦁 GIA SIGNAL PRO - TELEGRAM DELIVERY ENGINE
    """
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_signal(self, data):
        if self.token == "YOUR_BOT_TOKEN_HERE":
            print("⚠️ Telegram Token not configured.")
            return

        emoji = "🟢 BUY" if data['direction'] == "BUY" else "🔴 SELL"
        conf_stars = "⭐" * int(data['confidence'] / 20)
        
        message = (
            f"🦁 *GIA SIGNAL PRO - XAUUSD*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔹 *Direction:* {emoji}\n"
            f"🎯 *Confidence:* {data['confidence']}% {conf_stars}\n"
            f"⏳ *Context:* {data['timeframe']}\n"
            f"📊 *Analysis:* {data['reason']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}\n"
            f"⚠️ *Signal Only - Educational Context*"
        )

        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}

        try:
            r = requests.post(self.url, data=payload, timeout=10)
            if r.status_code == 200:
                print(f"✅ Telegram: Signal Sent ({data['direction']})")
        except Exception as e:
            print(f"❌ Telegram Error: {e}")
