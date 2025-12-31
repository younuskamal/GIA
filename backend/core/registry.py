import os
import json
import joblib
from datetime import datetime
from pathlib import Path

# مسارات النظام
BASE_DIR = Path(__file__).parent.parent
REGISTRY_PATH = BASE_DIR / "model_registry.json"
MODELS_DIR = BASE_DIR / "models"

class ModelManager:
    """Manages model versioning, registration, and loading for GIA."""
    
    def __init__(self, base_dir=None):
        # The base_dir parameter is now mostly for overriding the default BASE_DIR if needed.
        # If base_dir is provided, we'll use it to derive paths, otherwise use the module-level constants.
        if base_dir is None:
            self.base_dir = BASE_DIR
            self.registry_path = REGISTRY_PATH
            self.models_dir = MODELS_DIR
        else:
            self.base_dir = Path(base_dir)
            self.registry_path = self.base_dir / 'model_registry.json'
            self.models_dir = self.base_dir / 'models'
        
        # Ensure models directory exists
        if not self.models_dir.exists():
            self.models_dir.mkdir(parents=True, exist_ok=True)
            
        self._initialize_registry()

    def _initialize_registry(self):
        """Initializes the registry file if it doesn't exist."""
        if not os.path.exists(self.registry_path):
            initial_data = {
                "active_model_v": None,
                "history": []
            }
            with open(self.registry_path, 'w') as f:
                json.dump(initial_data, f, indent=2)

    def get_registry(self):
        with open(self.registry_path, 'r') as f:
            return json.load(f)

    def save_registry(self, data):
        with open(self.registry_path, 'w') as f:
            json.dump(data, f, indent=2)

    def get_active_model_path(self):
        """Returns path to the currently approved stable model."""
        registry = self.get_registry()
        version = registry.get("active_model_v")
        if version:
            return os.path.join(self.models_dir, f"model_v{version}.pkl")
        return None

    def register_candidate(self, model_file, metrics):
        """
        Registers a new trained model.
        Returns: (is_approved, reason)
        """
        registry = self.get_registry()
        history = registry["history"]
        
        new_version = len(history) + 1
        new_filename = f"model_v{new_version}.pkl"
        target_path = os.path.join(self.models_dir, new_filename)
        
        # Copy/Move the model file
        # Copy/Move the model file
        import shutil
        shutil.move(model_file, target_path)
        
        # If there's an associated .h5 file (for LSTM), move it too
        h5_source = model_file.replace('.pkl', '.h5')
        if os.path.exists(h5_source):
            h5_target = target_path.replace('.pkl', '.h5')
            shutil.move(h5_source, h5_target)
        
        # Performance Comparison Logic
        is_approved = False
        reason = "First model registration"
        
        active_version = registry.get("active_model_v")
        if active_version:
            # Find active model metrics
            active_meta = next((item for item in history if item["version"] == active_version and item["status"] == "APPROVED"), None)
            
            if active_meta:
                prev_acc = active_meta["metrics"]["accuracy"]
                prev_dd = active_meta["metrics"]["max_drawdown"]
                
                curr_acc = metrics["accuracy"]
                curr_dd = metrics["max_drawdown"]
                
                # REFINED CRITERIA: Safety-First Approach
                # 1. Extreme Safety: If drawdown is very low (< 5%), we are more lenient on accuracy.
                # 2. Reasonable Accuracy: In a 3-class market (BUY/SELL/WAIT), 33% is random. 
                #    If model filters effectively, > 25% with 0 drawdown is a win.
                
                is_safe_win = curr_dd <= 5.0 and curr_acc > 25.0
                is_pure_improvement = curr_acc >= prev_acc and curr_dd <= prev_dd
                
                # New Criteria: Strategic Expansion (More Activity)
                # If we have 50% more trades and still profitable with safe DD (< 20%), approve it.
                prev_trades = active_meta["metrics"].get("trades", 0)
                curr_trades = metrics.get("trades", 0)
                is_active_upgrade = (curr_trades > prev_trades * 1.5) and (curr_dd < 20.0) and (metrics["total_return_pct"] > 0)

                if is_pure_improvement:
                    is_approved = True
                    reason = f"Improved/Stable Performance (Acc: {curr_acc:.2f}%, DD: {curr_dd:.2f}%)"
                elif is_safe_win and curr_dd < prev_dd:
                    is_approved = True
                    reason = f"Safety Upgrade: significantly lower drawdown ({curr_dd:.1f}% vs {prev_dd:.1f}%)"
                elif is_active_upgrade:
                    is_approved = True
                    reason = f"Activity Upgrade: Trades increased ({prev_trades}->{curr_trades}) while maintaining safety (DD: {curr_dd:.1f}%)"
                else:
                    is_approved = False
                    reason = f"Performance degradation. Acc: {prev_acc:.2f}->{curr_acc:.2f}, DD: {prev_dd:.2f}->{curr_dd:.2f}"
            else:
                is_approved = True
                reason = "Previous active model metadata missing. Promoting new model."
        else:
            is_approved = True
            reason = "First approved stable model."

        # Update metadata
        new_entry = {
            "version": new_version,
            "filename": new_filename,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "status": "APPROVED" if is_approved else "REJECTED",
            "reason": reason
        }
        
        history.append(new_entry)
        if is_approved:
            registry["active_model_v"] = new_version
            
        self.save_registry(registry)
        return is_approved, reason

    def get_model_status_info(self):
        """Returns a string describing the current model status for the UI/LLM."""
        registry = self.get_registry()
        active_v = registry.get("active_model_v")
        
        if not active_v:
            return "Status: NO_AI - Analysis using technical rules fallback."
            
        # Check if there's a very recent training entry
        history = registry["history"]
        if history and (datetime.now() - datetime.fromisoformat(history[-1]["timestamp"])).total_seconds() < 3600:
            if history[-1]["status"] == "APPROVED":
                return f"Status: STABLE - System recently updated to v{active_v}."
            else:
                return f"Status: STABLE - Using v{active_v}. (Latest training was rejected: {history[-1]['reason']})"
                
        return f"Status: STABLE - Using model v{active_v}."
