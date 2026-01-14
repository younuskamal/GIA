
"""
GIA Trade Strategy Engine
Applies Unified Rules (Risk, Cooldown, News) to Raw Model Predictions.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any
from backend.core.rules import RiskRules, SystemMode, SignalType
from backend.utils.news import NewsGuard
from backend.utils.market import MarketGuard

class StrategyHandler:
    """
    Central logic for:
    Raw Signal -> Filters -> Risk Check -> Final Decision
    """
    def __init__(self, mode: SystemMode = SystemMode.ADVISOR_MODE, is_legacy: bool = False, uhf_mode: bool = False):
        self.mode = mode
        self.is_legacy = is_legacy
        self.uhf_mode = uhf_mode
        self.consecutive_losses = 0
        self.cooldown_counter = 0
        self.last_trade_date = None
        self.last_trade_time = None
        self.MAX_TRADES_PER_DAY = 100 # Ultra-High Frequency Scalping Cap
        self.MIN_TIME_BETWEEN_TRADES = 0.5 # 🦁 Professional Pulse (30 seconds)
        self.daily_trade_count = 0
        
        # 🛡️ Safety Units
        self.news_guard = NewsGuard()
        self.market_guard = MarketGuard()



    def apply_strategy(self, 
                       raw_signal: str, 
                       confidence: float, 
                       context: Dict[str, Any],
                       record_trade: bool = True) -> Dict[str, Any]:
        """
        Applies filtering logic based on the selected Mode.
        """
        decision = SignalType.WAIT.value
        risk_level = "LOW"
        reasons = []
        regime = context.get('regime_flag', 0)

        # 🛡️ Datetime Guard: Convert numpy types for calculation
        current_date = context.get('date')
        if current_date is not None and not hasattr(current_date, 'hour'):
            current_date = pd.Timestamp(current_date)


        # 🔓 INSTITUTIONAL MODE: Balanced Quality Guard
        entropy = context.get('market_entropy', 0.5)
        
        # Tier 1: Relaxed for Institutional Pursuit (2.0 threshold)
        if entropy > 2.0 and confidence < 0.82:
            reasons.append(f"Market Noise Filter (Entropy {entropy:.2f} > 2.0)")
            return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)
        # Tier 2: Extreme Chaos
        if entropy > 2.5 and confidence < 0.90:
            reasons.append(f"Extreme Market Chaos (Entropy {entropy:.2f} > 2.5)")
            return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 2. Exhaustion Filter (Anti-FOMO)
        exhaustion = context.get('exhaustion_index', 0)
        if exhaustion > 4.5 and confidence < 0.90: 
            reasons.append(f"Price Exhaustion ({exhaustion:.2f} > 4.5)")
            return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 🕒 3. Market Awareness & Gap Protection
        if not self.market_guard.is_market_open(current_date):
            reasons.append("Market Closed (XAUUSD)")
            return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)
            
        m_safe, m_reason = self.market_guard.check_gap_risk(current_date)
        if not m_safe:
            reasons.append(f"Market Gap Guard: {m_reason}")
            return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 📡 4. Dynamic News Guard
        # Only check news for live-like modes or explicitly enabled
        if self.mode != SystemMode.STRATEGY_TEST_MODE:
            n_safe, n_reason = self.news_guard.check_safety(current_date)
            if not n_safe:
                reasons.append(f"Safety Halt: {n_reason}")
                return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)



        # 2. Basic Confidence Check (Institutional Gold Standard)
        base_thresh = 0.50 
        if confidence < base_thresh:
            reasons.append(f"Low Confidence ({confidence:.2f} < {base_thresh})")
            return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 3. Daily Trade Limit & Time Clustering Control
        if current_date:
            # Daily reset
            trade_day = current_date.date()

            if trade_day != self.last_trade_date:
                self.last_trade_date = trade_day
                self.daily_trade_count = 0
            
            if self.daily_trade_count >= self.MAX_TRADES_PER_DAY:
                reasons.append(f"Daily Trade Limit Reached ({self.daily_trade_count})")
                return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

            # Time Clustering: Avoid opening trades too close to each other
            if self.last_trade_time:
                diff_sec = (current_date - self.last_trade_time).total_seconds()
                diff_min = diff_sec / 60.0
                
                # 🦁 SMART BYPASS: If confidence is elite (>88%), allow faster entry (10s cooldown)
                # Otherwise, use standard institutional pulse (30s)
                bypass_thresh = 0.88
                effective_cooldown = 0.15 if confidence > bypass_thresh else self.MIN_TIME_BETWEEN_TRADES # 0.15m = 9s
                
                if diff_min < effective_cooldown:
                    reasons.append(f"Clustering Guard ({diff_sec:.0f}s < {effective_cooldown*60:.0f}s)")
                    return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 4. Session & Liquidity IQ
        hour = current_date.hour if current_date else 0
        is_high_liquidity = (8 <= hour <= 11) or (13 <= hour <= 17) # London/NY Primary
        if not is_high_liquidity:
            # 🦁 Global Pulse: Disable liquidity penalty to capture 24/7 moves
            penalty = 0.00
            liquidity_thresh = base_thresh + penalty 
            if confidence < liquidity_thresh:
                reasons.append(f"Low Liquidity IQ ({confidence:.2f} < {liquidity_thresh:.2f})")
                return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)


        # 4. Volatility Squeeze Filter (DISABLED for High-Freq)
        if False: # bb_width < 0.0010: 
             reasons.append(f"Market Squeeze (BB Width {bb_width:.5f} < 0.0010)")
             return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)
        
        # 5. Realistic Spread/ATR Ratio (Cost Protection)
        if not self.is_legacy:
            atr = context.get('atr', 1.0)
            spread = context.get('spread', 0.5)
            # Threshold: 80% of ATR (Professional Standard)
            is_m1 = atr < 0.25 
            cost_limit = 0.80 # 🦁 Tightened for Small Account Protection
            if is_m1: 
                cost_limit = 10.0 if getattr(self, 'uhf_mode', False) else 1.2
            
            if spread > (atr * cost_limit) and confidence < 0.90:
                  reasons.append(f"High Cost/Spread ({spread:.2f} > {atr*cost_limit:.2f})")
                  return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)




        # Final Approval for Raw Signals
        if raw_signal != SignalType.WAIT.value:
            if record_trade:
                self.daily_trade_count += 1
                self.last_trade_time = current_date
            return self._finalize(raw_signal, confidence, "MEDIUM", ["Institutional Filter Approved"])

        return self._finalize(SignalType.WAIT.value, confidence, "LOW", ["Signal Filtered"])

        # If we passed filters, accept signal
        decision = raw_signal
        self.daily_trade_count += 1
        
        if confidence >= RiskRules.HIGH_CONFIDENCE_LEVEL:
            risk_level = "LOW" # High confidence = Lower risk trade theoretically
        elif confidence >= RiskRules.MIN_CONFIDENCE_LEVEL:
             risk_level = "MEDIUM"
        
        # Logic for Advisor Mode: Don't just say BUY/SELL, add context
        if self.mode == SystemMode.ADVISOR_MODE:
            if decision == "WAIT":
                reasons.append("Market conditions or confidence not optimal.")

        return self._finalize(decision, confidence, risk_level, reasons)

    def _finalize(self, signal, confidence, risk, reasons):
        if signal != "WAIT":
             # Record successful entry time
             pass # Will be done in record_trade_start if added, or here
        expl = "; ".join(reasons) if reasons else "Signal Approved"
        return {
            "signal": signal,
            "confidence": confidence,
            "risk_level": risk,
            "mode": self.mode.value,
            "explanation": expl
        }

    def record_trade_start(self, time):
        """Called by engine when a trade is actually opened"""
        self.last_trade_time = time


    def record_trade_result(self, pnl: float):
        """Update internal state for cooldowns (Strategy Mode only)"""
        if self.mode == SystemMode.STRATEGY_TEST_MODE:
            if pnl < 0:
                self.cooldown_counter = RiskRules.COOLDOWN_AFTER_LOSS
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0