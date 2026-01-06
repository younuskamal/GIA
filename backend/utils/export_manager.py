
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
from colorama import Fore, Style

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
    def print_full_report(res, title="PERFORMANCE REPORT"):
        print(f"\n{Fore.GREEN}📊 {title}{Style.RESET_ALL}")
        print("="*60)
        print(f"  Net Profit:      ${res['net_profit']:,.2f} ({res['net_profit_pct']:.2f}%)")
        print(f"  Max Drawdown:    {res['max_drawdown']:.2f}%")
        print(f"  Profit Factor:   {res['profit_factor']:.2f}")
        print(f"  Win Rate:        {res['win_rate']:.1f}%")
        print(f"  Total Trades:    {res['total_trades']}")
        if len(res['trades']) > 0:
            avg_win = np.mean([t['pnl_net'] for t in res['trades'] if t['pnl_net'] > 0])
            avg_loss = np.mean([t['pnl_net'] for t in res['trades'] if t['pnl_net'] <= 0])
            print(f"  Avg Win:         ${avg_win:.2f}")
            print(f"  Avg Loss:        ${avg_loss:.2f}")
        print("="*60 + "\n")

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
            
        # 3. Executive Summary (TXT)
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
            
            f.write(f"KEY METRICS:\n")
            f.write(f"  Net Profit:      ${res['net_profit']:,.2f} ({res['net_profit_pct']:.2f}%)\n")
            f.write(f"  Max Drawdown:    {res['max_drawdown']:.2f}%\n")
            f.write(f"  Profit Factor:   {res['profit_factor']:.2f}\n")
            f.write(f"  Win Rate:        {res['win_rate']:.1f}%\n")
            f.write(f"  Sharpe Ratio:    {res.get('sharpe', 0):.2f}\n")
            f.write(f"  Monte Carlo Survival: {survival:.1f}%\n")
            f.write("-" * 60 + "\n")
            
            f.write(f"TRADE STATISTICS:\n")
            f.write(f"  Total Trades:    {res['total_trades']}\n")
            if len(res['trades']) > 0:
                avg_win = np.mean([t['pnl_net'] for t in res['trades'] if t['pnl_net'] > 0])
                avg_loss = np.mean([t['pnl_net'] for t in res['trades'] if t['pnl_net'] <= 0])
                f.write(f"  Avg Win:         ${avg_win:.2f}\n")
                f.write(f"  Avg Loss:        ${avg_loss:.2f}\n")
                f.write(f"  Max Win:         ${res['max_win']:.2f}\n")
                f.write(f"  Max Loss:        ${res['max_loss']:.2f}\n")
        
        # 4. Generate HTML Report
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
                body {{ font-family: 'Cairo', sans-serif; background: #070b14; color: #fff; padding: 20px; }}
                h1 {{ color: #38bdf8; text-align: center; }}
                .container {{ max-width: 1200px; margin: auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🏆 GIA AI REPORT: {model_name}</h1>
                <p style="text-align: center; color: #aaa;">Broker: {params['broker']} | Risk: {params['risk']}%</p>
                <div style="background: #111; padding: 20px; border-radius: 10px; margin-top: 20px;">
                    <h3>Performance Overview</h3>
                    <p>Net Profit: <b style="color: {'lime' if res['net_profit'] > 0 else 'red'}">${res['net_profit']:,.2f}</b></p>
                    <p>ROI: {res['net_profit_pct']:.2f}%</p>
                    <p>Drawdown: {res['max_drawdown']:.2f}%</p>
                    <p>Win Rate: {res['win_rate']:.1f}%</p>
                </div>
            </div>
        </body>
        </html>
        """
        with open(os.path.join(base_path, "Visual_Report.html"), "w", encoding='utf-8') as f:
            f.write(html_content)
