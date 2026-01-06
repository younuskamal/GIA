
"""
GIA cTrader Direct OpenAPI Bridge
Enables near-zero latency execution via Protobuf/WebSocket.
"""
import logging
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
import pandas as pd
from twisted.internet import reactor
from ctrader_open_api import Client, Protobuf, Auth, EndPoints, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq, 
    ProtoOATraderReq, ProtoOAReconcileReq, ProtoOANewOrderReq,
    ProtoOASymbolsListReq, ProtoOAErrorRes, ProtoOASymbolByIdReq,
    ProtoOAAmendPositionSLTPReq, ProtoOAGetTrendbarsReq
)
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage

# Path Fix
BASE_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_BACKEND not in sys.path:
    sys.path.append(BASE_BACKEND)

from config.secrets import (
    CTRADER_CLIENT_ID, CTRADER_SECRET, CTRADER_ACCESS_TOKEN, 
    CTRADER_ACCOUNT_ID, CTRADER_ENV
)
from services.telegram_service import telegram_service

# Setup Logger
logger = logging.getLogger("cTraderBridge")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(os.path.join(BASE_BACKEND, "..", "active_trading.log"))
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

# Institutional Constants
ASSET = "XAUUSD"

class CTraderBridge:
    def __init__(self, active_strategy_handler=None):
        self.client_id = CTRADER_CLIENT_ID
        self.client_secret = CTRADER_SECRET
        self.access_token = CTRADER_ACCESS_TOKEN
        self.account_id = int(CTRADER_ACCOUNT_ID)
        self.strategy = active_strategy_handler
        
        self.client = None
        self.connected = False
        self.authorized = False
        self.current_equity = 0.0
        self.open_positions = []
        self.symbol_id = None
        self.digits = 2
        self.pip_position = 2
        self.min_volume = 100
        self.step_volume = 100
        self.latest_bid = None
        self.latest_ask = None
        self.pending_sl_tp = {} # Track pending SL/TP by clientMsgId or logic
        self.data_cache = {} # TF -> Candles
        self.last_notified_connected = False
        self.position_state = {} # PosID -> live tracking for BE/Trailing
        self.last_entry_atr = None
        self.last_entry_tf = None
        
        # 🦁 Project-Centric Path Mapping
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.abspath(os.path.join(base_dir, "..", "..", 'data'))
            
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Populate IDs
        Protobuf.populate()
        self._msg_counter = 0
        
        # Connection status events
        self.ready_event = threading.Event()
        self.auth_stage = 0 # 1: App, 2: Acc, 3: Symbols, 4: Ready

    def _on_connected(self, client):
        print("📡 cTrader API: Connected to Server. Handshaking...")
        self.connected = True
        
        # SSL Handshake delay
        def delayed_auth():
            time.sleep(1)
            print("🔐 cTrader API: Authenticating Application...")
            # Use the native send which handles mapping and wrapping
            self.client.send("ProtoOAApplicationAuthReq", 
                             clientId=self.client_id, 
                             clientSecret=self.client_secret)
            
        threading.Thread(target=delayed_auth, daemon=True).start()

    def _on_disconnected(self, client, reason):
        print(f"🔌 cTrader API: Disconnected. Reason: {reason}")
        self.connected = False
        self.authorized = False
        self.auth_stage = 0
        self.ready_event.clear()
        
        # Self-healing logic handled by the main loop usually, 
        # but the client might try to reconnect itself.
        if self.last_notified_connected:
            telegram_service.notify_connection_status(False)
            self.last_notified_connected = False

    def _on_message(self, client, message):
        # In this library version, 'message' is often the actual parsed payload 
        # because the internal 'received' call extracts it.
        msg_type = message.payloadType
        
        # App Auth Response (2101)
        if msg_type == Protobuf._names["ProtoOAApplicationAuthRes"]:
            print("🔐 cTrader API: Application Authorized. Authenticating Account...")
            self.client.send("ProtoOAAccountAuthReq", 
                             ctidTraderAccountId=self.account_id, 
                             accessToken=self.access_token)
            
        # Account Auth Response (2103)
        elif msg_type == Protobuf._names["ProtoOAAccountAuthRes"]:
            print(f"✅ cTrader API: Account {self.account_id} Authorized.")
            logger.info(f"AUTH: Account {self.account_id} Authorized.")
            self.authorized = True
            self.auth_stage = 2
            # Step 3: Fetch Symbols to find XAUUSD
            # Using the native send to avoid manual proto issues
            self.client.send("ProtoOASymbolsListReq", 
                             ctidTraderAccountId=self.account_id,
                             includeArchivedSymbols=False)
            print("🔍 cTrader API: Discovering symbols...")

        # Symbols List Response (2115)
        elif msg_type == Protobuf._names["ProtoOASymbolsListRes"]:
            actual_payload = Protobuf.extract(message)
            for s in actual_payload.symbol:
                if s.symbolName == "XAUUSD":
                    self.symbol_id = s.symbolId
                    print(f"🎯 cTrader API: XAUUSD Map Found (ID: {self.symbol_id})")
                    break
            
            if self.symbol_id:
                self.auth_stage = 3
                # Step 4: Get Full Symbol Details
                self.client.send("ProtoOASymbolByIdReq", 
                                 ctidTraderAccountId=self.account_id,
                                 symbolId=[self.symbol_id])
                print(f"🔬 cTrader API: Fetching details for Symbol {self.symbol_id}...")
            else:
                print("⚠️ Warning: XAUUSD not found in subscription list.")

        # Symbol By ID Response (2117)
        elif msg_type == Protobuf._names["ProtoOASymbolByIdRes"]:
            actual_payload = Protobuf.extract(message)
            if actual_payload.symbol:
                s = actual_payload.symbol[0]
                self.digits = s.digits
                self.pip_position = s.pipPosition
                self.min_volume = s.minVolume
                self.step_volume = s.stepVolume
                # Log all fields to debug
                print(f"📊 cTrader API Symbol: Digits={s.digits}, PipPos={s.pipPosition}, MinVol={s.minVolume}")
                self.auth_stage = 4
                
                # Step 5: Subscribe to Live Quotes for accurate SL/TP calculation
                self.client.send("ProtoOASubscribeSpotsReq", 
                                 ctidTraderAccountId=self.account_id,
                                 symbolId=[self.symbol_id])
                print(f"📡 cTrader API: Subscribed to Live Quotes for Symbol {self.symbol_id}")
                self._update_account_info()

        # Trader Response (Equity/Balance) (2122)
        elif msg_type == Protobuf._names["ProtoOATraderRes"]:
            try:
                actual_payload = Protobuf.extract(message)
                if hasattr(actual_payload, 'trader'):
                    self.current_equity = actual_payload.trader.balance / 100.0
                    # Silenced for clean Dashboard UI
                    # print(f"💰 Account Balance Updated: ${self.current_equity}")
                    if self.auth_stage == 4:
                        self.auth_stage = 5
                        self.ready_event.set()
                        if not self.last_notified_connected:
                            telegram_service.notify_connection_status(True)
                            self.last_notified_connected = True
            except: pass

        # Error Response
        elif msg_type == Protobuf._names["ProtoOAErrorRes"]:
            payload = Protobuf.extract(message)
            print(f"❌ cTrader API ERROR: {payload.errorCode} - {payload.description}")

        # Spot (Price) Event (2131)
        elif msg_type == Protobuf._names["ProtoOASpotEvent"]:
            payload = Protobuf.extract(message)
            if payload.symbolId == self.symbol_id:
                if hasattr(payload, 'bid'): 
                    new_bid = payload.bid / 100000.0
                    if self.latest_bid is None:
                        logger.info(f"First Ticket Received: Bid={new_bid}")
                    self.latest_bid = new_bid
                if hasattr(payload, 'ask'): 
                    new_ask = payload.ask / 100000.0
                    if self.latest_ask is None:
                        logger.info(f"First Ticket Received: Ask={new_ask}")
                    self.latest_ask = new_ask

        # Reconcile Response (Positions) (2125)
        elif msg_type == Protobuf._names["ProtoOAReconcileRes"]:
            try:
                if hasattr(message, 'position'):
                    self.open_positions = message.position
                else:
                    actual_payload = Protobuf.extract(message)
                    self.open_positions = actual_payload.position
                # Sync state for BE/Trailing when reconcile arrives
                for p in self.open_positions:
                    self._record_position(p)
            except:
                pass
            
        # Execution Event (2126)
        elif msg_type == Protobuf._names["ProtoOAExecutionEvent"]:
            payload = Protobuf.extract(message)
            self._update_account_info()
            
            exec_type = getattr(payload, 'executionType', None)
            if exec_type == 1: # ORDER_ACCEPTED
                print("📝 cTrader API: Order Accepted.")
                logger.info("EXEC: Order Accepted by cTrader.")
            elif exec_type == 3: # ORDER_FILLED
                # Log actual filled position details correctly
                pos = getattr(payload, 'position', None)
                sl_view = (pos.stopLoss / 100000.0) if (pos and pos.stopLoss) else 'N/A'
                tp_view = (pos.takeProfit / 100000.0) if (pos and pos.takeProfit) else 'N/A'
                
                if pos:
                    pos_id = pos.positionId
                    print(f"✨ cTrader API: Order Filled! (PosID: {pos_id})")
                    
                    # Check if we have pending SL/TP for this execution
                    # We use a simple logic: if we just opened a position and have pending SL/TP, apply it.
                    if self.pending_sl_tp:
                        sl = self.pending_sl_tp.get('sl')
                        tp = self.pending_sl_tp.get('tp')
                        if sl or tp:
                            # Use raw float prices rounded to symbol digits.
                            final_sl = round(sl, self.digits) if sl else None
                            final_tp = round(tp, self.digits) if tp else None
                            
                            # Safety Check: For BUY, SL must be < current Bid. For SELL, SL must be > current Ask.
                            direction = self.pending_sl_tp.get('direction')
                            if self.latest_bid and self.latest_ask and direction:
                                if direction == "BUY" and final_sl and final_sl >= self.latest_bid:
                                    final_sl = round(self.latest_bid - 0.50, self.digits) # Force below
                                elif direction == "SELL" and final_sl and final_sl <= self.latest_ask:
                                    final_sl = round(self.latest_ask + 0.50, self.digits) # Force above

                            print(f"🛡️ cTrader API: Protecting Pos {pos_id} | SL: {final_sl}, TP: {final_tp}")
                            
                            self.client.send("ProtoOAAmendPositionSLTPReq",
                                             ctidTraderAccountId=self.account_id,
                                             positionId=pos_id,
                                             stopLoss=final_sl,
                                             takeProfit=final_tp)
                            
                            # Initial notification will happen when SL/TP are confirmed by server
                        self.pending_sl_tp = {} 
                
                # Report to Telegram with actual position details
                if pos:
                    trade_data = getattr(pos, 'tradeData', None)
                    direction = "BUY" if trade_data and trade_data.tradeSide == 1 else "SELL"
                    raw_vol = getattr(trade_data, 'volume', 0) if trade_data else getattr(pos, 'volume', 0)
                    lots = raw_vol / 10000.0
                    entry_price = getattr(pos, 'entryPrice', 0)
                    if entry_price == 0 and hasattr(pos, 'price'): entry_price = pos.price
                    entry_price /= 100000.0
                    
                    # If we have confirmed SL/TP from the Fill, use them. 
                    # Otherwise use our pending ones if we just sent them.
                    sl_val = getattr(pos, 'stopLoss', 0) / 100000.0
                    tp_val = getattr(pos, 'takeProfit', 0) / 100000.0
                    
                    if sl_val == 0 and 'last_sent_sl' in globals().get('__dict__', {}): # conceptual
                        pass # complicated to track across threads without more state
                    
                    trig_name = getattr(self, 'last_trigger_name', 'AUTO')
                    # Record for BE/Trailing with ATR/TF hint from pending_sl_tp
                    self._record_position(
                        pos,
                        direction=direction,
                        atr=self.pending_sl_tp.get('atr', getattr(self, 'last_entry_atr', None)),
                        tf=self.pending_sl_tp.get('tf', getattr(self, 'last_entry_tf', None))
                    )
                    telegram_service.notify_trade_open(direction, lots, entry_price, sl_val, tp_val, trigger_name=trig_name)
                
                logger.info(f"EXEC: Order Filled. Position ID: {pos_id if pos else 'N/A'}")
            
            elif exec_type in [4, 5, 6]: # POSITION_CLOSED or similar
                pos = getattr(payload, 'position', None)
                if pos:
                    pnl = (payload.grossProfit / 100.0) if hasattr(payload, 'grossProfit') else 0
                    telegram_service.notify_trade_close(pos.positionId, pnl, reason="Closed/Stop-out")
            
        # Order Error Event (2132)
        elif msg_type == Protobuf._names["ProtoOAOrderErrorEvent"]:
            payload = Protobuf.extract(message)
            err_msg = f"ORDER ERROR: {payload.errorCode} - {payload.description}"
            print(f"❌ {err_msg}")
            logger.error(err_msg)
            
        # Common Error Response (2142)
        elif msg_type == Protobuf._names["ProtoOAErrorRes"]:
            payload = Protobuf.extract(message)
            err_msg = f"GENERAL API ERROR: {payload.errorCode} - {payload.description}"
            print(f"❌ {err_msg}")
            logger.error(err_msg)

        # Reconcile Response (Positions) (2125)

        # Trendbars Response (2138)
        elif msg_type == Protobuf._names["ProtoOAGetTrendbarsRes"]:
            payload = Protobuf.extract(message)
            tf_map = {1: "M1", 7: "M15", 8: "M30", 9: "H1"}
            period = payload.period
            tf_label = tf_map.get(period, "UNKNOWN")
            
            # Fallback for different library versions
            raw_bars = getattr(payload, 'trendbar', getattr(payload, 'trendbars', []))
            
            bars = []
            for bar in raw_bars:
                # Direct extraction with defaults to avoid errors
                ts_min = getattr(bar, 'utcTimestampInMinutes', 0)
                l_raw = getattr(bar, 'low', 0)
                o_raw = l_raw + getattr(bar, 'deltaOpen', 0)
                h_raw = l_raw + getattr(bar, 'deltaHigh', 0)
                c_raw = l_raw + getattr(bar, 'deltaClose', 0)
                v = getattr(bar, 'volume', 0)
                
                if ts_min == 0: continue
                
                ts_ms = ts_min * 60 * 1000
                o, h, l, c = [p / 100000.0 for p in [o_raw, h_raw, l_raw, c_raw]]
                
                # Force UTC for internal engine consistency
                # Convert to UTC+3 (User's timezone)
                dt = datetime.fromtimestamp(ts_ms/1000.0) + timedelta(hours=3)
                dt_str = dt.strftime('%Y-%m-%d %H:%M') + ":00" # Force minute alignment
                bars.append(f"{dt_str},{o:.2f},{h:.2f},{l:.2f},{c:.2f},{v}")
                
            if bars:
                last_ts_str = bars[-1].split(',')[0]
                print(f"   🔍 DEBUG: Received {len(bars)} {tf_label} bars. Last: {last_ts_str}")
            
            if tf_label != "UNKNOWN":
                self.data_cache[tf_label] = bars
                self._save_to_csv(tf_label, bars)
                print(f"💾 cTrader API: Synced {len(bars)} candles for {tf_label} to disk.")

    def _save_to_csv(self, tf, bars):
        """Merges new bars with existing CSV data to preserve history."""
        fpath = os.path.join(self.data_dir, f"{ASSET}_{tf}.csv")
        try:
            # 1. Load existing data if available
            existing_df = pd.DataFrame()
            if os.path.exists(fpath):
                try:
                    existing_df = pd.read_csv(fpath)
                except: pass
            
            # 2. Parse new bars
            new_data = []
            for b in bars:
                parts = b.split(',')
                new_data.append({
                    "Time": parts[0],
                    "Open": float(parts[1]),
                    "High": float(parts[2]),
                    "Low": float(parts[3]),
                    "Close": float(parts[4]),
                    "Volume": int(parts[5])
                })
            new_df = pd.DataFrame(new_data)
            
            # 3. Merge and deduplicate
            if not existing_df.empty:
                df = pd.concat([existing_df, new_df]).drop_duplicates(subset=['Time'])
            else:
                df = new_df
            
            # 4. Sort and Save
            df = df.sort_values('Time').tail(20000) # Keep a healthy 20k bars buffer
            df.to_csv(fpath, index=False)
        except Exception as e:
            logger.error(f"Sync Merge Error for {tf}: {str(e)}")

    def _update_account_info(self):
        """Requests latest equity and position state."""
        if not self.authorized: return
        self.client.send("ProtoOATraderReq", ctidTraderAccountId=self.account_id)
        self.client.send("ProtoOAReconcileReq", ctidTraderAccountId=self.account_id)
        
    def fetch_live_data(self):
        """Fetches latest Trendbars (candles) for all TFs."""
        if not self.authorized or not self.symbol_id: return
        
        print("\n⏳ Syncing Market Data...")
        
        # Broker Server might be ahead (UTC+3), so we request up to "future" (24h) to catch latest bars.
        # But we must calculate START time relative to REAL CURRENT TIME to get actual history depth.
        real_now_ms = int(time.time() * 1000)
        future_now_ms = real_now_ms + (24 * 3600 * 1000)
        
        # M1=1h(min), M15=7, M30=8, H1=9
        # Need ~1500 bars for indicators
        ranges = {
            1: 1500 * 60 * 1000,          # M1: ~25 Hours
            7: 1500 * 15 * 60 * 1000,     # M15: ~15 Days
            8: 1000 * 30 * 60 * 1000,     # M30: ~20 Days
            9: 1000 * 60 * 60 * 1000      # H1: ~41 Days
        }
        
        for p, r in ranges.items():
            start_ms = real_now_ms - r
            self.client.send("ProtoOAGetTrendbarsReq",
                             ctidTraderAccountId=self.account_id,
                             symbolId=self.symbol_id,
                             period=p,
                             fromTimestamp=start_ms,
                             toTimestamp=future_now_ms)
            time.sleep(0.25) # Prevent request flooding

    def connect(self):
        """Initiates the Twisted Reactor and connects the client."""
        host = EndPoints.PROTOBUF_LIVE_HOST if CTRADER_ENV == "LIVE" else EndPoints.PROTOBUF_DEMO_HOST
        port = 5035
        
        self.client = Client(host, port, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)
        
        def run_reactor():
            self.client.startService()
            if not reactor.running:
                reactor.run(installSignalHandlers=False)
            
        self.reactor_thread = threading.Thread(target=run_reactor, daemon=True)
        self.reactor_thread.start()
        
        print("⏳ Waiting for cTrader API Authorization...")
        success = self.ready_event.wait(timeout=25)
        if not success:
            print("❌ FAIL: cTrader API Connection/Auth Timeout.")
            return False
            
        return True

    def get_open_position_count(self) -> int:
        return len(self.open_positions)

    def send_market_order(self, direction, lots, sl_pips=None, tp_pips=None, trigger_name="AUTO"):
        """Sends a Market Order and queues SL/TP for amendment after fill."""
        self.last_trigger_name = trigger_name
        if not self.authorized or not self.symbol_id:
            logger.error("Order Blocked: Bridge not ready.")
            return False
            
        # Volume calculation: Standard cTrader API usually expects units.
        # XAUUSD 1 Lot = 100 oz. Volume is usually in units (oz) or cents?
        # If API expects units: 1 Lot = 100 units.
        # If API expects cents: 1 Lot = 10000 cents.
        # Let's try standard 100,000 multiplier first as it is most common for FX/Commds in ProtoOA.
        # If volume step is 1.00 (unit), then int(lots * 100000) is safe.
        volume = int(lots * 100000)
        
        logger.info(f"🚀 Preparing Order: {direction} {lots} Lots -> Volume {volume}")
        trade_side = 1 if direction == "BUY" else 2
        
        # Queue SL/TP for the amendment that happens in _on_message (ORDER_FILLED)
        price = self.latest_ask if direction == "BUY" else self.latest_bid
        if price and (sl_pips or tp_pips):
            sl = (price - (sl_pips/10.0)) if direction == "BUY" else (price + (sl_pips/10.0))
            tp = (price + (tp_pips/10.0)) if direction == "BUY" else (price - (tp_pips/10.0))
            # Carry ATR/TF hints for BE/Trailing state seeding
            self.pending_sl_tp = {
                'sl': sl,
                'tp': tp,
                'direction': direction,
                'atr': getattr(self, 'last_entry_atr', None),
                'tf': getattr(self, 'last_entry_tf', None)
            }
        
        print(f"🚀 [API] Transmitting {direction} {lots} Lots (Base Order)...")
        
        self.client.send("ProtoOANewOrderReq",
                         ctidTraderAccountId=self.account_id,
                         symbolId=self.symbol_id,
                         orderType=1,
                         tradeSide=trade_side,
                         volume=volume)
        return True

    # --- BE / Trailing Helpers ---
    def _record_position(self, pos, direction=None, atr=None, tf=None):
        """Populate internal state for BE/Trailing tracking."""
        try:
            pos_id = getattr(pos, 'positionId', None)
            if pos_id is None: return
            trade_data = getattr(pos, 'tradeData', None)
            if direction is None and trade_data:
                direction = "BUY" if getattr(trade_data, 'tradeSide', 0) == 1 else "SELL"
            volume_raw = getattr(trade_data, 'volume', getattr(pos, 'volume', 0))
            lots = volume_raw / 10000.0 if volume_raw else 0
            entry_price = getattr(pos, 'entryPrice', getattr(pos, 'price', 0)) / 100000.0
            sl_val = getattr(pos, 'stopLoss', 0) / 100000.0 if getattr(pos, 'stopLoss', 0) else None
            tp_val = getattr(pos, 'takeProfit', 0) / 100000.0 if getattr(pos, 'takeProfit', 0) else None

            st = self.position_state.get(pos_id, {})
            st.update({
                'direction': direction,
                'entry_price': entry_price,
                'sl': sl_val,
                'tp': tp_val,
                'lots': lots,
                'atr': atr or st.get('atr'),
                'tf': tf or st.get('tf'),
                'mfe': st.get('mfe', 0.0)
            })
            # Initialize extremes
            if direction == "BUY":
                st['high_water'] = max(st.get('high_water', entry_price), entry_price)
            elif direction == "SELL":
                st['low_water'] = min(st.get('low_water', entry_price), entry_price)
            # Detect if SL already at/above BE
            if st.get('sl') is not None:
                if direction == "BUY" and st['sl'] >= st['entry_price']:
                    st['be_active'] = True
                elif direction == "SELL" and st['sl'] <= st['entry_price']:
                    st['be_active'] = True
            st.setdefault('be_active', False)
            self.position_state[pos_id] = st
        except Exception as e:
            logger.error(f"State record error: {e}")

    def _amend_sl_tp(self, pos_id, new_sl=None, new_tp=None):
        """Safe SL/TP amend helper."""
        if not self.authorized or not self.symbol_id: 
            return False
        if new_sl is None and new_tp is None:
            return False
        params = {
            "ctidTraderAccountId": self.account_id,
            "positionId": pos_id
        }
        if new_sl is not None:
            params["stopLoss"] = round(new_sl, self.digits)
        if new_tp is not None:
            params["takeProfit"] = round(new_tp, self.digits)
        try:
            self.client.send("ProtoOAAmendPositionSLTPReq", **params)
            return True
        except Exception as e:
            logger.error(f"Trailing amend failed for {pos_id}: {e}")
            return False

    def trail_positions(self, atr_lookup=None):
        """Apply BE + ATR-based trailing to live positions."""
        if not self.open_positions:
            return
        for pos in list(self.open_positions):
            pos_id = getattr(pos, 'positionId', None)
            if pos_id is None:
                continue
            # Ensure state exists
            self._record_position(pos)
            st = self.position_state.get(pos_id, {})
            direction = st.get('direction')
            if direction not in ("BUY", "SELL"):
                continue
            price = self.latest_bid if direction == "BUY" else self.latest_ask
            if not price:
                continue
            # Choose ATR: entry ATR -> TF cache -> fallback
            atr_val = st.get('atr')
            if (atr_val is None or atr_val <= 0) and atr_lookup:
                tf = st.get('tf')
                if tf and atr_lookup.get(tf):
                    atr_val = atr_lookup.get(tf)
                elif atr_lookup.get("M15"):
                    atr_val = atr_lookup.get("M15")
            if atr_val is None or atr_val <= 0:
                continue

            entry = st.get('entry_price', price)
            current_sl = st.get('sl')

            if direction == "BUY":
                st['high_water'] = max(st.get('high_water', entry), price)
                delta = st['high_water'] - entry
            else:
                st['low_water'] = min(st.get('low_water', entry), price)
                delta = entry - st['low_water']

            st['mfe'] = max(st.get('mfe', 0.0), delta)

            # Break-even activation
            if not st.get('be_active', False) and st['mfe'] > (atr_val * 1.0):
                comm_buffer = 0.03
                if direction == "BUY":
                    new_sl = entry + comm_buffer
                    # Ensure SL below current bid to avoid immediate stop
                    new_sl = min(new_sl, price - 0.05)
                    if current_sl is None or new_sl > current_sl:
                        if self._amend_sl_tp(pos_id, new_sl=new_sl):
                            st['sl'] = new_sl
                            st['be_active'] = True
                            logger.info(f"BE Armed (BUY) pos {pos_id}: SL->{new_sl}")
                else:
                    new_sl = entry - comm_buffer
                    new_sl = max(new_sl, price + 0.05)
                    if current_sl is None or new_sl < current_sl:
                        if self._amend_sl_tp(pos_id, new_sl=new_sl):
                            st['sl'] = new_sl
                            st['be_active'] = True
                            logger.info(f"BE Armed (SELL) pos {pos_id}: SL->{new_sl}")

            # Trailing after BE
            if st.get('be_active', False):
                trail_dist = atr_val * 2.0
                if direction == "BUY":
                    candidate = st['high_water'] - trail_dist
                    candidate = min(candidate, price - 0.05)
                    if current_sl is None or candidate > current_sl:
                        if self._amend_sl_tp(pos_id, new_sl=candidate):
                            st['sl'] = candidate
                            logger.info(f"Trail SL (BUY) pos {pos_id}: SL->{candidate}")
                else:
                    candidate = st['low_water'] + trail_dist
                    candidate = max(candidate, price + 0.05)
                    if current_sl is None or candidate < current_sl:
                        if self._amend_sl_tp(pos_id, new_sl=candidate):
                            st['sl'] = candidate
                            logger.info(f"Trail SL (SELL) pos {pos_id}: SL->{candidate}")

            self.position_state[pos_id] = st

    def shutdown(self):
        if self.client:
            self.client.stopService()
        if reactor.running:
            reactor.stop()
        print("🔌 Bridge Disconnected.")
