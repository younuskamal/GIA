
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
            elif f == 'body_ratio' or f == 'body_rel':
                 df[f] = (df['close'] - df['open']).abs() / (df['high'] - df['low'] + 1e-9)
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
            <title>تقرير أداء GIA PRO - {model_name}</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
                body {{ font-family: 'Cairo', sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
                .container {{ max-width: 1200px; margin: auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
                .header {{ border-bottom: 2px solid #334155; padding-bottom: 20px; margin-bottom: 30px; text-align: center; }}
                .header h1 {{ margin: 0; color: #38bdf8; font-size: 2.5em; }}
                .header p {{ color: #94a3b8; font-size: 1.1em; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 30px; }}
                .stat-card {{ background: #0f172a; padding: 15px; border-radius: 8px; border: 1px solid #334155; text-align: center; transition: transform 0.2s; }}
                .stat-card:hover {{ transform: translateY(-5px); border-color: #38bdf8; }}
                .stat-card h3 {{ margin: 0; color: #94a3b8; font-size: 0.85em; text-transform: uppercase; }}
                .stat-card p {{ margin: 8px 0 0; font-size: 1.5em; font-weight: bold; color: #38bdf8; }}
                .chart-container {{ background: #0f172a; padding: 20px; border-radius: 8px; margin-bottom: 30px; border: 1px solid #334155; height: 450px; }}
                .trades-section {{ background: #0f172a; padding: 20px; border-radius: 8px; border: 1px solid #334155; }}
                .table-wrapper {{ overflow-x: auto; max-height: 500px; margin-top: 15px; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
                th {{ padding: 12px; text-align: right; background: #1e293b; color: #38bdf8; position: sticky; top: 0; z-index: 10; border-bottom: 2px solid #334155; }}
                td {{ padding: 10px; text-align: right; border-bottom: 1px solid #334155; color: #f8fafc; }}
                .win {{ color: #22c55e !important; font-weight: bold; }}
                .loss {{ color: #ef4444 !important; font-weight: bold; }}
                .footer {{ text-align: center; margin-top: 40px; color: #64748b; font-size: 0.85em; }}
                ::-webkit-scrollbar {{ width: 8px; }}
                ::-webkit-scrollbar-track {{ background: #0f172a; }}
                ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 4px; }}
                ::-webkit-scrollbar-thumb:hover {{ background: #38bdf8; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🦁 ذكاء الأداء - نظام GIA PRO</h1>
                    <p>الموديل: {model_name} | الوسيط: {params['broker']} | الإطار الزمني: {params['tf']}</p>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card"><h3>صافي الربح</h3><p class="{ 'win' if res['net_profit'] >=0 else 'loss' }">${res['net_profit']:.2f}</p></div>
                    <div class="stat-card"><h3>عائد الإستثمار</h3><p class="{ 'win' if res['net_profit_pct'] >=0 else 'loss' }">{res['net_profit_pct']:.2f}%</p></div>
                    <div class="stat-card"><h3>عامل الربح</h3><p>{res['profit_factor']:.2f}</p></div>
                    <div class="stat-card"><h3>نسبة النجاح</h3><p>{res['win_rate']:.1f}%</p></div>
                    <div class="stat-card"><h3>أقصى تراجع</h3><p class="loss">{res['max_drawdown']:.2f}%</p></div>
                    <div class="stat-card"><h3>معدل البقاء</h3><p class="win">{survival:.1f}%</p></div>
                    <div class="stat-card"><h3>نسبة شارب</h3><p>{res.get('sharpe', 0):.2f}</p></div>
                    <div class="stat-card"><h3>الصفقات/يوم</h3><p>{res.get('avg_trades_day', 0):.1f}</p></div>
                </div>

                <div class="chart-container">
                    <canvas id="equityChart"></canvas>
                </div>

                <div class="header" style="margin-top: 40px;"><h2>📊 تحليل الموسمية (الأداء حسب التوقيت)</h2></div>
                <div class="stats-grid">
                    <div class="chart-container" style="height: 300px;">
                        <canvas id="hourlyChart"></canvas>
                    </div>
                    <div class="chart-container" style="height: 300px;">
                        <canvas id="dailyChart"></canvas>
                    </div>
                </div>

                <div class="trades-section">
                    <h2 style="margin: 0; color: #38bdf8; font-size: 1.5em;">📜 سجل الصفقات التفصيلي</h2>
                    <div class="table-wrapper">
                        <table id="tradesTable">
                            <thead>
                                <tr>
                                    <th>تاريخ الدخول</th>
                                    <th>النوع</th>
                                    <th>سعر الدخول</th>
                                    <th>الربح/الخسارة ($)</th>
                                    <th>النسبة (%)</th>
                                    <th>سبب الخروج</th>
                                </tr>
                            </thead>
                            <tbody></tbody>
                        </table>
                    </div>
                </div>

                <div class="footer">
                    GIA TRADING SYSTEMS - INTEGRATED ANALYTICAL SUITE v2.4 <br>
                    تم إنشاء هذا التقرير تلقائياً بتاريخ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>

            <script>
                // 🕒 Hourly Performance Chart
                const hourlyCtx = document.getElementById('hourlyChart').getContext('2d');
                const hourlyData = {json.dumps(res.get('hourly_pnl', [0]*24))};
                new Chart(hourlyCtx, {{
                    type: 'bar',
                    data: {{
                        labels: Array.from({{length: 24}}, (_, i) => i + ':00'),
                        datasets: [{{
                            label: 'الربح ($)',
                            data: hourlyData,
                            backgroundColor: hourlyData.map(v => v >= 0 ? 'rgba(34, 197, 94, 0.6)' : 'rgba(239, 68, 68, 0.6)'),
                            borderRadius: 4
                        }}]
                    }},
                    options: {{
                        responsive: true, maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{ y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }} }}
                    }}
                }});

                // 📅 Daily Performance Chart
                const dailyCtx = document.getElementById('dailyChart').getContext('2d');
                const days = ['الاثن', 'الثلاث', 'الأربع', 'الخميس', 'الجمعة', 'السبت', 'الأحد'];
                const dailyData = {json.dumps(res.get('daily_pnl', [0]*7))};
                new Chart(dailyCtx, {{
                    type: 'bar',
                    data: {{
                        labels: days,
                        datasets: [{{
                            label: 'الربح ($)',
                            data: dailyData,
                            backgroundColor: dailyData.map(v => v >= 0 ? 'rgba(34, 197, 94, 0.6)' : 'rgba(239, 68, 68, 0.6)'),
                            borderRadius: 4
                        }}]
                    }},
                    options: {{
                        responsive: true, maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{ y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }} }}
                    }}
                }});

                // 📈 Equity Curve
                const ctx = document.getElementById('equityChart').getContext('2d');
                const equityData = {equity_data};
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: Array.from({{length: equityData.length}}, (_, i) => i),
                        datasets: [{{
                            label: 'Equity Growth',
                            data: equityData,
                            borderColor: '#38bdf8',
                            backgroundColor: 'rgba(56, 189, 248, 0.1)',
                            fill: true,
                            tension: 0.1,
                            pointRadius: 0,
                            borderWidth: 2
                        }}]
                    }},
                    options: {{
                        responsive: true, maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }} }}
                    }}
                }});

                // 📋 Table Populator
                try {{
                    const trades = {trades_json};
                    const tbody = document.querySelector('#tradesTable tbody');
                    if (trades && trades.length > 0) {{
                        trades.forEach(t => {{
                            const row = document.createElement('tr');
                            const pnl = parseFloat(t.pnl_net || t.pnl || 0);
                            const pnlClass = pnl >= 0 ? 'win' : 'loss';
                            
                            const date = t.entry_date || t.date || t.time || 'N/A';
                            const type = t.type || 'N/A';
                            const price = parseFloat(t.entry_price || t.price || 0).toFixed(2);
                            const pnlStr = pnl.toFixed(2);
                            const pctStr = (t.pnl_pct || 0).toFixed(2);
                            const reason = t.exit_reason || 'Manual';

                            row.innerHTML = `
                                <td>${{date}}</td>
                                <td>${{type}}</td>
                                <td>${{price}}</td>
                                <td class="${{pnlClass}}">${{pnlStr}}</td>
                                <td class="${{pnlClass}}">${{pctStr}}%</td>
                                <td>${{reason}}</td>
                            `;
                            tbody.appendChild(row);
                        }});
                    }} else {{
                        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding: 20px;">لا توجد صفقات مسجلة</td></tr>';
                    }}
                }} catch (e) {{
                    console.error("Error populating trades:", e);
                }}
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
    def __init__(self):
        self.data_dir = os.path.join(os.getcwd(), 'backend', 'hestory')
        self.models_dir = os.path.join(os.getcwd(), 'backend', 'models')
        self.pro_models_dir = os.path.join(os.getcwd(), 'GIA_SIGNAL_PRO', 'models')
        self.cache = {}

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
        res['max_consecutive_losses'] = loss_streaks.max() if not loss_streaks.empty else 0
        
        # 🕒 Seasonality Calculation
        trades['hour'] = trades['entry_date'].dt.hour
        trades['day'] = trades['entry_date'].dt.dayofweek
        
        hourly = trades.groupby('hour')['pnl_net'].sum()
        res['hourly_pnl'] = [float(hourly.get(h, 0)) for h in range(24)]
        
        daily = trades.groupby('day')['pnl_net'].sum()
        res['daily_pnl'] = [float(daily.get(d, 0)) for d in range(7)]
        
        return res

    def start(self, cli_args=None):
        print_banner()
        
        if cli_args:
            if cli_args.compare:
                targets = sorted([m for m in os.listdir(self.models_dir) if m.endswith('.pkl')])
                if os.path.exists(self.pro_models_dir):
                    targets += sorted([m for m in os.listdir(self.pro_models_dir) if m.endswith('.pkl')])
            else:
                targets = [cli_args.model] if cli_args.model else []
            
            tf = getattr(cli_args, 'tf', "M15")
            broker = cli_args.broker
            capital = cli_args.capital
            risk = cli_args.risk
            sizing_mode = cli_args.mode
            fixed_lot = cli_args.lots
            start_y = cli_args.from_year
            end_y = cli_args.to_year
        else:
            # --- PROFESSIONAL DASHBOARD ---
            print(f"\n {Fore.YELLOW}STEP 1: SELECT YOUR AI MODEL{Style.RESET_ALL}")
            models_main = sorted([f for f in os.listdir(self.models_dir) if f.endswith('.pkl')])
            models_pro = sorted([f for f in os.listdir(self.pro_models_dir) if f.endswith('.pkl')]) if os.path.exists(self.pro_models_dir) else []
            
            all_paths = {m: os.path.join(self.models_dir, m) for m in models_main}
            for m in models_pro: all_paths[m] = os.path.join(self.pro_models_dir, m)
            
            all_models = sorted(list(all_paths.keys()))
            for i, m in enumerate(all_models):
                label = "[PRO]" if m in models_pro else "[CORE]"
                print(f"  [{Fore.GREEN}{i+1}{Style.RESET_ALL}] {m:<25} {Fore.LIGHTBLACK_EX}{label}{Style.RESET_ALL}")
            print(f"  [{Fore.GREEN}A{Style.RESET_ALL}] COMPARE ALL MODELS")
            
            choice = input(f"\n {Fore.WHITE}Enter Selection > {Style.RESET_ALL}").strip().upper()
            targets = all_models if choice == 'A' else [all_models[int(choice)-1]] if choice.isdigit() else [all_models[0]]

            print(f"\n {Fore.YELLOW}STEP 2: SELECT EXECUTION TIMEFRAME{Style.RESET_ALL}")
            print(f"  [{Fore.GREEN}0{Style.RESET_ALL}] M1 (Scalping)   [{Fore.GREEN}1{Style.RESET_ALL}] M15 (Tactical)  [{Fore.GREEN}2{Style.RESET_ALL}] M30 (Balanced)  [{Fore.GREEN}3{Style.RESET_ALL}] H1 (Strategic)")
            tf_choice = input(f"\n {Fore.WHITE}Enter Selection [Default M15] > {Style.RESET_ALL}").strip() or "1"
            tf = {"0":"M1", "1":"M15", "2":"M30", "3":"H1"}.get(tf_choice, "M15")

            print(f"\n {Fore.YELLOW}STEP 3: BROKER PHYSICS{Style.RESET_ALL}")
            brokers = list(BrokerSimulator.PROFILES.keys())
            for i, b in enumerate(brokers): print(f"  [{Fore.GREEN}{i+1}{Style.RESET_ALL}] {b:12}", end=" " if (i+1)%3 != 0 else "\n")
            b_choice = input(f"\n\n {Fore.WHITE}Select Broker [Enter for FIPER] > {Style.RESET_ALL}").strip()
            broker = brokers[int(b_choice)-1] if b_choice.isdigit() else "FIPER"
            
            sizing_mode = "dynamic" if (input(f"\n {Fore.YELLOW}STEP 4: MM MODE (1=Dynamic, 2=Fixed) > {Style.RESET_ALL}") or "1") == "1" else "fixed"
            fixed_lot = float(input(f"  {Fore.WHITE}Fixed Lot Size [0.01] > {Style.RESET_ALL}") or 0.01) if sizing_mode == "fixed" else 0.01
            capital = float(input(f"  {Fore.WHITE}STEP 5: CAPITAL > {Style.RESET_ALL}") or 1000)
            risk = float(input(f"  {Fore.WHITE}STEP 6: RISK % > {Style.RESET_ALL}") or 1.0) if sizing_mode == "dynamic" else 1.0
            start_y, end_y = 2024, 2025

        # --- EXECUTION LOOP ---
        final_table = []
        comparison_data = []
        base_tf = tf

        for m_name in targets:
            print_separator("-", color=Fore.LIGHTBLACK_EX)
            current_tf = "M1" if "SIGNAL_PRO" in m_name else base_tf
            print(f"🦁 {Fore.WHITE}ENGINEERING: {Fore.YELLOW}{m_name}{Style.RESET_ALL} | {Fore.CYAN}{current_tf}{Style.RESET_ALL} [NATIVE]")
            
            try:
                pro_path = os.path.join(self.pro_models_dir, m_name)
                core_path = os.path.join(self.models_dir, m_name)
                path = pro_path if os.path.exists(pro_path) else core_path
                
                m_data = joblib.load(path)
                req_feats = m_data.get('feature_columns', m_data.get('features', []))
                needs_mtf = any(('_h1' in f or '_m15' in f or '_m5' in f or '_m30' in f) for f in req_feats)
                
                df = self._load_data(current_tf, needs_mtf)
                df = df[(df['date'].dt.year >= start_y) & (df['date'].dt.year <= end_y)].copy()
                if df.empty: continue
                
                df_proc = FeatureFactory.construct(df, req_feats)
                df_proc = df_proc.dropna(subset=[f for f in req_feats if f in df_proc.columns])
                
                engine = BacktestEngine(model_path=path, is_legacy="v14" in m_name)
                engine.load_model()
                
                res = engine.backtest(df_proc, broker_name=broker, initial_balance=capital, risk_pct=risk, sizing_mode=sizing_mode, fixed_lot_size=fixed_lot)
                if "error" in res: continue

                res = self._calculate_extended_stats(res)
                
                # Monte Carlo Stress
                mc_pnl = []
                for _ in range(3):
                    rmc = engine.backtest(df_proc, broker_name=broker, risk_pct=risk, initial_balance=capital, sizing_mode=sizing_mode, fixed_lot_size=fixed_lot)
                    if "error" not in rmc: mc_pnl.append(rmc['net_profit_pct'])
                survival = (len([p for p in mc_pnl if p > 0]) / len(mc_pnl)) * 100 if mc_pnl else 0
                
                params = {"tf": current_tf, "broker": broker, "start": start_y, "end": end_y, "risk": risk if sizing_mode == 'dynamic' else f"FIXED {fixed_lot}", "mode": sizing_mode}
                save_path = ExportManager.save(m_name, res, survival, params)
                
                print_ascii_chart(res['equity_curve'], title=f"GIA Elite Bench: {m_name}")
                print(f" {Fore.WHITE}Trades: {Fore.GREEN}{res['win_count']}W {Fore.RED}{res['loss_count']}L {Fore.WHITE}| ROI: {res['net_profit_pct']:.2f}% | Surv: {survival:.1f}%")
                
                final_table.append({"Model": m_name, "PF": res['profit_factor'], "DD": res['max_drawdown'], "ROI%": res['net_profit_pct'], "Surv%": survival})
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
            dash_path = ExportManager._generate_comparison_dashboard(comparison_data, {"broker": broker})
            print(f"\n{Fore.GREEN}🏆 Global Dashboard Ready: {Fore.WHITE}{dash_path}{Style.RESET_ALL}")

    def _load_data(self, primary_tf, needs_multi):
        key = f"{primary_tf}_{'MTF' if needs_multi else 'STF'}"
        if key in self.cache: return self.cache[key]
        
        df_p = self._read_csv(f'XAUUSD_{primary_tf}.csv')
        if needs_multi:
            # Enhanced Context Mapping: Ensure all common training contexts are available
            contexts = [('m1', 'XAUUSD_M1.csv'), ('m5', 'XAUUSD_M1.csv'), ('m15', 'XAUUSD_M15.csv'), ('m30', 'XAUUSD_M30.csv'), ('h1', 'XAUUSD_H1.csv')]
            merged = df_p.sort_values('date')
            for suffix, filename in contexts:
                try:
                    target_path = os.path.join(self.data_dir, filename)
                    if not os.path.exists(target_path): continue
                    
                    df_sec = self._read_csv(filename)
                    if suffix == 'm5' and 'M1.csv' in filename:
                        # Resample M1 to M5 context
                        df_sec = df_sec.set_index('date').resample('5min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
                    
                    eng_sec = self._engineer_secondary(df_sec, suffix)
                    merged = pd.merge_asof(merged, eng_sec.sort_values('date'), on='date', direction='backward')
                except Exception as e:
                    print(f"   {Fore.RED}⚠️ Error merging context {suffix}: {e}{Style.RESET_ALL}")
            
            self.cache[key] = merged.dropna()
        else:
            self.cache[key] = df_p
        return self.cache[key]

    def _read_csv(self, name):
        df = pd.read_csv(os.path.join(self.data_dir, name))
        df.columns = [c.lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['time'], format='%m/%d/%Y %I:%M:%S %p' if '/' in str(df['time'].iloc[0]) else None)
        return df

    def _engineer_secondary(self, df, suffix):
        df = df.copy()
        df[f'rsi_{suffix}'] = FeatureFactory._rsi(df['close'])
        e12 = df['close'].ewm(span=12, adjust=False).mean()
        e26 = df['close'].ewm(span=26, adjust=False).mean()
        df[f'macd_{suffix}'] = (e12 - e26) / (df['close'] + 1e-9)
        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df[f'bb_width_{suffix}'] = (4 * std) / (ma + 1e-9)
        df[f'bbw_{suffix}'] = df[f'bb_width_{suffix}']
        # 🧪 Critical features for advanced models (GIA_SIGNAL_PRO)
        df[f'vol_{suffix}'] = df['close'].pct_change().rolling(20).std()
        df[f'trend_{suffix}'] = np.sign(df['close'].diff(5))
        
        # FIX: Ensure 'date' is present but NOT duplicated in the list
        cols_to_keep = ['date'] + [c for c in df.columns if c.endswith(suffix)]
        # Remove duplicates while preserving order
        seen = set()
        clean_cols = [x for x in cols_to_keep if not (x in seen or seen.add(x))]
        return df[clean_cols]

    def _print_scoreboard(self, scores):
        print("\n" + Fore.YELLOW + "="*80)
        print(f"{'🏆 GIA PRO BATTLEGROUND LEADERBOARD':^80}")
        print("="*80 + Style.RESET_ALL)
        print(f"{Fore.CYAN}{'Model Name':<25} | {'PF':<8} | {'MDD%':<8} | {'ROI%':<10} | {'Surv%':<8}")
        for s in sorted(scores, key=lambda x: x['PF'], reverse=True):
            print(f"{Fore.WHITE}{s['Model']:<25}{Style.RESET_ALL} | {s['PF']:<8.2f} | {s['DD']:<8.2f} | {s['ROI%']:<10.2f} | {s['Surv%']:<8.1f}")
        print(Fore.YELLOW + "="*80 + Style.RESET_ALL + "\n")

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
    args = parser.parse_args()
    BattleArena().start(args)

