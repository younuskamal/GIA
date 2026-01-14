
import sys
import os
import time

# Add base path
sys.path.append("/var/www/GIA")

from backend.connectors.ctrader_bridge import CTraderBridge

def check():
    print("Connecting to cTrader to check status...")
    bridge = CTraderBridge()
    if not bridge.connect():
        print("Failed to connect!")
        return
    
    # Wait for reconcile
    time.sleep(5)
    
    print(f"--- GIA STATUS REPORT ---")
    print(f"Account Balance: ${bridge.current_balance}")
    print(f"Active Positions: {len(bridge.open_positions)}")
    
    for p in bridge.open_positions:
        print(f"--- Position Details (ID: {p.positionId}) ---")
        # Try to print all attributes
        for attr in dir(p):
            if not attr.startswith('_') and not callable(getattr(p, attr)):
                print(f"  {attr}: {getattr(p, attr)}")
        
        # Check tradeData
        td = getattr(p, 'tradeData', None)
        if td:
             print(f"  --- TradeData ---")
             for attr in dir(td):
                 if not attr.startswith('_') and not callable(getattr(td, attr)):
                     print(f"    {attr}: {getattr(td, attr)}")
        
        # PnL Check
        gp = getattr(p, 'grossProfit', 'N/A')
        print(f"  Gross Profit (Raw): {gp}")
        if isinstance(gp, (int, float)):
            print(f"  Gross Profit ($): {gp/100.0:.2f}")

    bridge.shutdown()

if __name__ == "__main__":
    check()
