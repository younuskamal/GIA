
"""
GIA Trade Strategy Engine
Applies Unified Rules (Risk, Cooldown, News) to Raw Model Predictions.
"""
from typing import Dict, Any
from backend.core.rules import RiskRules, SystemMode, SignalType

class StrategyHandler:
    """
    Central logic for:
    Raw Signal -> Filters -> Risk Check -> Final Decision
    """
    def __init__(self, mode: SystemMode = SystemMode.ADVISOR_MODE, is_legacy: bool = False):
        self.mode = mode
        self.is_legacy = is_legacy
        self.consecutive_losses = 0
        self.cooldown_counter = 0
        self.last_trade_date = None
        self.daily_trade_count = 0
        self.MAX_TRADES_PER_DAY = 30 # Nuclear Frequency Spec

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

        # 🔓 NUCLEAR AGGRESSION: All filters disabled for Maximum Frequency
        if raw_signal != SignalType.WAIT.value:
            self.daily_trade_count += 1
            return self._finalize(raw_signal, confidence, "MEDIUM", ["Nuclear High-Frequency Entry"])

        # 2. Basic Confidence Check (v14 Spec: 0.40)
        base_thresh = 0.40 if self.is_legacy else RiskRules.MIN_CONFIDENCE_LEVEL
        if confidence < base_thresh:
            reasons.append(f"Low Confidence ({confidence:.2f} < {base_thresh})")
            return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 3. Daily Trade Limit Control
        current_date = context.get('date')
        if current_date:
            trade_day = current_date.date() if hasattr(current_date, 'date') else str(current_date)[:10]
            if trade_day != self.last_trade_date:
                self.last_trade_date = trade_day
                self.daily_trade_count = 0
            
            if self.daily_trade_count >= self.MAX_TRADES_PER_DAY:
                reasons.append(f"Daily Trade Limit Reached ({self.daily_trade_count})")
                return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # 4. News Filter
        news_impact = context.get("news_impact_score", 0)
        if abs(news_impact) > RiskRules.MAX_NEWS_IMPACT:
             reasons.append(f"High News Impact ({news_impact})")
             if self.mode == SystemMode.STRATEGY_TEST_MODE:
                 return self._finalize(SignalType.WAIT.value, confidence, "HIGH", reasons)
             risk_level = "HIGH"

        # 4. Volatility Squeeze Filter (DISABLED for High-Freq)
        if False: # bb_width < 0.0010: 
             reasons.append(f"Market Squeeze (BB Width {bb_width:.5f} < 0.0010)")
             return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)
        
        # 5. Realistic Spread/ATR Ratio (DISABLED for High-Freq)
        if False: # not self.is_legacy:
            atr = context.get('atr', 1.0)
            spread = context.get('spread', 0.5)
            spread_limit = 0.50
            if spread > (atr * spread_limit):
                 reasons.append(f"High Cost/Spread ({spread:.2f} > {atr*spread_limit:.2f})")
                 return self._finalize(SignalType.WAIT.value, confidence, "LOW", reasons)

        # [Filters removed for Nuclear Mode]
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
        expl = "; ".join(reasons) if reasons else "Signal Approved"
        return {
            "signal": signal,
            "confidence": confidence,
            "risk_level": risk,
            "mode": self.mode.value,
            "explanation": expl
        }

    def record_trade_result(self, pnl: float):
        """Update internal state for cooldowns (Strategy Mode only)"""
        if self.mode == SystemMode.STRATEGY_TEST_MODE:
            if pnl < 0:
                self.cooldown_counter = RiskRules.COOLDOWN_AFTER_LOSS
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0
