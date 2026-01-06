
import requests
import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta

# Import secrets
try:
    from backend.config.secrets import TELEGRAM_BOT_TOKEN
except ImportError:
    try:
        from config.secrets import TELEGRAM_BOT_TOKEN
    except ImportError:
        TELEGRAM_BOT_TOKEN = None

print(f"DEBUG: TELEGRAM_BOT_TOKEN version: {TELEGRAM_BOT_TOKEN[:10] if TELEGRAM_BOT_TOKEN else 'NONE'}")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBSCRIBERS_FILE = os.path.join(os.path.dirname(BASE_DIR), "GIA_SIGNAL_PRO", "data", "subscribers.json")

# Ensure the data directory exists
os.makedirs(os.path.dirname(SUBSCRIBERS_FILE), exist_ok=True)

class TelegramService:
    """
    Institutional Telegram Service for GIA
    Handles trade alerts, daily reports, emergency notifications, and signal confirmations.
    """
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.subscribers = self._load_subscribers()
        self.last_update_id = 0
        self.trading_enabled = True # Production Default: Enabled
        self.bridge_ref = None # Reference to the cTrader bridge
        
        # Configuration Defaults (Will be updated by main engine)
        self.risk = 0.5
        self.leverage = 100
        self.margin_guard = 80
        self.message_history = {} # chat_id -> list of message_ids to cleanup
        
        if not self.bot_token:
            logging.error("❌ Telegram Bot Token is missing! Notifications will not work.")

    def _load_subscribers(self):
        if os.path.exists(SUBSCRIBERS_FILE):
            try:
                with open(SUBSCRIBERS_FILE, 'r') as f:
                    data = json.load(f)
                    return set(data) if isinstance(data, list) else set()
            except Exception as e:
                logging.error(f"Error loading subscribers: {e}")
        return set()

    def _save_subscribers(self):
        try:
            with open(SUBSCRIBERS_FILE, 'w') as f:
                json.dump(list(self.subscribers), f)
        except Exception as e:
            logging.error(f"Error saving subscribers: {e}")

    def start_listener(self):
        """Starts the background listener for commands and interactivity."""
        if not self.bot_token: return
        threading.Thread(target=self._polling_loop, daemon=True).start()
        logging.info("📡 GIA Control Center: Telegram Listener Active.")

    def _get_control_keyboard(self):
        """Returns the main Arabic control keyboard."""
        status_btn = "🛑 إيقاف التداول" if self.trading_enabled else "🟢 تشغيل التداول"
        
        keyboard = {
            "inline_keyboard": [
                [{"text": status_btn, "callback_data": "toggle_trading"}],
                [
                    {"text": "📊 حالة النظام", "callback_data": "get_status"},
                    {"text": "💰 تقرير اليوم", "callback_data": "get_report"}
                ],
                [
                    {"text": f"⚖️ مخاطرة: {self.risk}%", "callback_data": "set_risk_menu"},
                    {"text": f"🚀 رافعة: 1:{self.leverage}", "callback_data": "set_lev_menu"}
                ],
                [{"text": "🖥️ مراقبة الشاشة الحية", "callback_data": "view_terminal"}],
                [
                    {"text": "🔄 تحديث البيانات", "callback_data": "sync_now"},
                    {"text": "🧹 تنظيف الشاشة", "callback_data": "clear_chat"}
                ]
            ]
        }
        return json.dumps(keyboard)

    def _get_risk_keyboard(self):
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "0.1%", "callback_data": "set_risk_0.1"},
                    {"text": "0.2%", "callback_data": "set_risk_0.2"},
                    {"text": "0.5%", "callback_data": "set_risk_0.5"}
                ],
                [
                    {"text": "1.0%", "callback_data": "set_risk_1.0"},
                    {"text": "2.0%", "callback_data": "set_risk_2.0"},
                    {"text": "5.0%", "callback_data": "set_risk_5.0"}
                ],
                [{"text": "🔙 العودة", "callback_data": "main_menu"}]
            ]
        }
        return json.dumps(keyboard)

    def _get_lev_keyboard(self):
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "1:30", "callback_data": "set_lev_30"},
                    {"text": "1:50", "callback_data": "set_lev_50"},
                    {"text": "1:100", "callback_data": "set_lev_100"}
                ],
                [
                    {"text": "1:200", "callback_data": "set_lev_200"},
                    {"text": "1:500", "callback_data": "set_lev_500"},
                    {"text": "1:1000", "callback_data": "set_lev_1000"}
                ],
                [{"text": "🔙 العودة", "callback_data": "main_menu"}]
            ]
        }
        return json.dumps(keyboard)

    def _polling_loop(self):
        logging.info(f"🌀 Polling loop started with token: {self.bot_token[:10]}...")
        while True:
            try:
                url = f"{self.api_url}/getUpdates?offset={self.last_update_id + 1}&timeout=30"
                r = requests.get(url, timeout=35)
                response = r.json()
                
                if response.get("ok"):
                    updates = response.get("result", [])
                    for update in updates:
                        self.last_update_id = update["update_id"]
                        
                        # Handle Callback Queries (Buttons)
                        if "callback_query" in update:
                            self._handle_callback(update["callback_query"])
                            continue

                        # Handle Text Messages
                        if "message" in update:
                            message = update["message"]
                            chat_id = message["chat"]["id"]
                            inc_msg_id = message["message_id"]
                            
                            # Track incoming user message for cleanup
                            if chat_id not in self.message_history: self.message_history[chat_id] = []
                            self.message_history[chat_id].append(inc_msg_id)
                            
                            text = message.get("text", "")
                            
                            text_lower = text.strip().lower()
                            if text_lower == "/start" or text_lower == "قائمة التحكم":
                                if chat_id not in self.subscribers:
                                    self.subscribers.add(chat_id)
                                    self._save_subscribers()
                                self.send_control_panel(chat_id)
                            elif text_lower == "/status":
                                self._handle_status_request(chat_id)
                else:
                    logging.error(f"Telegram API Error response: {response}")
            except Exception as e:
                logging.error(f"Telegram Polling Exception: {e}")
                time.sleep(10)

    def _handle_callback(self, query):
        chat_id = query["message"]["chat"]["id"]
        message_id = query["message"]["message_id"]
        data = query["data"]
        callback_id = query["id"]
        
        # 🟢 Answer callback to stop loading spinner
        requests.post(f"{self.api_url}/answerCallbackQuery", json={"callback_query_id": callback_id})

        if data == "toggle_trading":
            self.trading_enabled = not self.trading_enabled
            status_text = "✅ تم تشغيل التداول بنجاح" if self.trading_enabled else "🛑 تم إيقاف التداول مؤقتاً"
            self._update_message(chat_id, message_id, f"<b>{status_text}</b>", use_main_kbd=True)
            logging.info(f"Trading Toggle: {self.trading_enabled}")
            
        elif data == "get_status":
            self._handle_status_request(chat_id, message_id)
            
        elif data == "get_report":
            self.send_daily_report(0.0, 0, 0.0)

        elif data == "sync_now":
            if self.bridge_ref:
                self.bridge_ref.fetch_live_data() # Force bridge update
                time.sleep(1) # Small delay for file writing
                
                snapshot = self._get_csv_snapshot()
                last_bid = f"{self.bridge_ref.latest_bid:.2f}" if self.bridge_ref.latest_bid else "N/A"
                last_ask = f"{self.bridge_ref.latest_ask:.2f}" if self.bridge_ref.latest_ask else "N/A"
                
                sync_msg = (
                    "🔄 <b>تقرير مزامنة البيانات | GIA Pro</b>\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"💰 <b>العرض:</b> <code>{last_bid}</code> | <b>الطلب:</b> <code>{last_ask}</code>\n\n"
                    "📁 <b>حالة البيانات (Local Time +3):</b>\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"{snapshot}"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "✅ تم تحديث كاش البيانات بنجاح."
                )
                self._update_message(chat_id, message_id, sync_msg, use_main_kbd=True)
            else:
                self._update_message(chat_id, message_id, "⚠️ النظام غير متصل بالجسر حالياً.", use_main_kbd=True)

        elif data == "view_terminal":
            self._handle_terminal_request(chat_id, message_id)

        elif data == "clear_chat":
            # 1. Get history for this user
            history = self.message_history.get(chat_id, [])
            
            # 2. Try to delete current message first
            history.append(message_id)
            
            # 3. Mass delete
            for msg_id in set(history):
                try:
                    requests.post(f"{self.api_url}/deleteMessage", json={"chat_id": chat_id, "message_id": msg_id}, timeout=5)
                except: pass
            
            # 4. Clear history and send fresh panel
            self.message_history[chat_id] = []
            self.send_control_panel(chat_id)

        elif data == "main_menu":
            self.send_control_panel(chat_id, message_id)

        elif data == "set_risk_menu":
            self._update_message(chat_id, message_id, "⚖️ <b>اختر مستوى المخاطرة للصفقة الواحدة:</b>", use_risk_kbd=True)
        
        elif data.startswith("set_risk_"):
            new_risk = float(data.replace("set_risk_", ""))
            self.risk = new_risk
            self._update_message(chat_id, message_id, f"✅ <b>تم ضبط المخاطرة على {new_risk}%</b>", use_main_kbd=True)
            logging.info(f"Risk Updated: {new_risk}%")

        elif data == "set_lev_menu":
            self._update_message(chat_id, message_id, "🚀 <b>اختر الرافعة المالية المطلوبة:</b>", use_lev_kbd=True)

        elif data.startswith("set_lev_"):
            new_lev = int(data.replace("set_lev_", ""))
            self.leverage = new_lev
            self._update_message(chat_id, message_id, f"✅ <b>تم ضبط الرافعة على 1:{new_lev}</b>", use_main_kbd=True)
            logging.info(f"Leverage Updated: 1:{new_lev}")

    def _get_csv_snapshot(self):
        """Reads the last line of each timeframe CSV (now already UTC+3)."""
        timeframes = ["M1", "M15", "M30", "H1"]
        results = []
        data_dir = os.path.join(os.path.dirname(BASE_DIR), "data")
        
        for tf in timeframes:
            fpath = os.path.join(data_dir, f"XAUUSD_{tf}.csv")
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r') as f:
                        lines = f.readlines()
                        if len(lines) > 1:
                            last_line = lines[-1].strip()
                            parts = last_line.split(',')
                            # Format: Timestamp, Open, High, Low, Close, Volume
                            raw_ts = parts[0]
                            close = parts[4]
                            
                            # Extract time part for cleaner display
                            try:
                                ts_display = raw_ts.split(' ')[1]
                            except:
                                ts_display = raw_ts
                                
                            results.append(f"⏱ <b>{tf}:</b> <code>{ts_display}</code> | 🟢 <code>{close}</code>")
                        else:
                            results.append(f"⏱ <b>{tf}:</b> ملف فارغ")
                except:
                    results.append(f"⏱ <b>{tf}:</b> خطأ قراءة")
            else:
                results.append(f"⏱ <b>{tf}:</b> غير موجود")
        
        return "\n".join(results) + "\n"

    def _handle_terminal_request(self, chat_id, message_id=None):
        """Captures the last few lines from the screen session."""
        try:
            temp_file = "/tmp/gia_screen_dump.txt"
            os.system(f"screen -S gia_institutional -X hardcopy {temp_file}")
            time.sleep(0.5)
            
            if os.path.exists(temp_file):
                with open(temp_file, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                
                # Get last 15 lines of relevant output
                output = "".join(lines[-15:])
                clean_output = output.replace('\x00', '').strip()
                
                term_msg = (
                    "🖥️ <b>لقطة حية من التيرمنال</b>\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"<code>{clean_output}</code>\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🕒 {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}"
                )
                if message_id:
                    self._update_message(chat_id, message_id, term_msg, use_main_kbd=True)
                else:
                    self._send_text(chat_id, term_msg, include_keyboard=True)
            else:
                self._send_text(chat_id, "❌ تعذر الحصول على لقطة من الشاشة حالياً.")
        except Exception as e:
            logging.error(f"Error capturing terminal: {e}")
            self._send_text(chat_id, "❌ خطأ تقني في جلب بيانات التيرمنال.")

    def _update_message(self, chat_id, message_id, text, use_main_kbd=False, use_risk_kbd=False, use_lev_kbd=False):
        try:
            url = f"{self.api_url}/editMessageText"
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML"
            }
            if use_main_kbd:
                payload["reply_markup"] = self._get_control_keyboard()
            elif use_risk_kbd:
                payload["reply_markup"] = self._get_risk_keyboard()
            elif use_lev_kbd:
                payload["reply_markup"] = self._get_lev_keyboard()
            
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                # Track for cleanup
                new_id = r.json().get("result", {}).get("message_id")
                if new_id:
                    if chat_id not in self.message_history: self.message_history[chat_id] = []
                    self.message_history[chat_id].append(new_id)
        except Exception as e:
            logging.error(f"Error updating message: {e}")

    def _handle_status_request(self, chat_id, message_id=None):
        conn_status = "🟢 متصل" if (self.bridge_ref and self.bridge_ref.connected) else "🔴 غير متصل"
        trading_status = "🟢 نشط" if self.trading_enabled else "⏸️ متوقف"
        equity = f"${self.bridge_ref.current_equity:.2f}" if (self.bridge_ref and self.bridge_ref.current_equity) else "N/A"
        
        local_now = datetime.now() + timedelta(hours=3)
        pos_count = len(self.bridge_ref.open_positions) if self.bridge_ref else 0
        status_msg = (
            f"🖥️ <b>حالة نظام GIA </b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📡 <b>الاتصال:</b> {conn_status}\n"
            f"⚙️ <b>وضع التداول:</b> {trading_status}\n"
            f"⚖️ <b>المخاطرة:</b> {self.risk}%\n"
            f"🚀 <b>الرافعة:</b> 1:{self.leverage}\n"
            f"💰 <b>الرصيد المتاح:</b> <code>{equity}</code>\n"
            f"📊 <b>الصفقات المفتوحة:</b> <code>{pos_count}</code>\n"
            f"📊 <b>الأداة:</b> XAUUSD (Gold)\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🕒 {local_now.strftime('%Y-%m-%d | %H:%M:%S')}"
        )
        if message_id:
            self._update_message(chat_id, message_id, status_msg, use_main_kbd=True)
        else:
            self._send_text(chat_id, status_msg, include_keyboard=True)

    def _send_text(self, chat_id, text, include_keyboard=False):
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": chat_id, 
                "text": text, 
                "parse_mode": "HTML"
            }
            if include_keyboard:
                payload["reply_markup"] = self._get_control_keyboard()
            
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                logging.info(f"✅ Message sent to {chat_id}")
                # Track for cleanup
                new_id = r.json().get("result", {}).get("message_id")
                if new_id:
                    if chat_id not in self.message_history: self.message_history[chat_id] = []
                    self.message_history[chat_id].append(new_id)
            else:
                logging.error(f"❌ Telegram Send Error ({r.status_code}) to {chat_id}: {r.text}")
        except Exception as e:
            logging.error(f"❌ Telegram Send Exception: {e}")

    def broadcast(self, text, include_keyboard=False):
        if not self.subscribers:
            logging.warning("No subscribers to broadcast to.")
            return
        for chat_id in list(self.subscribers):
            self._send_text(chat_id, text, include_keyboard=include_keyboard)

    def send_control_panel(self, chat_id, message_id=None):
        welcome = (
            "🦁 <b>لوحة التحكم المركزية - GIA Pro 4.0</b>\n"
            "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            "أهلاً بك في واجهة التحكم العربية المتطورة. من هنا يمكنك إدارة عمليات التداول الآلي بالكامل بمستوى احترافي.\n\n"
            "📩 <b>استخدم الأزرار أدناه للتحكم:</b>"
        )
        if message_id:
            self._update_message(chat_id, message_id, welcome, use_main_kbd=True)
        else:
            self._send_text(chat_id, welcome, include_keyboard=True)

    # 1. Trade Alerts
    def notify_trade_open(self, direction, lots, price, sl, tp):
        emoji = "🔵" if direction == "BUY" else "🔴"
        msg = (
            f"{emoji} <b>GIA: فتح صفقة جديدة</b>\n"
            f"----------------------------------\n"
            f"💎 <b>الأداة:</b> XAUUSD\n"
            f"⚖️ <b>النوع:</b> {direction}\n"
            f"📦 <b>الحجم:</b> {lots} Lots\n"
            f"💰 <b>السعر:</b> {price:.2f}\n"
            f"🛑 <b>الوقف (SL):</b> {sl:.2f}\n"
            f"🎯 <b>الهدف (TP):</b> {tp:.2f}\n"
            f"----------------------------------\n"
            f"🕒 {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}"
        )
        self.broadcast(msg)

    def notify_trade_close(self, position_id, profit, reason="Closed"):
        emoji = "💰" if profit >= 0 else "📉"
        msg = (
            f"{emoji} <b>GIA: إغلاق صفقة</b>\n"
            f"----------------------------------\n"
            f"🆔 <b>رقم الصفقة:</b> {position_id}\n"
            f"📊 <b>النتيجة:</b> {profit:+.2f}$\n"
            f"📝 <b>السبب:</b> {reason}\n"
            f"----------------------------------\n"
            f"🕒 {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}"
        )
        self.broadcast(msg)

    # 2. Performance Report
    def send_daily_report(self, total_profit, total_trades, win_rate):
        msg = (
            f"📊 <b>تقرير الأداء اليومي | GIA</b>\n"
            f"----------------------------------\n"
            f"💵 <b>صافي الربح:</b> {total_profit:+.2f}$\n"
            f"🤝 <b>إجمالي الصفقات:</b> {total_trades}\n"
            f"🎯 <b>نسبة النجاح:</b> {win_rate:.1f}%\n"
            f"----------------------------------\n"
            f"🏆 <i>يوم تداول ناجح!</i>"
        )
        self.broadcast(msg)

    # 3. Emergency Notifications
    def notify_emergency(self, error_msg):
        msg = (
            f"🚨 <b>تنبيه طوارئ: GIA SYSTEM</b>\n"
            f"----------------------------------\n"
            f"⚠️ <b>الخطأ:</b> <code>{error_msg}</code>\n"
            f"----------------------------------\n"
            f"❗ يرجى التحقق من حالة السيرفر فوراً."
        )
        self.broadcast(msg)

    def notify_connection_status(self, connected):
        status = "🟢 متصل (Online)" if connected else "🔴 منقطع (Offline)"
        msg = (
            f"📡 <b>تحديث الاتصال | GIA</b>\n"
            f"----------------------------------\n"
            f"الحالة الحالية: {status}\n"
            f"----------------------------------\n"
            f"🕒 {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}"
        )
        self.broadcast(msg)

    # 4. Signal Confirmation & Pre-Alerts
    def notify_pre_alert(self, direction, reason, confidence):
        emoji = "🟡" # Yellow warning for "Pre-Alert"
        msg = (
            f"{emoji} <b>GIA: تنبيه مبكر (Pre-Alert)</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"👀 <b>المراقبة الحالية:</b> احتمالية {direction}\n"
            f"💡 <b>السبب:</b> {reason}\n"
            f"📊 <b>قوة الإشارة الأولية:</b> {confidence}%\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"⏳ <i>قد يتم الدخول خلال الـ 15 دقيقة القادمة إذا اكتملت الشروط...</i>\n"
            f"🕒 {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}"
        )
        self.broadcast(msg)

    def notify_signal_detection(self, direction, analysis, confidence):
        emoji = "📡"
        msg = (
            f"{emoji} <b>GIA: كشف إشارة قوية</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"⚖️ <b>الاتجاه المتوقع:</b> {direction}\n"
            f"🧠 <b>التحليل:</b> {analysis}\n"
            f"📊 <b>مستوى الثقة:</b> {confidence}%\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"⏳ <i>سيتم التنفيذ تلقائياً بعد الفحص النهائي...</i>"
        )
        self.broadcast(msg)

# Global instance
telegram_service = TelegramService()
