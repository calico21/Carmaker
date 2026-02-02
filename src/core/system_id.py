import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV, RANSACRegressor
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from scipy.signal import savgol_filter
import logging

class SystemIdentifier:
    """
    SINDy (Sparse Identification of Nonlinear Dynamics) for Tire Modeling.
    
    UPGRADED: Now features Signal Smoothing (Savitzky-Golay) and 
    Robust Regression (RANSAC) to ignore outliers (cones, curbs).
    """
    def __init__(self):
        self.logger = logging.getLogger("SystemID")
        self.poly = PolynomialFeatures(degree=3, include_bias=False)
        self.scaler = StandardScaler()
        
        # --- ROBUST ESTIMATOR ---
        # 1. LassoCV: Enforces sparsity (finds the simplest equation).
        # 2. RANSAC: Ignores data points that don't fit the trend (outliers).
        base_estimator = LassoCV(cv=5, fit_intercept=False, max_iter=10000, n_jobs=-1)
        
        self.model = RANSACRegressor(
            estimator=base_estimator,
            min_samples=0.6,  # Require at least 60% of data to agree
            residual_threshold=None, # Auto-detect based on MAD
            random_state=42
        )
        
        self.is_fitted = False
        self.feature_names = None

    def fit(self, telemetry_path):
        """
        Reads telemetry, cleans noise, and discovers the governing equations.
        """
        try:
            # 1. Load Data
            df = pd.read_csv(telemetry_path)
            required_cols = ['time', 'vx', 'vy', 'yaw_rate', 'steer_angle', 'ax', 'ay']
            if not all(col in df.columns for col in required_cols):
                self.logger.error(f"Missing columns in {telemetry_path}")
                return False

            # 2. Pre-Process (The "Reality" Filter)
            # Raw telemetry is too noisy for derivative calculation.
            # We use Savitzky-Golay to smooth it without killing the peaks.
            df_clean = self._smooth_signals(df)

            # 3. Calculate States (Slip Angles)
            # alpha = atan(vy + r*lf / vx) - steer
            # (Simplified for single track)
            lf = 1.53 # Approx CG to front axle (m) - should be config
            
            # Avoid division by zero
            vx_safe = np.maximum(df_clean['vx'], 1.0) 
            
            alpha_f = np.arctan((df_clean['vy'] + df_clean['yaw_rate']*lf) / vx_safe) - df_clean['steer_angle']
            Fy_f = df_clean['ay'] * 250.0 # Approx Effective Mass (kg)
            
            # 4. Prepare SINDy Matrices
            X = alpha_f.values.reshape(-1, 1)
            y = Fy_f.values
            
            # Filter out low-speed data (physics don't apply at < 3 m/s)
            mask = df_clean['vx'] > 3.0
            X = X[mask]
            y = y[mask]

            if len(y) < 100:
                self.logger.warning("Not enough high-speed data to fit tire model.")
                return False

            # 5. Fit the Model (Discover Physics)
            # Create pipeline: Polynomials -> Scale -> RANSAC(Lasso)
            # Note: We manually transform X to polynomials first so we can extract names later
            X_poly = self.poly.fit_transform(X)
            
            self.logger.info("Fitting SINDy model with RANSAC...")
            self.model.fit(X_poly, y)
            
            # 6. Validate Physics (Guardrail)
            # Check R-squared on the inliers only
            score = self.model.score(X_poly, y)
            if score < 0.8:
                self.logger.warning(f"SINDy Fit Poor (R2={score:.2f}). Data might be garbage.")
                return False

            self.is_fitted = True
            self.logger.info(f"Tire Model Identified! (R2={score:.2f})")
            
            # Extract coefficients for inspection
            estimator = self.model.estimator_
            coeffs = estimator.coef_
            self._log_equation(coeffs)
            
            return True

        except Exception as e:
            self.logger.error(f"System ID Failed: {e}")
            return False

    def _smooth_signals(self, df):
        """
        Applies Savitzky-Golay filter to remove sensor jitter.
        Window length must be odd.
        """
        df_new = df.copy()
        window = 11 # 110ms at 100Hz
        poly = 2
        
        for col in ['vx', 'vy', 'yaw_rate', 'steer_angle', 'ax', 'ay']:
            try:
                df_new[col] = savgol_filter(df[col], window_length=window, polyorder=poly)
            except Exception:
                pass # If signal is too short, skip filtering
        
        return df_new

    def _log_equation(self, coeffs):
        """
        Pretty-prints the discovered math.
        """
        feature_names = self.poly.get_feature_names_out(['alpha'])
        equation = "Fy = "
        for name, coef in zip(feature_names, coeffs):
            if abs(coef) > 0.1: # Threshold for sparsity
                equation += f"{coef:+.2f}*{name} "
        self.logger.info(f"Discovered Law: {equation}")

    def get_tire_curve(self):
        """
        Returns x, y arrays for plotting the discovered curve.
        """
        if not self.is_fitted:
            return None, None
            
        alpha_range = np.linspace(-0.3, 0.3, 100).reshape(-1, 1) # -15 to +15 deg
        X_poly = self.poly.transform(alpha_range)
        Fy_pred = self.model.predict(X_poly)
        
        return alpha_range.flatten(), Fy_pred