
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
        self.sent_messages = [] # Track: (chat_id, message_id, expiry_ts)
        self.lock = threading.Lock()
        
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
        """Starts background threads for listener and cleanup."""
        threading.Thread(target=self._polling_loop, daemon=True).start()
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        logger.info("📡 Telegram Bot Listener & Cleanup Engine started...")

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

    def _cleanup_loop(self):
        """Background worker to delete expired signals (The 'Self-Cleaning' Logic)."""
        while True:
            try:
                now = time.time()
                with self.lock:
                    to_delete = [m for m in self.sent_messages if now >= m['expiry']]
                    self.sent_messages = [m for m in self.sent_messages if now < m['expiry']]

                for msg in to_delete:
                    try:
                        url = f"{self.api_url}/deleteMessage"
                        payload = {"chat_id": msg['chat_id'], "message_id": msg['message_id']}
                        requests.post(url, json=payload, timeout=5)
                    except: pass
                
                time.sleep(30) # Check every 30 seconds
            except Exception as e:
                logger.error(f"⚠️ Cleanup error: {e}")
                time.sleep(10)

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
        self.broadcast_message(message, is_signal=False)

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
        self.broadcast_message(message, is_signal=False)

    def send_signal(self, direction, confidence, signal_time=None, price=0):
        """Broadcasts a high-confidence signal to all subscribers."""
        if signal_time is None:
            signal_time = datetime.now().strftime('%H:%M:%S')
        
        dir_ar = "🔵 شراء (BUY)" if direction == "BUY" else "🔴 بيع (SELL)"
        
        # Visual Confidence Meter
        filled = int(confidence / 10)
        meter = "█" * filled + "░" * (10 - filled)
        
        # ULTRA-PREMIUM Layout
        message = (
            f"🚀 <b>GIA APEX | إشارة سكالبينج ذهبية</b> ⚡\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"💎 <b>الأداة:</b> <code>{ASSET}</code>\n"
            f"⏱️ <b>الفريم:</b> <code>M1 (Hyper-Scalp)</code>\n"
            f"� <b>النوع:</b> <b>{dir_ar}</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"� <b>سعر الدخول:</b> <code>{price:.2f}</code>\n"
            f"📊 <b>قوة الإشارة:</b> [<code>{meter}</code>] {confidence}%\n"
            f"🕒 <b>وقت الدخول:</b> <code>{signal_time}</code>\n"
            f"⏳ <b>صلاحية الإشارة:</b> <u>5 دقائق فقط</u>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🎯 <b>الهدف (TP):</b> <code>+1.50$</code> (15 Pips)\n"
            f"🛑 <b>الوقف (SL):</b> <code>-2.00$</code> (20 Pips)\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"⚠️ <i>تحذير: لا تدخل الصفقة إذا تغير السعر كثيراً.</i>\n"
            f"🦁 <b>GIA SIGNAL PRO | Institutional Sniper</b>"
        )
        return self.broadcast_message(message)

    def broadcast_message(self, text, is_signal=True):
        if not self.subscribers:
            logger.warning("⚠️ No subscribers found. Message not sent.")
            return False
            
        success_flag = False
        expiry_ts = time.time() + (5 * 60) # 5 Minutes validity
        
        for chat_id in list(self.subscribers):
            try:
                url = f"{self.api_url}/sendMessage"
                payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
                r = requests.post(url, json=payload, timeout=10).json()
                
                if r.get("ok"):
                    success_flag = True
                    if is_signal:
                        message_id = r["result"]["message_id"]
                        with self.lock:
                            self.sent_messages.append({
                                'chat_id': chat_id,
                                'message_id': message_id,
                                'expiry': expiry_ts
                            })
                else:
                    logger.error(f"❌ Telegram API Error: {r}")
                    
            except Exception as e:
                logger.error(f"❌ Failed to send to {chat_id}: {e}")
        return success_flag

# Global instance
notifier = TelegramSignalNotifier()
