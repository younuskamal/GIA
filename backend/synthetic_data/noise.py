
import random
import numpy as np
from config import SyntheticConfig

class NoiseGenerator:
    """Generates asset-specific micro-structure noise and sudden price spikes."""
    
    @staticmethod
    def get_news_spike(asset_profile, stress_level='NORMAL'):
        """Simulates a sudden news event based on asset profile."""
        prob_mult = 1.0
        if stress_level == 'EXTREME': prob_mult = 3.0
        elif stress_level == 'LOW': prob_mult = 0.5

        if random.random() < (SyntheticConfig.NEWS_PROB * prob_mult):
            direction = 1 if random.random() > 0.5 else -1
            impact = asset_profile['news_impact'] * (0.8 + random.random() * 0.5)
            return direction * impact
        return 0.0

    @staticmethod
    def get_micro_noise(volatility):
        """Simulates tiny fluctuations."""
        return np.random.normal(0, volatility * 0.1)

    @staticmethod
    def get_wick_factor(asset_profile):
        """Returns a multiplier for high/low wick generation based on asset intensity."""
        intensity = asset_profile['wick_multiplier']
        # lognormal to ensure positive wicks with some extreme outliers
        return 1.0 + np.random.lognormal(0.0, 0.4) * (intensity * 0.5)
