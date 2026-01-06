
import joblib
import sys
import os

class MockEncoder:
    def inverse_transform(self, idxs):
        mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

import __main__
__main__.MockEncoder = MockEncoder

model_path = 'backend/models/GIA_v2_FLASH.pkl'
if not os.path.exists(model_path):
    print(f"Error: {model_path} not found.")
    sys.exit(1)

try:
    m = joblib.load(model_path)
    print("--- GIA_v2_FLASH MODEL INSPECTION ---")
    print(f"Features ({len(m.get('feature_columns', [])) if 'feature_columns' in m else 0}):", m.get('feature_columns', m.get('features', 'Missing')))
    
    metadata_keys = [k for k in m.keys() if k != 'model']
    print("\nMetadata Summary:")
    for k in metadata_keys:
        val = m[k]
        if isinstance(val, (dict, list)):
            print(f"  {k}: {len(val)} items")
        else:
            print(f"  {k}: {val}")
            
    if 'metrics' in m:
        print("\nTraining Metrics:")
        print(m['metrics'])
        
except Exception as e:
    print(f"Error loading model: {e}")
