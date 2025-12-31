"""
LSTM Trainer - Deep Sequential Intelligence
"""
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization, Bidirectional
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.regularizers import l2
from sklearn.preprocessing import StandardScaler
import os
import sys
import joblib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class GoldLSTMTrainer:
    def __init__(self, window_size=20):
        self.window_size = window_size
        self.scaler = StandardScaler()
        self.model = None
        self.feature_columns = [
            'rsi', 'rsi_slope', 'ret_1', 'ret_2', 'ret_3',
            'vol_5', 'vol_20', 'ema_9_dist', 'ema_21_dist', 'ema_50_dist',
            'atr_pct', 'rel_range', 'bb_width',
            'macd_norm', 'bb_pos', 'stoch_k',
            'body_size', 'upper_wick', 'lower_wick',
            'mom_3', 'mom_5', 'mom_10', 'mom_weekly', 'mom_monthly',
            'news_sentiment', 'news_impact_score'
        ]

    def prepare_sequences(self, df, feature_columns=None):
        if feature_columns: self.feature_columns = feature_columns
        
        # Filter features that exist in df
        self.feature_columns = [f for f in self.feature_columns if f in df.columns]
        
        data = df[self.feature_columns].values
        mapping = {'BUY': 0, 'SELL': 1, 'WAIT': 2}
        y = np.array([mapping[l] for l in df['label'].values])
        
        scaled_data = self.scaler.fit_transform(data)
        
        X_seq, y_seq = [], []
        for i in range(len(scaled_data) - self.window_size):
            X_seq.append(scaled_data[i : i + self.window_size])
            y_seq.append(y[i + self.window_size])
            
        return np.array(X_seq), np.array(y_seq)

    def build_model(self, input_shape):
        """High-Power Bidirectional LSTM for market context."""
        model = Sequential([
            Bidirectional(LSTM(128, input_shape=input_shape, return_sequences=True)),
            Dropout(0.3),
            BatchNormalization(),
            
            Bidirectional(LSTM(64, return_sequences=False)),
            Dropout(0.3),
            BatchNormalization(),
            
            Dense(32, activation='relu', kernel_regularizer=l2(0.01)),
            Dense(3, activation='softmax')
        ])
        
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.0005),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )
        self.model = model
        return model

    def train(self, X_train, y_train, X_val, y_val, epochs=100, batch_size=32):
        print(f"🚀 Training Deep LSTM (Professional Sequence Learning)...")
        early_stop = EarlyStopping(monitor='val_loss', patience=15, restore_best_weights=True)
        return self.model.fit(
            X_train, y_train, validation_data=(X_val, y_val),
            epochs=epochs, batch_size=batch_size, callbacks=[early_stop], verbose=0
        )

    def save_model(self, path):
        base_path = path.replace('.pkl', '')
        self.model.save(f"{base_path}.h5")
        
        metadata = {
            'model_type': 'LSTM',
            'feature_columns': self.feature_columns,
            'window_size': self.window_size,
            'scaler': self.scaler
        }
        joblib.dump(metadata, f"{base_path}_meta.joblib")
        joblib.dump(metadata, path) # satisfy ModelManager
        print(f"💾 Deep LSTM Model Saved: {path}")
