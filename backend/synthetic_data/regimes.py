
import numpy as np
import random
from config import SyntheticConfig, AssetProfiles

class RegimeManager:
    """Handles asset-specific market regime transitions and state logic."""
    
    def __init__(self, asset_name):
        self.asset_name = asset_name
        self.profile = self._get_profile(asset_name)
        self.current_regime = 'RANGING'
        self.regime_timer = 0
        self.config = SyntheticConfig.REGIMES

    def _get_profile(self, name):
        for category in [AssetProfiles.METALS, AssetProfiles.FOREX, AssetProfiles.CRYPTO]:
            if name in category:
                return category[name]
        raise ValueError(f"Asset {name} not found in profiles.")

    def update(self):
        """Transition logic for market regimes."""
        if self.regime_timer <= 0:
            regimes = list(self.config.keys())
            probs = [self.config[r]['prob'] for r in regimes]
            self.current_regime = np.random.choice(regimes, p=probs)
            
            # Asset specific regime durations
            if self.asset_name == 'BTCUSD':
                self.regime_timer = random.randint(100, 1000) # Faster shifts in Crypto
            else:
                self.regime_timer = random.randint(1440, 5000) # 1-4 days for FX/Metals
                
        self.regime_timer -= 1
        
        regime_data = self.config[self.current_regime]
        return {
            'drift': self.profile['drift'] * regime_data['drift_mult'],
            'vol': self.profile['volatility'] * regime_data['vol_mult']
        }

    def get_session_mult(self, hour):
        """Get volatility multiplier based on trading session and asset type."""
        # Crypto is 24/7 with less session dependency
        if not self.profile['has_weekends']:
            return 1.0 + (random.random() * 0.2) # Slight random variance

        active_mults = []
        for sess, data in SyntheticConfig.SESSIONS.items():
            if data['start'] <= hour < data['end']:
                active_mults.append(data['vol_mult'])
        
        return max(active_mults) if active_mults else 0.5
