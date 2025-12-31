
"""
🦁 GIA PRO BATTLEGROUND (v2.2 - Ultimate Edition)
-----------------------------------------------
The most comprehensive analytical suite for GIA Professional Trading Bots.
Features: 
- Interactive Timeframe & Broker Sync
- Institutional Metrics (Sharpe, Sortino, Calmar)
- Deep Trade Analysis (Win/Loss, Bias, Frequency)
- Monte Carlo Robustness Validation
- Automated Result Archiving

Usage:
    Interactive Entry: python run_backtest.py
    CLI Comparison:    python run_backtest.py --compare --year 2024
"""
import sys
import os
import argparse
import pandas as pd
import numpy as np
import joblib
import json
from datetime import datetime
import traceback
import colorama
from colorama import Fore, Style

# Initialize Colorama for Windows/Linux
colorama.init()

# Setup backend path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.engine.backtest import BacktestEngine
from backend.core.rules import SystemMode
from backend.core.regime import MarketRegimeEngine
from backend.core.broker import BrokerSimulator

# --- MockEncoder to handle Custom pickled objects ---
class MockEncoder:
    def inverse_transform(self, idxs):
        mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

# --- ASCII Visualization ---
def print_separator(char="=", length=80, color=Fore.CYAN):
    print(color + char * length + Style.RESET_ALL)

def print_banner():
    banner = f"""
    {Fore.YELLOW}██████╗ ██╗ █████╗     ██████╗ ██████╗  ██████╗ 
    ██╔════╝ ██║██╔══██╗    ██╔══██╗██╔══██╗██╔═══██╗
    ██║  ███╗██║███████║    ██████╔╝██████╔╝██║   ██║
    ██║   ██║██║██╔══██║    ██╔═══╝ ██╔══██╗██║   ██║
    ╚██████╔╝██║██║  ██║    ██║     ██║  ██║╚██████╔╝
     ╚═════╝ ╚═╝╚═╝  ╚═╝    ╚═╝     ╚═╝  ╚═╝ ╚═════╝ {Style.RESET_ALL}
    {Fore.CYAN}--- ULTIMATE ANALYTICAL SUITE v2.2 ---{Style.RESET_ALL}
    """
    print(banner)

def print_ascii_chart(values, height=12, width=80, title="Equity Growth"):
    if not values: return
    min_v, max_v = min(values), max(values)
    range_v = max_v - min_v
    if range_v == 0: range_v = 1
    
    normalized = [int((v - min_v) / range_v * (height - 1)) for v in values]
    step = len(normalized) / width
    resampled = [normalized[int(i * step)] for i in range(width)]
    
    print(f"\n{Fore.WHITE}📈 {title}{Style.RESET_ALL}")
    print(" " + Fore.LIGHTBLACK_EX + "┌" + "─" * width + "┐" + Style.RESET_ALL)
    for h in range(height - 1, -1, -1):
        line = ""
        for v in resampled:
            if v == h: line += Fore.GREEN + "*" + Style.RESET_ALL
            elif v > h: line += Fore.LIGHTBLACK_EX + "·" + Style.RESET_ALL
            else: line += " "
        print(Fore.LIGHTBLACK_EX + " |" + Style.RESET_ALL + line + Fore.LIGHTBLACK_EX + "|" + Style.RESET_ALL)
    print(" " + Fore.LIGHTBLACK_EX + "└" + "─" * width + "┘" + Style.RESET_ALL)
    
    roi = ((values[-1] / values[0]) - 1) * 100
    color = Fore.GREEN if roi >= 0 else Fore.RED
    print(f" {Fore.WHITE}Start: ${values[0]:,.0f} {Fore.LIGHTBLACK_EX}|{Fore.WHITE} Peak: ${max_v:,.0f} {Fore.LIGHTBLACK_EX}|{Fore.WHITE} End: ${values[-1]:,.0f} ({color}{roi:+.2f}%{Fore.WHITE}){Style.RESET_ALL}\n")

