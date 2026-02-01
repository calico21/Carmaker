import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C
import logging

logger = logging.getLogger(__name__)

class DeltaLearner:
    """
    The 'Truth' Module (Gen 3.0).
    Learns the BIAS between Simulation and Reality to fix 'Garbage In, Garbage Out'.
    
    Equation: Real_Performance = CarMaker_Physics(x) + Delta_GP(x)
    """
    def __init__(self):
        # GP Kernel: Constant * RBF (Radial Basis Function) to smooth out noise
        # This allows the model to learn complex error surfaces (e.g. Tire model is wrong only at high speed)
        kernel = C(1.0, (1e-3, 1e3)) * RBF(10, (1e-2, 1e2))
        self.gp = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=10, alpha=0.1)
        
        self.is_active = False
        self.X_train = [] # Design Parameters (Springs, Dampers...)
        self.y_error = [] # Error = Real_Time - Sim_Time

    def ingest_real_data(self, sim_params: dict, sim_result: float, real_result: float):
        """
        Feeds the learner with a ground-truth data point.
        """
        error = real_result - sim_result
        self.X_train.append(list(sim_params.values()))
        self.y_error.append(error)
        
        # Only activate after we have enough statistical significance (e.g., 3 runs)
        if len(self.X_train) >= 3:
            self.fit()

    def fit(self):
        try:
            self.gp.fit(np.array(self.X_train), np.array(self.y_error))
            self.is_active = True
            logger.info(f"🔮 Delta Model Calibrated. Learned bias from {len(self.X_train)} real runs.")
        except Exception as e:
            logger.warning(f"Delta Learner failed to fit: {e}")

    def predict_bias(self, params: dict):
        """
        Returns (Mean_Bias, Uncertainty_of_Bias).
        Example: If CarMaker is 1.0s too optimistic, this returns (+1.0, 0.1)
        """
        if not self.is_active:
            return 0.0, 0.0
        
        features = np.array([list(params.values())])
        bias_mean, bias_std = self.gp.predict(features, return_std=True)
        return bias_mean[0], bias_std[0]