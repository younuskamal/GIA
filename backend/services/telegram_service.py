
import requests
import os
import sys
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
STATE_FILE = os.path.join(os.path.dirname(BASE_DIR), "GIA_SIGNAL_PRO", "data", "bot_state.json")

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
        self.active_model_name = "Unknown" # Tracking active model name
        
        # 🟢 Real-time Analysis State
        self.latest_analysis = {
            "signal": "WAIT",
            "confidence": 0.0,
            "rsi_status": "Calculating...",
            "vol_status": "Calculating...",
            "news_status": "Safe",
            "sentiment": "Neutral",
            "timestamp": datetime.now()
        }
        # Alert throttling to reduce spam
        self.last_signal_alert = {"ts": 0, "direction": None, "confidence": 0.0}
        self.signal_cooldown_sec = 3600 # 60 minutes between identical alerts
        self.min_signal_conf_pct = 55.0 # Don't send alerts below this confidence %
        
        self.analyzer_ref = None # Reference to the Analysis Engine
        self.daily_trades = [] # List of (profit, timestamp) for today
        
        # Load persistent state if exists
        self._load_state()
        
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

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    self.trading_enabled = state.get('trading_enabled', True)
                    self.risk = state.get('risk', 0.5)
                    self.leverage = state.get('leverage', 100)
                    self.active_model_name = state.get('active_model_name', "Unknown")
                    
                    # Convert saved trade times back to datetime objects
                    raw_trades = state.get('daily_trades', [])
                    for t in raw_trades:
                        try:
                            t['time'] = datetime.fromisoformat(t['time'])
                            self.daily_trades.append(t)
                        except: pass
            except Exception as e:
                logging.error(f"Error loading state: {e}")

    def _save_state(self):
        try:
            state = {
                'trading_enabled': self.trading_enabled,
                'risk': self.risk,
                'leverage': self.leverage,
                'active_model_name': self.active_model_name,
                'daily_trades': [
                    {'pnl': t['pnl'], 'time': t['time'].isoformat() if isinstance(t['time'], datetime) else t['time']}
                    for t in self.daily_trades[-100:] # Keep last 100 trades
                ]
            }
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logging.error(f"Error saving state: {e}")

    def start_listener(self):
        """Starts the background listener for commands and interactivity."""
        if not self.bot_token: return
        threading.Thread(target=self._polling_loop, daemon=True).start()
        logging.info("📡 GIA Control Center: Telegram Listener Active.")

    def _get_control_keyboard(self):
        """Returns the ultra-premium grouped control keyboard in Arabic."""
        status_btn = "📡 [ تشغيل ]" if self.trading_enabled else "📡 [ إيقاف ]"
        status_color = "🟢" if self.trading_enabled else "🔴"
        
        keyboard = {
            "inline_keyboard": [
                [{"text": f"{status_color} {status_btn}", "callback_data": "toggle_trading"}],
                [
                    {"text": "📊 حالة النظام", "callback_data": "get_status"},
                    {"text": "🧠 رؤية الذكاء", "callback_data": "get_ai_vision"}
                ],
                [
                    {"text": f"⚙️ إعداد المخاطرة: {self.risk}%", "callback_data": "set_risk_menu"},
                    {"text": f"🚀 الرافعة: 1:{self.leverage}", "callback_data": "set_lev_menu"}
                ],
                [
                    {"text": "💰 الصفقات النشطة", "callback_data": "get_trades_info"},
                    {"text": "📈 تقرير الأداء", "callback_data": "get_report"}
                ],
                [
                    {"text": "🧬 التعلم العصبي", "callback_data": "trigger_learning"},
                    {"text": "🔄 مزامنة البيانات", "callback_data": "sync_now"}
                ],
                [{"text": "🖥️ التيرمنال", "callback_data": "view_terminal"}, {"text": "🧹 تنظيف", "callback_data": "clear_chat"}]
            ]
        }
        return json.dumps(keyboard)

    def _get_trades_keyboard(self):
        return json.dumps({
            "inline_keyboard": [[{"text": "🔙 العودة للقائمة", "callback_data": "main_menu"}]]
        })

    def _get_risk_keyboard(self):
        def _btn(val):
            text = f"✅ {val}%" if self.risk == val else f"{val}%"
            return {"text": text, "callback_data": f"set_risk_{val}"}

        keyboard = {
            "inline_keyboard": [
                [_btn(0.1), _btn(0.2), _btn(0.5)],
                [_btn(1.0), _btn(1.5), _btn(2.0)],
                [_btn(3.0), _btn(5.0), _btn(10.0)],
                [{"text": "🔙 العودة للقائمة", "callback_data": "main_menu"}]
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
            self._save_state()
            status_text = "✅ تم تشغيل التداول بنجاح" if self.trading_enabled else "🛑 تم إيقاف التداول مؤقتاً"
            self._update_message(chat_id, message_id, f"<b>{status_text}</b>", use_main_kbd=True)
            logging.info(f"Trading Toggle: {self.trading_enabled}")
            
        elif data == "get_status":
            self._handle_status_request(chat_id, message_id)
            
        elif data == "get_report":
            self.send_daily_report()

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
        elif data == "update_dashboard":
            self.send_control_panel(chat_id, message_id)

        elif data == "get_trades_info":
            self._handle_trades_info(chat_id, message_id)

        elif data == "get_ai_vision":
            self._handle_ai_vision(chat_id, message_id)

        elif data == "trigger_learning":
            self._handle_neural_learning(chat_id, message_id)

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
            self._save_state()
            self._update_message(chat_id, message_id, f"✅ <b>تم ضبط المخاطرة على {new_risk}%</b>", use_main_kbd=True)
            logging.info(f"Risk Updated: {new_risk}%")

        elif data == "set_lev_menu":
            self._update_message(chat_id, message_id, "🚀 <b>اختر الرافعة المالية المطلوبة:</b>", use_lev_kbd=True)

        elif data.startswith("set_lev_"):
            new_lev = int(data.replace("set_lev_", ""))
            self.leverage = new_lev
            self._save_state()
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

    def _handle_neural_learning(self, chat_id, message_id):
        """Launches the neural retraining script in background."""
        import subprocess
        try:
            # 1. Notify user that training is starting
            self._update_message(chat_id, message_id, "🧠 <b>بدء التعلم العصبي (Neural Adaptation)...</b>\n\nجارٍ دراسة بيانات السوق الحديثة وتحديث الذكاء الاصطناعي في الخلفية. التداول لن يتوقف.")
            
            # 2. Launch trainer in background
            # Use absolute path to venv and trainer
            trainer_script = os.path.join(os.path.dirname(BASE_DIR), "GIA_SIGNAL_PRO", "train.py")
            python_exe = sys.executable
            
            # Start process in background
            subprocess.Popen([python_exe, trainer_script])
            
            def check_training_done():
                # Simple poll: check if LIVE_PRO_PATH was updated in the last 10 mins (conceptual check)
                # For now just send a completion message after a realistic time or via a log check
                # A better way is to have the trainer send a broadcast when done.
                pass

            # Since the trainer now auto-updates the live model, 
            # and inference.py reloads it on next analyze(), it's fully automatic.
            
            # Update message after few seconds to confirm launch
            time.sleep(2)
            msg = (
                "🚀 <b>تم إطلاق عملية التعلم بنجاح!</b>\n"
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                "🤖 النظام الآن يحلل الأنماط السعرية الجديدة.\n"
                "🛡️ بمجرد الانتهاء، سيتم تحديث 'الدماغ' تلقائياً.\n"
                "✅ يمكنك الاستمرار في التداول كالمعتاد."
            )
            self._update_message(chat_id, message_id, msg, use_main_kbd=True)
            
        except Exception as e:
            logging.error(f"Failed to trigger learning: {e}")
            self._send_text(chat_id, f"❌ خطأ تقني في بدء عملية التعلم: {e}")

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

    def _handle_trades_info(self, chat_id, message_id):
        pos_count = len(self.bridge_ref.open_positions) if self.bridge_ref else 0
        details = "📝 <b>تفاصيل الصفقات الحالية:</b>\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        if pos_count > 0:
            for p in self.bridge_ref.open_positions:
                side = "🔵 شراء" if getattr(p.tradeData, 'tradeSide', 1) == 1 else "🔴 بيع"
                raw_vol = getattr(p.tradeData, 'volume', 0) if hasattr(p, 'tradeData') else getattr(p, 'volume', 0)
                lots = raw_vol / 10000.0
                pnl = p.grossProfit / 100.0 if hasattr(p, 'grossProfit') else 0.0
                price = p.entryPrice / 100000.0
                details += f"• {side} | {lots}L | ${price:.2f}\n  💰 الربح: <code>{pnl:+.2f}$</code>\n"
        else:
            details += "<i>لا توجد صفقات مفتوحة حالياً.</i>"
        
        self._update_message(chat_id, message_id, details, use_main_kbd=True)

    def update_market_status(self, signal, confidence, rsi, vol_regime, news_safe):
        """Updates the internal state with LATEST REAL data from the engine."""
        sentiment_map = {
            "BUY": "صعودي (Bullish) 🟢", 
            "SELL": "هبوطي (Bearish) 🔴", 
            "WAIT": "تذبذب / محايد ⚪"
        }
        
        # Derive human-readable statuses
        def _get_bar(val, max_val=100):
            filled = int((val / max_val) * 10) if max_val > 0 else 0
            return "▰" * min(filled, 10) + "▱" * max(0, 10 - filled)

        rsi_val = rsi
        vol_val = min(vol_regime * 50, 100) # Normalize for bar
        conf_val = confidence * 100
        
        rsi_st = "🟢 مثالي" if 40 <= rsi <= 60 else ("🔴 تشبع شرائي" if rsi > 70 else "🔴 تشبع بيعي" if rsi < 30 else "🟡 متوسط")
        vol_st = "🟢 مستقر" if vol_regime < 1.0 else "⚠️ مرتفع"
        news_st = "🟢 آمن" if news_safe else "🔴 خطر أخبار"
        
        self.latest_analysis = {
            "signal": signal,
            "confidence": confidence,
            "rsi_status": rsi_st,
            "rsi_val": rsi_val,
            "rsi_bar": _get_bar(rsi_val),
            "vol_status": vol_st,
            "vol_val": vol_val,
            "vol_bar": _get_bar(vol_val),
            "news_status": news_st,
            "conf_bar": _get_bar(conf_val),
            "sentiment": sentiment_map.get(signal, "غير محدد"),
            "timestamp": datetime.now()
        }

    def _handle_ai_vision(self, chat_id, message_id):
        """Shows REAL internal AI metrics + Account Health from the latest analysis cycle in Arabic."""
        la = self.latest_analysis
        age = (datetime.now() - la['timestamp']).seconds
        freshness = f"({age}ث)" if age < 120 else "⚠️ (قديم)"
        
        # 🏥 Live Account Data from Bridge
        acc_info = "⚠️ Bridge Offline"
        health_color = "🔴"
        if self.bridge_ref:
            try:
                equity = self.bridge_ref.equity
                balance = self.bridge_ref.current_balance
                pnl = equity - balance
                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                acc_info = (
                    f"💳 <b>الرصيد (Balance):</b> <code>${balance:,.2f}</code>\n"
                    f"🏥 <b>السيولة (Equity):</b> <code>${equity:,.2f}</code>\n"
                    f"{pnl_emoji} <b>الربح العائم:</b> <code>{pnl:+.2f}$</code>"
                )
                health_color = "🟢"
            except: 
                acc_info = "⚠️ Error fetching health"

        vision_msg = (
            "🏦 <b>لوحة التداول المؤسسي - GIA Dashboard</b>\n"
            "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"{acc_info}\n"
            f"📡 <b>حالة الاتصال:</b> {health_color} نشط (Active)\n"
            "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            "🧠 <b>رؤية الذكاء الاصطناعي:</b>\n"
            f"🤖 <b>الموديل:</b> <code>{self.active_model_name}</code>\n"
            f"📈 <b>التوقع:</b> <code>{la['sentiment']}</code>\n"
            f"🎯 <b>الثقة:</b> <code>{la['confidence']*100:.1f}%</code> {freshness}\n"
            f"<code>{la['conf_bar']}</code>\n\n"
            "⚖️ <b>المؤشرات الحيوية:</b>\n"
            "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📊 <b>نبض RSI:</b> {la['rsi_status']} ({la['rsi_val']:.1f})\n"
            f"<code>{la['rsi_bar']}</code>\n\n"
            f"🌊 <b>التقلب:</b> {la['vol_status']}\n"
            f"<code>{la['vol_bar']}</code>\n\n"
            f"🗞️ <b>درع الأخبار:</b> {la['news_status']}\n"
            "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            "🔭 <i>بيانات حية محدثة من الخادم مباشرة.</i>"
        )
        self._update_message(chat_id, message_id, vision_msg, use_main_kbd=True)

    def _handle_status_request(self, chat_id, message_id=None):
        conn_status = "🟢 متصل" if (self.bridge_ref and self.bridge_ref.connected) else "🔴 غير متصل"
        trading_status = "🟢 نشط" if self.trading_enabled else "⏸️ متوقف"
        equity = f"${self.bridge_ref.current_equity:.2f}" if (self.bridge_ref and self.bridge_ref.current_equity) else "N/A"

        # Safety Guard Status
        n_safe, n_msg = True, "Active"
        m_safe, m_msg = True, "Stable"
        if self.analyzer_ref and hasattr(self.analyzer_ref, 'strategy'):
            n_safe, n_msg = self.analyzer_ref.strategy.news_guard.check_safety()
            m_safe, m_msg = self.analyzer_ref.strategy.market_guard.check_gap_risk()
        
        guard_status = "🛡️ آمن" if (n_safe and m_safe) else "⚠️ حذر (قيود مفعلة)"
        
        local_now = datetime.now() + timedelta(hours=3)
        pos_count = len(self.bridge_ref.open_positions) if self.bridge_ref else 0
        
        # Details of Open Positions
        pos_details = ""
        if pos_count > 0 and self.bridge_ref:
            for p in self.bridge_ref.open_positions:
                side = "BUY" if p.tradeSide == 1 else "SELL"
                # Safely get volume
                raw_vol = getattr(p, 'volume', 0)
                if raw_vol == 0 and hasattr(p, 'tradeData'):
                    raw_vol = getattr(p.tradeData, 'volume', 0)
                lots = raw_vol / 10000.0
                p_pnl = p.grossProfit / 100.0 if hasattr(p, 'grossProfit') else 0.0
                pos_details += f"  • {side} {lots}L: <code>{p_pnl:+.2f}$</code>\n"
        else:
            pos_details = "  <i>لا يوجد صفقات مفتوحة</i>\n"

        status_msg = (
            f"<b>📊 عرض هيكلية النظام</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"💎 <b>الأصل:</b> <code>الذهب (XAUUSD)</code>\n"
            f"📡 <b>الشبكة:</b> <code>{conn_status}</code>\n"
            f"⚙️ <b>المحرك:</b> <code>{trading_status}</code>\n"
            f"🛡️ <b>درع الحماية:</b> <code>{guard_status}</code>\n"
            f"🤖 <b>المنطق:</b> <code>{self.active_model_name}</code>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🏦 <b>الرصيد الجاري:</b> <code>{equity}</code>\n"
            f"⚖️ <b>المخاطرة:</b> <code>{self.risk}%</code> | 🚀 <b>الرافعة:</b> <code>1:{self.leverage}</code>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🏷️ <b>الصفقات النشطة:</b>\n"
            f"{pos_details}"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🕐 <b>توقيت المزامنة:</b> <code>{local_now.strftime('%H:%M:%S')}</code>"
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
        conn_status = "� متصل" if (self.bridge_ref and self.bridge_ref.connected) else "🔴 منقطع"
        bid = f"{self.bridge_ref.latest_bid:.2f}" if (self.bridge_ref and self.bridge_ref.latest_bid) else "---"
        ask = f"{self.bridge_ref.latest_ask:.2f}" if (self.bridge_ref and self.bridge_ref.latest_ask) else "---"
        equity = f"${self.bridge_ref.current_equity:,.2f}" if (self.bridge_ref and self.bridge_ref.current_equity) else "$0.00"
        
        # Determine safety emoji
        n_safe, m_safe = True, True
        if self.analyzer_ref and hasattr(self.analyzer_ref, 'strategy'):
            n_safe, _ = self.analyzer_ref.strategy.news_guard.check_safety()
            m_safe, _ = self.analyzer_ref.strategy.market_guard.check_gap_risk()
        guard_emoji = "🛡️" if (n_safe and m_safe) else "⚠️"

        dashboard = (
            f"🏛 <b>مركز تحكم GIA المؤسسي 4.0</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"💰 <b>السعر اللحظي:</b> <code>{bid} / {ask}</code>\n"
            f"🏦 <b>إجمالي الرصيد:</b> <code>{equity}</code>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🤖 <b>الموديل النشط:</b> <code>{self.active_model_name}</code>\n"
            f"⚖️ <b>المخاطرة:</b> <code>{self.risk}%</code> | {guard_emoji} <b>الأمان:</b> مفعل\n"
            f"📡 <b>الاتصال:</b> <code>{conn_status}</code> | ⚙️ <b>التداول:</b> {'قيد العمل' if self.trading_enabled else 'متوقف'}\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            "<i>اختر من القائمة التفاعلية أدناه للتحكم:</i>"
        )
        if message_id:
            self._update_message(chat_id, message_id, dashboard, use_main_kbd=True)
        else:
            self._send_text(chat_id, dashboard, include_keyboard=True)

    # 1. Trade Alerts
    def notify_trade_open(self, direction, lots, price, sl, tp, trigger_name="MANUAL"):
        model_emoji = "⚡" if "FLASH" in str(trigger_name).upper() else ("🦁" if "PRO" in str(trigger_name).upper() else "🤖")
        
        emoji = "🔵" if direction == "BUY" else "🔴"
        dir_ar = "شراء (BUY)" if direction == "BUY" else "بيع (SELL)"
        
        # 🧪 Get LIVE Account Health if bridge is available
        account_health = ""
        if self.bridge_ref:
            try:
                equity = self.bridge_ref.equity
                margin_level = getattr(self.bridge_ref, 'margin_level', 999) # Conceptual
                account_health = (
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🏥 <b>حالة الحساب:</b> <code>${equity:,.2f}</code>\n"
                    f"🛡️ <b>نظام الحماية:</b> 🟢 نشط (Active)\n"
                )
            except: pass

        msg = (
            f"📥 <b>تنبيه تنفيذ صفقة جديدة</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"💎 <b>الأصل:</b> الذهب (XAUUSD)\n"
            f"⚖️ <b>نوع الأمر:</b> <b>{dir_ar}</b>\n"
            f"📦 <b>الحجم:</b> <code>{lots} Lots</code>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"💰 <b>سعر الدخول:</b> <code>{price:.2f}</code>\n"
            f"🛑 <b>وقف الخسارة:</b> <code>{sl:.2f}</code>\n"
            f"🎯 <b>هدف الربح:</b> <code>{tp:.2f}</code>\n"
            f"{account_health}"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🤖 <b>المصدر:</b> <code>{trigger_name} {model_emoji}</code>\n"
            f"🕒 <b>بتوقيت مكة:</b> <code>{(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}</code>"
        )
        self.broadcast(msg)

    def notify_trade_close(self, position_id, profit, reason="Closed"):
        # Record trade for daily report
        self.daily_trades.append({'pnl': profit, 'time': datetime.now()})
        self._save_state()
        
        emoji = "💰" if profit >= 0 else "📉"
        status_ar = "✅ ربح (Take Profit)" if profit > 0 else ("🛑 خسارة (Stop Loss)" if profit < 0 else "⚪ تعادل (Break Even)")
        
        # Determine specific Arabic reason
        reason_ar = "إغلاق يدوي"
        if "TP" in str(reason).upper(): reason_ar = "تحقيق الهدف التلقائي (TP)"
        elif "SL" in str(reason).upper(): reason_ar = "ضرب وقف الخسارة (SL)"
        elif "TAILING" in str(reason).upper() or "BE" in str(reason).upper(): reason_ar = "إغلاق على ربح محجوز (Trailing/BE)"
        elif "STOP-OUT" in str(reason).upper(): reason_ar = "إغلاق اضطراري (Stop-out)"

        # 🏥 Account Health Summary
        equity_info = ""
        if self.bridge_ref:
            try:
                equity = self.bridge_ref.equity
                equity_info = f"💰 <b>إجمالي الرصيد الحالي:</b> <code>${equity:,.2f}</code>\n"
            except: pass

        msg = (
            f"📤 <b>تقرير إغلاق صفقة - نهائي</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🆔 <b>رقم العملية:</b> <code>#{position_id}</code>\n"
            f"📊 <b>النتيجة الصافية:</b> <code>{profit:+.2f}$</code> {emoji}\n"
            f"📝 <b>طريقة الإغلاق:</b> {reason_ar}\n"
            f"📉 <b>الحالة:</b> {status_ar}\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"{equity_info}"
            f"🕒 <b>التوقيت المحلي:</b> <code>{(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}</code>"
        )
        self.broadcast(msg)

    # 2. Performance Report
    def send_daily_report(self):
        # Filter trades for today
        now = datetime.now()
        today_trades = [t for t in self.daily_trades if t['time'].day == now.day]
        
        total_profit = sum(t['pnl'] for t in today_trades)
        total_count = len(today_trades)
        winning_trades = [t for t in today_trades if t['pnl'] > 0]
        win_rate = (len(winning_trades) / total_count * 100) if total_count > 0 else 0
        
        status_emoji = "🚀" if total_profit >= 0 else "📉"
        
        msg = (
            f"{status_emoji} <b>تقرير الأداء اليومي | GIA Pro</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"💵 <b>صافي الربح:</b> <code>{total_profit:+.2f}$</code>\n"
            f"🤝 <b>عدد الصفقات:</b> <code>{total_count}</code>\n"
            f"🎯 <b>نسبة النجاح:</b> <code>{win_rate:.1f}%</code>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📅 التاريخ: {now.strftime('%Y-%m-%d')}\n"
            f"🏆 <i>{'يوم تداول ممتاز!' if total_profit > 0 else 'يوم متوازن، ننتظر الفرص القادمة.'}</i>"
        )
        self.broadcast(msg, include_keyboard=True)

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
        # 🟢 PREVENT SPAM: Ignore WAIT signals totally
        if str(direction).upper() == "WAIT":
            return

        # Normalize confidence to percentage
        try:
            conf_val = float(confidence) if confidence is not None else 0.0
        except:
            conf_val = 0.0
            
        conf_pct = conf_val * 100 if conf_val <= 1.0 else conf_val

        # Skip low-quality signals
        if conf_pct < self.min_signal_conf_pct:
            logging.info(f"Signal alert skipped (low confidence {conf_pct:.1f}%).")
            return

        now_ts = time.time()
        # Throttle duplicate alerts (same direction within cooldown)
        # We allow re-alert if confidence improved significantly (>5%)
        last_dir = self.last_signal_alert.get("direction")
        last_conf = self.last_signal_alert.get("confidence", 0.0)
        
        if (
            direction == last_dir and
            (now_ts - self.last_signal_alert.get("ts", 0)) < self.signal_cooldown_sec and
            (conf_pct - last_conf) < 5 # Only alert again if confidence increased by 5%+
        ):
            logging.info("Signal alert suppressed (duplicate within cooldown).")
            return

        emoji = "📡"
        msg = (
            f"{emoji} <b>GIA: كشف إشارة قوية</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"⚖️ <b>الاتجاه المتوقع:</b> {direction}\n"
            f"🧠 <b>التحليل:</b> {analysis}\n"
            f"📊 <b>مستوى الثقة:</b> {conf_pct:.1f}%\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"⏳ <i>سيتم التنفيذ تلقائياً بعد الفحص النهائي...</i>"
        )
        self.broadcast(msg)
        self.last_signal_alert = {"ts": now_ts, "direction": direction, "confidence": conf_pct}

# Global instance
telegram_service = TelegramService()
