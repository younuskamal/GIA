"""
Backtest Engine - Professional Financial Simulator
Simulates realistic market conditions including variable spreads, commissions,
slippage, and advanced risk management (ATR stops, Trailing, Equity Guards).
"""
import pandas as pd
import numpy as np
import os
import sys
import joblib
from datetime import datetime
from sklearn.metrics import accuracy_score

# Fix path for package imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.rules import SystemMode, RiskRules
from backend.core.broker import BrokerSimulator
from backend.engine.strategy import StrategyHandler

class BacktestEngine:
    def __init__(self, model_path: str, is_legacy: bool = False):
        self.model_path = model_path
        self.is_legacy = is_legacy
        self.model_data = None
        
    def load_model(self):
        self.model_data = joblib.load(self.model_path)

    def backtest(self, df, broker_name="VIPER", initial_balance=10000, risk_pct=1.0, 
                 mode=SystemMode.STRATEGY_TEST_MODE, sizing_mode='dynamic', fixed_lot_size=0.01,
                 external_signals=None):
        """
        Runs a professional simulation.
        
        Args:
            df (pd.DataFrame): Data with 'date', 'open', 'high', 'low', 'close', 'atr' (optional)
            broker_name (str): 'VIPER', 'ICMARKETS', 'PEPPERSTONE'
            initial_balance (float): Starting equity
            risk_pct (float): Risk per trade (0.5 - 1.0)
            mode (SystemMode): Simulation mode
            sizing_mode (str): 'dynamic' (Risk %) or 'fixed' (Fixed Lots)
            fixed_lot_size (float): Lot size for 'fixed' mode
            external_signals (dict): Optional dict with 'labels' and 'probs' (for consensus mode)
        """
        if df.empty: return {"error": "No data"}
        
        # 1. Setup Environment
        broker = BrokerSimulator(broker_name)
        strategy = StrategyHandler(mode=mode, is_legacy=self.is_legacy)
        leverage = 500 # Default Gold Leverage
        
        # Ensure necessary columns
        required_cols = ['open', 'high', 'low', 'close']
        if not all(c in df.columns for c in required_cols):
            return {"error": f"Missing columns: {required_cols}"}
            
        # 2. Pre-Calculate Model Signals 
        if external_signals:
            y_pred_labels = external_signals['labels']
            y_pred_probs = external_signals['probs']
            external_sizing = external_signals.get('sizing', None) # New: per-trade size multiplier
        elif self.model_data:
            # Flexible feature key detection
            feature_cols = self.model_data.get('feature_columns', self.model_data.get('features', []))
            
            # Check availability
            available_feats = [f for f in feature_cols if f in df.columns]
            if len(available_feats) < len(feature_cols):
                missing = [f for f in feature_cols if f not in df.columns]
                return {"error": f"Dataset missing features: {missing}"}
                
            probs = self.model_data['model'].predict_proba(df[feature_cols])
            
            # 🦁 Calibrator Integration (v3.0+)
            if 'calibrator' in self.model_data:
                probs = self.model_data['calibrator'].calibrate(probs)
                
            y_pred_probs = np.max(probs, axis=1)
            y_pred_idx = np.argmax(probs, axis=1)
            
            # Encoder Support
            encoder = self.model_data.get('label_encoder', self.model_data.get('encoder'))
            if encoder:
                y_pred_labels = encoder.inverse_transform(y_pred_idx)
            else:
                # Fallback mapping
                mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
                y_pred_labels = [mapping.get(i, 'WAIT') for i in y_pred_idx]
                
            external_sizing = None
        else:
            # Fallback for "Strategy Only" testing without ML component (rare)
            y_pred_labels = ['WAIT'] * len(df)
            y_pred_probs = [0.0] * len(df)
            external_sizing = None

        # 3. Simulation State
        balance = initial_balance
        equity = initial_balance
        peak_equity = initial_balance
        
        position = None # { 'type': 'BUY'/'SELL', 'entry_price': float, 'lots': float, 'sl': float, 'tp': float, 'entry_time': date }
        trades_log = []
        
        equity_curve = [initial_balance]
        dates = pd.to_datetime(df['date']).values
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        atrs = df['atr'].values if 'atr' in df.columns else np.zeros(len(df))
        
        # Cooldown & Risk State
        cooldown_counter = 0
        consecutive_losses = 0
        from collections import Counter
        no_trade_reasons = Counter()
        
        # 4. Event Loop
        for i in range(len(df)):
            current_date = dates[i]
            
            # --- A. Check Stop Conditions ---
            if equity < initial_balance * RiskRules.EQUITY_HARD_STOP_PCT:
                break # Hard Stop
                
            # --- B. Manage Open Position ---
            if position:
                # Mark to market (Equity Update)
                # Using 'Close' for estimation, but High/Low for stop checks
                curr_price = closes[i]
                
                # Check for SL/TP hits (High/Low)
                exit_price = None
                exit_reason = None
                
                # Dynamic Spread for Exit
                spread = broker.get_dynamic_spread() 
                
                if position['type'] == 'BUY':
                    # Stop Loss Hit? (Low check)
                    # Sell exit price = Bid ~ Low
                    if lows[i] <= position['sl']:
                        exit_price = position['sl'] # Assume filled at SL (slippage handled below?)
                        exit_reason = 'SL'
                    # Take Profit Hit?
                    elif highs[i] >= position['tp']:
                        exit_price = position['tp']
                        exit_reason = 'TP'
                    # Signal Close? (Reverse signal or Strategy logic? Assuming StrategyHandler manages this via applied rules)
                    # For simplicity, StrategyHandler usually returns BUY/SELL. If opposite, close.
                    
                elif position['type'] == 'SELL':
                    # Stop Loss Hit? (High check + Spread)
                    # Buy exit price = Ask ~ High + Spread
                    if highs[i] + spread >= position['sl']:
                        exit_price = position['sl']
                        exit_reason = 'SL'
                    elif lows[i] + spread <= position['tp']:
                        exit_price = position['tp']
                        exit_reason = 'TP'
                
                # Execute Exit if Triggered
                if exit_price:
                    # Calculate Real Exit Cost
                    cost_info = broker.calculate_cost(position['lots'], exit_price, position['type']) # Reverse? No, calculate_cost is generic
                    # Wait, calculate_cost is for Entry. Exit is simpler:
                    # Commission is usually paid round-trip or per side. BrokerProfile is per LOT (standard is round trip or single side?)
                    # Usually "7 per lot" is Round Trip (RT). So 3.5 per side.
                    # Let's assume BrokerProfile.commission is RT. So we paid half on entry? Or fully on entry?
                    # Standard MT4: Comm charged on entry. Swap charged midnight.
                    # We simulated comm on entry. So exit is just price delta.
                    
                    real_exit_price = cost_info['exec_price'] # Applies Slippage/Spread logic again
                    
                    # PnL Calc based on Price
                    price_delta = 0
                    if position['type'] == 'BUY':
                        price_delta = real_exit_price - position['entry_price']
                    else:
                        price_delta = position['entry_price'] - real_exit_price
                    
                    # Dollar Value ($10 per pip per lot is standard for XAUUSD? No.)
                    # Gold: 1 lot = 100 oz. $1 move = $100.
                    # If price_delta is 1.0 (1300 -> 1301), and lots is 1.0, PnL is $100.
                    # Formula: Delta * Lots * ContractSize(100)
                    contract_size = 100
                    pnl = price_delta * position['lots'] * contract_size
                    
                    # Apply Swap? (Ignored for now)
                    
                    balance += pnl
                    trades_log.append({
                        'entry_date': position['entry_time'],
                        'exit_date': current_date,
                        'type': position['type'],
                        'lots': position['lots'],
                        'entry': position['entry_price'],
                        'exit': real_exit_price,
                        'pnl_net': pnl, # Comm deducted on entry
                        'confidence': position.get('confidence', 0),
                        'reason': exit_reason
                    })
                    
                    if pnl < 0:
                        consecutive_losses += 1
                        cooldown_counter = RiskRules.COOLDOWN_AFTER_LOSS
                    else:
                        consecutive_losses = 0
                        
                    position = None # Position Closed
                    
            # --- C. New Trade Logic ---
            # Decrement Cooldown
            if cooldown_counter > 0:
                cooldown_counter -= 1
                continue
                
            if position is None:
                # --- Circuit Breaker: Drawdown Limit ---
                current_dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
                if current_dd > (RiskRules.MAX_TOTAL_DRAWDOWN_PCT / 100.0):
                    return self._generate_report(trades_log, equity_curve, initial_balance, len(df), y_pred_labels, no_trade_reasons, error=f"Hard Equity Stop: {current_dd*100:.1f}% Drawdown")

                # Strategy Decision
                signal = y_pred_labels[i]
                conf = y_pred_probs[i]
                
                # Context
                atr = atrs[i] if atrs[i] > 0 else 1.0
                spread = broker.get_dynamic_spread()
                ctx = {
                    "date": current_date, # Required for Daily Limit
                    "volatility_ratio": 1.0,
                    "regime_flag": df.iloc[i].get('regime_flag', 0),
                    "dist_ema200": df.iloc[i].get('dist_ema200', 0),
                    "bb_width": df.iloc[i].get('bb_width', 0.01),
                    "atr": atr,
                    "spread": spread
                }
                
                decision = strategy.apply_strategy(signal, conf, ctx)
                final_sig = decision['signal']
                
                if final_sig == 'WAIT':
                    full_reason = decision.get('explanation', 'Unknown')
                    if isinstance(full_reason, list): full_reason = full_reason[0] if full_reason else 'Unknown'
                    
                    # Grouping for cleaner report
                    simple_reason = "Other"
                    if "Confidence" in full_reason: simple_reason = "Low Confidence"
                    elif "threshold" in full_reason: simple_reason = "Regime Threshold Filter"
                    elif "Limit" in full_reason: simple_reason = "Daily Trade Limit"
                    elif "Squeeze" in full_reason: simple_reason = "Market Squeeze"
                    elif "Spread" in full_reason: simple_reason = "High Cost/Spread"
                    elif "News" in full_reason: simple_reason = "News Impact"
                    elif "Cooldown" in full_reason: simple_reason = "Cooldown Active"
                    
                    no_trade_reasons[simple_reason] += 1
                
                if final_sig in ['BUY', 'SELL']:
                    # 1. Calculate Potential Lots
                    if sizing_mode == 'fixed':
                        lots = fixed_lot_size
                    else:
                        # Risk Management Size
                        risk_amount = equity * (risk_pct / 100.0)
                        
                        # Legacy vs Modern Multipliers
                        if self.is_legacy:
                            sl_mult, tp_mult = 1.5, 3.0 # v14 standard
                        else:
                            regime = ctx.get('regime_flag', 0)
                            if regime == 2: # HIGH_VOL
                                sl_mult, tp_mult = 2.5, 4.0 
                            elif regime == 1: # TREND
                                sl_mult, tp_mult = 1.8, 3.5 
                            else: # RANGE
                                sl_mult, tp_mult = 2.0, 2.7
                        
                        sl_dist = atr * sl_mult
                        tp_dist = atr * tp_mult
                        
                        # Lot Calculation (Risk based)
                        contract_size = 100
                        lots = risk_amount / (contract_size * sl_dist)
                    
                    lots = max(0.01, round(lots, 2))
                    if external_sizing is not None:
                        lots = max(0.01, round(lots * external_sizing[i], 2))
                        
                    if sizing_mode == 'dynamic':
                        lots = min(lots, 50.0) # Cap for dynamic sanity
                    
                    # 2. Execution Price (for margin check)
                    entry_price = opens[i]
                    
                    # 3. Margin Check (Gold 100oz contract)
                    # Required = (Price * Lots * 100) / Leverage
                    margin_required = (entry_price * lots * 100) / leverage
                    
                    if equity < margin_required:
                        no_trade_reasons["Insufficient Margin"] += 1
                        if equity < (initial_balance * 0.1): # If extremely low, stop
                             return self._generate_report(trades_log, equity_curve, initial_balance, len(df), y_pred_labels, no_trade_reasons, error="Account Blown: Insufficient Margin")
                        continue
                    
                    # Store distances for SL/TP prices (calculated even for fixed for consistency in exit check)
                    # Note: for fixed mode we still need SL/TP for the simulation to exit
                    if sizing_mode == 'fixed':
                         # Use standard multipliers for exit logic even if lot is fixed
                         sl_mult, tp_mult = (1.5, 3.0) if self.is_legacy else (2.0, 2.7)
                         sl_dist = atr * sl_mult
                         tp_dist = atr * tp_mult
                    # Realistic: Close of prev is decision point. Open of this is entry.
                    
                    cost_info = broker.calculate_cost(lots, entry_price, final_sig)
                    real_entry_price = cost_info['exec_price']
                    total_comm = cost_info['commission']
                    
                    # Deduct Comm immediately (Balance separation)
                    balance -= total_comm
                    
                    # Set SL/TP
                    sl_price = 0
                    tp_price = 0
                    if final_sig == 'BUY':
                        sl_price = real_entry_price - sl_dist
                        tp_price = real_entry_price + tp_dist
                    else:
                        sl_price = real_entry_price + sl_dist
                        tp_price = real_entry_price - tp_dist
                        
                    position = {
                        'type': final_sig,
                        'entry_price': real_entry_price,
                        'lots': lots,
                        'sl': sl_price,
                        'tp': tp_price,
                        'confidence': conf,
                        'entry_time': current_date
                    }
            
            # Update Equity (Floating PnL + Balance)
            floating_pnl = 0
            if position:
                delta = 0
                if position['type'] == 'BUY':
                    delta = closes[i] - position['entry_price']
                else:
                    delta = position['entry_price'] - closes[i]
                floating_pnl = delta * position['lots'] * 100
                
            equity = balance + floating_pnl
            peak_equity = max(peak_equity, equity)
            equity_curve.append(equity)

        # 5. Compile Statistics
        return self._generate_report(trades_log, equity_curve, initial_balance, len(df), y_pred_labels, no_trade_reasons)

    def _generate_report(self, trades, equity_curve, initial_bal, total_rows, y_pred_labels, no_trade_reasons, error=None):
        # 5. Finalize Results
        if not trades:
            # Diagnostic: Why no trades?
            stats = {
                "total_rows": total_rows,
                "signals_received": len([s for s in y_pred_labels if s != 'WAIT']),
                "reasons": dict(no_trade_reasons)
            }
            return {"error": error or "No trades executed", "diagnostic": stats}
            
        df_t = pd.DataFrame(trades)
        
        net_profit = df_t['pnl_net'].sum()
        wins = df_t[df_t['pnl_net'] > 0]
        losses = df_t[df_t['pnl_net'] <= 0]
        
        win_rate = (len(wins) / len(df_t)) * 100
        avg_win = wins['pnl_net'].mean() if not wins.empty else 0
        avg_loss = abs(losses['pnl_net'].mean()) if not losses.empty else 0
        profit_factor = (wins['pnl_net'].sum() / abs(losses['pnl_net'].sum())) if not losses.empty else 999
        
        # DD
        eq_arr = np.array(equity_curve)
        peak = np.maximum.accumulate(eq_arr)
        dd = (peak - eq_arr) / peak
        max_dd = np.max(dd) * 100
        
        # Monthly Logic (Requires pandas dates in 'entry_date')
        df_t['month'] = pd.to_datetime(df_t['entry_date']).dt.to_period('M')
        monthly = df_t.groupby('month')['pnl_net'].sum()
        # Convert PeriodIndex to string keys for JSON compatibility
        monthly_dict = {str(k): v for k, v in monthly.to_dict().items()}
        
        return {
            "net_profit": net_profit,
            "net_profit_pct": (net_profit / initial_bal) * 100,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_trades": len(df_t),
            "win_count": len(wins),
            "loss_count": len(losses),
            "max_win": wins['pnl_net'].max() if not wins.empty else 0,
            "max_loss": losses['pnl_net'].min() if not losses.empty else 0,
            "avg_trades_day": len(df_t) / (total_rows / (24 * 4)) if total_rows > 0 else 0,
            "avg_win_loss_ratio": avg_win / avg_loss if avg_loss > 0 else 0,
            "monthly_performance": monthly_dict,
            "equity_curve": equity_curve,
            "trades": trades,
            "simulation_error": error
        }
