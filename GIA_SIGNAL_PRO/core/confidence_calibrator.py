import numpy as np
from sklearn.isotonic import IsotonicRegression
import joblib

class ConfidenceCalibrator:
    """
    🦁 GIA SIGNAL PRO - CALIBRATION MODULE (v2.0)
    Uses Isotonic Regression to ensure predicted probabilities 
    match real-world success rates and remain strictly monotonic.
    """
    def __init__(self):
        self.calibrator_buy = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1)
        self.calibrator_sell = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1)
        self.is_fitted = False

    def fit(self, probs, true_labels):
        """
        Fits the calibrator on validation data.
        probs: model predict_proba output (N, 3)
        true_labels: actual targets (0=SKIP, 1=BUY, 2=SELL)
        """
        # Fit BUY calibrator (BUY probability is index 1)
        y_buy = (true_labels == 1).astype(int)
        x_buy = probs[:, 1]
        self.calibrator_buy.fit(x_buy, y_buy)
        
        # Fit SELL calibrator (SELL probability is index 2)
        y_sell = (true_labels == 2).astype(int)
        x_sell = probs[:, 2]
        self.calibrator_sell.fit(x_sell, y_sell)
            
        self.is_fitted = True

    def calibrate(self, probs):
        """
        Adjusts raw probabilities for realistic, monotonic confidence.
        """
        if not self.is_fitted:
            return probs
            
        calibrated = np.copy(probs)
        # Calibrate BUY prob
        calibrated[:, 1] = self.calibrator_buy.transform(probs[:, 1])
        # Calibrate SELL prob
        calibrated[:, 2] = self.calibrator_sell.transform(probs[:, 2])
        
        # Renormalize to ensure they sum to <= 1 (approx)
        # or just use them as independent confidence scores.
        # For our engine, we take the argmax of these.
        
        return calibrated

    def save(self, path):
        joblib.dump(self, path)

    @staticmethod
    def load(path):
        return joblib.load(path)

