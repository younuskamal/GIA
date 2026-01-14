# 🦁 GIA (Gold Institutional Advisor) - System Architecture v4.0

## 1. Project Overview
GIA is a high-frequency, institutional-grade autonomous trading system designed exclusively for **Gold (XAUUSD)**. It leverages a hybrid AI architecture (XGBoost + Wavelet Transforms + Technical Indicators) to execute trades via the **cTrader Open API (Protobuf)**.

The system is optimized for **Linux-based Server deployment** and features a 24/7 autonomous loop with real-time Telegram control.

---

## 2. Core Architecture
The system is divided into five specialized layers:

### A. Execution Layer (`ctrader_bridge.py`)
- **Protocol:** Specialized implementation of cTrader's Protobuf Open API.
- **Identity:** Handles authentication (App & Account), Symbol mapping, and real-time Spot/Execution events.
- **Institutional Sizing:** Implements a dynamic volume multiplier that scales lot sizes based on the broker's `minVolume` and `stepVolume` to ensure order acceptance across different brokers.
- **State Management:** Tracks internal `position_state` for Trailing Stops, Break-even (BE) triggers, and Maximum Favorable Excursion (MFE).
- **Anti-Spam:** Synchronizes closure notifications using a `notified_closures` set to prevent duplicate reports for a single position.

### B. Analysis Layer (`inference.py`)
- **MTF Feature Engineering:** Real-time generation of 85+ features across multiple timeframes (M1, M5, M15, M30, H1).
- **Hybrid Engines:**
    - `EliteDuoEngine`: Harmonizes PRO (M15) for trend and FLASH (M1) for entries.
    - `TripleConsensusModel`: Requires agreement across v2_PRO, v2_FLASH, and v14_Institutional models.
- **Adaptive Pulse:** Triggers analysis every 60 seconds (Minute-based key) rather than waiting for candle closures, capturing intra-candle micro-structure.

### C. Strategic Guard Layer (`strategy.py`)
- **Market Entropy:** Filters trades during chaotic/efficient market phases (Entropy > 2.0).
- **Exhaustion Index:** Prevents FOMO entries during extreme price extensions.
- **Dynamic Risk Logic:** Calculates risk as a percentage of **Dynamic Equity** (Balance + Floating PnL), not just balance.
- **News/Gap Guards:** Automatic halts during high-impact news or weekend market gaps.

### D. Interface Layer (`telegram_service.py`)
- **GIA Vision Dashboard:** A real-time command center showing AI confidence, RSI pulse, volatility regime, news safety, and Account Health (Equity/PnL).
- **Autonomous Feedback:** Sends Arabic-localized reports for every trade open/close with precise entry/exit logic.
- **Neural Trigger:** Allows manual initiation of background model retraining.

### E. Self-Learning Layer (`train.py`)
- **Predator Mode:** Retrains models on the latest server-cached data (CSVs).
- **Neural Link:** Automatically updates the live `GIA_v2_PRO.pkl` brain upon training completion via hot-swapping (Inference engine reloads on the next cycle).

---

## 3. High-Frequency Execution Logic
1. **Pulse Trigger:** Main loop (`run_live_demo.py`) detects a new minute.
2. **Data Sync:** Bridge fetches latest M1/M15/H1 candles from Broker.
3. **Inference:** AI predicts direction (BUY/SELL/WAIT) + Confidence.
4. **Strategy Filter:** StrategyHandler applies Entropy, Clustering, and News filters.
5. **Auto-Sizing:** Risk engine calculates Lots based on ATR and Account Equity.
6. **Transmission:** Bridge sends `ProtoOANewOrderReq`.
7. **Protection:** Once Filled, the system immediately sends a `ProtoOAAmendPositionSLTPReq` for Stop Loss and Take Profit protection.

---

## 4. Key Improvements (Release v4.0.2)
- [x] **Dynamic Equity Property:** PnL is hardware-calculated from `grossProfit` cents.
- [x] **XGold Heuristic:** Corrected volume multiplier to handle XAUUSD unit differences (e.g., 100 vs 100,000).
- [x] **Closure Integrity:** Verified `positionStatus == 2` for true closure detection.
- [x] **Background Training:** Retraining no longer blocks the main trading thread.

---

## 5. Technical Requirements
- **Runtime:** Python 3.10+ (Linux Recommended).
- **Communication:** cTrader Open API ID + Secret + Access Token.
- **User Control:** Telegram Bot API.
- **Process Manager:** `screen` session named `gia_institutional`.
