
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
from datetime import datetime
from twisted.internet import reactor
from ctrader_open_api import Client, Protobuf, Auth, EndPoints, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq, 
    ProtoOATraderReq, ProtoOAReconcileReq, ProtoOANewOrderReq,
    ProtoOASymbolsListReq, ProtoOAErrorRes, ProtoOASymbolByIdReq,
    ProtoOAAmendPositionSLTPReq
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

# Setup Logger
logger = logging.getLogger("cTraderBridge")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(os.path.join(BASE_BACKEND, "..", "active_trading.log"))
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

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
        self.ready_event.clear()

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
                    print(f"💰 Account Balance Updated: ${self.current_equity}")
                    if self.auth_stage == 4:
                        self.auth_stage = 5
                        self.ready_event.set()
            except: pass

        # Error Response
        elif msg_type == Protobuf._names["ProtoOAErrorRes"]:
            payload = Protobuf.extract(message)
            print(f"❌ cTrader API ERROR: {payload.errorCode} - {payload.description}")

        # Spot (Price) Event (2131)
        elif msg_type == Protobuf._names["ProtoOASpotEvent"]:
            payload = Protobuf.extract(message)
            if payload.symbolId == self.symbol_id:
                # cTrader OpenAPI standard: prices are always shifted by 10^5
                if hasattr(payload, 'bid'): self.latest_bid = payload.bid / 100000.0
                if hasattr(payload, 'ask'): self.latest_ask = payload.ask / 100000.0

        # Reconcile Response (Positions) (2125)
        elif msg_type == Protobuf._names["ProtoOAReconcileRes"]:
            try:
                if hasattr(message, 'position'):
                    self.open_positions = message.position
                else:
                    actual_payload = Protobuf.extract(message)
                    self.open_positions = actual_payload.position
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
                        self.pending_sl_tp = {} 
                
                logger.info(f"EXEC: Order Filled. Position ID: {pos_id if pos else 'N/A'}")
            
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

    def _update_account_info(self):
        """Requests latest equity and position state."""
        if not self.authorized: return
        self.client.send("ProtoOATraderReq", ctidTraderAccountId=self.account_id)
        self.client.send("ProtoOAReconcileReq", ctidTraderAccountId=self.account_id)

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

    def send_market_order(self, direction, lots, sl_pips=None, tp_pips=None):
        """Sends a Market Order and queues SL/TP for immediate amendment."""
        if not self.authorized or not self.symbol_id:
            logger.error("Order Blocked: Bridge not ready.")
            return False
            
        volume = int(lots * 100 * 100)
        trade_side = 1 if direction == "BUY" else 2
        
        # Calculate Absolute SL/TP for the amendment
        price = self.latest_ask if direction == "BUY" else self.latest_bid
        if price and (sl_pips or tp_pips):
            sl = (price - (sl_pips/10.0)) if direction == "BUY" else (price + (sl_pips/10.0))
            tp = (price + (tp_pips/10.0)) if direction == "BUY" else (price - (tp_pips/10.0))
            self.pending_sl_tp = {'sl': sl, 'tp': tp, 'direction': direction}
        
        print(f"� [API] Transmitting {direction} {lots} Lots (Base Order)...")
        self.client.send("ProtoOANewOrderReq",
                         ctidTraderAccountId=self.account_id,
                         symbolId=self.symbol_id,
                         orderType=1,
                         tradeSide=trade_side,
                         volume=volume)
        return True

    def shutdown(self):
        if self.client:
            self.client.stopService()
        if reactor.running:
            reactor.stop()
        print("🔌 Bridge Disconnected.")
