import numpy as np
import os
import joblib
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel, ConstantKernel
from sklearn.base import clone
import logging
import warnings

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

class SurrogateOracle:
    """
    GEN 6.0: Constrained Bayesian Optimization (cBO) Oracle.
    Replaces the 'Trust Gate' with Dual Gaussian Processes.
    
    Model 1: Objective (Lap Time)
    Model 2: Constraint (Probability of Crash)
    """
    def __init__(self, storage_path="data/knowledge_base.pkl"):
        self.storage_path = storage_path
        
        # Generic Kernel
        kernel = ConstantKernel(1.0) * Matern(nu=2.5) + WhiteKernel(noise_level=0.1)
        
        # Dual Models [cite: 526-527]
        self.model_time = GaussianProcessRegressor(kernel=clone(kernel), n_restarts_optimizer=2, normalize_y=True)
        self.model_feas = GaussianProcessRegressor(kernel=clone(kernel), n_restarts_optimizer=2, normalize_y=False) # Predicts 0 or 1
        
        self.is_trained = False
        self.X = []
        self.y_time = [] # Lap times (only for valid runs)
        self.y_feas = [] # 1.0 = Valid, 0.0 = Crash
        
        self._load_state()

    def update(self, params: dict, cost: float, is_crash: bool):
        """
        Updates the knowledge base. 
        Note: If crash, 'cost' should be the Soft Penalty cost.
        """
        x_vec = list(params.values())
        
        self.X.append(x_vec)
        self.y_feas.append(0.0 if is_crash else 1.0)
        
        # We only train the Time model on data that isn't a total failure
        # to prevent "poisoning" the regression with outliers.
        if not is_crash:
            self.y_time.append(cost)
        else:
            # Impute a pessimistic value for time to keep array lengths aligned if needed,
            # or manage separate arrays (better).
            pass 

        self.train()
        self._save_state()

    def predict_score(self, params: dict):
        """
        UPGRADE: Expected Improvement (EI) Acquisition Function.
        Mathematically rigorous search used by AMZ/Delft.
        """
        if not self.is_trained:
            return 1.0 # Pure exploration

        x_in = np.array([list(params.values())])
        
        # 1. Predict Mean and Uncertainty (Standard Deviation)
        mu, sigma = self.model_time.predict(x_in, return_std=True)
        
        # 2. Get current best observed value
        current_best = min(self.y_time) if self.y_time else 100.0
        
        # 3. Calculate Expected Improvement
        # We want to minimize time, so improvement = (current_best - prediction)
        with np.errstate(divide='warn'):
            imp = current_best - mu
            Z = imp / (sigma + 1e-9)
            from scipy.stats import norm
            ei = imp * norm.cdf(Z) + sigma * norm.pdf(Z)
            
        # 4. Feasibility Weighting (Constraint)
        prob_success, _ = self.model_feas.predict(x_in, return_std=True)
        prob_success = np.clip(prob_success[0], 0.0, 1.0)
        
        # Final Score: High EI * High Probability of Survival
        # We return negative because Optuna minimizes, but EI is "higher is better"
        return -(ei[0] * prob_success)

    def train(self):
        if len(self.X) < 5: return
        
        X_all = np.array(self.X)
        y_feas = np.array(self.y_feas)
        
        # Filter for time model
        valid_indices = [i for i, f in enumerate(self.y_feas) if f > 0.5]
        
        try:
            self.model_feas.fit(X_all, y_feas)
            if len(valid_indices) > 2:
                self.model_time.fit(X_all[valid_indices], np.array(self.y_time))
            self.is_trained = True
        except Exception: pass

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            joblib.dump({
                "X": self.X, "y_time": self.y_time, "y_feas": self.y_feas
            }, self.storage_path)
        except: pass

    def _load_state(self):
        if os.path.exists(self.storage_path):
            try:
                data = joblib.load(self.storage_path)
                self.X = data["X"]
                self.y_time = data["y_time"]
                self.y_feas = data["y_feas"]
                self.is_trained = True
            except: pass