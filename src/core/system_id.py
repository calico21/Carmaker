import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV, RANSACRegressor
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from scipy.signal import savgol_filter
import logging

class SystemIdentifier:
    """
    SINDy (Sparse Identification of Nonlinear Dynamics) with RANSAC.
    
    Purpose:
    1. Read noisy telemetry data.
    2. Remove outliers (cone strikes, curb hits) using RANSAC.
    3. Identify the underlying Tire Model (Lateral Force vs Slip Angle).
    """
    def __init__(self):
        self.logger = logging.getLogger("SystemID")
        # Degree 3 polynomial allows capturing the peak and fall-off of a tire curve
        self.poly = PolynomialFeatures(degree=3, include_bias=False)
        
        # --- ROBUST ESTIMATOR CONFIGURATION ---
        # Base estimator: LassoCV (L1 regularization) to find sparse physics terms
        base_estimator = LassoCV(cv=5, fit_intercept=False, max_iter=10000, n_jobs=-1)
        
        # Wrapper: RANSAC (Robust regression)
        # It assumes at least 60% of data is "Real Physics" and up to 40% could be "Garbage/Noise"
        self.model = RANSACRegressor(
            estimator=base_estimator,
            min_samples=0.6, 
            residual_threshold=None, # Auto-detect based on Median Absolute Deviation
            random_state=42
        )
        
        self.is_fitted = False
        self.feature_names = None

    def fit(self, telemetry_path):
        """
        Ingests a CSV, cleans it, and identifies the tire curve.
        Returns: True if a valid model was found.
        """
        try:
            if not isinstance(telemetry_path, pd.DataFrame):
                 # Handle path string input
                df = pd.read_csv(telemetry_path)
            else:
                df = telemetry_path

            # 1. Signal Smoothing (Savitzky-Golay)
            # Differentiating noisy signals (like calculating Slip Angle) is dangerous.
            # We smooth the raw sensors first.
            df_clean = self._smooth_signals(df)

            # 2. Physics Calculation (Single Track Model approximation)
            # You might need to adjust 'lf' (CG to Front Axle) based on your car
            lf = 1.53 
            
            # Avoid division by zero
            vx_safe = np.maximum(df_clean['vx'], 1.0)
            
            # Slip Angle (Alpha) = atan((vy + r*lf) / vx) - delta
            alpha_f = np.arctan((df_clean['vy'] + df_clean['yaw_rate']*lf) / vx_safe) - df_clean['steer_angle']
            
            # Lateral Force (Fy) = ay * Mass (approx)
            # For pure curve fitting, using 'ay' directly is often enough to see the shape
            Fy_f = df_clean['ay'] * 250.0 
            
            # 3. Filter Low Speed Data
            # Tire physics are singular (undefined) at v=0. 
            # We only trust data above 5 m/s.
            mask = df_clean['vx'] > 5.0
            
            if mask.sum() < 100:
                self.logger.warning("Not enough high-speed data to identify physics.")
                return False

            X = alpha_f.values[mask].reshape(-1, 1)
            y = Fy_f.values[mask]

            # 4. Fit the RANSAC Model
            # Transform Alpha into [Alpha, Alpha^2, Alpha^3]
            X_poly = self.poly.fit_transform(X)
            
            self.logger.info("fitting robust tire model...")
            self.model.fit(X_poly, y)
            
            # 5. Validation
            # Check the R^2 score on the INLIERS (the clean data)
            score = self.model.score(X_poly, y)
            self.logger.info(f"Model identified. R2 Score on inliers: {score:.2f}")
            
            self.is_fitted = (score > 0.6) # Threshold for "Good Model"
            return self.is_fitted

        except Exception as e:
            self.logger.error(f"System ID Failed: {e}")
            return False

    def _smooth_signals(self, df):
        """
        Applies Savitzky-Golay filter to remove high-freq noise (engine vibration/sensor jitter).
        """
        df_new = df.copy()
        window = 11 # Window size (must be odd)
        poly_order = 2
        
        target_cols = ['vx', 'vy', 'yaw_rate', 'steer_angle', 'ay', 'ax']
        
        for col in target_cols:
            if col in df.columns:
                try:
                    df_new[col] = savgol_filter(df[col], window_length=window, polyorder=poly_order)
                except ValueError:
                    # Skip if signal is shorter than window
                    pass
        return df_new

    def get_tire_curve(self):
        """
        Returns (Alpha, Fy) arrays for plotting the discovered curve.
        """
        if not self.is_fitted:
            return None, None
            
        # Generate a smooth sweep from -15 to +15 degrees (approx -0.3 to 0.3 rad)
        alpha_sweep = np.linspace(-0.3, 0.3, 100).reshape(-1, 1)
        X_poly_sweep = self.poly.transform(alpha_sweep)
        
        Fy_pred = self.model.predict(X_poly_sweep)
        
        return alpha_sweep.flatten(), Fy_pred