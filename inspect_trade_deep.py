
import sys
import os
import time

# Add base path
sys.path.append("/var/www/GIA")

from backend.connectors.ctrader_bridge import CTraderBridge

def check_deep():
    print("Connecting to cTrader for Deep Inspection...")
    bridge = CTraderBridge()
    if not bridge.connect():
        print("Failed to connect!")
        return
    
    time.sleep(3)
    
    print("\n" + "="*50)
    print("🦁 GIA LIVE TRADE INSPECTION")
    print("="*50)
    
    if not bridge.open_positions:
        print("No open positions found.")
    else:
        for p in bridge.open_positions:
            print(f"POSITION ID: {p.positionId}")
            print(f"Symbol: {p.symbolId}")
            print(f"Entry Price: {p.entryPrice}")
            print(f"Stop Loss (RAW from Server): {p.stopLoss}")
            print(f"Take Profit (RAW from Server): {p.takeProfit}")
            
            # Detect scaling based on raw values
            def format_p(v):
                if v is None or v == 0: return "NOT SET"
                if v > 100000: return f"{v/100000.0} (SCALED 10^5)"
                return f"{v} (LITERAL)"
            
            print(f"Calculated SL: {format_p(p.stopLoss)}")
            print(f"Calculated TP: {format_p(p.takeProfit)}")
            print("-" * 30)

    bridge.shutdown()

if __name__ == "__main__":
    check_deep()
