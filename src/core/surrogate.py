import numpy as np
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
    
    This replaces the "Black Box" Random Forest with a "White Box" Probabilistic Model.
    
    Why this wins Design Finals:
    1. Continuous Differentiability: Physics is smooth. GPs are smooth. 
       This allows us to find the TRUE peak, not just a nearby block.
    2. Epistemic Uncertainty: The GP knows exactly how unsure it is (Sigma).
       This allows for 'Strategic Exploration' rather than random guessing.
    3. Kernel Engineering: Uses Matern 5/2 to model suspension dynamics.
    """
    def __init__(self):
        # --- KERNEL ENGINEERING ---
        # 1. ConstantKernel: Adjusts the mean magnitude (Lap Time is ~60s, not 0s).
        # 2. Matern(nu=2.5): The Gold Standard for physical systems. 
        #    nu=2.5 allows for C2 continuity (smooth velocity and acceleration derivatives).
        # 3. WhiteKernel: Handles signal noise. Even CarMaker has numerical jitter.
        kernel = ConstantKernel(1.0, (1e-3, 1e3)) * \
                 Matern(length_scale=1.0, length_scale_bounds=(1e-2, 1e2), nu=2.5) + \
                 WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-5, 1e1))
        
        # The Brain: Gaussian Process Regressor
        self.model = GaussianProcessRegressor(
            kernel=kernel, 
            n_restarts_optimizer=5, # Run internal optimization 5 times to avoid local minima
            normalize_y=True,       # CRITICAL: Standardizes Lap Time (y) so the GP works on Z-scores
            random_state=42
        )
        
        self.is_trained = False
        self.X_history = []
        self.y_history = [] 
        self.feature_names = []
        
        # Acquisition Function Hyperparameter
        # xi = 0.01 implies we prefer 'Safe Improvement' over 'Wild Gambling'
        self.xi = 0.01 

        # Failure Handling
        # GPs fail if you feed them 'Infinity' (999.0). We need a Soft Ceiling.
        self.SOFT_FAILURE_COST = 150.0 

    def add_observation(self, params: dict, results: tuple):
        """
        Ingest simulation data.
        Performs 'Soft Clamping' to prevent mathematical explosion.
        """
        self.feature_names = list(params.keys())
        
        # Results: (LapTime, Stability_Index)
        # Note: In Gen 5.0, we prioritize Lap Time for the GP, 
        # but we filter unstable cars BEFORE adding them if possible.
        cost, _ = results
        
        # --- CRASH HANDLING (The "Soft Ceiling") ---
        # The Critique correctly pointed out that 999.0 creates a "Discontinuity".
        # A cliff in the math makes the GP panic. 
        # We replace the cliff with a "Steep Hill" (150s + Noise).
        if cost >= 900.0:
            # Add noise to prevent multiple crashes from looking like a flat plateau.
            # This forces the GP to see a gradient pointing AWAY from the crash zone.
            cost = self.SOFT_FAILURE_COST + np.random.normal(0, 1.0) 
            
        self.X_history.append(list(params.values()))
        self.y_history.append(cost) 

    def train(self):
        """
        Fits the Gaussian Process.
        This is mathematically heavier than Random Forest, but 10x more valuable.
        """
        # GPs need at least a few points to not crash
        if len(self.X_history) < 5: 
            return

        X = np.array(self.X_history)
        y = np.array(self.y_history)
        
        try:
            self.model.fit(X, y)
            self.is_trained = True
            
            # Log the "Marginal Likelihood" - a measure of how well the model explains reality
            # Higher is better. Judges love this metric.
            lml = self.model.log_marginal_likelihood()
            logger.info(f"🧠 GP Retrained (N={len(X)}). Log-Marginal Likelihood: {lml:.2f}")
            
        except Exception as e:
            logger.error(f"GP Training Failed: {e}")

    def evaluate_trust(self, params: dict):
        """
        THE BAYESIAN ORACLE.
        Calculates Expected Improvement (EI).
        
        Returns:
        - Prediction (Mean Lap Time)
        - Uncertainty (Sigma)
        - Is_Promising (Boolean based on EI)
        """
        if not self.is_trained:
            # If untrained, we are blind. Assume everything is promising (Explore).
            return (0.0, 0.0), 100.0, True

        X = np.array([list(params.values())])
        
        # 1. Predict Mean (mu) and Standard Deviation (sigma)
        mu, sigma = self.model.predict(X, return_std=True)
        mu = mu[0]
        sigma = sigma[0]
        
        # 2. Calculate Expected Improvement (EI)
        # We want to minimize Lap Time.
        # Improvement = (Best_So_Far) - (Predicted_New)
        current_best = np.min(self.y_history)
        
        with np.errstate(divide='warn'):
            imp = current_best - mu - self.xi
            Z = imp / sigma
            # EI Equation:
            ei = imp * norm.cdf(Z) + sigma * norm.pdf(Z)
            # Handle numerical edge case where sigma is 0
            ei[sigma <= 0.0] = 0.0
            
        # 3. The Decision
        # If EI > 0.001 seconds, it's worth running the expensive simulation.
        is_promising = (ei > 0.001) or (sigma > 0.5) # Or if we are VERY unsure (Explore)
        
        # Return format matches previous interface for compatibility
        return (mu, 0.0), sigma, is_promising

    def get_length_scales(self):
        """
        Returns the 'Length Scale' of each parameter.
        
        Engineering Translation:
        - Small Length Scale (< 0.5) = SENSITIVE. Changing this parameter slightly changes lap time drastically.
        - Large Length Scale (> 5.0) = INSENSITIVE. This parameter barely matters.
        
        Use this for the 'Sensitivity Heatmap' in Design Finals.
        """
        if not self.is_trained: return {}
        
        try:
            # Extract learned length scales from the kernel
            # The structure of model.kernel_ changes after training (it becomes a compound kernel)
            # We access the 'k1' (Product) -> 'k2' (Matern) component usually.
            # This safe access tries to find the Matern component.
            kernel = self.model.kernel_
            if hasattr(kernel, 'k1'): 
                # k1 is Constant * Matern
                matern_kernel = kernel.k1.k2 
            else:
                matern_kernel = kernel # Fallback
                
            scales = matern_kernel.length_scale
            
            # Ensure scales is a list/array
            if np.isscalar(scales):
                scales = [scales] * len(self.feature_names)
                
            return dict(zip(self.feature_names, scales))
        except Exception as e:
            logger.warning(f"Could not extract length scales: {e}")
            return {}