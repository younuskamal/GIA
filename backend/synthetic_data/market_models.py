
import random
from noise import NoiseGenerator

class CandleFactory:
    """Universal Asset Candle Anatomy Model."""
    
    @staticmethod
    def create_candle(asset_profile, open_price, drift, vol, session_mult, stress_level):
        """Generates a single candle for any asset class."""
        
        # 1. Price Change
        news = NoiseGenerator.get_news_spike(asset_profile, stress_level)
        noise = NoiseGenerator.get_micro_noise(vol)
        
        change = (drift + news + noise + (vol * session_mult * random.gauss(0, 1)))
        close_price = open_price * (1 + change)
        
        # 2. Wicks (Shadows)
        body_abs = abs(close_price - open_price)
        max_body = max(open_price, close_price)
        min_body = min(open_price, close_price)
        
        wick_intensity = NoiseGenerator.get_wick_factor(asset_profile)
        # Randomize distribution between upper and lower wick
        total_wick_space = body_abs * wick_intensity
        upper_wick = total_wick_space * random.random()
        lower_wick = total_wick_space * random.random()
        
        high = max_body + upper_wick
        low = min_body - lower_wick
        
        # 3. Digits & Precision
        digits = asset_profile['digits']
        
        # 4. Volume Profile
        base_vol = 1000 if asset_profile.get('has_weekends', True) else 10000
        volume = int(base_vol * session_mult * (0.5 + random.random()))
        
        return {
            'Open': round(open_price, digits),
            'High': round(high, digits),
            'Low': round(low, digits),
            'Close': round(close_price, digits),
            'Volume': volume
        }
