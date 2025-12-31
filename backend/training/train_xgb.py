"""
XGBoost Trainer - Refined & Organized
"""
import pandas as pd
import numpy as np
import os
import sys
import joblib
import json
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report
import xgboost as xgb

# Add parent to path for package imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class GoldModelTrainer:
    def __init__(self, dataset_path=None):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if dataset_path is None:
            self.dataset_path = os.path.join(self.base_dir, 'gold_dataset_pro.csv')
        else:
            self.dataset_path = dataset_path
            
        self.model = None
        self.label_encoder = LabelEncoder()
        self.feature_columns = [
            'rsi', 'rsi_slope', 'ret_1', 'ret_2', 'ret_3',
            'vol_5', 'vol_20', 'ema_9_dist', 'ema_21_dist', 'ema_50_dist',
            'atr_pct', 'rel_range', 'bb_width',
            'macd_norm', 'bb_pos', 'stoch_k',
            'body_size', 'upper_wick', 'lower_wick',
            'mom_3', 'mom_5', 'mom_10', 'mom_weekly', 'mom_monthly',
            'news_sentiment', 'news_impact_score'
        ]
        
        self.model_params = {
            'max_depth': 6,
            'learning_rate': 0.02,
            'n_estimators': 1200,
            'objective': 'multi:softmax',
            'num_class': 3,
            'eval_metric': 'mlogloss',
            'random_state': 42,
            'tree_method': 'hist',
            'reg_alpha': 0.5,
            'reg_lambda': 2.0,
            'subsample': 0.8
        }

    def load_data(self):
        df = pd.read_csv(self.dataset_path)
        return df

    def prepare_features(self, df):
        # Ensure columns exist
        existing_features = [f for f in self.feature_columns if f in df.columns]
        X = df[existing_features].copy()
        y = self.label_encoder.fit_transform(df['label'])
        return X, y, df['label']

    def split_data(self, X, y):
        n = len(X)
        itrain, ival, itest = int(n*0.7), int(n*0.85), n
        return X.iloc[:itrain], X.iloc[itest:], X.iloc[itrain:ival], \
               y[:itrain], y[itest:], y[itrain:ival]

    def train_model(self, X_train, y_train, X_val, y_val):
        print(f"🚀 Training XGBoost (Professional Config)...")
        self.model = xgb.XGBClassifier(**self.model_params)
        self.model.fit(X_train, y_train, eval_set=[(X_val, y_val)], 
                       early_stopping_rounds=30, verbose=False)
        return self.model

    def evaluate(self, X_train, y_train, X_test, y_test):
        train_acc = accuracy_score(y_train, self.model.predict(X_train))
        test_acc = accuracy_score(y_test, self.model.predict(X_test))
        gap = abs(train_acc - test_acc)
        return {
            'accuracy': test_acc,
            'train_accuracy': train_acc,
            'bias_gap': gap,
            'is_biased': gap > 0.20
        }

    def save_model(self, path):
        model_data = {
            'model_type': 'XGBOOST',
            'model': self.model,
            'label_encoder': self.label_encoder,
            'feature_columns': [f for f in self.feature_columns if f in self.model.get_booster().feature_names]
        }
        joblib.dump(model_data, path)
        print(f"💾 XGBoost Model Saved: {path}")