# --- Tactical Feature Factory ---
class FeatureFactory:
    @staticmethod
    def construct(df, features_needed):
        df = df.copy()
        for f in features_needed:
            if f in df.columns: continue
            
            # Momentum
            if f == 'rsi': df['rsi'] = FeatureFactory._rsi(df['close'])
            elif f == 'rsi_7': df['rsi_7'] = FeatureFactory._rsi(df['close'], period=7)
            elif f == 'roc_3': df['roc_3'] = df['close'].pct_change(3)
            elif f == 'rsi_slope': df['rsi_slope'] = FeatureFactory._rsi(df['close']).diff(3)
            elif f == 'momentum': df['momentum'] = df['close'].diff(5) / (df['close'].shift(5) + 1e-9)
            elif f == 'mom_5': df['mom_5'] = df['close'].pct_change(5)
            elif f == 'change': df['change'] = df['close'].pct_change()
            elif f.startswith('mom_'):
                lookback = 5
                if '3' in f: lookback = 3
                elif '10' in f: lookback = 10
                elif 'weekly' in f: lookback = 120
                elif 'monthly' in f: lookback = 480
                df[f] = df['close'].diff(lookback) / (df['close'] + 1e-9)
            
            # Structural
            elif f.startswith('ema_') and '_dist' in f:
                span = int(f.split('_')[1])
                ema = df['close'].ewm(span=span, adjust=False).mean()
                df[f] = (df['close'] - ema) / (ema + 1e-9)
            elif f == 'ema_dist':
                ema = df['close'].ewm(span=20, adjust=False).mean()
                df['ema_dist'] = (df['close'] - ema) / (ema + 1e-9)
            elif f == 'sma_dist':
                sma = df['close'].rolling(20).mean()
                df['sma_dist'] = (df['close'] - sma) / (sma + 1e-9)
                
            elif f == 'bb_width':
                ma = df['close'].rolling(20).mean()
                std = df['close'].rolling(20).std()
                df['bb_width'] = (4 * std) / (ma + 1e-9)
            elif f == 'bb_pos':
                ma = df['close'].rolling(20).mean()
                std = df['close'].rolling(20).std()
                df['bb_pos'] = (df['close'] - (ma - 2*std)) / (4*std + 1e-9)
            
            elif f == 'macd_norm':
                e12 = df['close'].ewm(span=12, adjust=False).mean()
                e26 = df['close'].ewm(span=26, adjust=False).mean()
                df['macd_norm'] = (e12 - e26) / (df['close'] + 1e-9)
            
            # Volatility
            elif f == 'volatility':
                df['volatility'] = df['close'].pct_change().rolling(20).std()
            elif f == 'vol_change':
                v = df['close'].pct_change().rolling(20).std()
                df['vol_change'] = v.pct_change()
            elif f == 'rsi_slope':
                if 'rsi' not in df.columns: df['rsi'] = FeatureFactory._rsi(df['close'])
                df['rsi_slope'] = df['rsi'].diff(3)
            elif f == 'momentum':
                df['momentum'] = df['close'].pct_change(5)
            
            # Candle Morphology
            elif f == 'body_ratio':
                 df['body_ratio'] = (df['close'] - df['open']).abs() / (df['high'] - df['low'] + 1e-9)
            elif f == 'wick_ratio':
                 u = (df['high'] - df[['open', 'close']].max(axis=1))
                 l = (df[['open', 'close']].min(axis=1) - df['low'])
                 df['wick_ratio'] = u / (l + 1e-9)
            elif f == 'body_size': df['body_size'] = (df['close'] - df['open']).abs() / (df['close'] + 1e-6)
            elif f == 'upper_wick': df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['close'] + 1e-6)
            elif f == 'lower_wick': df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / (df['close'] + 1e-6)
            
            # Special & Structural
            elif f == 'regime_flag':
                re = MarketRegimeEngine()
                df = re.classify(df)
            elif f == 'atr_norm' or f == 'atr_pct':
                df[f] = FeatureFactory._atr(df, 14) / (df['close'] + 1e-6)
            elif f == 'sqz_gate':
                ma = df['close'].rolling(100).mean()
                std = df['close'].rolling(100).std()
                bw = (4 * std) / (ma + 1e-6)
                df['sqz_gate'] = (bw > bw.rolling(100).mean()).astype(int)
            elif f == 'vol_20':
                df['vol_20'] = df['close'].rolling(20).std()
            elif f == 'vol_regime':
                v20 = df['close'].rolling(20).std()
                df['vol_regime'] = (v20 / (v20.rolling(200).mean() + 1e-6)).fillna(1.0)
            elif f in ['is_london', 'is_ny', 'is_peak', 'is_peak_hour', 'session_london', 'session_ny']:
                hour = df['date'].dt.hour
                df['is_london'] = ((hour >= 8) & (hour <= 16)).astype(int)
                df['is_ny'] = ((hour >= 13) & (hour <= 21)).astype(int)
                df['session_london'] = df['is_london']
                df['session_ny'] = df['is_ny']
                df['is_peak'] = ((hour >= 7) & (hour <= 21)).astype(int)
                df['is_peak_hour'] = df['is_peak']
            elif f == 'velocity':
                v20 = df['close'].rolling(20).std()
                df['velocity'] = df['close'].diff(5) / (v20 + 1e-9)
            elif f == 'coiling':
                ma = df['close'].rolling(20).mean()
                std = df['close'].rolling(20).std()
                bw = (4 * std) / (ma + 1e-6)
                df['coiling'] = bw / (bw.rolling(50).mean() + 1e-6)
            elif f == 'price_dist_bb':
                ma = df['close'].rolling(20).mean()
                df['price_dist_bb'] = (df['close'] - ma) / (ma + 1e-6)
            elif f == 'div_proxy':
                pv = df['close'].diff(5) / (df['close'].shift(5) + 1e-6)
                rv = FeatureFactory._rsi(df['close']).diff(5) / 100.0
                df['div_proxy'] = pv - rv
            elif f == 'ribbon_align':
                align = 0
                for s in [9, 21, 50, 100, 200]:
                    ema = df['close'].ewm(span=s, adjust=False).mean()
                    align += np.sign((df['close'] - ema) / (ema + 1e-6))
                df['ribbon_align'] = align / 5.0
            elif f == 'trend_harmony':
                e12 = df['close'].ewm(span=12, adjust=False).mean()
                e26 = df['close'].ewm(span=26, adjust=False).mean()
                m_norm = (e12 - e26) / (df['close'] + 1e-6)
                df['trend_harmony'] = (
                    np.sign(m_norm) + 
                    np.sign(df.get('macd_m30', 0)) + 
                    np.sign(df.get('macd_h1', 0))
                ) / 3.0
            
            elif f == 'rel_range':
                df['rel_range'] = (df['high'] - df['low']) / (df['close'] + 1e-6)
            elif f == 'stoch_k':
                low_14 = df['low'].rolling(14).min()
                high_14 = df['high'].rolling(14).max()
                df['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14 + 1e-6)
            elif f == 'news_sentiment' or f == 'news_impact_score':
                df[f] = 0.0

        return df.dropna()

    @staticmethod
    def _rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(df, period=14):
        h_l = df['high'] - df['low']
        h_pc = (df['high'] - df['close'].shift()).abs()
        l_pc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        return tr.rolling(period).mean()

# --- Institutional Export Manager ---
class ExportManager:
    @staticmethod
    def save(model_name, res, survival, params):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = model_name.replace(".pkl", "")
        base_path = os.path.join(os.getcwd(), 'backend', 'results', f"{clean_name}_{timestamp}")
        os.makedirs(base_path, exist_ok=True)
        
        # 1. Detailed JSON Report
        report = {
            "model": model_name,
            "params": params,
            "metrics": {
                "net_profit": res['net_profit'],
                "net_profit_pct": res['net_profit_pct'],
                "max_drawdown": res['max_drawdown'],
                "profit_factor": res['profit_factor'],
                "win_rate": res['win_rate'],
                "total_trades": res['total_trades'],
                "wins": res['win_count'],
                "losses": res['loss_count'],
                "max_win": res['max_win'],
                "max_loss": res['max_loss'],
                "avg_trades_per_day": res['avg_trades_day'],
                "survival_prob": survival,
                "sharpe": res.get('sharpe', 0),
                "calmar": res.get('calmar', 0),
                "equity_curve": res.get('equity_curve', [])
            },
            "monthly": res.get('monthly_breakdown', {})
        }
        
        with open(os.path.join(base_path, "Full_Report.json"), "w") as f:
            json.dump(report, f, indent=4)
            
        # 2. Complete Trade Log (CSV)
        trades_df = pd.DataFrame(res['trades'])
        if not trades_df.empty:
            trades_df.to_csv(os.path.join(base_path, "Trade_Log.csv"), index=False)
            
        # 3. Executive Summary (TXT) - Beautifully Formatted
        with open(os.path.join(base_path, "Summary.txt"), "w", encoding='utf-8') as f:
            f.write(f"🦁 GIA EXECUTIVE PERFORMANCE REPORT\n")
            f.write(f"Model: {model_name}\n")
            f.write("="*60 + "\n")
            
            f.write(f"CORE PARAMETERS:\n")
            f.write(f"  Period:   {params['start']} to {params['end']}\n")
            f.write(f"  Timeframe: {params['tf']}\n")
            f.write(f"  Broker:    {params['broker']}\n")
            f.write(f"  MM Mode:   {params.get('mode', 'dynamic').upper()}\n")
            risk_val = params['risk']
            risk_str = f"{risk_val}%" if isinstance(risk_val, (int, float)) else str(risk_val)
            f.write(f"  Risk/Size: {risk_str}\n")
            f.write("-" * 60 + "\n")
            
            f.write(f"KEY PERFORMANCE METRICS:\n")
            f.write(f"  Net Profit:     ${res['net_profit']:,.2f} ({res['net_profit_pct']:.2f}%)\n")
            f.write(f"  Max Drawdown:   {res['max_drawdown']:.2f}%\n")
            f.write(f"  Profit Factor:  {res['profit_factor']:.2f}\n")
            f.write(f"  Win Rate:       {res['win_rate']:.1f}%\n")
            f.write(f"  Survival (MC):  {survival:.1f}% {'[ELITE]' if survival > 90 else '[RISKY]'}\n")
            f.write("-" * 60 + "\n")
            
            f.write(f"TRADE ANALYSIS:\n")
            f.write(f"  Total Trades:   {res['total_trades']}\n")
            f.write(f"  Wins/Losses:    {res['win_count']} Wins / {res['loss_count']} Losses\n")
            f.write(f"  Daily Frequency: {res['avg_trades_day']:.2f} trades/day\n")
            f.write(f"  Largest Win:    ${res['max_win']:,.2f}\n")
            f.write(f"  Largest Loss:   ${res['max_loss']:,.2f}\n")
            f.write("-" * 60 + "\n")
            
            f.write(f"ANALYTICS & RATIOS:\n")
            f.write(f"  Sharpe Ratio:   {res.get('sharpe', 0):.2f}\n")
            f.write(f"  Calmar Ratio:   {res.get('calmar', 0):.2f}\n")
            f.write("-" * 60 + "\n")
            
            f.write(f"MONTHLY PERFORMANCE:\n")
            monthly = res.get('monthly_breakdown', {})
            for m, pnl in monthly.items():
                f.write(f"  {m:<10}: ${pnl:>10,.2f}\n")
                
            f.write("\n" + "="*60 + "\n")
            f.write(f"📁 FULL ASSETS SAVED AT:\n")
            f.write(f"Log:    Trade_Log.csv\n")
            f.write(f"Data:   Full_Report.json\n")
            f.write("="*60 + "\n")
            
        return base_path

# --- Battle Ground Engine ---
class BattleArena:
    def __init__(self):
        self.data_dir = os.path.join(os.getcwd(), 'backend', 'hestory')
        self.models_dir = os.path.join(os.getcwd(), 'backend', 'models')
        self.pro_models_dir = os.path.join(os.getcwd(), 'GIA_SIGNAL_PRO', 'models')
        self.cache = {}

    def _calculate_extended_stats(self, res):
        trades = pd.DataFrame(res['trades'])
        if trades.empty:
            res.update({'win_count':0,'loss_count':0,'max_win':0,'max_loss':0,'avg_trades_day':0})
            return res
        
        res['win_count'] = len(trades[trades['pnl_net'] > 0])
        res['loss_count'] = len(trades[trades['pnl_net'] <= 0])
        res['max_win'] = trades['pnl_net'].max()
        res['max_loss'] = trades['pnl_net'].min()
        
        # Frequency
        trades['entry_date'] = pd.to_datetime(trades['entry_date'])
        days_active = (trades['entry_date'].max() - trades['entry_date'].min()).days or 1
        res['avg_trades_day'] = len(trades) / days_active
        
        # Financial Ratios
        daily = trades.set_index('entry_date')['pnl_net'].resample('D').sum()
        std = daily.std()
        res['sharpe'] = (daily.mean() / std * np.sqrt(252)) if std > 0 else 0
        res['calmar'] = (res['net_profit_pct'] / res['max_drawdown']) if res['max_drawdown'] > 0 else 0
        
        return res

    def start(self, cli_args=None):
        print_banner()
        
        if cli_args:
            targets = [m for m in os.listdir(self.models_dir) if m.endswith('.pkl')] if cli_args.compare else [cli_args.model]
            tf = "M15"
            broker = cli_args.broker
            capital = cli_args.capital
            risk = cli_args.risk
            sizing_mode = cli_args.mode
            fixed_lot = cli_args.lots
            start_y = cli_args.from_year
            end_y = cli_args.to_year + 1
        else:
            # --- PROFESSIONAL DASHBOARD REPLACEMENT ---
            # 1. Model Selection
            print(f"\n {Fore.YELLOW}STEP 1: SELECT YOUR AI MODEL{Style.RESET_ALL}")
            
            # Combine models from both directories
            models_main = sorted([f for f in os.listdir(self.models_dir) if f.endswith('.pkl')])
            models_pro = sorted([f for f in os.listdir(self.pro_models_dir) if f.endswith('.pkl')]) if os.path.exists(self.pro_models_dir) else []
            
            # Store full paths associated with filenames
            self.model_paths = {m: os.path.join(self.models_dir, m) for m in models_main}
            for m in models_pro:
                self.model_paths[m] = os.path.join(self.pro_models_dir, m)
            
            all_models = sorted(list(self.model_paths.keys()))
            
            for i, m in enumerate(all_models):
                dir_label = "[PRO]" if m in models_pro else "[CORE]"
                print(f"  [{Fore.GREEN}{i+1}{Style.RESET_ALL}] {m:<25} {Fore.LIGHTBLACK_EX}{dir_label}{Style.RESET_ALL}")
            print(f"  [{Fore.GREEN}A{Style.RESET_ALL}] COMPARE ALL MODELS")
            
            choice = input(f"\n {Fore.WHITE}Enter Selection > {Style.RESET_ALL}").strip().upper()
            targets = all_models if choice == 'A' else [all_models[int(choice)-1]] if (choice.isdigit() and int(choice) <= len(all_models)) else [all_models[0]]

            # 2. Timeframe
            print(f"\n {Fore.YELLOW}STEP 2: SELECT EXECUTION TIMEFRAME{Style.RESET_ALL}")
            print(f"  [{Fore.GREEN}0{Style.RESET_ALL}] M1 (Scalping)   [{Fore.GREEN}1{Style.RESET_ALL}] M15 (Tactical)  [{Fore.GREEN}2{Style.RESET_ALL}] M30 (Balanced)  [{Fore.GREEN}3{Style.RESET_ALL}] H1 (Strategic)")
            tf_choice = input(f"\n {Fore.WHITE}Enter Selection [Default M15] > {Style.RESET_ALL}").strip() or "1"
            tf = {"0":"M1", "1":"M15", "2":"M30", "3":"H1"}.get(tf_choice, "M15")

            # 3. Environment & Risk (Streamlined)
            print(f"\n {Fore.YELLOW}STEP 3: BROKER PHYSICS{Style.RESET_ALL}")
            brokers = list(BrokerSimulator.PROFILES.keys())
            for i, b in enumerate(brokers):
                display_name = f"{b} (Default)" if b == "FIPER" else b
                color = Fore.CYAN if b == "FIPER" else Fore.WHITE
                print(f"  [{Fore.GREEN}{i+1}{Style.RESET_ALL}] {color}{display_name:12}{Style.RESET_ALL}", end=" " if (i+1)%3 != 0 else "\n")
            
            b_choice = input(f"\n\n {Fore.WHITE}Select Broker [Enter for FIPER] > {Style.RESET_ALL}").strip()
            broker = brokers[int(b_choice)-1] if (b_choice.isdigit() and int(b_choice) <= len(brokers)) else "FIPER"
            
            # 4. Money Management
            print(f"\n {Fore.YELLOW}STEP 4: POSITION SIZING MODE{Style.RESET_ALL}")
            print(f"  [{Fore.GREEN}1{Style.RESET_ALL}] DYNAMIC RISK (%)  [{Fore.GREEN}2{Style.RESET_ALL}] FIXED LOT")
            mm_choice = input(f"\n {Fore.WHITE}Select Mode [1] > {Style.RESET_ALL}").strip() or "1"
            sizing_mode = "dynamic" if mm_choice == "1" else "fixed"
            fixed_lot = 0.01
            if sizing_mode == "fixed":
                 fixed_lot = float(input(f"  {Fore.WHITE}Fixed Lot Size [0.01] > {Style.RESET_ALL}") or 0.01)

            # 5. Environment Config
            print(f"\n {Fore.YELLOW}STEP 5: SIMULATION PARAMS{Style.RESET_ALL}")
            print(f"  [{Fore.GREEN}Q{Style.RESET_ALL}] QUICK (2024, $10k, 1% Risk)")
            print(f"  [{Fore.GREEN}C{Style.RESET_ALL}] CUSTOM (Manual Entry)")
            cfg_choice = input(f"\n {Fore.WHITE}Choice [Q] > {Style.RESET_ALL}").strip().upper() or "Q"
            
            risk = 1.0
            capital = 10000.0
            start_y, end_y = 2024, 2025
            
            if cfg_choice == "C":
                capital = float(input(f"  {Fore.WHITE}Balance > {Style.RESET_ALL}") or 10000)
                if sizing_mode == "dynamic":
                    risk = float(input(f"  {Fore.WHITE}Risk % > {Style.RESET_ALL}") or 1.0)
                else:
                    risk = 1.0 # Default fallback, not used for fixed
                start_y = int(input(f"  {Fore.WHITE}Start Year > {Style.RESET_ALL}") or 2024)
                end_y = int(input(f"  {Fore.WHITE}End Year > {Style.RESET_ALL}") or 2025)
                end_y += 1

            print(f"\n{Fore.GREEN}⚡ Initializing GIA Battle Arena... Engines Warming Up...{Style.RESET_ALL}\n")

        # --- Consensus Mode Dispatch ---
        if getattr(cli_args, 'mode', '') == 'consensus':
            self._run_consensus(cli_args)
            return

        # Execution
        final_table = []
        for m_name in targets:
            print_separator("-", color=Fore.LIGHTBLACK_EX)
            print(f"🦁 {Fore.WHITE}ENGINEERING: {Fore.YELLOW}{m_name}{Style.RESET_ALL} | {Fore.CYAN}{tf}{Style.RESET_ALL}")
            
            try:
                # Resolve Path
                if hasattr(self, 'model_paths'):
                    path = self.model_paths.get(m_name, os.path.join(self.models_dir, m_name))
                else:
                    # Fallback for CLI args
                    path = os.path.join(self.pro_models_dir, m_name) if 'SIGNAL_PRO' in m_name else os.path.join(self.models_dir, m_name)
                
                m_data = joblib.load(path)
                req_feats = m_data.get('feature_columns', m_data.get('features', []))
                
                # Intelligent Timeframe Detection: if SIGNAL_PRO is used, M1 is usually the core.
                if 'SIGNAL_PRO' in m_name and not cli_args:
                    tf = "M1"
                
                # Data Load
                # GIA_SIGNAL_PRO needs m5, m15, h1 context
                needs_mtf = any(('_h1' in f or '_m15' in f or '_m5' in f or '_m30' in f or 'trend_harmony' in f) for f in req_feats)
                df = self._load_data(tf, needs_mtf)
                df = df[(df['date'].dt.year >= start_y) & (df['date'].dt.year <= end_y)].copy()
                
                if len(df) < 100:
                    print(f"   {Fore.RED}❌ Insufficient data for {start_y}-{end_y} period.{Style.RESET_ALL}")
                    continue
                
                # Sim
                df_proc = FeatureFactory.construct(df, req_feats)
                
                # Diagnostic: Check if all required features are present
                missing = [f for f in req_feats if f not in df_proc.columns]
                if missing:
                    print(f"   {Fore.RED}⚠️  Missing Features: {missing}{Style.RESET_ALL}")
                
                is_legacy = "v14" in m_name
                engine = BacktestEngine(model_path=path, is_legacy=is_legacy)
                engine.load_model()
                
                # Base Sim
                res = engine.backtest(df_proc, broker_name=broker, initial_balance=capital, risk_pct=risk, 
                                      sizing_mode=sizing_mode, fixed_lot_size=fixed_lot)
                if "error" in res:
                    print(f"   {Fore.RED}❌ Simulation Failed: {res['error']}{Style.RESET_ALL}")
                    if "diagnostic" in res:
                        diag = res['diagnostic']
                        print(f"      {Fore.WHITE}Signals Received: {diag['signals_received']}")
                        if diag.get('reasons'):
                            print(f"      {Fore.WHITE}Rejection Breakdown:")
                            for reason, count in diag['reasons'].items():
                                print(f"        - {reason}: {count} times")
                    continue

                if res.get('simulation_error'):
                    print(f"   {Fore.RED}⚠️  Critical Alert: {res['simulation_error']}{Style.RESET_ALL}")
                
                # Advanced Metrics
                res = self._calculate_extended_stats(res)
                
                # Stress
                print(f"   🎲 Stress Testing (Monte Carlo)...")
                mc_pnl = []
                for _ in range(5):
                    rmc = engine.backtest(df_proc, broker_name=broker, risk_pct=risk, initial_balance=capital,
                                          sizing_mode=sizing_mode, fixed_lot_size=fixed_lot)
                    if "error" not in rmc: mc_pnl.append(rmc['net_profit_pct'])
                survival = (len([p for p in mc_pnl if p > 0]) / len(mc_pnl)) * 100 if mc_pnl else 0
                
                # Export
                p_meta = {
                    "tf": tf, 
                    "broker": broker, 
                    "start": start_y, 
                    "end": end_y, 
                    "risk": risk if sizing_mode == 'dynamic' else f"FIXED {fixed_lot}",
                    "mode": sizing_mode
                }
                save_path = ExportManager.save(m_name, res, survival, p_meta)
                
                # UI Result
                print_ascii_chart(res['equity_curve'], title=f"GIA Elite Bench: {m_name}")
                
                # Visual Win/Loss Bar
                w, l = res['win_count'], res['loss_count']
                total = w + l
                w_bar = int((w/total)*40) if total > 0 else 0
                l_bar = 40 - w_bar
                print(f" {Fore.WHITE}Trade Distribution:{Style.RESET_ALL}")
                print(f"  [{Fore.GREEN}{'█'*w_bar}{Fore.RED}{'█'*l_bar}{Fore.WHITE}] {w}W / {l}L")

                print(f"\n {Fore.CYAN}--- INSTITUTIONAL SCORECARD ---{Style.RESET_ALL}")
                print(f"  {Fore.WHITE}Net Profit:    {Fore.GREEN if res['net_profit']>=0 else Fore.RED}${res['net_profit']:,.2f} ({res['net_profit_pct']:.2f}%){Style.RESET_ALL}")
                print(f"  {Fore.WHITE}Profit Factor: {Fore.YELLOW}{res['profit_factor']:.2f}{Style.RESET_ALL}  |  {Fore.WHITE}Win Rate:  {res['win_rate']:.1f}%{Style.RESET_ALL}")
                print(f"  {Fore.WHITE}Max Drawdown:  {Fore.RED}{res['max_drawdown']:.2f}%{Style.RESET_ALL}  |  {Fore.WHITE}Sharpe:    {res.get('sharpe',0):.2f}{Style.RESET_ALL}")
                print(f"  {Fore.WHITE}Largest Win:   {Fore.GREEN}${res['max_win']:,.2f}{Style.RESET_ALL} | {Fore.WHITE}Largest Loss: {Fore.RED}${res['max_loss']:,.2f}{Style.RESET_ALL}")
                print(f"  {Fore.WHITE}Daily Avg:     {res['avg_trades_day']:.2f} trades/day{Style.RESET_ALL}")
                print(f"  {Fore.WHITE}Survival Prob: {Fore.GREEN if survival > 80 else Fore.RED}{survival:.1f}% (MC Stress Test){Style.RESET_ALL}")
                print(f"  {Fore.MAGENTA}📁 Results Dir: {save_path}{Style.RESET_ALL}")
                
                final_table.append({
                    "Model": m_name, "PF": res['profit_factor'], "DD": res['max_drawdown'],
                    "ROI%": res['net_profit_pct'], "Surv%": survival, "AvgWin": res['max_win']/res['win_count'] if res['win_count']>0 else 0
                })

            except Exception as e:
                print(f"   {Fore.RED}❌ Crash: {e}{Style.RESET_ALL}")
                traceback.print_exc()

        if len(final_table) > 1: self._print_scoreboard(final_table)

    def _load_data(self, primary_tf, needs_multi):
        key = f"{primary_tf}_{'MTF' if needs_multi else 'STF'}"
        if key in self.cache: return self.cache[key]
        
        print(f"   📂 Loading {primary_tf} History...")
        df_p = self._read_csv(f'XAUUSD_{primary_tf}.csv')
        if needs_multi:
            # Context list depends on what's available and needed
            contexts = []
            if primary_tf != "M5": contexts.append(('m5', 'XAUUSD_M1.csv')) # M1 resampled to M5
            if primary_tf != "M15": contexts.append(('m15', 'XAUUSD_M15.csv'))
            if primary_tf not in ["M30", "M30"]: contexts.append(('m30', 'XAUUSD_M30.csv'))
            if primary_tf != "H1": contexts.append(('h1', 'XAUUSD_H1.csv'))
            
            merged = df_p.sort_values('date')
            for suffix, filename in contexts:
                try:
                    if suffix == 'm5' and filename == 'XAUUSD_M1.csv':
                        # Special Resample for M1 to M5
                        df_m1 = self._read_csv(filename)
                        df_sec = df_m1.set_index('date').resample('5min').agg({
                            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                        }).dropna().reset_index()
                    else:
                        df_sec = self._read_csv(filename)
                    
                    eng_sec = self._engineer_secondary(df_sec, suffix)
                    merged = pd.merge_asof(merged, eng_sec.sort_values('date'), on='date', direction='backward')
                except Exception as e:
                    print(f"   ⚠️  Could not load context {suffix}: {e}")
            
            self.cache[key] = merged.dropna()
        else:
            self.cache[key] = df_p
            
        return self.cache[key]

    def _read_csv(self, name):
        df = pd.read_csv(os.path.join(self.data_dir, name))
        df.columns = [c.lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['time'], format='%m/%d/%Y %I:%M:%S %p')
        return df

    def _engineer_secondary(self, df, suffix):
        df = df.copy()
        df[f'rsi_{suffix}'] = FeatureFactory._rsi(df['close'])
        e12 = df['close'].ewm(span=12, adjust=False).mean()
        e26 = df['close'].ewm(span=26, adjust=False).mean()
        df[f'macd_{suffix}'] = (e12 - e26) / (df['close'] + 1e-9)
        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df[f'bbw_{suffix}'] = (4 * std) / (ma + 1e-9)
        df[f'vol_{suffix}'] = df['close'].pct_change().rolling(20).std()
        
        # Trend detection logic
        if suffix == 'h1':
            ema200 = df['close'].ewm(span=200, adjust=False).mean()
            df[f'ema_dist_h1'] = (df['close'] - ema200) / (df['close'] + 1e-9)
            df['mom_h1'] = df['close'].diff(4) / (df['close'] + 1e-9)
            df['trend_h1'] = np.where(df['close'] > ema200, 1, -1)
        else:
            # Generic trend for M30, M15, M5
            ma20 = df['close'].rolling(20).mean()
            df[f'trend_{suffix}'] = np.where(df['close'] > ma20, 1, -1)
            
        return df[['date'] + [c for c in df.columns if c.endswith(suffix)]]

    def _run_consensus(self, args):
        print(f"{Fore.CYAN}🦁 GIA TRIPLE CONSENSUS ACTIVATED{Style.RESET_ALL}")
        print(f" Models: {Fore.YELLOW}v14_PRO (Risk) + v2_PRO (Core) + v2_FLASH (Tactical){Style.RESET_ALL}")
        
        # 1. Load Models with smarter mapping
        try:
            # Flexible mapping
            model_map = {
                'v14': 'GIA_v14_PRO.pkl',
                'v2': 'GIA_v2_PRO.pkl',
                'v2_pro': 'GIA_v2_PRO.pkl',
                'flash': 'GIA_v2_FLASH.pkl',
                'v2_flash': 'GIA_v2_FLASH.pkl'
            }
            
            # Use provided models or defaults
            m_list = args.models.split(',') if getattr(args, 'models', None) else ['v14', 'v2', 'flash']
            actual_files = [model_map.get(m.lower().strip(), m if m.endswith('.pkl') else f"{m}.pkl") for m in m_list]
            
            # Ensure we have the big three
            m14_file = next((f for f in actual_files if 'v14' in f.lower()), 'GIA_v14_PRO.pkl')
            m2p_file = next((f for f in actual_files if ('v2' in f.lower() and 'flash' not in f.lower())), 'GIA_v2_PRO.pkl')
            m2f_file = next((f for f in actual_files if 'flash' in f.lower()), 'GIA_v2_FLASH.pkl')

            m14 = joblib.load(os.path.join(self.models_dir, m14_file))
            m2p = joblib.load(os.path.join(self.models_dir, m2p_file))
            m2f = joblib.load(os.path.join(self.models_dir, m2f_file))
            
            print(f" 🧠 Brains: {m14_file} | {m2p_file} | {m2f_file}")
        except Exception as e:
            print(f"{Fore.RED}❌ Error loading models for consensus: {e}{Style.RESET_ALL}")
            return

        # 2. Sync Features
        all_req = sorted(list(set(m14['feature_columns'] + m2p['feature_columns'] + m2f['feature_columns'])))
        needs_multi = any(('_h1' in f or '_m30' in f or f == 'trend_harmony') for f in all_req)
        df_base = self._load_data("M15", needs_multi)
        df = df_base[(df_base['date'].dt.year >= args.from_year) & (df_base['date'].dt.year <= args.to_year)].copy()
        df_proc = FeatureFactory.construct(df, all_req)
        
        # 3. Generate Signals
        print(f" ⏳ Synchronizing Decision Brains...")
        p14 = m14['model'].predict(df_proc[m14['feature_columns']])
        # p14 mapping: 0=WAIT, 1=BUY, 2=SELL
        
        pr2p = m2p['model'].predict_proba(df_proc[m2p['feature_columns']])
        s2p = m2p['label_encoder'].inverse_transform(np.argmax(pr2p, axis=1))
        c2p = np.max(pr2p, axis=1)
        
        pr2f = m2f['model'].predict_proba(df_proc[m2f['feature_columns']])
        s2f = m2f['label_encoder'].inverse_transform(np.argmax(pr2f, axis=1))
        c2f = np.max(pr2f, axis=1)
        
        # Logic Loop
        final_labels = []
        final_probs = []
        final_sizing = []
        
        for i in range(len(df_proc)):
            v14_sig = p14[i]
            v2p_sig = s2p[i]
            v2f_sig = s2f[i]
            
            # Consensus Logic
            sig = 'WAIT'
            prob = 0.0
            size = 1.0
            
            # Rule 1 & 4 (Risk Veto & Conflict)
            # v14 blocks if it doesn't agree with the direction
            v14_allows_buy = (v14_sig == 1)
            v14_allows_sell = (v14_sig == 2)
            
            if v2p_sig == 'BUY' and v14_allows_buy:
                if v2f_sig == 'BUY':
                    # Rule 2: Full Agreement
                    if (c2p[i] + c2f[i])/2.0 >= 0.6:
                        sig, prob, size = 'BUY', (c2p[i] + c2f[i])/2.0, 1.0
                elif v2f_sig == 'WAIT':
                    # Rule 3: Assisted Entry
                    if c2p[i] >= 0.65:
                        sig, prob, size = 'BUY', c2p[i], 0.5
            
            elif v2p_sig == 'SELL' and v14_allows_sell:
                if v2f_sig == 'SELL':
                    # Rule 2: Full Agreement
                    if (c2p[i] + c2f[i])/2.0 >= 0.6:
                        sig, prob, size = 'SELL', (c2p[i] + c2f[i])/2.0, 1.0
                elif v2f_sig == 'WAIT':
                    # Rule 3: Assisted Entry
                    if c2p[i] >= 0.65:
                        sig, prob, size = 'SELL', c2p[i], 0.5
            
            final_labels.append(sig)
            final_probs.append(prob)
            final_sizing.append(size)
            
        # 4. Simulate
        print(f" 🏹 Executing Combined Campaign...")
        engine = BacktestEngine(model_path=os.path.join(self.models_dir, 'GIA_v2_PRO.pkl'))
        engine.load_model()
        
        ext = {'labels': final_labels, 'probs': final_probs, 'sizing': final_sizing}
        res = engine.backtest(df_proc, broker_name=args.broker, initial_balance=args.capital, 
                              risk_pct=args.risk, sizing_mode=args.mode if args.mode != 'consensus' else 'dynamic',
                              fixed_lot_size=args.lots, external_signals=ext)
        
        if "error" in res:
            print(f" {Fore.RED}❌ Consensus Failed: {res['error']}{Style.RESET_ALL}")
            return
            
        res = self._calculate_extended_stats(res)
        
        # 5. Dedicated Report
        print("\n" + Fore.MAGENTA + "╔" + "═"*78 + "╗")
        print(f"║ {'🦁 GIA CONSENSUS PERFORMANCE REPORT':^76} ║")
        print("╠" + "═"*78 + "╣" + Style.RESET_ALL)
        print(f"  {Fore.WHITE}Models: v14_PRO + v2_PRO + v2_FLASH | Mode: Triple Consensus{Style.RESET_ALL}")
        print(f"  ---")
        print(f"  {Fore.WHITE}Net Profit:    {Fore.GREEN if res['net_profit']>=0 else Fore.RED}${res['net_profit']:,.2f} ({res['net_profit_pct']:.2f}%){Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Max Drawdown:  {Fore.RED}{res['max_drawdown']:.2f}%{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Win Rate:      {res['win_rate']:.1f}% | PF: {res['profit_factor']:.2f}{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Trade Count:   {res['total_trades']} | Sharpe: {res.get('sharpe',0):.2f}{Style.RESET_ALL}")
        print(Fore.MAGENTA + "╚" + "═"*78 + "╝" + Style.RESET_ALL)

        # 6. Comparison Section
        print(f"\n {Fore.CYAN}⚖️  SIDE-BY-SIDE BENCHMARK:{Style.RESET_ALL}")
        comparisons = []
        for m_name in ['GIA_v14_PRO.pkl', 'GIA_v2_PRO.pkl', 'GIA_v2_FLASH.pkl']:
            path = os.path.join(self.models_dir, m_name)
            eng = BacktestEngine(model_path=path, is_legacy='v14' in m_name)
            eng.load_model()
            r = eng.backtest(df_proc, broker_name=args.broker, initial_balance=args.capital, risk_pct=args.risk)
            if "error" not in r:
                r = self._calculate_extended_stats(r)
                comparisons.append({"Model": m_name, "ROI": r['net_profit_pct'], "PF": r['profit_factor'], "DD": r['max_drawdown']})
        
        comparisons.append({"Model": "TRIPLE_CONSENSUS", "ROI": res['net_profit_pct'], "PF": res['profit_factor'], "DD": res['max_drawdown']})
        
        # Print Tiny Table
        print(f"  {Fore.WHITE}{'Model':<20} | {'ROI%':<10} | {'PF':<8} | {'MDD%'}")
        for c in comparisons:
            color = Fore.YELLOW if c['Model'] == 'TRIPLE_CONSENSUS' else Fore.WHITE
            print(f"  {color}{c['Model'][:18]:<20} | {c['ROI']:<10.1f} | {c['PF']:<8.2f} | {c['DD']:.1f}%")

    def _print_scoreboard(self, scores):
        print("\n" + Fore.YELLOW + "="*80)
        print(f"{'🏆 GIA PRO BATTLEGROUND LEADERBOARD':^80}")
        print("="*80 + Style.RESET_ALL)
        print(f"{Fore.CYAN}{'Model Name':<25} | {'PF':<8} | {'MDD%':<8} | {'ROI%':<10} | {'Surv%':<8} | {'AvgWin':<10}")
        print("-" * 80 + Style.RESET_ALL)
        for s in sorted(scores, key=lambda x: x['PF'], reverse=True):
            print(f"{Fore.WHITE}{s['Model']:<25}{Style.RESET_ALL} | {s['PF']:<8.2f} | {s['DD']:<8.2f} | {s['ROI%']:<10.2f} | {s['Surv%']:<8.1f} | ${s['AvgWin']:<10.2f}")
        print(Fore.YELLOW + "="*80 + Style.RESET_ALL + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--model', type=str)
    parser.add_argument('--from_year', type=int, default=2023)
    parser.add_argument('--to_year', type=int, default=2025)
    parser.add_argument('--broker', type=str, default='FIPER')
    parser.add_argument('--risk', type=float, default=1.0)
    parser.add_argument('--capital', type=float, default=1000.0)
    parser.add_argument('--mode', type=str, choices=['dynamic', 'fixed', 'consensus'], default='dynamic')
    parser.add_argument('--lots', type=float, default=0.01)
    args = parser.parse_args()
    
    BattleArena().start(cli_args=args if (args.model or args.compare or args.mode == 'consensus') else None)
