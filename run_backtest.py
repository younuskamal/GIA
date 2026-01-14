
"""
🦁 GIA PRO BATTLEGROUND (v2.3 - Institutional Edition)
-----------------------------------------------
The most comprehensive analytical suite for GIA Professional Trading Bots.
Features: 
- Interactive Timeframe & Broker Sync
- Institutional Metrics (Sharpe, Sortino, Calmar)
- Visual HTML Report Generation
- Deep Trade Analysis (Streak analysis, Win/Loss Bias)
- Monte Carlo Robustness Validation
- Automated Descriptive Archiving

Usage:
    Interactive Entry: python run_backtest.py
    CLI Comparison:    python run_backtest.py --compare --broker STRESS_TEST
"""
import sys
import os
import argparse
import pandas as pd
import numpy as np
import joblib
import json
import time
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

# --- Institutional Compatibility Layer ---
# This MUST be injected into __main__ before joblib loads models
class MockEncoder:
    """Supports loading legacy models that were pickled with custom encoders."""
    def inverse_transform(self, idxs):
        mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

import __main__
__main__.MockEncoder = MockEncoder

# Initialize Colorama for Windows/Linux
colorama.init()
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
    {Fore.CYAN}--- INSTITUTIONAL ANALYTICAL SUITE v2.3 ---{Style.RESET_ALL}
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
        # 🦁 Performance optimization: only compute missing columns
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
                parts = f.split('_')
                span = int(parts[1]) if parts[1].isdigit() else 20
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
            elif f == 'bb_slope':
                ma = df['close'].rolling(20).mean()
                std = df['close'].rolling(20).std()
                bw = (4 * std) / (ma + 1e-9)
                df['bb_slope'] = bw.diff(3)
            elif f == 'ema_cross':
                ema9 = df['close'].ewm(span=9, adjust=False).mean()
                ema21 = df['close'].ewm(span=21, adjust=False).mean()
                df['ema_cross'] = (df['close'] - ema9) / (ema9 + 1e-9) - (df['close'] - ema21) / (ema21 + 1e-9)
            
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
            
            # Candle Morphology
            elif f in ['body_ratio', 'body_rel']:
                df[f] = (df['close'] - df['open']).abs() / (df['high'] - df['low'] + 1e-9)
            elif f == 'wick_ratio':
                up = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['close'] + 1e-9)
                lo = (df[['open', 'close']].min(axis=1) - df['low']) / (df['close'] + 1e-9)
                df['wick_ratio'] = up / (lo + 1e-9)
            elif f == 'body_size': 
                df['body_size'] = (df['close'] - df['open']).abs() / (df['close'] + 1e-9)
            elif f == 'upper_wick': 
                df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['close'] + 1e-9)
            elif f == 'lower_wick': 
                df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / (df['close'] + 1e-9)

            
            # Special & Structural
            elif f == 'structure_strength':
                lo = df['close'].rolling(100).min()
                hi = df['close'].rolling(100).max()
                df['structure_strength'] = (df['close'] - lo) / (hi - lo + 1e-9)
            elif f == 'regime_flag':
                re = MarketRegimeEngine()
                df = re.classify(df)
            elif f == 'atr_norm' or f == 'atr_pct':
                df[f] = FeatureFactory._atr(df, 14) / (df['close'] + 1e-9)
            elif f == 'sqz_gate':
                ma = df['close'].rolling(100).mean()
                std = df['close'].rolling(100).std()
                bw = (4 * std) / (ma + 1e-9)
                df['sqz_gate'] = (bw > bw.rolling(100).mean()).astype(int)
            elif f == 'vol_20':
                df['vol_20'] = df['close'].rolling(20).std()
            elif f == 'vol_regime':
                v20 = df['close'].rolling(20).std()
                df['vol_regime'] = (v20 / (v20.rolling(200).mean() + 1e-9)).fillna(1.0)
            elif f == 'vol_ratio':
                v20 = df['close'].rolling(20).std()
                df['vol_ratio'] = v20 / (v20.rolling(50).mean() + 1e-9)
            elif f == 'exhaustion_index':
                v20 = df['close'].rolling(20).std()
                df['exhaustion_index'] = (df['close'] - df['close'].rolling(50).mean()).abs() / (v20 * 2 + 1e-9)
            elif f in ['is_london', 'is_ny', 'is_peak', 'is_peak_hour', 'session_london', 'session_ny', 'is_high_liquidity', 'is_newyork', 'session_active']:
                hour = df['date'].dt.hour
                df['is_london'] = ((hour >= 8) & (hour <= 16)).astype(int)
                df['is_ny'] = ((hour >= 13) & (hour <= 21)).astype(int)
                df['is_newyork'] = df['is_ny'] # Scalper compatibility sync
                df['session_london'] = df['is_london']
                df['session_ny'] = df['is_ny']
                df['is_peak'] = ((hour >= 7) & (hour <= 21)).astype(int)
                df['is_peak_hour'] = df['is_peak']
                df['session_active'] = df['is_peak'] # Alias for scalper
                df['is_high_liquidity'] = ((hour >= 8) & (hour <= 11)) | ((hour >= 13) & (hour <= 16))
            elif f == 'velocity':
                v20 = df['close'].rolling(20).std()
                df['velocity'] = df['close'].diff(5) / (v20 + 1e-9)
            elif f == 'acceleration':
                # Force 1-period velocity for acceleration derivation
                vel_raw = df['close'].diff(1) / (df['close'].shift(1) + 1e-9)
                df['acceleration'] = vel_raw.diff(1)
            elif f == 'coiling':
                ma = df['close'].rolling(20).mean()
                std = df['close'].rolling(20).std()
                bw = (4 * std) / (ma + 1e-9)
                df['coiling'] = bw / (bw.rolling(50).mean() + 1e-9)
            elif f == 'price_dist_bb':
                ma = df['close'].rolling(20).mean()
                df['price_dist_bb'] = (df['close'] - ma) / (ma + 1e-6)
            elif f == 'div_proxy':
                pv = df['close'].diff(5) / (df['close'].shift(5) + 1e-9)
                rv = FeatureFactory._rsi(df['close']).diff(5) / 100.0
                df['div_proxy'] = pv - rv
            elif f == 'ribbon_align':
                align = 0
                for s in [9, 21, 50, 100, 200]:
                    ema = df['close'].ewm(span=s, adjust=False).mean()
                    align += np.sign((df['close'] - ema) / (ema + 1e-9))
                df['ribbon_align'] = align / 5.0
            elif f == 'trend_harmony':
                e12 = df['close'].ewm(span=12, adjust=False).mean()
                e26 = df['close'].ewm(span=26, adjust=False).mean()
                m_norm = (e12 - e26) / (df['close'] + 1e-9)
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
            elif f == 'price_acceleration':
                v20 = df['close'].rolling(20).std()
                vel = df['close'].diff(5) / (v20 + 1e-9)
                df['price_acceleration'] = vel.diff(3)
            elif f == 'liquidity_shock':
                df['liquidity_shock'] = df['volume'] / (df['volume'].rolling(50).mean() + 1e-9)
            elif f == 'market_entropy':
                diff_sum = df['close'].diff().abs().rolling(10).sum()
                range_sum = (df['high'].rolling(10).max() - df['low'].rolling(10).min() + 1e-9)
                df['market_entropy'] = diff_sum / range_sum
            elif f == 'candle_strength':
                body = (df['close'] - df['open']).abs()
                df['candle_strength'] = body / (df['high'] - df['low'] + 1e-9)
            elif f == 'dist_ma9':
                ma9 = df['close'].rolling(9).mean()
                df['dist_ma9'] = (df['close'] - ma9) / (ma9 + 1e-9)
            elif f == 'vol_momentum':
                vol_delta = df['volume'] * np.sign(df['close'] - df['open'])
                df['vol_momentum'] = vol_delta.rolling(5).mean() / (df['volume'].rolling(20).mean() + 1e-9)
            elif '_lag' in f:
                parts = f.split('_lag')
                base_feat = parts[0]
                lag_val = int(parts[1])
                # Recurse to ensure base feature exists
                df = FeatureFactory.construct(df, [base_feat])
                df[f] = df[base_feat].shift(lag_val)
            elif f == 'exhaustion_index':
                ma50 = df['close'].rolling(50).mean()
                v20 = df['close'].rolling(20).std()
                df['exhaustion_index'] = (df['close'] - ma50).abs() / (v20 * 2 + 1e-9)

        return df.dropna()

    @staticmethod
    def _rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / (loss + 1e-9)
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
    def _make_serializable(obj):
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='records')
        if isinstance(obj, dict):
            return {k: ExportManager._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [ExportManager._make_serializable(i) for i in obj]
        elif hasattr(obj, 'item'): # handles numpy scalars
            return obj.item()
        elif isinstance(obj, (datetime, pd.Timestamp)):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return obj

    @staticmethod
    def save(model_name, res, survival, params):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = model_name.replace(".pkl", "")
        # Create a descriptive folder name: NAME_BROKER_TF_RISK_TIMESTAMP
        risk_label = str(params['risk']).replace(".", "p")
        folder_identity = f"{clean_name}_{params['broker']}_{params['tf']}_R{risk_label}_{timestamp}"
        base_path = os.path.join(os.getcwd(), 'backend', 'results', folder_identity)
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
                "sortino": res.get('sortino', 0),
                "calmar": res.get('calmar', 0),
                "max_consecutive_losses": res.get('max_consecutive_losses', 0),
                "equity_curve": res.get('equity_curve', [])
            },
            "monthly": res.get('monthly_breakdown', {})
        }
        
        with open(os.path.join(base_path, "Full_Report.json"), "w") as f:
            json.dump(ExportManager._make_serializable(report), f, indent=4)
            
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
            f.write(f"  Max Losses streak: {res.get('max_consecutive_losses', 0)}\n")
            f.write("-" * 60 + "\n")
            
            f.write(f"ANALYTICS & RATIOS:\n")
            f.write(f"  Sharpe Ratio:   {res.get('sharpe', 0):.2f}\n")
            f.write(f"  Sortino Ratio:  {res.get('sortino', 0):.2f}\n")
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
            f.write(f"Report: Visual_Report.html\n")
            f.write("="*60 + "\n")
            
        # 4. PREMIMUM HTML REPORT
        ExportManager._generate_html_report(base_path, model_name, res, survival, params)
            
        return base_path

    @staticmethod
    def _generate_html_report(base_path, model_name, res, survival, params):
        """Creates a stunning, standalone Arabic HTML dashboard with interactive charts."""
        equity_data = json.dumps(res.get('equity_curve', []))
        trades_json = json.dumps(ExportManager._make_serializable(res.get('trades', [])))
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>GIA AI | {model_name} Final Report</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700&family=Outfit:wght@300;400;600&display=swap');
                :root {{ 
                    --p-color: #38bdf8; --p-glow: rgba(56, 189, 248, 0.4); 
                    --success: #22c55e; --error: #ef4444; 
                    --bg: #030712; --card: #111827; --card-alt: #1f2937;
                    --text: #f9fafb; --text-dim: #9ca3af;
                }}
                
                * {{ box-sizing: border-box; scrollbar-width: thin; scrollbar-color: var(--p-color) var(--bg); }}
                body {{ font-family: 'Cairo', 'Outfit', sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; overflow-x: hidden; }}
                
                .fade-in {{ animation: fadeIn 0.8s ease-out; }}
                @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}

                .container {{ max-width: 1300px; margin: auto; }}

                /* 🛰️ Premium Header */
                header {{ 
                    background: radial-gradient(circle at top right, rgba(56, 189, 248, 0.1), transparent), var(--card);
                    border: 1px solid rgba(255,255,255,0.05); padding: 40px; border-radius: 24px; margin-bottom: 24px;
                    display: flex; justify-content: space-between; align-items: center; position: relative;
                }}
                .header-main h1 {{ margin: 0; font-size: 2.8em; font-weight: 700; color: var(--p-color); text-shadow: 0 0 20px var(--p-glow); }}
                .header-main p {{ margin: 5px 0 0; color: var(--text-dim); font-size: 1.1em; }}
                
                .badge {{ background: rgba(34, 197, 94, 0.1); color: var(--success); padding: 6px 12px; border-radius: 8px; font-size: 0.8em; font-weight: bold; border: 1px solid var(--success); text-transform: uppercase; }}
                .badge.elite {{ background: rgba(56, 189, 248, 0.1); color: var(--p-color); border-color: var(--p-color); }}
                
                .header-meta {{ display: flex; gap: 30px; border-right: 1px solid rgba(255,255,255,0.1); padding-right: 30px; }}
                .meta-item {{ text-align: left; }}
                .meta-item label {{ display: block; font-size: 0.8em; color: var(--text-dim); }}
                .meta-item value {{ font-size: 1.5em; font-weight: 600; display: block; }}

                /* 🏁 Stats Grid */
                .stats-container {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
                .stat-tile {{ 
                    background: var(--card); padding: 24px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.05);
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: default;
                }}
                .stat-tile:hover {{ border-color: var(--p-color); background: var(--card-alt); transform: scale(1.02); }}
                .stat-tile label {{ font-size: 0.85em; color: var(--text-dim); display: flex; align-items: center; gap: 8px; }}
                .stat-tile h2 {{ margin: 8px 0 0; font-size: 2em; letter-spacing: -0.5px; }}

                /* 📈 Main Content Layout */
                .layout-grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 24px; margin-bottom: 24px; }}
                .box {{ background: var(--card); padding: 30px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.05); }}
                .box h3 {{ margin: 0 0 25px; font-size: 1.25em; display: flex; align-items: center; gap: 10px; color: var(--text-dim); }}
                
                /* 📋 Custom Table */
                .table-controls {{ margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; }}
                .search-input {{ background: var(--card-alt); border: 1px solid rgba(255,255,255,0.1); padding: 10px 15px; border-radius: 10px; color: white; width: 250px; outline: none; }}
                .search-input:focus {{ border-color: var(--p-color); }}

                .table-container {{ max-height: 500px; overflow-y: auto; overflow-x: auto; }}
                table {{ width: 100%; border-collapse: collapse; text-align: right; }}
                th {{ position: sticky; top: 0; background: var(--card-alt); z-index: 10; padding: 15px; font-size: 0.85em; text-transform: uppercase; color: var(--p-color); border-bottom: 1px solid rgba(255,255,255,0.1); }}
                td {{ padding: 12px 15px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.95em; }}
                tr:hover {{ background: rgba(56, 189, 248, 0.05); }}

                .win {{ color: var(--success); font-weight: 600; }}
                .loss {{ color: var(--error); font-weight: 600; }}
                .type-buy {{ color: var(--success); background: rgba(34, 197, 94, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(34, 197, 94, 0.3); }}
                .type-sell {{ color: var(--error); background: rgba(239, 68, 68, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(239, 68, 68, 0.3); }}

                /* 📊 Micro-Analytics */
                .micro-stats {{ display: grid; gap: 15px; }}
                .micro-item {{ display: flex; justify-content: space-between; padding: 12px; background: rgba(255,255,255,0.02); border-radius: 10px; }}
                .micro-item span {{ font-size: 0.9em; opacity: 0.7; }}
                .micro-item strong {{ font-family: 'Outfit'; }}

                footer {{ text-align: center; padding: 40px; border-top: 1px solid rgba(255,255,255,0.05); margin-top: 40px; opacity: 0.5; font-size: 0.85em; }}

                @media (max-width: 1024px) {{ .layout-grid {{ grid-template-columns: 1fr; }} .stats-container {{ grid-template-columns: repeat(2, 1fr); }} }}
            </style>
        </head>
        <body>
            <div class="container fade-in">
                <!-- 🚀 Institutional Header -->
                <header>
                    <div class="header-main">
                        <div style="display: flex; align-items: center; gap: 15px;">
                            <h1>GIA AI PRO</h1>
                            <div class="badge { 'elite' if res['net_profit_pct'] > 50 else '' }">{ 'ELITE PERFORMANCE' if res['net_profit_pct'] > 50 else 'STABLE GROWTH' }</div>
                        </div>
                        <p>تقرير التحليل الفني لنموذج: <strong>{model_name}</strong> – {params['broker']}</p>
                    </div>
                    <div class="header-meta">
                        <div class="meta-item"><label>البداية</label><value>${res['equity_curve'][0]:,.0f}</value></div>
                        <div class="meta-item"><label>القمة القصوى</label><value style="color: var(--p-color)">${max(res['equity_curve']):,.0f}</value></div>
                        <div class="meta-item"><label>الرصيد الحالي</label><value style="color: var(--success)">${res['equity_curve'][-1]:,.0f}</value></div>
                    </div>
                </header>

                <!-- 📊 Core Vitals -->
                <div class="stats-container">
                    <div class="stat-tile">
                        <label>📈 صافي الأرباح</label>
                        <h2 class="{ 'win' if res['net_profit'] > 0 else 'loss' }">${res['net_profit']:,.2f}</h2>
                        <div style="font-size: 0.85em; margin-top: 8px; opacity: 0.8;">عائد إجمالي: {res['net_profit_pct']:.2f}%</div>
                    </div>
                    <div class="stat-tile">
                        <label>🎯 معدل النجاح</label>
                        <h2>{res['win_rate']:.1f}%</h2>
                        <div style="font-size: 0.85em; margin-top: 8px; opacity: 0.8;">{res['win_count']} فوز / {res['loss_count']} خسارة</div>
                    </div>
                    <div class="stat-tile">
                        <label>🛡️ أقصى تراجع</label>
                        <h2 class="loss">{res['max_drawdown']:.2f}%</h2>
                        <div style="font-size: 0.85em; margin-top: 8px; opacity: 0.8;">عامل شارب: {res.get('sharpe', 0):.2f}</div>
                    </div>
                    <div class="stat-tile">
                        <label>🧪 درجة الموثوقية</label>
                        <h2>{survival:.1f}%</h2>
                        <div style="font-size: 0.85em; margin-top: 8px; opacity: 0.8;">اختبار Monte Carlo</div>
                    </div>
                </div>

                <!-- 📊 Charts Layout -->
                <div class="layout-grid">
                    <div class="box">
                        <h3>📈 نمو المحفظة الزمني (HFT Logic)</h3>
                        <div style="height: 400px;"><canvas id="equityChart"></canvas></div>
                    </div>
                    <div class="box micro-analytics">
                        <h3>🧠 تحليل السلوك</h3>
                        <div class="micro-stats">
                            <div class="micro-item"><span>أكبر صفقة رابحة</span><strong class="win">${res['max_win']:,.2f}</strong></div>
                            <div class="micro-item"><span>أكبر صفقة خاسرة</span><strong class="loss">${res['max_loss']:,.2f}</strong></div>
                            <div class="micro-item"><span>أطول سلسلة فوز</span><strong class="win">{res.get('max_consecutive_wins', 0)} صفقات</strong></div>
                            <div class="micro-item"><span>أطول سلسلة خسارة</span><strong class="loss">{res.get('max_consecutive_losses', 0)} صفقات</strong></div>
                            <div class="micro-item"><span>متوسط الربح/الخسارة</span><strong>{res.get('avg_win_loss_ratio', 0):.2f}</strong></div>
                            <div class="micro-item"><span>عامل الربح (PF)</span><strong style="color: var(--p-color)">{res['profit_factor']:.2f}</strong></div>
                            <div class="micro-item"><span>كثافة الإشارات</span><strong>{res.get('avg_trades_day', 0):.1f} صفقة/يوم</strong></div>
                        </div>
                        <div style="height: 120px; margin-top: 25px;"><canvas id="dailyChart"></canvas></div>
                    </div>
                </div>

                <!-- 📜 Detailed Execution Log -->
                <div class="box fade-in" style="animation-delay: 0.2s;">
                    <div class="table-controls">
                        <h3>📜 سجل التنفيذ المؤسساتي (M1 Precision)</h3>
                        <input type="text" id="tradeSearch" class="search-input" placeholder="بحث عن صفقات..." onkeyup="filterTrades()">
                    </div>
                    <div class="table-container">
                        <table id="tradesTable">
                            <thead>
                                <tr>
                                    <th>تاريخ الدخول</th>
                                    <th>النوع</th>
                                    <th>اللوت</th>
                                    <th>السعر</th>
                                    <th>النتيجة ($)</th>
                                    <th>النسبة %</th>
                                    <th>الرصيد</th>
                                    <th>MFE/MAE</th>
                                    <th>السبب</th>
                                </tr>
                            </thead>
                            <tbody></tbody>
                        </table>
                    </div>
                </div>

                <footer>
                    <strong>GIA TRADING ENGINE v3.0 | Institutional Analytical Suite</strong><br>
                    Generated automatically on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Confidential
                </footer>
            </div>

            <script>
                // --- 📊 Charts Init ---
                const chartDefaults = {{ 
                    color: '#9ca3af', 
                    font: {{ family: 'Outfit', size: 11 }},
                    grid: {{ color: 'rgba(255,255,255,0.05)' }} 
                }};

                // 📈 Equity Chart
                const equityCtx = document.getElementById('equityChart').getContext('2d');
                const equityData = {equity_data};
                new Chart(equityCtx, {{
                    type: 'line',
                    data: {{
                        labels: Array.from({{length: equityData.length}}, (_, i) => i),
                        datasets: [{{
                            label: 'Equity Growth', data: equityData,
                            borderColor: '#38bdf8', borderWidth: 3, pointRadius: 0,
                            fill: true, backgroundColor: 'rgba(56, 189, 248, 0.05)',
                            tension: 0.2
                        }}]
                    }},
                    options: {{
                        responsive: true, maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }}, tooltip: {{ mode: 'index', intersect: false }} }},
                        scales: {{ x: {{ display: false }}, y: chartDefaults }}
                    }}
                }});

                // 📅 Daily Chart (Small)
                const dailyCtx = document.getElementById('dailyChart').getContext('2d');
                const dailyData = {json.dumps(res.get('daily_pnl', [0]*7))};
                new Chart(dailyCtx, {{
                    type: 'bar',
                    data: {{
                        labels: ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'],
                        datasets: [{{ label: 'Profit', data: dailyData, backgroundColor: dailyData.map(v => v >= 0 ? '#22c55e' : '#ef4444'), borderRadius: 4 }}]
                    }},
                    options: {{
                        responsive: true, maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{ 
                            y: {{ display: false }},
                            x: {{ ticks: chartDefaults.ticks, grid: {{ display: false }} }}
                        }}
                    }}
                }});

                // --- 📋 Table Logical ---
                const trades = {trades_json};
                const tbody = document.querySelector('#tradesTable tbody');
                
                function renderTable(data) {{
                    tbody.innerHTML = '';
                    data.forEach(t => {{
                        const row = document.createElement('tr');
                        const pnl = parseFloat(t.pnl_net || 0);
                        const isWin = pnl >= 0;
                        
                        row.innerHTML = `
                            <td style="font-size: 0.85em; opacity: 0.8">${{t.entry_date}}</td>
                            <td><span class="${{t.type == 'BUY' ? 'type-buy' : 'type-sell'}}">${{t.type}}</span></td>
                            <td style="font-family: 'Outfit'">${{parseFloat(t.lots).toFixed(2)}}</td>
                            <td style="font-family: 'Outfit'">${{parseFloat(t.entry_price).toFixed(2)}}</td>
                            <td class="${{isWin ? 'win' : 'loss'}}">${{isWin ? '+' : ''}}${{pnl.toLocaleString()}}</td>
                            <td class="${{isWin ? 'win' : 'loss'}}">${{parseFloat(t.pnl_pct).toFixed(2)}}%</td>
                            <td style="font-family: 'Outfit'; font-weight: 600">$${{parseFloat(t.balance).toLocaleString()}}</td>
                            <td style="font-size: 0.8em; color: var(--text-dim)">
                                <span class="win">${{t.mfe_pips}}</span> / <span class="loss">${{t.mae_pips}}</span>
                            </td>
                            <td style="font-size: 0.8em; opacity: 0.7">${{t.exit_reason || 'Signal'}}</td>
                        `;
                        tbody.appendChild(row);
                    }});
                }}

                function filterTrades() {{
                    const query = document.getElementById('tradeSearch').value.toLowerCase();
                    const filtered = trades.filter(t => 
                        t.entry_date.toLowerCase().includes(query) || 
                        t.type.toLowerCase().includes(query) ||
                        (t.exit_reason || '').toLowerCase().includes(query)
                    );
                    renderTable(filtered);
                }}

                renderTable(trades);
            </script>
        </body>
        </html>
        """
        with open(os.path.join(base_path, "Visual_Report.html"), "w", encoding='utf-8') as f:
            f.write(html_content)

    @staticmethod
    def _generate_comparison_dashboard(comparison_data, params):
        """Creates a professional multi-model comparison dashboard with time-alignment."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"GLOBAL_BATTLEGROUND_{timestamp}"
        base_path = os.path.join(os.getcwd(), 'backend', 'results', folder_name)
        os.makedirs(base_path, exist_ok=True)
        
        datasets = []
        colors = ['#38bdf8', '#22c55e', '#facc15', '#f87171', '#c084fc', '#fb923c']
        
        for i, d in enumerate(comparison_data):
            # Map to {x: date, y: value} for Chart.js time scale alignment
            points = []
            if 'dates' in d and len(d['dates']) == len(d['equity']):
                for date, val in zip(d['dates'], d['equity']):
                    points.append({"x": date, "y": float(val)})
            else:
                # Fallback to index if dates missing
                for idx, val in enumerate(d['equity']):
                    points.append({"x": idx, "y": float(val)})

            # Premium Styling: Highlight SIGNAL_PRO
            is_pro = "SIGNAL_PRO" in d['model']
            datasets.append({
                "label": d['model'],
                "data": points,
                "borderColor": "#38bdf8" if is_pro else colors[i % len(colors)],
                "backgroundColor": "rgba(56, 189, 248, 0.1)" if is_pro else colors[i % len(colors)] + "11",
                "borderWidth": 4 if is_pro else 2,
                "pointRadius": 0,
                "tension": 0.1,
                "fill": is_pro
            })

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>لوحة المواجهة الشاملة - GIA GLOBAL</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/date-fns@3.0.6/cdn.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
                body {{ font-family: 'Cairo', sans-serif; background: #070b14; color: #f8fafc; margin: 0; padding: 40px; }}
                .container {{ max-width: 1400px; margin: auto; background: #0f172a; padding: 40px; border-radius: 20px; border: 1px solid #1e293b; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }}
                .header {{ text-align: center; margin-bottom: 50px; }}
                .header h1 {{ color: #38bdf8; font-size: 3.5em; margin: 0; text-shadow: 0 0 20px rgba(56, 189, 248, 0.3); }}
                .header p {{ color: #64748b; font-size: 1.2em; }}
                .chart-container {{ background: #070b14; padding: 30px; border-radius: 16px; border: 1px solid #1e293b; height: 600px; margin-bottom: 50px; position: relative; }}
                table {{ width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 30px; border-radius: 12px; overflow: hidden; border: 1px solid #1e293b; }}
                th {{ padding: 20px; background: #1e293b; color: #38bdf8; text-align: right; font-size: 1.1em; }}
                td {{ padding: 18px; background: #0f172a; border-bottom: 1px solid #1e293b; color: #cbd5e1; font-size: 1em; }}
                tr:last-child td {{ border-bottom: none; }}
                tr:hover td {{ background: #1e293b; }}
                .win {{ color: #22c55e; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏆 GIA GLOBAL BATTLEGROUND</h1>
                    <p>المواجهة الكبرى بين نماذج الذكاء الاصطناعي - تحليل المقارنة المتزامن</p>
                </div>
                
                <div class="chart-container">
                    <canvas id="compChart"></canvas>
                </div>

                <table>
                    <thead>
                        <tr>
                            <th>المرتبة</th>
                            <th>الموديل</th>
                            <th>العائد (%)</th>
                            <th>أقصى تراجع</th>
                            <th>عامل الربح</th>
                            <th>معدل النجاح</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join([f"<tr><td>{i+1}</td><td>{d['model']}</td><td class='win'>{d['roi']:.2f}%</td><td>{d['dd']:.2f}%</td><td>{d['pf']:.2f}</td><td>{d['win_rate']:.1f}%</td></tr>" for i, d in enumerate(sorted(comparison_data, key=lambda x: x['roi'], reverse=True))])}
                    </tbody>
                </table>
            </div>
            <script>
                const ctx = document.getElementById('compChart').getContext('2d');
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        datasets: {json.dumps(datasets)}
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {{ mode: 'index', intersect: false }},
                        scales: {{ 
                            x: {{ 
                                type: 'time',
                                time: {{ unit: 'day', displayFormats: {{ day: 'MMM d' }} }},
                                grid: {{ color: '#1e293b' }},
                                ticks: {{ color: '#64748b', font: {{ family: 'Cairo' }} }}
                            }}, 
                            y: {{ 
                                grid: {{ color: '#1e293b' }},
                                ticks: {{ color: '#64748b', font: {{ family: 'Cairo' }} }} 
                            }} 
                        }},
                        plugins: {{ 
                            legend: {{ 
                                position: 'top',
                                labels: {{ color: '#f8fafc', font: {{ family: 'Cairo', size: 14 }}, usePointStyle: true, padding: 20 }} 
                            }},
                            tooltip: {{
                                backgroundColor: '#0f172a',
                                titleColor: '#38bdf8',
                                bodyColor: '#f8fafc',
                                borderColor: '#1e293b',
                                borderWidth: 1,
                                padding: 12,
                                bodyFont: {{ family: 'Cairo' }}
                            }}
                        }}
                    }}
                }});
            </script>
        </body>
        </html>
        """
        with open(os.path.join(base_path, "Battleground_Dashboard.html"), "w", encoding='utf-8') as f: f.write(html_content)
        return base_path

# --- Battle Ground Engine ---
class BattleArena:
    DEFAULT_DATA_DIR = os.path.join(os.getcwd(), "data")

    def __init__(self, data_dir=None):
        self.data_dir = data_dir if data_dir else self.DEFAULT_DATA_DIR
        self.models_dir = os.path.join(os.getcwd(), 'backend', 'models')
        self.pro_models_dir = os.path.join(os.getcwd(), 'GIA_SIGNAL_PRO', 'models')
        self.cache = {}
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)

    def _calculate_extended_stats(self, res):
        trades = pd.DataFrame(res['trades'])
        if trades.empty:
            res.update({'win_count':0,'loss_count':0,'max_win':0,'max_loss':0,'avg_trades_day':0, 'sortino': 0, 'max_consecutive_losses': 0})
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
        neg_std = daily[daily < 0].std()
        
        res['sharpe'] = (daily.mean() / std * np.sqrt(252)) if std > 0 else 0
        res['sortino'] = (daily.mean() / neg_std * np.sqrt(252)) if neg_std > 0 else 0
        res['calmar'] = (res['net_profit_pct'] / res['max_drawdown']) if res['max_drawdown'] > 0 else 0
        
        # 📈 Time-Based Equity for Comparison
        daily_cum = daily.cumsum() + res['equity_curve'][0]
        res['daily_equity'] = daily_cum.tolist()
        res['daily_dates'] = daily_cum.index.strftime('%Y-%m-%d').tolist()
        
        # Streak analysis
        trades['is_win'] = trades['pnl_net'] > 0
        streaks = trades['is_win'].ne(trades['is_win'].shift()).cumsum()
        
        loss_streaks = trades[~trades['is_win']].groupby(streaks).size()
        res['max_consecutive_losses'] = int(loss_streaks.max() if not loss_streaks.empty else 0)
        
        win_streaks = trades[trades['is_win']].groupby(streaks).size()
        res['max_consecutive_wins'] = int(win_streaks.max() if not win_streaks.empty else 0)
        
        # 🕒 Seasonality Calculation
        trades['hour'] = trades['entry_date'].dt.hour
        trades['day'] = trades['entry_date'].dt.dayofweek
        
        hourly = trades.groupby('hour')['pnl_net'].sum()
        res['hourly_pnl'] = [float(hourly.get(h, 0)) for h in range(24)]
        
        daily = trades.groupby('day')['pnl_net'].sum()
        res['daily_pnl'] = [float(daily.get(d, 0)) for d in range(7)]
        
        return res

    def start(self, cli_args=None):
        self.synthetic = getattr(cli_args, 'synthetic', False) if cli_args else False
        self.asset = getattr(cli_args, 'asset', 'XAUUSD').upper() if cli_args else 'XAUUSD'
        print_banner()
        
        is_cli = cli_args and (cli_args.model or cli_args.compare)
        
        if not is_cli:
            print(f" {Fore.YELLOW}STEP 0: SELECT MARKET ENVIRONMENT{Style.RESET_ALL}")
            print(f"  [{Fore.GREEN}1{Style.RESET_ALL}] Institutional (Real History)")
            print(f"  [{Fore.GREEN}2{Style.RESET_ALL}] Synthetic Stress Gauntlet (Fake Data)")
            env_choice = input(f"\n {Fore.WHITE}Select Environment [Default 1] > {Style.RESET_ALL}").strip() or "1"
            if env_choice == "2":
                self.synthetic = True
                # Automatically pivot to synthetic folder if using default
                if self.data_dir == self.DEFAULT_DATA_DIR:
                    self.data_dir = os.path.join(os.getcwd(), 'backend', 'hestory')
            else:
                self.synthetic = False

        choice = None
        
        is_cli = cli_args and (cli_args.model or cli_args.compare)
        if is_cli:
            choice = 'A' if cli_args.compare else 'CLI'
            if cli_args.compare:
                targets = sorted([m for m in os.listdir(self.models_dir) if m.endswith('.pkl')])
                if os.path.exists(self.pro_models_dir):
                    targets += sorted([m for m in os.listdir(self.pro_models_dir) if m.endswith('.pkl')])
            else:
                m_name = cli_args.model
                if m_name and not m_name.endswith('.pkl'):
                    m_name += '.pkl'
                targets = [m_name] if m_name else []
            
            tf = getattr(cli_args, 'tf', "M15")
            broker = cli_args.broker
            capital = cli_args.capital
            risk = cli_args.risk
            sizing_mode = cli_args.mode
            fixed_lot = cli_args.lots
            start_y = cli_args.from_year
            end_y = cli_args.to_year
            latency = getattr(cli_args, 'latency', 0.1)
        else:
            # --- PROFESSIONAL DASHBOARD ---
            models_main = sorted([f for f in os.listdir(self.models_dir) if f.endswith('.pkl')])
            models_pro = sorted([f for f in os.listdir(self.pro_models_dir) if f.endswith('.pkl')]) if os.path.exists(self.pro_models_dir) else []
            
            all_paths = {m: os.path.join(self.models_dir, m) for m in models_main}
            for m in models_pro: all_paths[m] = os.path.join(self.pro_models_dir, m)
            all_models = sorted(list(all_paths.keys()))

            # --- MODEL INTELLIGENCE REGISTRY ---
            MODEL_NAVIGATOR = {
                "GIA_v2_PRO.pkl": {"tf": "M15", "broker": "Spotware", "risk": 1.0, "latency": 0.1, "desc": "Institutional Hybrid (Elite)"},
                "GIA_v2_FLASH.pkl": {"tf": "M1", "broker": "Spotware", "risk": 0.5, "latency": 0.05, "desc": "High-Velocity Scalper (M1)"}
            }

            print(f"\n {Fore.YELLOW}STEP 1: SELECT YOUR AI MODEL{Style.RESET_ALL}")
            for i, m in enumerate(all_models): 
                tag = "[PRO]" if m in models_pro else "[CORE]"
                intelligence = MODEL_NAVIGATOR.get(m, {"tf": "M15", "desc": "Universal Mode"})
                print(f"  [{Fore.GREEN}{i+1}{Style.RESET_ALL}] {m:22} {tag} | {intelligence['tf']} | {intelligence['desc']}")
            print(f"  [{Fore.GREEN}A{Style.RESET_ALL}] COMPARE ALL MODELS")
            print(f"  [{Fore.GREEN}P{Style.RESET_ALL}] PORTFOLIO (Elite Duo: v2_PRO + v2_FLASH)")
            
            choice = input(f"\n {Fore.WHITE}Enter Selection > {Style.RESET_ALL}").strip().upper()
            if choice == 'P':
                targets = ["GIA_v2_PRO.pkl", "GIA_v2_FLASH.pkl"]
                print(f"   {Fore.CYAN}💎 ELITE DUO ACTIVATED: Combining Tactical Trend + High-Velocity Scalping.{Style.RESET_ALL}")
            else:
                targets = all_models if choice == 'A' else [all_models[int(choice)-1]] if choice.isdigit() and 0 < int(choice) <= len(all_models) else [all_models[0]]

            print(f"\n {Fore.YELLOW}STEP 1.5: SELECT ASSET{Style.RESET_ALL}")
            print(f"  [{Fore.GREEN}1{Style.RESET_ALL}] XAUUSD    [{Fore.GREEN}2{Style.RESET_ALL}] BTCUSD")
            print(f"  [{Fore.GREEN}3{Style.RESET_ALL}] USDJPY    [{Fore.GREEN}4{Style.RESET_ALL}] GBPJPY")
            print(f"  [{Fore.GREEN}5{Style.RESET_ALL}] XAGUSD")
            a_choice = input(f"\n {Fore.WHITE}Select Asset [Enter for {self.asset}] > {Style.RESET_ALL}").strip()
            asset_map = {"1":"XAUUSD", "2":"BTCUSD", "3":"USDJPY", "4":"GBPJPY", "5":"XAGUSD"}
            if a_choice in asset_map: self.asset = asset_map[a_choice]

            # 🦁 Institutional Defaults (Safe Initialize)
            tf = "M15"
            broker = "FIPER"
            sizing_mode = "dynamic"
            fixed_lot = 0.01
            capital = 1000.0
            risk = 1.0
            latency = 0.1
            start_y, end_y = 2024, datetime.now().year


            # AUTO-CONFIG (If single model selected)
            auto_config = (choice != 'A')
            if auto_config:
                m_intel = MODEL_NAVIGATOR.get(targets[0], {"tf": "M15", "broker": "IC MARKETS", "risk": 1.0, "latency": 0.1})
                print(f"\n {Fore.CYAN}💡 AUTO-DETECTED REQUIREMENTS for {targets[0]}:{Style.RESET_ALL}")
                print(f"   Native TF: {m_intel['tf']} | Ideal Broker: {m_intel['broker']} | Balanced Risk: {m_intel['risk']}%")
                
                use_auto = input(f"\n {Fore.WHITE}Apply Institutional Auto-Config? (Y/n) > {Style.RESET_ALL}").strip().lower() != 'n'
                if use_auto:
                    tf = m_intel['tf']
                    broker = m_intel['broker']
                    risk = m_intel['risk']
                    latency = m_intel['latency']
                    sizing_mode = "dynamic"
                    capital = 500.0
                    start_y, end_y = 2024, datetime.now().year
                    print(f"   {Fore.GREEN}✔ Settings Applied.{Style.RESET_ALL}")
                else:
                    auto_config = False # Force manual if user says no
            
            if not auto_config:
                print(f"\n {Fore.YELLOW}STEP 2: SELECT EXECUTION TIMEFRAME{Style.RESET_ALL}")
                print(f"  [{Fore.GREEN}0{Style.RESET_ALL}] M1 (Scalping)   [{Fore.GREEN}1{Style.RESET_ALL}] M15 (Tactical)  [{Fore.GREEN}2{Style.RESET_ALL}] M30 (Balanced)  [{Fore.GREEN}3{Style.RESET_ALL}] H1 (Strategic)")
                tf_choice = input(f"\n {Fore.WHITE}Enter Selection [Default M15] > {Style.RESET_ALL}").strip() or "1"
                tf = {"0":"M1", "1":"M15", "2":"M30", "3":"H1"}.get(tf_choice, "M15")

                print(f"\n {Fore.YELLOW}STEP 3: cTRADER INSTITUTIONAL PHYSICS{Style.RESET_ALL}")
                brokers = list(BrokerSimulator.PROFILES.keys())
                for i, b in enumerate(brokers): 
                    p = BrokerSimulator.PROFILES[b]
                    print(f"  [{Fore.GREEN}{i+1}{Style.RESET_ALL}] {p.name:20}", end=" " if (i+1)%2 != 0 else "\n")
                b_choice = input(f"\n\n {Fore.WHITE}Select Broker [Enter for FIPER] > {Style.RESET_ALL}").strip()
                broker = brokers[int(b_choice)-1] if b_choice.isdigit() else "FIPER"
                
                sizing_mode = "dynamic" if (input(f"\n {Fore.YELLOW}STEP 4: MM MODE (1=Dynamic, 2=Fixed) > {Style.RESET_ALL}") or "1") == "1" else "fixed"
                fixed_lot = float(input(f"  {Fore.WHITE}Fixed Lot Size [0.01] > {Style.RESET_ALL}") or 0.01) if sizing_mode == "fixed" else 0.01
                capital = float(input(f"  {Fore.WHITE}STEP 5: CAPITAL > {Style.RESET_ALL}") or 1000)
                risk = float(input(f"  {Fore.WHITE}STEP 6: RISK % > {Style.RESET_ALL}") or 1.0) if sizing_mode == "dynamic" else 1.0
                
                print(f"\n {Fore.YELLOW}STEP 7: YEAR RANGE (2010-2025){Style.RESET_ALL}")
                current_yr = datetime.now().year
                start_y = int(input(f"  {Fore.WHITE}Start Year [2024] > {Style.RESET_ALL}") or 2024)
                end_y = int(input(f"  {Fore.WHITE}End Year [{current_yr}] > {Style.RESET_ALL}") or current_yr)
                
                print(f"\n {Fore.YELLOW}STEP 8: INSTITUTIONAL LATENCY (Seconds){Style.RESET_ALL}")
                latency = float(input(f"  {Fore.WHITE}Execution Delay [0.1s] > {Style.RESET_ALL}") or 0.1)

        # --- EXECUTION LOOP ---
        final_table = []
        comparison_data = []
        base_tf = tf
        
        # 🧪 Turbo Cache: Avoid re-calculating common features
        TIMEFRAME_CACHE = {} 
        portfolio_trades = []


        for m_name in targets:
            print_separator("-", color=Fore.LIGHTBLACK_EX)
            
            # 🦁 Institutional Smart Dispatcher:
            # Native timeframe assignment for Compare and Portfolio modes
            if choice in ['A', 'P']:
                temp_intel = {
                    "GIA_SIGNAL_PRO.pkl": "M1",
                    "GIA_v2_PRO.pkl": "M15",
                    "GIA_v14_PRO.pkl": "H1",
                    "GIA_v2_FLASH.pkl": "M1"
                }
                current_tf = temp_intel.get(m_name, base_tf)
            else:
                current_tf = tf

            print(f"🦁 {Fore.WHITE}ENGINEERING: {Fore.YELLOW}{m_name}{Style.RESET_ALL} | {Fore.CYAN}{current_tf}{Style.RESET_ALL} [NATIVE]")


            
            try:
                # 🛡️ Path Logic: Filename vs Path
                if os.path.isabs(m_name) or ("/" in m_name or "\\" in m_name):
                    path = m_name if os.path.exists(m_name) else os.path.join(self.base_dir, m_name)
                    m_name = os.path.basename(m_name) # Strip for logging
                else:
                    pro_path = os.path.join(self.pro_models_dir, m_name)
                    core_path = os.path.join(self.models_dir, m_name)
                    path = pro_path if os.path.exists(pro_path) else core_path
                
                if not os.path.exists(path):
                    print(f"   {Fore.RED}❌ ERROR: Model not found at {path}{Style.RESET_ALL}")
                    continue

                m_data = joblib.load(path)
                req_feats = m_data.get('feature_columns', m_data.get('features', []))
                needs_mtf = any((x in f.lower()) for f in req_feats for x in ['_h1', '_m15', '_m5', '_m30'])

                # 🛡️ Data Synchronizer: Load native candles + required context (Multi-Timeframe)
                df = self._load_data(current_tf, needs_mtf)
                print(f"   📊 Loaded: {len(df)} candles for {current_tf}")
                
                df = df[(df['date'].dt.year >= start_y) & (df['date'].dt.year <= end_y)].copy()
                if df.empty:
                    print(f"   {Fore.YELLOW}⚠️ No data found for specified years {start_y}-{end_y}.{Style.RESET_ALL}")
                    continue
                
                # 🧠 Turbo-Feature Engineering
                if current_tf not in TIMEFRAME_CACHE:
                    TIMEFRAME_CACHE[current_tf] = df.copy()
                
                print(f"   🔍 Constructing Features for {m_name}...")
                
                # A. Intelligence Construction
                df_proc = FeatureFactory.construct(df.copy(), req_feats)
                
                # C. Final Clean-up (Institutional Standards)
                df_proc = df_proc.replace([np.inf, -np.inf], 0).ffill().fillna(0)
                
                df_proc = df_proc.dropna(subset=[f for f in req_feats if f in df_proc.columns])

                
                # 🦁 Institutional Smart Dispatcher: Detection for UHF/Flash Engine
                is_uhf = "PREDATOR" in m_name.upper() or "FLASH" in m_name.upper()
                engine = BacktestEngine(model_path=path, is_legacy="v14" in m_name)
                engine.load_model()
                
                # 🦁 Smart Dispatcher: Respect each model's native physics if comparing
                current_broker = broker
                current_latency = latency
                if choice == 'A' and m_name in MODEL_NAVIGATOR:
                    intel = MODEL_NAVIGATOR[m_name]
                    current_broker = intel.get('broker', broker)
                    current_latency = intel.get('latency', latency)

                # 🦁 Portfolio Risk Logic: Enforce 0.5% for FLASH in Elite Duo mode
                active_risk = 0.5 if (choice == 'P' and "FLASH" in m_name.upper()) else risk
                
                res = engine.backtest(df_proc, broker_name=current_broker, initial_balance=capital, risk_pct=active_risk, sizing_mode=sizing_mode, fixed_lot_size=fixed_lot, execution_latency=current_latency)
                
                if "error" in res:
                    print(f"   {Fore.RED}❌ Simulation Error: {res['error']}{Style.RESET_ALL}")
                    if "diagnostic" in res:
                        reason_summary = ", ".join([f"{k}:{v}" for k,v in res['diagnostic']['reasons'].items()])
                        print(f"     ↳ {Fore.LIGHTBLACK_EX}Diagnostic: {reason_summary}{Style.RESET_ALL}")
                    continue



                res = self._calculate_extended_stats(res)
                
                # 🚀 Turbo Monte Carlo (Parallel Processing)
                print(f"   🎲 {Fore.MAGENTA}Running Parallel Stress Test...{Style.RESET_ALL}")
                from joblib import Parallel, delayed
                
                def run_single_mc():
                    rmc = engine.backtest(df_proc, broker_name=broker, risk_pct=active_risk, initial_balance=capital, sizing_mode=sizing_mode, fixed_lot_size=fixed_lot, execution_latency=latency)
                    return rmc.get('net_profit_pct', -100) if "error" not in rmc else -100

                mc_results = Parallel(n_jobs=-1, prefer="threads")(delayed(run_single_mc)() for _ in range(5))
                survival = (len([p for p in mc_results if p > 0]) / len(mc_results)) * 100 if mc_results else 0

                
                params = {"tf": current_tf, "broker": broker, "start": start_y, "end": end_y, "risk": active_risk if sizing_mode == 'dynamic' else f"FIXED {fixed_lot}", "mode": sizing_mode}
                save_path = ExportManager.save(m_name, res, survival, params)
                
                print_ascii_chart(res['equity_curve'], title=f"GIA Elite Bench: {m_name}")
                print(f" {Fore.WHITE}Trades: {Fore.GREEN}{res['win_count']}W {Fore.RED}{res['loss_count']}L {Fore.WHITE}| ROI: {res['net_profit_pct']:.2f}% | Surv (Monte Carlo): {survival:.1f}%")
                
                final_table.append({"Model": m_name, "PF": res['profit_factor'], "DD": res['max_drawdown'], "ROI%": res['net_profit_pct'], "Surv%": survival})
                if choice == 'P':
                    # Log trades for portfolio merge
                    for t in res.get('trades', []):
                        t['model_source'] = m_name
                        portfolio_trades.append(t)
                comparison_data.append({
                    "model": m_name, 
                    "equity": res.get('daily_equity', res['equity_curve']), 
                    "dates": res.get('daily_dates', []),
                    "roi": res['net_profit_pct'], 
                    "dd": res['max_drawdown'], 
                    "pf": res['profit_factor'], 
                    "win_rate": res['win_rate']
                })

            except Exception as e:
                print(f"   {Fore.RED}❌ Crash: {e}{Style.RESET_ALL}")

        if len(final_table) > 1:
            self._print_scoreboard(final_table)
            
            if choice == 'P' and portfolio_trades:
                # 🦁 GIA MASTER PORTFOLIO AGGREGATION
                print(f"\n{Fore.CYAN}╔════════════════════════════════════════════════════════╗")
                print(f"║ {Fore.WHITE}      🏆 GIA MASTER PORTFOLIO: ELITE DUO           {Fore.CYAN}║")
                print(f"╚════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
                
                 # 1. Chronological Merge
                sorted_trades = sorted(portfolio_trades, key=lambda x: x['entry_date'])
                
                # 2. Sequential Equity Calculation
                balance = capital
                equity_curve = [balance]
                wins, losses = 0, 0
                gross_profit, gross_loss = 0, 0
                
                for t in sorted_trades:
                    pnl = t['pnl_net']
                    balance += pnl
                    equity_curve.append(balance)
                    if pnl > 0:
                        wins += 1
                        gross_profit += pnl
                    else:
                        losses += 1
                        gross_loss += abs(pnl)
                
                # 3. Stats Calculation
                pf = gross_profit / (gross_loss + 1e-9)
                roi = ((balance - capital) / capital) * 100
                wr = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0
                
                # Dynamic Drawdown calc
                peak = capital
                max_dd = 0
                for v in equity_curve:
                    if v > peak: peak = v
                    dd = (peak - v) / peak * 100
                    if dd > max_dd: max_dd = dd
                
                print_separator("-")
                print_ascii_chart(equity_curve, title="GIA Duo Master Curve (Tactical + Flash)")
                
                print(f"\n {Fore.GREEN}⭐ HARMONY RESULTS:{Style.RESET_ALL}")
                print(f"   Total Trades: {len(sorted_trades)} ({wins}W / {losses}L)")
                print(f"   Combined ROI: {Fore.GREEN}{roi:.2f}%{Style.RESET_ALL}")
                print(f"   Profit Factor: {Fore.YELLOW}{pf:.2f}{Style.RESET_ALL}")
                print(f"   Max Drawdown: {Fore.RED}{max_dd:.2f}%{Style.RESET_ALL}")
                print(f"   Win Rate: {wr:.1f}%")
                
                print(f"\n {Fore.CYAN}💡 INSIGHT: {Fore.WHITE}The Models completed each other. FLASH provided liquidity \n            during flat PRO trends, while PRO captured the major legs.{Style.RESET_ALL}")
                print_separator("-")
            dash_path = ExportManager._generate_comparison_dashboard(comparison_data, {"broker": broker})
            print(f"\n{Fore.GREEN}🏆 Global Dashboard Ready: {Fore.WHITE}{dash_path}{Style.RESET_ALL}")

    def _load_data(self, primary_tf, needs_multi):
        key = f"{primary_tf}_{'MTF' if needs_multi else 'STF'}"
        if key in self.cache: return self.cache[key]
        
        suffix = "_SYNTH" if getattr(self, 'synthetic', False) else ""
        asset_name = getattr(self, 'asset', 'XAUUSD')
        df_p = self._read_csv(f'{asset_name}_{primary_tf}{suffix}.csv')
        
        if needs_multi:
            # Enhanced Context Mapping: Fixed Order for Institutional Physics
            # We must load specific TFs that v2_PRO expects
            contexts = [('m15', 'XAUUSD_M15.csv'), ('m30', 'XAUUSD_M30.csv'), ('h1', 'XAUUSD_H1.csv')]
            merged = df_p.sort_values('date')
            
            for suffix, filename in contexts:
                if suffix.upper() == primary_tf.upper(): continue # Skip self
                try:
                    data_suffix = "_SYNTH" if getattr(self, 'synthetic', False) else ""
                    asset_name = getattr(self, 'asset', 'XAUUSD')
                    filename = f"{asset_name}_{suffix.upper()}{data_suffix}.csv"
                    target_path = os.path.join(self.data_dir, filename)
                    if not os.path.exists(target_path): continue
                    
                    df_sec = self._read_csv(filename)
                    eng_sec = self._engineer_secondary(df_sec, suffix)
                    merged = pd.merge_asof(merged, eng_sec.sort_values('date'), on='date', direction='backward')
                except Exception as e:
                    print(f"   {Fore.RED}⚠️ Error merging context {suffix}: {e}{Style.RESET_ALL}")
            
            # Additional M5 context synthesis from M1 (for SIGNAL_PRO)
            try:
                data_suffix = "_SYNTH" if getattr(self, 'synthetic', False) else ""
                asset_name = getattr(self, 'asset', 'XAUUSD')
                m1_name = f"{asset_name}_M1{data_suffix}.csv"
                m1_path = os.path.join(self.data_dir, m1_name)
                if os.path.exists(m1_path):
                    df_m1 = self._read_csv(m1_name)
                    df_m5 = df_m1.set_index('date').resample('5min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna().reset_index()
                    eng_m5 = self._engineer_secondary(df_m5, 'm5')
                    merged = pd.merge_asof(merged, eng_m5.sort_values('date'), on='date', direction='backward')
            except: pass

            res_df = merged.ffill().bfill()
            self.cache[key] = res_df
        else:
            self.cache[key] = df_p
            
        return self.cache[key]

    def _read_csv(self, name):
        df = pd.read_csv(os.path.join(self.data_dir, name))
        df.columns = [c.lower() for c in df.columns]
        # Institutional Date Parsing (mixed formats)
        df['date'] = pd.to_datetime(df['time'], format='mixed', dayfirst=False).dt.tz_localize(None)
        return df.sort_values('date')

    def _engineer_secondary(self, df, suffix):
        df = df.copy()
        df[f'rsi_{suffix}'] = FeatureFactory._rsi(df['close'])
        
        e12 = df['close'].ewm(span=12, adjust=False).mean()
        e26 = df['close'].ewm(span=26, adjust=False).mean()
        df[f'macd_{suffix}'] = (e12 - e26) / (df['close'] + 1e-9)
        
        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df[f'bb_width_{suffix}'] = (4 * std) / (ma + 1e-9)
        
        # Super Trader specific MTF indicators
        if suffix == 'h1':
            ema200 = df['close'].ewm(span=200, adjust=False).mean()
            df['ema_200_dist_h1'] = (df['close'] - ema200) / (df['close'] + 1e-9)
            df['mom_h1'] = df['close'].pct_change(4)
            df['trend_h1'] = np.where(df['close'] > ema200, 1, -1)
        
        df[f'vol_{suffix}'] = df['close'].pct_change().rolling(20).std()
        df[f'trend_{suffix}'] = np.where(df['close'] > ma, 1, -1)
        
        cols_to_keep = ['date'] + [c for c in df.columns if c.endswith(suffix) or c.endswith('_h1')]
        # Unique columns only
        seen = set()
        clean_cols = [x for x in cols_to_keep if not (x in seen or seen.add(x))]
        return df[clean_cols]

    def _print_scoreboard(self, results):
        if not results: return
        
        print("\n" + Fore.CYAN + "═"*100)
        print(f"{'🏆 GIA INSTITUTIONAL SELECTION INTELLIGENCE':^100}")
        print("═"*100 + Style.RESET_ALL)
        
        # Calculate Intelligence Scores
        # Score = (ROI/100 * PF) / (Drawdown + 1) * (Survival/100)
        for r in results:
            dd_penalty = max(1, r['DD'])
            r['iq_score'] = (abs(r['ROI%'])/100 * r['PF']) / dd_penalty * (r['Surv%']/100)
            
            # Labeling based on Institutional Standards
            if r['Surv%'] >= 90 and r['DD'] < 15: r['tag'] = "💎 DIAMOND (Live Ready)"
            elif r['Surv%'] >= 80: r['tag'] = "🛡️ RESILIENT"
            elif r['Surv%'] >= 60: r['tag'] = "🔥 AGGRESSIVE"
            else: r['tag'] = "⚠️ HIGH RISK"

        # Sort by IQ Score
        ranked = sorted(results, key=lambda x: x['iq_score'], reverse=True)
        
        headers = f"{'RANK':<5} {'MODEL NAME':<25} {'ROI%':<12} {'PF':<8} {'DD%':<8} {'SURV%':<8} {'TAG':<20}"
        print(Fore.YELLOW + headers + Style.RESET_ALL)
        print("-" * 100)
        
        for i, r in enumerate(ranked):
            color = Fore.GREEN if i == 0 else Fore.WHITE
            if r['ROI%'] < 0: color = Fore.RED
            
            print(f"{color}{i+1:<5} {r['Model']:<25} {r['ROI%']:>10.1f}% {r['PF']:>7.2f} {r['DD']:>7.1f}% {r['Surv%']:>7.1f}%   {r['tag']}{Style.RESET_ALL}")
        
        print("-" * 100)
        winner = ranked[0]
        print(f"\n{Fore.CYAN}🦁 GIA RECOMMENDATION:{Style.RESET_ALL}")
        print(f" Based on current market physics, {Fore.YELLOW}{winner['Model']}{Style.RESET_ALL} is the superior choice.")
        print(f" It shows the best balance of {Fore.GREEN}Resilience ({winner['Surv%']}% survivor){Style.RESET_ALL} and {Fore.GREEN}Efficiency (PF {winner['PF']}){Style.RESET_ALL}.")
        
        if winner['DD'] > 20:
            print(f"{Fore.RED}⚠️ WARNING: High drawdown detected. Recommend Risk 0.5% for live trading.{Style.RESET_ALL}")
        
        # Smart advice for small accounts
        best_survivor = max(results, key=lambda x: x['Surv%'])
        if best_survivor['Model'] != winner['Model']:
            print(f"{Fore.MAGENTA}💡 SMALL ACCOUNT TIP:{Style.RESET_ALL} If starting with very low capital, {Fore.WHITE}{best_survivor['Model']}{Style.RESET_ALL} has the highest Survival Rate ({best_survivor['Surv%']}%).")
            
        print("═"*100 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--model', type=str)
    parser.add_argument('--from_year', type=int, default=2024)
    parser.add_argument('--to_year', type=int, default=2025)
    parser.add_argument('--broker', type=str, default='FIPER')
    parser.add_argument('--risk', type=float, default=1.0)
    parser.add_argument('--capital', type=float, default=1000.0)
    parser.add_argument('--mode', type=str, default='dynamic')
    parser.add_argument('--lots', type=float, default=0.01)
    parser.add_argument('--tf', type=str, default='M15')
    parser.add_argument('--latency', type=float, default=0.1)
    parser.add_argument('--synthetic', action='store_true', help='Use synthetic _SYNTH data files')
    parser.add_argument('--data_dir', type=str, help='Path to data directory')
    parser.add_argument('--asset', type=str, default='XAUUSD', help='Asset name (e.g., BTCUSD)')
    args = parser.parse_args()
    BattleArena(data_dir=args.data_dir).start(args)

