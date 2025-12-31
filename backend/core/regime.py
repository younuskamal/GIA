
import pandas as pd
import numpy as np

class MarketRegimeEngine:
    """
    Classifies market state into TREND, RANGE, or HIGH_VOL/CHAOS.
    Used for filtering and feature enrichment.
    """
    def __init__(self, atr_period=14, bb_period=20, rsi_period=14):
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.rsi_period = rsi_period

    def classify(self, df):
        """
        Classifies each row of the dataframe.
        """
        df = df.copy()
        
        # 1. Calculate ATR Slope
        df['atr'] = self._calculate_atr(df, self.atr_period)
        df['atr_slope'] = df['atr'].diff(5) / df['atr'].shift(5)
        
        # 2. Calculate BB Width
        df['ma_bb'] = df['close'].rolling(window=self.bb_period).mean()
        df['std_bb'] = df['close'].rolling(window=self.bb_period).std()
        df['bb_upper'] = df['ma_bb'] + (2 * df['std_bb'])
        df['bb_lower'] = df['ma_bb'] - (2 * df['std_bb'])
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['ma_bb']
        
        # 3. Momentum Dispersion (Difference between short and long EMA)
        df['ema_short'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema_long'] = df['close'].ewm(span=26, adjust=False).mean()
        df['mom_dispersion'] = (df['ema_short'] - df['ema_long']).abs() / df['ma_bb']
        
        # 4. RSI Variance
        df['rsi'] = self._calculate_rsi(df, self.rsi_period)
        df['rsi_var'] = df['rsi'].rolling(window=10).std()
        
        # Adaptive Thresholds (Rolling 500 bars ~ 1 week of data)
        rolling_vol_q90 = df['bb_width'].rolling(window=500).quantile(0.90)
        rolling_rsi_q90 = df['rsi_var'].rolling(window=500).quantile(0.90)
        rolling_mom_median = df['mom_dispersion'].rolling(window=500).median()
        rolling_vol_median = df['bb_width'].rolling(window=500).median()

        # Default State
        df['regime'] = 'RANGE'
        
        # High Vol/Chaos: Wide BB or high RSI variance relative to recent history
        chaos_mask = (df['bb_width'] > rolling_vol_q90) | (df['rsi_var'] > rolling_rsi_q90)
        df.loc[chaos_mask, 'regime'] = 'HIGH_VOL'
        
        # Trend: High momentum dispersion relative to recent median
        trend_mask = (df['mom_dispersion'] > rolling_mom_median) & \
                     (df['regime'] != 'HIGH_VOL') & \
                     (df['bb_width'] > rolling_vol_median)
        df.loc[trend_mask, 'regime'] = 'TREND'
        
        # Map regimes to integers
        regime_map = {'RANGE': 0, 'TREND': 1, 'HIGH_VOL': 2}
        df['regime_flag'] = df['regime'].map(regime_map).fillna(0).astype(int)
        
        return df

    def _calculate_atr(self, df, period):
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return true_range.rolling(period).mean()

    def _calculate_rsi(self, df, period):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
