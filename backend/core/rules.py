
"""
GIA Core Rules & Constants
Single Source of Truth for Logic, Risk, and Modes.
"""
from enum import Enum

# --- MODES ---
class SystemMode(Enum):
    ADVISOR_MODE = "ADVISOR"             # Pure analysis, conservative
    STRATEGY_TEST_MODE = "STRATEGY_TEST" # Backtest with full risk management
    STRESS_TEST_MODE = "STRESS_TEST"     # Raw model performance (no filters)
    AUTO_TRADING_DEMO_MODE = "AUTO_DEMO" # Live Trading (Demo Only)

# --- RISK MANAGEMENT RULES ---
class RiskRules:
    # Minimum confidence to even consider a trade
    MIN_CONFIDENCE_LEVEL = 0.20  
    
    # Strong confidence for aggressive entry
    HIGH_CONFIDENCE_LEVEL = 0.65 

    # Stop Loss / Take Profit (Static fallback)
    DEFAULT_SL_PIPS = 50
    DEFAULT_TP_PIPS = 80

    # Risk per trade (% of Equity)
    RISK_PER_TRADE_PCT = 0.65
    
    # Capital Protection
    EQUITY_HARD_STOP_PCT = 0.80  # Stop trading if equity drops below 80% of initial
    SOFT_STOP_PCT = 0.85         # Halve risk if equity drops below 85%
    
    # Volatility Filter
    MAX_VOLATILITY_RATIO = 1.5   # Don't trade if ATR > 1.5x Average ATR
    
    # Max Drawdown allowed before "Circuit Breaker"
    MAX_DAILY_DRAWDOWN_PCT = 5.0
    MAX_TOTAL_DRAWDOWN_PCT = 20.0

    # Cooldown: Candles to wait after a loss
    COOLDOWN_AFTER_LOSS = 3

    # Pyramiding: Max concurrent trades
    MAX_CONCURRENT_TRADES = 3

    # News Filter: Don't trade if impact > threshold
    MAX_NEWS_IMPACT = 2  # 3=High, 2=Medium, 1=Low

# --- MARKET CONDITIONS (REALITY CHECK) ---
class MarketConditions:
    # Costs associated with Live Trading
    SPREAD_AVG = 0.35       # $0.35 spread on Gold
    COMMISSION_PER_LOT = 7.0 # $7 per round turn
    SLIPPAGE_MAX = 0.10     # Max random slippage ($)

# --- TRADING SIGNALS ---
class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"

# --- OUTPUT CONTRACT ---
RESPONSE_TEMPLATE = {
    "signal": "WAIT",
    "confidence": 0.0,
    "risk_level": "LOW",
    "mode": "ADVISOR",
    "explanation": ""
}
