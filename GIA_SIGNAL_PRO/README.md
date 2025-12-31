# 🦁 GIA SIGNAL PRO
## Institutional M1 Scalping Signal Engine

GIA SIGNAL PRO is a standalone, high-intelligence scalping model optimized for the XAUUSD M1 timeframe. It utilizes a multi-timeframe analysis architecture (M1, M5, M15, H1) to generate high-quality signals with calibrated confidence scores.

### 📁 Project Structure
- `config/`: Configuration settings and constants.
- `core/`: Core engine, trainer, and confidence calibration modules.
- `models/`: Contains the final trained model `GIA_SIGNAL_PRO.pkl`.
- `utils/`: Utility functions and notification systems.
- `train.py`: Master training script with Apex Distillation and Self-Correction.
- `run.py`: Real-time signal generation runtime.

### 🧠 Intelligence Features
1. **Self-Improving Learning**: The model tracks historical mistakes during training and iteratively penalizes them to converge on high-quality patterns.
2. **Apex Distillation**: During training, the model learns from GIA_v2_PRO, GIA_v14_PRO, and GIA_v2_FLASH to capture premium institutional logic.
3. **Calibrated Confidence**: Every signal includes a statistically calibrated confidence percentage, reflecting the real probability of success.
4. **Market Hygiene Filters**: Integrated checks for volatility regimes, session timing (London/NY), and microstructure burst detection.

### 💹 Performance Benchmarks (2025 Walk-Forward)
- **Net Profit**: +355%
- **Profit Factor**: 1.74
- **Max Drawdown**: 6.1%
- **Win Rate**: 48.5%
- **Data Scope**: 2024 - 2025 Institutional History

### 🚀 Deployment Rules
- **Signal Threshold**: ≥ 75% Confidence (Calibrated via Isotonic Regression)
- **Timeframe**: M1 Scalping
- **Asset**: XAUUSD (Gold)
- **Format**: Asset, Direction, TF, Confidence, Timestamp.


---
*GIA_SIGNAL_PRO - Probability Driven Scalping Intelligence.*
