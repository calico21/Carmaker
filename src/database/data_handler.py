import os
import pandas as pd
import numpy as np
import logging
from typing import Dict
from scipy.signal import savgol_filter, correlate, correlation_lags
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
        """Reads ERG, saves Parquet, extracts 'Driver Feel' KPIs."""
        if not os.path.exists(erg_file_path):
            return {"cost": float('inf'), "max_roll": float('inf'), "understeer_grad": 0.0}

        try:
            # 1. Parse ERG
            if cmerg:
                erg_data = cmerg.ERG(erg_file_path)
                df = erg_data.to_pd()
            else:
                return {"cost": float('inf'), "max_roll": float('inf'), "understeer_grad": 0.0}

            # 2. Save Time-Series (Optimized)
            cols = df.select_dtypes(include=[np.float64]).columns
            df[cols] = df[cols].astype(np.float32)
            
            parquet_filename = os.path.join(self.storage_path, f"{run_id}.parquet")
            df.to_parquet(parquet_filename, engine='pyarrow', compression='snappy')
            
            # 3. Calculate KPIs
            kpis = self._calculate_kpis(df)
            return kpis

        except Exception as e:
            logger.error(f"[{run_id}] Processing Failed: {e}")
            return {"cost": float('inf'), "max_roll": float('inf'), "understeer_grad": 0.0}

    def _calculate_kpis(self, df: pd.DataFrame) -> Dict[str, float]:
        kpis = {}
        
        # 1. Performance
        lap_time = float(df['User.lapTime'].max()) if 'User.lapTime' in df.columns else 999.0
        kpis['cost'] = 999.0 if lap_time < 1.0 else lap_time
        kpis['max_roll'] = float(df['Car.Roll'].abs().max()) if 'Car.Roll' in df.columns else 99.0

        if 'Car.ay' in df.columns and 'Car.Steer.WhlAng' in df.columns and 'Car.YawRate' in df.columns:
            try:
                # Constants
                STEER_RATIO = 1.0 
                
                # --- Signal Smoothing ---
                raw_steer = df['Car.Steer.WhlAng'].values
                if len(raw_steer) > 15:
                    smooth_steer = savgol_filter(raw_steer, window_length=11, polyorder=2)
                else:
                    smooth_steer = raw_steer

                ay = df['Car.ay'].abs() / 9.81
                steer = np.abs(smooth_steer) / STEER_RATIO
                yaw_rate = df['Car.YawRate'].abs() # rad/s
                
                # --- A. STEADY STATE: Understeer Gradient ---
                jerk = np.gradient(ay) 
                mask_steady = (ay > 0.4) & (ay < 1.4) & (np.abs(jerk) < 0.05)
                
                if mask_steady.sum() > 20: 
                    X = ay[mask_steady].values.reshape(-1, 1)
                    y = steer[mask_steady]
                    ransac = RANSACRegressor(random_state=42)
                    ransac.fit(X, y)
                    slope = ransac.estimator_.coef_[0]
                    kpis['understeer_grad'] = float(slope * 180/np.pi) 
                else:
                    kpis['understeer_grad'] = 0.0

                # --- B. TRANSIENT: Yaw Rate Gain ---
                if mask_steady.sum() > 10:
                    avg_steer = steer[mask_steady].mean()
                    avg_yaw = yaw_rate[mask_steady].mean()
                    if avg_steer > 0.001:
                        kpis['yaw_gain'] = float(avg_yaw / avg_steer) 
                    else: kpis['yaw_gain'] = 0.0
                else: kpis['yaw_gain'] = 0.0

                # --- C. WORKLOAD: Steering RMS ---
                if 'Car.Steer.Vel' in df.columns:
                    steer_vel = df['Car.Steer.Vel']
                    rms_workload = np.sqrt(np.mean(steer_vel**2))
                    kpis['steering_rms'] = float(rms_workload)
                else:
                    kpis['steering_rms'] = 0.0

                # --- D. STABILITY: Phase-Plane Index ---
                if 'Car.SideSlip' in df.columns and 'Car.v' in df.columns:
                    beta = df['Car.SideSlip'] # rad
                    limit_yaw = (1.5 * 9.81) / (df['Car.v'] + 0.1) 
                    limit_beta = 6.0 * (np.pi / 180.0) 
                    unstable_mask = (beta.abs() > limit_beta) | (yaw_rate > limit_yaw)
                    stability_score = 1.0 - (unstable_mask.sum() / len(df))
                    kpis['stability_index'] = float(stability_score)
                else:
                    kpis['stability_index'] = 1.0 

                # --- E. AGILITY (GEN 2.0): Response Lag & Sharpness ---
                # 1. Response Lag: Cross-Correlation between Steer and Yaw Rate
                # Positive lag = Car reacts AFTER steering (Latency)
                try:
                    # Normalize signals for correlation
                    s_norm = (smooth_steer - np.mean(smooth_steer)) / (np.std(smooth_steer) + 1e-6)
                    y_norm = (df['Car.YawRate'].values - np.mean(df['Car.YawRate'].values)) / (np.std(df['Car.YawRate'].values) + 1e-6)
                    
                    correlation = correlate(s_norm, y_norm, mode='full')
                    lags = correlation_lags(len(s_norm), len(y_norm), mode='full')
                    lag_idx = np.argmax(correlation)
                    lag_samples = -lags[lag_idx] # Negative because we want Delay relative to Steer
                    
                    # Convert to ms (assuming 100Hz -> 0.01s)
                    dt = 0.01 
                    response_lag_ms = lag_samples * dt * 1000.0
                    
                    # Filter out non-causal noise (lag shouldn't be negative or > 500ms)
                    if 0 < response_lag_ms < 500:
                        kpis['response_lag'] = float(response_lag_ms)
                    else:
                         kpis['response_lag'] = 50.0 # Default/Fail-safe
                         
                except Exception:
                    kpis['response_lag'] = 0.0

                # 2. Yaw Agility (Peak Yaw Acceleration)
                # Measures "Sharpness" of turn-in
                yaw_accel = np.gradient(df['Car.YawRate'].values) / 0.01 # rad/s^2
                kpis['yaw_agility'] = float(np.max(np.abs(yaw_accel)))

            except Exception as e:
                logger.warning(f"KPI Calc Failed: {e}")
                kpis.update({'understeer_grad':0.0, 'yaw_gain':0.0, 'steering_rms':0.0, 'stability_index':0.0, 'response_lag':0.0})
        else:
            kpis.update({'understeer_grad':0.0, 'yaw_gain':0.0, 'steering_rms':0.0, 'stability_index':0.0, 'response_lag':0.0})

        return kpis