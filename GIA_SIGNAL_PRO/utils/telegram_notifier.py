
import requests
import os
import logging
import json
import threading
import time
from datetime import datetime
from GIA_SIGNAL_PRO.config.settings import (
    TELEGRAM_BOT_TOKEN, 
    ASSET,
    TIMEFRAME,
    TIMEZONE
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TelegramNotifier")

SUBSCRIBERS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "subscribers.json")

class TelegramSignalNotifier:
    """
    🦁 GIA SIGNAL PRO - Telegram Subscriber Module
    Handles /start subscription logic and broadcasting to all users.
    """
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.subscribers = self._load_subscribers()
        self.last_update_id = 0
        
        if not self.bot_token or self.bot_token == "YOUR_BOT_TOKEN_HERE":
            logger.warning("⚠️ TELEGRAM_BOT_TOKEN is missing. Bot mode disabled.")

    def _load_subscribers(self):
        if os.path.exists(SUBSCRIBERS_FILE):
            try:
                with open(SUBSCRIBERS_FILE, 'r') as f:
                    return set(json.load(f))
            except Exception as e:
                logger.error(f"❌ Error loading subscribers: {e}")
        return set()

    def _save_subscribers(self):
        try:
            os.makedirs(os.path.dirname(SUBSCRIBERS_FILE), exist_ok=True)
            with open(SUBSCRIBERS_FILE, 'w') as f:
                json.dump(list(self.subscribers), f)
        except Exception as e:
            logger.error(f"❌ Error saving subscribers: {e}")

    def start_listener(self):
        """Starts a background thread to listen for /start and /stop commands."""
        thread = threading.Thread(target=self._polling_loop, daemon=True)
        thread.start()
        logger.info("📡 Telegram Bot Listener started...")

    def _polling_loop(self):
        while True:
            try:
                url = f"{self.api_url}/getUpdates?offset={self.last_update_id + 1}&timeout=30"
                response = requests.get(url, timeout=35).json()
                
                if response.get("ok"):
                    for update in response.get("result", []):
                        self.last_update_id = update["update_id"]
                        message = update.get("message")
                        if not message: continue
                        
                        chat_id = message["chat"]["id"]
                        text = message.get("text", "").strip().lower()
                        
                        if text == "/start":
                            if chat_id not in self.subscribers:
                                self.subscribers.add(chat_id)
                                self._save_subscribers()
                                
                                welcome = (
                                    f"🦁 <b>مرحباً بك في نظام GIA PRO للذكاء الاصطناعي</b>\n"
                                    f"----------------------------------\n"
                                    f"🚀 تم تفعيل اشتراكك بنجاح لاستلام أقوى إشارات السكالبينج على الذهب (XAUUSD).\n\n"
                                    f"<b>ماذا يميز هذا النظام؟</b>\n"
                                    f"✅ تحليل مؤسساتي فائق الدقة لفريم الدقيقة.\n"
                                    f"✅ إشارات قناصة تعتمد على زخم السيولة (Liquidity Momentum).\n"
                                    f"✅ نظام متطور لإدارة المخاطر مدمج في كل إشارة.\n"
                                    f"----------------------------------\n"
                                    f"✨ <i>ترقب الإشارة القادمة... السوق لا ينام!</i>"
                                )
                                self._send_text(chat_id, welcome)
                                logger.info(f"🆕 New subscriber: {chat_id}")
                        elif text == "/stop":
                            if chat_id in self.subscribers:
                                self.subscribers.remove(chat_id)
                                self._save_subscribers()
                                self._send_text(chat_id, "🛑 <b>تم إيقاف الاشتراك</b>\nلقد توقفت الآن عن استلام إشارات GIA PRO. يمكنك العودة في أي وقت بإرسال /start")
                                logger.info(f"🚫 Subscriber left: {chat_id}")
            except Exception as e:
                time.sleep(5)

    def _send_text(self, chat_id, text):
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            requests.post(url, json=payload, timeout=5)
        except: pass

    def send_startup_message(self, min_confidence):
        """Broadcasts startup message to all subscribers."""
        message = (
            f"🦁 <b>تنبيه: تشغيل نظام GIA PRO</b>\n"
            f"----------------------------------\n"
            f"✅ <b>الحالة:</b> المحرك يعمل بكفاءة عالية\n"
            f"🎯 <b>دقة التصفية:</b> {min_confidence}%\n"
            f"� <b>المراقبة:</b> جارية الآن على XAUUSD M1\n"
            f"----------------------------------\n"
            f"� <i>نحن الآن نراقب السيولة لاقتناص أقوى الفرص...</i>"
        )
        self.broadcast_message(message)

    def send_shutdown_message(self):
        """Broadcasts shutdown message to all subscribers."""
        message = (
            f"⚠️ <b>تنبيه: توقف نظام GIA PRO</b>\n"
            f"----------------------------------\n"
            f"🛑 <b>الحالة:</b> النظام غير متصل الآن (Offline)\n"
            f"💤 لن يتم إرسال إشارات حتى يتم إعادة التشغيل.\n"
            f"----------------------------------\n"
            f"🕒 {datetime.now().strftime('%Y-%m-%d | %H:%M:%S')}"
        )
        self.broadcast_message(message)

    def send_signal(self, direction, confidence, signal_time=None):
        """Broadcasts a high-confidence signal to all subscribers."""
        if signal_time is None:
            signal_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        dir_ar = "🔵 شراء (BUY)" if direction == "BUY" else "🔴 بيع (SELL)"
        
        # FINAL Professional Hybrid Format
        message = (
            f"⚡ <b>GIA SIGNAL PRO</b>\n"
            f"----------------------------------\n"
            f"💎 <b>الأداة:</b> {ASSET}\n"
            f"⏱️ <b>الفريم:</b> {TIMEFRAME} (سكالبينج)\n"
            f"🚀 <b>الاتجاه:</b> {dir_ar}\n"
            f"📊 <b>مستوى الثقة:</b> {confidence}%\n"
            f"🕒 <b>التوقيت:</b> {signal_time} ({TIMEZONE})\n"
            f"----------------------------------\n"
            f"🦁 <i>التحليلات المؤسساتية - دقة الصفر خطأ</i>"
        )
        self.broadcast_message(message)

    def broadcast_message(self, text):
        for chat_id in list(self.subscribers):
            try:
                url = f"{self.api_url}/sendMessage"
                payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
                requests.post(url, json=payload, timeout=5)
            except Exception as e:
                logger.error(f"❌ Failed to send to {chat_id}: {e}")

# Global instance
notifier = TelegramSignalNotifier()
