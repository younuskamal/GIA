import os

class AssetProfiles:
    # 🥇 METALS: High volatility, Sharp wicks, Institutional spikes
    METALS = {
        'XAUUSD': {
            'base_price': 2050.0,
            'volatility': 0.0006,
            'drift': 0.0001,
            'wick_multiplier': 2.0,
            'news_impact': 0.015,
            'has_weekends': True,
            'digits': 2
        },
        'XAGUSD': {
            'base_price': 23.50,
            'volatility': 0.0009,
            'drift': 0.00015,
            'wick_multiplier': 2.5,
            'news_impact': 0.020,
            'has_weekends': True,
            'digits': 3
        }
    }

    # 💱 FOREX: Clean trends, Smoother moves, Session dependent
    FOREX = {
        'USDJPY': {
            'base_price': 148.50,
            'volatility': 0.0003,
            'drift': 0.00005,
            'wick_multiplier': 1.2,
            'news_impact': 0.005,
            'has_weekends': True,
            'digits': 3
        },
        'GBPJPY': {
            'base_price': 185.20,
            'volatility': 0.0005,
            'drift': 0.00008,
            'wick_multiplier': 1.8,
            'news_impact': 0.008,
            'has_weekends': True,
            'digits': 3
        }
    }

    # ₿ CRYPTO: Extreme volatility, 24/7 trading, Momentum runs
    CRYPTO = {
        'BTCUSD': {
            'base_price': 45000.0,
            'volatility': 0.0015,
            'drift': 0.0005,
            'wick_multiplier': 3.0,
            'news_impact': 0.040,
            'has_weekends': False,
            'digits': 1
        }
    }

class SyntheticConfig:
    # 🌍 Environment
    START_DATE = "2024-01-01 00:00:00"
    TIMEZONE = "UTC"
    SEED = 42
    
    # 📊 Regime Logic (Default mix)
    REGIMES = {
        'BULL_TREND':      {'drift_mult': 1.5,  'vol_mult': 1.2, 'prob': 0.15},
        'BEAR_TREND':      {'drift_mult': -1.5, 'vol_mult': 1.2, 'prob': 0.15},
        'RANGING':         {'drift_mult': 0.0,  'vol_mult': 0.8, 'prob': 0.55},
        'LIQUIDITY_SHOCK': {'drift_mult': 0.0,  'vol_mult': 4.0, 'prob': 0.15}
    }
    
    # 🕒 Session Physics (Applied to Forex/Metals)
    SESSIONS = {
        'ASIA':   {'start': 0,  'end': 8,  'vol_mult': 0.6},
        'LONDON': {'start': 8,  'end': 16, 'vol_mult': 1.2},
        'NY':     {'start': 13, 'end': 21, 'vol_mult': 1.5},
        'GAP':    {'start': 22, 'end': 23, 'vol_mult': 0.1}
    }
    
    # Selection of Active Asset for the next run
    # Options: XAUUSD, XAGUSD, USDJPY, GBPJPY, BTCUSD
    ACTIVE_ASSET = 'XAUUSD'
    STRESS_LEVEL = 'NORMAL' # LOW, NORMAL, EXTREME
    NEWS_PROB = 0.0015      # Global probability of a news spike per minute
    
    # 📂 Paths (Relative to project root for cross-platform support)
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
