
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
        "VIPER": BrokerProfile("VIPER", 0.30, 0.45, 7.0),
        "FIPER": BrokerProfile("FIPER", 0.20, 0.35, 6.0), # Aggressive low-cost
        "ICMARKETS": BrokerProfile("IC MARKETS", 0.25, 0.40, 6.0),
        "PEPPERSTONE": BrokerProfile("PEPPERSTONE", 0.35, 0.50, 7.0),
        "BLACKBULL": BrokerProfile("BLACKBULL", 0.40, 0.60, 6.0),
        "STRESS_TEST": BrokerProfile("STRESS TEST", 0.60, 1.00, 10.0),
        "SURVIVAL": BrokerProfile("SURVIVAL", 1.20, 1.80, 7.0), # 1.2-1.8 pip spread, $7 commission
        "ZERO": BrokerProfile("ZERO", 0.0, 0.0, 0.0) # For raw tests
    }

    def __init__(self, profile_name="VIPER"):
        self.profile = self.PROFILES.get(profile_name.upper(), self.PROFILES["VIPER"])

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
