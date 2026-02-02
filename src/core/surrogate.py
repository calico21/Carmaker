import numpy as np
import os
import joblib
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel, ConstantKernel
from scipy.stats import norm
import logging
import warnings

# Suppress convergence warnings to keep the console clean for the demo
warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

class SurrogateOracle:
    """
    GEN 5.0 TITAN STANDARD: Bayesian Gaussian Process (Kriging).
    
    Now features 'Warm Start' capability to learn across sessions.
    """
    def __init__(self, storage_path="data/suspension_knowledge.pkl"):
        self.storage_path = storage_path
        
        # --- KERNEL ENGINEERING ---
        # 1. ConstantKernel: Adjusts the mean magnitude.
        # 2. Matern(nu=2.5): C2 continuity (smooth physics).
        # 3. WhiteKernel: Handles noise/jitter.
        kernel = ConstantKernel(1.0, (1e-3, 1e3)) * \
                 Matern(length_scale=1.0, length_scale_bounds=(1e-2, 1e2), nu=2.5) + \
                 WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-5, 1e1))
        
        self.model = GaussianProcessRegressor(
            kernel=kernel, 
            n_restarts_optimizer=5, 
            normalize_y=True,
            random_state=42
        )
        
        self.is_trained = False
        self.X_history = []
        self.y_history = [] 
        self.feature_names = []
        
        # Expected Improvement parameters
        self.xi = 0.01 
        self.SOFT_FAILURE_COST = 150.0 

        # Try to load existing knowledge
        self._load_state()

    def update(self, params: dict, cost: float):
        """
        The main entry point for the Orchestrator.
        1. Adds data.
        2. Retrains the model.
        3. Saves state to disk (Persistence).
        """
        self.feature_names = list(params.keys())
        
        # --- CRASH HANDLING (Soft Fail) ---
        # If cost is near 999 (Crash), we map it to 150 (Soft Fail).
        # This creates a "gradient" pointing away from the crash, 
        # instead of a flat "impossible" plateau.
        if cost >= 900.0:
            cost = self.SOFT_FAILURE_COST + np.random.normal(0, 1.0) 
            
        self.X_history.append(list(params.values()))
        self.y_history.append(cost)
        
        self.train()
        self._save_state()

    def predict(self, params: dict):
        """
        Interface wrapper for Orchestrator.
        Returns: (predicted_cost, uncertainty_sigma)
        """
        if not self.is_trained:
            # If untrained, return 0 cost but HIGH uncertainty (999)
            # This forces the optimizer to explore.
            return 0.0, 999.0

        X = np.array([list(params.values())])
        mu, sigma = self.model.predict(X, return_std=True)
        return mu[0], sigma[0]

    def train(self):
        """
        Fits the Gaussian Process.
        """
        if len(self.X_history) < 5: 
            return

        X = np.array(self.X_history)
        y = np.array(self.y_history)
        
        try:
            self.model.fit(X, y)
            self.is_trained = True
        except Exception as e:
            logger.error(f"GP Training Failed: {e}")

    def _save_state(self):
        """
        Persist the knowledge base to disk.
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            
            state = {
                "model": self.model,
                "X": self.X_history,
                "y": self.y_history,
                "features": self.feature_names
            }
            joblib.dump(state, self.storage_path)
        except Exception as e:
            logger.warning(f"Failed to save Surrogate state: {e}")

    def _load_state(self):
        """
        Warm start from disk.
        """
        if not os.path.exists(self.storage_path):
            return

        try:
            state = joblib.load(self.storage_path)
            self.model = state["model"]
            self.X_history = state["X"]
            self.y_history = state["y"]
            self.feature_names = state["features"]
            
            if len(self.X_history) > 0:
                self.is_trained = True
                logger.info(f"🧠 Surrogate Warm Start: Loaded {len(self.X_history)} prior simulations.")
        except Exception as e:
            logger.warning(f"Failed to load Surrogate state (starting fresh): {e}")