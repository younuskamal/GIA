
"""
Broker Simulation Module
Simulates realistic spread, commission, and slippage behavior.
"""
from dataclasses import dataclass
import random

@dataclass
class BrokerProfile:
    name: str
    spread_min: float
    spread_max: float
    commission_per_lot: float
    slippage_probability: float = 0.2
    slippage_max: float = 0.1 # Max slippage in dollars

class BrokerSimulator:
    PROFILES = {
        "FIPER": BrokerProfile("FIPER cTrader", 0.10, 0.25, 5.0, slippage_probability=0.05, slippage_max=0.02),
        "ICMARKETS": BrokerProfile("IC MARKETS (Raw)", 0.05, 0.20, 7.0, slippage_probability=0.10, slippage_max=0.03),
        "PEPPERSTONE": BrokerProfile("PEPPERSTONE (Razor)", 0.05, 0.25, 7.0, slippage_probability=0.10, slippage_max=0.03),
        "TOPSTEP": BrokerProfile("TOPSTEP (Prop)", 0.30, 0.60, 6.0, slippage_probability=0.20, slippage_max=0.10),
        "VANTAGE": BrokerProfile("VANTAGE (Inst)", 0.15, 0.35, 6.0, slippage_probability=0.08, slippage_max=0.04),
        "TICKMILL": BrokerProfile("TICKMILL (Raw)", 0.10, 0.30, 4.0, slippage_probability=0.12, slippage_max=0.05),
        "XM": BrokerProfile("XM (Ultra-Low)", 0.18, 0.35, 0.0, slippage_probability=0.12, slippage_max=0.04),
        "DOOMSDAY": BrokerProfile("THE DOOMSDAY MACHINE", 2.50, 5.00, 15.0, slippage_probability=0.80, slippage_max=0.50)
    }

    def __init__(self, profile_name="FIPER"):
        self.profile = self.PROFILES.get(profile_name.upper(), self.PROFILES["FIPER"])

    def get_dynamic_spread(self):
        """Returns a randomized spread value within the broker's range."""
        return random.uniform(self.profile.spread_min, self.profile.spread_max)

    def calculate_cost(self, lots: float, current_price: float, trade_type: str):
        """
        Calculates total cost of entry including spread, commission and potential slippage.
        Returns:
            - cost_value: Total $ cost (negative impact on PnL usually, but here returned as positive cost)
            - execution_price: The actual filled price
        """
        spread = self.get_dynamic_spread()
        comm = self.profile.commission_per_lot * lots
        
        # Slippage simulation
        slippage = 0.0
        if random.random() < self.profile.slippage_probability:
            slippage = random.uniform(0, self.profile.slippage_max)
            # Slippage always hurts (Murphy's Law of Trading)
            if trade_type == 'BUY':
                slippage = slippage # Add to price (buy higher)
            else:
                slippage = -slippage # Subtract from price (sell lower)

        # Spread impact on price
        # Buy: Ask = Bid + Spread. Entry is higher.
        # Sell: Bid. Exit is Ask.
        # Simple Simulation: We assume 'current_price' is MID.
        # Buy fill = Mid + Spread/2 + Slippage
        # Sell fill = Mid - Spread/2 - Slippage
        
        half_spread = spread / 2.0
        
        if trade_type == 'BUY':
            exec_price = current_price + half_spread + slippage
        else:
            exec_price = current_price - half_spread - slippage
            
        return {
            'commission': comm,
            'spread': spread,
            'slippage': abs(slippage),
            'exec_price': exec_price
        }
