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

    def backtest(self, df, broker_name="FIPER", initial_balance=10000, risk_pct=1.0, 
                 mode=SystemMode.STRATEGY_TEST_MODE, sizing_mode='dynamic', fixed_lot_size=0.01,
                 external_signals=None, execution_latency=0.05): # 50ms latency by default
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
        is_predator = "PREDATOR" in self.model_path.upper() or "FLASH" in self.model_path.upper()
        strategy = StrategyHandler(mode=mode, is_legacy=self.is_legacy, uhf_mode=is_predator)
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
        
        positions = [] # List of open position dicts
        trades_log = []
        
        equity_curve = [initial_balance]
        dates = pd.to_datetime(df['date']).values
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        atrs = df['atr'].values if 'atr' in df.columns else np.zeros(len(df))
        
        # 🧪 Performance Optimization: Pre-extract metadata to NumPy
        regimes = df['regime_flag'].values if 'regime_flag' in df.columns else np.zeros(len(df))
        entropies = df['market_entropy'].values if 'market_entropy' in df.columns else np.full(len(df), 0.5)
        exhaustions = df['exhaustion_index'].values if 'exhaustion_index' in df.columns else np.zeros(len(df))
        bb_widths = df['bb_width'].values if 'bb_width' in df.columns else np.full(len(df), 0.01)

        
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
                
            # --- B. Manage Open Positions ---
            for position in positions[:]:
                # Mark to market (Equity Update for this position)
                # Using 'Close' for estimation, but High/Low for stop checks
                curr_price = closes[i]
                
                # --- B. Update MFE/MAE (Maximum Favorable/Adverse Excursion) ---
                if position['type'] == 'BUY':
                    position['mfe'] = max(position.get('mfe', 0), highs[i] - position['entry_price'])
                    position['mae'] = min(position.get('mae', 0), lows[i] - position['entry_price'])
                else:
                    position['mfe'] = max(position.get('mfe', 0), position['entry_price'] - lows[i])
                    position['mae'] = min(position.get('mae', 0), position['entry_price'] - highs[i])
                
                # --- Trailing / BE Logic ---
                curr_atr = atrs[i] if atrs[i] > 0 else 1.0
                mfe_pips = position.get('mfe', 0)
                
                if not position.get('be_active', False) and mfe_pips > (curr_atr * 1.0):
                    comm_buffer = 0.03
                    if position['type'] == 'BUY':
                        position['sl'] = position['entry_price'] + comm_buffer
                    else:
                        position['sl'] = position['entry_price'] - comm_buffer
                    position['be_active'] = True
                
                if position.get('be_active', False):
                    trail_dist = curr_atr * 2.0
                    if position['type'] == 'BUY':
                        new_sl = highs[i] - trail_dist
                        if new_sl > position['sl']: position['sl'] = new_sl
                    else:
                        new_sl = lows[i] + trail_dist
                        if new_sl < position['sl']: position['sl'] = new_sl
                
                # --- Check for SL/TP hits ---
                exit_price = None
                exit_reason = None
                spread = broker.get_dynamic_spread() 
                
                if position['type'] == 'BUY':
                    hit_sl = lows[i] <= position['sl']
                    hit_tp = highs[i] >= position['tp']
                    if hit_sl and hit_tp:
                        exit_price, exit_reason = position['sl'], 'SL (Collision)'
                    elif hit_sl:
                        exit_price, exit_reason = position['sl'], 'SL'
                    elif hit_tp:
                        exit_price, exit_reason = position['tp'], 'TP'
                        
                elif position['type'] == 'SELL':
                    hit_sl = highs[i] + spread >= position['sl']
                    hit_tp = lows[i] + spread <= position['tp']
                    if hit_sl and hit_tp:
                        exit_price, exit_reason = position['sl'], 'SL (Collision)'
                    elif hit_sl:
                        exit_price, exit_reason = position['sl'], 'SL'
                    elif hit_tp:
                        exit_price, exit_reason = position['tp'], 'TP'
                
                if exit_price:
                    cost_info = broker.calculate_cost(position['lots'], exit_price, position['type'])
                    real_exit_price = cost_info['exec_price']
                    
                    price_delta = (real_exit_price - position['entry_price']) if position['type'] == 'BUY' else (position['entry_price'] - real_exit_price)
                    pnl = price_delta * position['lots'] * 100
                    pnl_pct = (pnl / balance) * 100 if balance != 0 else 0
                    balance += pnl
                        
                    trades_log.append({
                        'entry_date': str(position['entry_time']),
                        'exit_date': str(current_date),
                        'type': position['type'],
                        'lots': position['lots'],
                        'entry_price': position['entry_price'],
                        'exit_price': real_exit_price,
                        'pnl_net': pnl, 
                        'pnl_pct': pnl_pct,
                        'balance': balance,
                        'mfe_pips': round(position.get('mfe', 0) * 10, 1),
                        'mae_pips': round(position.get('mae', 0) * 10, 1),
                        'confidence': position.get('confidence', 0),
                        'exit_reason': exit_reason
                    })
                    
                    if pnl < 0:
                        consecutive_losses += 1
                        cooldown_counter = RiskRules.COOLDOWN_AFTER_LOSS
                    else:
                        consecutive_losses = 0
                        
                    positions.remove(position)
                    
            # --- C. New Trade Logic ---
            # Decrement Cooldown
            if cooldown_counter > 0:
                cooldown_counter -= 1
                continue
                
            if len(positions) < RiskRules.MAX_CONCURRENT_TRADES:
                # --- Circuit Breaker: Drawdown Limit ---
                current_dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
                if current_dd > (RiskRules.MAX_TOTAL_DRAWDOWN_PCT / 100.0):
                    return self._generate_report(trades_log, equity_curve, initial_balance, len(df), y_pred_labels, no_trade_reasons, error=f"Hard Equity Stop: {current_dd*100:.1f}% Drawdown")

                # Strategy Decision
                signal = y_pred_labels[i]
                conf = y_pred_probs[i]
                spread = broker.get_dynamic_spread()
                atr = atrs[i] if atrs[i] > 0 else 1e-6
                
                # Context (Vectorized Access)
                ctx = {
                    "date": current_date, 
                    "regime_flag": regimes[i],
                    "market_entropy": entropies[i],
                    "exhaustion_index": exhaustions[i],
                    "bb_width": bb_widths[i],
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
                    
                    # 🚀 INSTITUTIONAL REALISM: Execution Latency & Slip
                    # In high volatility (ATR), latency hurts more
                    vol_impact = (atr / entry_price) * 1000
                    latency_slip = execution_latency * vol_impact
                    if final_sig == 'BUY':
                        real_entry_price += latency_slip
                    else:
                        real_entry_price -= latency_slip
                        
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
                        
                    new_position = {
                        'type': final_sig,
                        'entry_price': real_entry_price,
                        'lots': lots,
                        'sl': sl_price,
                        'tp': tp_price,
                        'confidence': conf,
                        'entry_time': current_date
                    }
                    positions.append(new_position)
                    strategy.record_trade_start(current_date)

            
            # Update Equity (Floating PnL + Balance)
            floating_pnl = 0
            for pos in positions:
                delta = (closes[i] - pos['entry_price']) if pos['type'] == 'BUY' else (pos['entry_price'] - closes[i])
                floating_pnl += delta * pos['lots'] * 100
                
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
