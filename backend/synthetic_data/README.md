
# 🦁 GIA Universal Market Simulator

Institutional-grade multi-asset synthetic data generator.

## 📊 Supported Assets
- **Metals**: `XAUUSD` (Gold), `XAGUSD` (Silver)
- **Forex**: `USDJPY` (Smoother trends), `GBPJPY` (Aggressive volatility)
- **Crypto**: `BTCUSD` (24/7 trading, Extreme momentum, Crashes/Pumps)

## 🚀 Usage
To generate a specific asset (2-year dataset):
```bash
python generate_year.py BTCUSD
```
Or edit `ACTIVE_ASSET` in `config.py` and run:
```bash
python generate_year.py
```

## 🧠 Institutional Physics
1. **Asset-Specific DNA**: Each asset has its own volatility coefficient, drift, and candle morphology (wicks/body ratios).
2. **Session Context**: Forex and Metals respect Asia/London/NY sessions. Crypto operates 24/7 with stochastic volatility spikes.
3. **Stress Testing**: Set `STRESS_LEVEL` to `EXTREME` in `config.py` to simulate black-swan news events and massive slippage scenarios.
4. **Consistency**: M15, M30, and H1 are strictly aggregated from M1 to eliminate look-ahead bias and ensure 100% time-alignment for M15 models like GIA_v2_PRO.

## 📂 Output Locations
Files are saved as `<ASSET>_<TF>_SYNTH.csv` in `backend/hestory/`.
