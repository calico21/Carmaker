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
        # Adapt scalar cost to tuple format expected by internal logic
        self.add_observation(params, (cost, 0.0))
        self.train()
        self._save_state()

    def predict(self, params: dict):
        """
        Interface wrapper for Orchestrator.
        Returns: (predicted_cost, uncertainty_sigma)
        """
        prediction_tuple, sigma, _ = self.evaluate_trust(params)
        predicted_cost = prediction_tuple[0]
        return predicted_cost, sigma

    def add_observation(self, params: dict, results: tuple):
        """
        Ingest simulation data.
        """
        self.feature_names = list(params.keys())
        cost, _ = results
        
        # --- CRASH HANDLING ---
        if cost >= 900.0:
            cost = self.SOFT_FAILURE_COST + np.random.normal(0, 1.0) 
            
        self.X_history.append(list(params.values()))
        self.y_history.append(cost) 

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
            
            # Optional: Log marginal likelihood rarely to reduce spam
            if len(self.X_history) % 10 == 0:
                lml = self.model.log_marginal_likelihood()
                logger.info(f"🧠 GP Retrained (N={len(X)}). LML: {lml:.2f}")
            
        except Exception as e:
            logger.error(f"GP Training Failed: {e}")

    def evaluate_trust(self, params: dict):
        """
        Calculates Expected Improvement (EI).
        """
        if not self.is_trained:
            return (0.0, 0.0), 100.0, True

        X = np.array([list(params.values())])
        mu, sigma = self.model.predict(X, return_std=True)
        mu = mu[0]
        sigma = sigma[0]
        
        current_best = np.min(self.y_history)
        
        with np.errstate(divide='warn'):
            imp = current_best - mu - self.xi
            Z = imp / sigma
            ei = imp * norm.cdf(Z) + sigma * norm.pdf(Z)
            ei[sigma <= 0.0] = 0.0
            
        is_promising = (ei > 0.001) or (sigma > 0.5)
        
        return (mu, 0.0), sigma, is_promising

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

    def get_length_scales(self):
        if not self.is_trained: return {}
        try:
            kernel = self.model.kernel_
            if hasattr(kernel, 'k1'): 
                matern_kernel = kernel.k1.k2 
            else:
                matern_kernel = kernel
            scales = matern_kernel.length_scale
            if np.isscalar(scales):
                scales = [scales] * len(self.feature_names)
            return dict(zip(self.feature_names, scales))
        except Exception as e:
            return {}