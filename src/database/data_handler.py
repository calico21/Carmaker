import os
import pandas as pd
import numpy as np
import logging
from typing import Dict
from scipy.signal import savgol_filter, correlate, correlation_lags, welch
from sklearn.linear_model import RANSACRegressor

# Try import cmerg
try:
    import cmerg
except ImportError:
    cmerg = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [DATA] - %(message)s')
logger = logging.getLogger(__name__)

class ResultHandler:
    def __init__(self, parquet_storage_path: str):
        self.storage_path = parquet_storage_path
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
        
    def process_results(self, run_id: str, erg_file_path: str) -> Dict[str, float]:
        """
        Ingests simulation binary, converts to optimized Parquet, 
        and calculates Gen 3.0 Vehicle Dynamics Metrics.
        """
        # Default "Crash" KPIs
        fail_kpis = {
            "cost": float('inf'), "max_roll": float('inf'), 
            "stability_index": 0.0, "response_lag": 100.0, "steer_bandwidth": 0.0
        }

        if not os.path.exists(erg_file_path):
            return fail_kpis

        try:
            # 1. Parse ERG (Binary Telemetry)
            if cmerg:
                erg_data = cmerg.ERG(erg_file_path)
                df = erg_data.to_pd()
            else:
                logger.error("cmerg library not found. Cannot parse ERG.")
                return fail_kpis

            # 2. Save Time-Series (Optimized for Dashboard)
            # Downcast to float32 to save space
            cols = df.select_dtypes(include=[np.float64]).columns
            df[cols] = df[cols].astype(np.float32)
            
            parquet_filename = os.path.join(self.storage_path, f"{run_id}.parquet")
            df.to_parquet(parquet_filename, engine='pyarrow', compression='snappy')
            
            # 3. Calculate Advanced KPIs
            return self._calculate_kpis(df)

        except Exception as e:
            logger.error(f"[{run_id}] Processing Failed: {e}")
            return fail_kpis

    def _calculate_kpis(self, df: pd.DataFrame) -> Dict[str, float]:
        kpis = {}
        
        # --- 1. BASIC PERFORMANCE ---
        lap_time = float(df['User.lapTime'].max()) if 'User.lapTime' in df.columns else 999.0
        kpis['cost'] = 999.0 if lap_time < 1.0 else lap_time
        kpis['max_roll'] = float(df['Car.Roll'].abs().max()) if 'Car.Roll' in df.columns else 99.0

        # Check for required channels
        required = ['Car.ay', 'Car.Steer.WhlAng', 'Car.YawRate']
        if not all(col in df.columns for col in required):
            return kpis

        try:
            # --- PRE-PROCESSING ---
            # Signal Smoothing (Savitzky-Golay) to remove sensor noise
            raw_steer = df['Car.Steer.WhlAng'].values
            if len(raw_steer) > 15:
                smooth_steer = savgol_filter(raw_steer, window_length=11, polyorder=2)
            else:
                smooth_steer = raw_steer

            ay = df['Car.ay'].abs() / 9.81
            steer = np.abs(smooth_steer)
            yaw_rate = df['Car.YawRate'].abs() # rad/s
            
            # --- 2. STEADY STATE: Understeer Gradient (RANSAC) ---
            # Robust Regression to ignore transient spikes/curbs
            jerk = np.gradient(ay)
            mask_steady = (ay > 0.4) & (ay < 1.4) & (np.abs(jerk) < 0.05)
            
            if mask_steady.sum() > 20:
                X = ay[mask_steady].values.reshape(-1, 1)
                y = steer[mask_steady]
                ransac = RANSACRegressor(random_state=42)
                ransac.fit(X, y)
                kpis['understeer_grad'] = float(ransac.estimator_.coef_[0] * 180/np.pi) # deg/g
            else:
                kpis['understeer_grad'] = 0.0

            # --- 3. STABILITY: Phase-Plane Index ---
            # Quantifies fraction of lap spent inside the "Stable Diamond"
            if 'Car.SideSlip' in df.columns and 'Car.v' in df.columns:
                beta = df['Car.SideSlip'] # rad
                # Dynamic Yaw Limit based on Friction Circle (approx mu=1.5)
                limit_yaw = (1.5 * 9.81) / (df['Car.v'] + 0.1) 
                limit_beta = 6.0 * (np.pi / 180.0) # 6 deg max beta
                
                unstable_mask = (beta.abs() > limit_beta) | (yaw_rate > limit_yaw)
                kpis['stability_index'] = 1.0 - (unstable_mask.sum() / len(df))
            else:
                kpis['stability_index'] = 1.0 # Default to safe

            # --- 4. AGILITY: Response Lag (Time Domain) ---
            # Cross-Correlation between Steer Input and Yaw Output
            try:
                # Normalize signals
                s_norm = (smooth_steer - np.mean(smooth_steer)) / (np.std(smooth_steer) + 1e-6)
                y_norm = (df['Car.YawRate'] - np.mean(df['Car.YawRate'])) / (np.std(df['Car.YawRate']) + 1e-6)
                
                corr = correlate(s_norm, y_norm, mode='full')
                lags = correlation_lags(len(s_norm), len(y_norm), mode='full')
                
                # Find max correlation shift
                lag_idx = np.argmax(corr)
                lag_samples = -lags[lag_idx] # Negative because output (Yaw) follows input (Steer)
                
                # Convert to ms (assuming 100Hz -> 0.01s)
                response_lag_ms = lag_samples * 10.0 
                
                # Sanity Filter (0 to 500ms is realistic)
                if 0 < response_lag_ms < 500:
                    kpis['response_lag'] = float(response_lag_ms)
                else:
                    kpis['response_lag'] = 50.0 # Default
            except:
                kpis['response_lag'] = 0.0

            # --- 5. RESPONSIVENESS: Bandwidth (Frequency Domain) ---
            # GEN 3.0 FEATURE: Measures how "fast" the driver can shake the wheel
            # before the car stops responding.
            try:
                # Calculate Power Spectral Density
                f, Pxx_steer = welch(smooth_steer, fs=100, nperseg=256)
                f, Pxx_yaw = welch(df['Car.YawRate'], fs=100, nperseg=256)
                
                # Find Frequency where Yaw Power drops to 50% of Steer Power (approx -3dB point)
                # This is a simplified "Control Bandwidth" metric
                ratio = Pxx_yaw / (Pxx_steer + 1e-9)
                # Find freq where ratio drops below threshold
                bandwidth_idx = np.where(ratio < 0.5)[0]
                if len(bandwidth_idx) > 0:
                    kpis['steer_bandwidth'] = float(f[bandwidth_idx[0]]) # Hz
                else:
                    kpis['steer_bandwidth'] = 3.0 # Default Hz
            except:
                kpis['steer_bandwidth'] = 0.0

            # --- 6. WORKLOAD & GAIN ---
            if 'Car.Steer.Vel' in df.columns:
                kpis['steering_rms'] = float(np.sqrt(np.mean(df['Car.Steer.Vel']**2)))
            else: kpis['steering_rms'] = 0.0
            
            if mask_steady.sum() > 10 and steer[mask_steady].mean() > 0.001:
                kpis['yaw_gain'] = float(yaw_rate[mask_steady].mean() / steer[mask_steady].mean())
            else: kpis['yaw_gain'] = 0.0

        except Exception as e:
            logger.warning(f"KPI Calc Failed: {e}")
            # Return safe defaults so optimization continues
            kpis.update({
                'understeer_grad':0.0, 'yaw_gain':0.0, 
                'steering_rms':0.0, 'stability_index':0.0, 
                'response_lag':0.0, 'steer_bandwidth':0.0
            })
    
        return kpis