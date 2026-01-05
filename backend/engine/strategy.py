
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
        self.MIN_TIME_BETWEEN_TRADES = 1 if uhf_mode else 5 # Dynamic clustering
        self.daily_trade_count = 0
        
        # 🛡️ Safety Units
        self.news_guard = NewsGuard()
        self.market_guard = MarketGuard()



    def apply_strategy(self, 
                       raw_signal: str, 
                       confidence: float, 
                       context: Dict[str, Any]) -> Dict[str, Any]:
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


        # 🔓 INSTITUTIONAL MODE: Smart Filtering based on Market Physics
        # 1. Entropy Guard (Chaos Filter) - Softened for High-Frequency Scaling
        entropy = context.get('market_entropy', 0.5)
        if entropy > 0.88 and confidence < 0.85: # Increased from 0.75
            reasons.append(f"High Market Chaos (Entropy {entropy:.2f} > 0.88)")
            return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 2. Exhaustion Filter (Anti-FOMO) - Softened to capture extended runs
        exhaustion = context.get('exhaustion_index', 0)
        if exhaustion > 4.5 and confidence < 0.90: # Increased from 3.5
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



        # 2. Basic Confidence Check (v14 Spec: 0.40)
        base_thresh = 0.40 if self.is_legacy else RiskRules.MIN_CONFIDENCE_LEVEL
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
                diff = (current_date - self.last_trade_time).total_seconds() / 60
                if diff < self.MIN_TIME_BETWEEN_TRADES:
                    reasons.append(f"Trade Clustering Guard ({diff:.1f}m < {self.MIN_TIME_BETWEEN_TRADES}m)")
                    return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 4. Session & Liquidity IQ
        hour = current_date.hour if current_date else 0
        is_high_liquidity = (8 <= hour <= 11) or (13 <= hour <= 17) # London/NY Primary
        if not is_high_liquidity:
            # UHF Mode bypasses liquidity penalty for 24/7 pulse-capture
            penalty = 0.00 if getattr(self, 'uhf_mode', False) else 0.15
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
            # Threshold: 50% of ATR (Standard Institutional)
            # 🦁 H-Freq Scalper Protection: On M1, Gold ATR is very small. 
            # We bypass the cost filter for M1 to allow for ultra-high frequency.
            is_m1 = atr < 0.25 # M1 Gold ATR is typically below 0.25
            cost_limit = 0.60
            if is_m1: 
                cost_limit = 10.0 if getattr(self, 'uhf_mode', False) else 1.25
            
            if spread > (atr * cost_limit) and confidence < 0.90:
                 reasons.append(f"High Cost/Spread ({spread:.2f} > {atr*cost_limit:.2f})")
                 return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)




        # Final Approval for Raw Signals
        if raw_signal != SignalType.WAIT.value:
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
