
import numpy as np

class ConfidenceCalculator:
    """
    🦁 GIA SIGNAL PRO - PROBABILITY ENGINE
    """
    @staticmethod
    def calculate(probabilities):
        raw_conf = np.max(probabilities)
        if np.argmax(probabilities) == 0: return 0
        
        # Scale 0.33-1.0 to 0-100
        confidence = (raw_conf - 0.33) / (1.0 - 0.33)
        return int(min(max(confidence, 0.0), 1.0) * 100)
