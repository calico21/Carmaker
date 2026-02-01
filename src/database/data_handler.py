import os
import pandas as pd
import numpy as np
import logging
from typing import Dict
from scipy.signal import savgol_filter, welch
from scipy.stats import linregress

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [DATA] - %(message)s')
logger = logging.getLogger(__name__)

class ResultHandler:
    """
    GEN 5.0 DATA INGESTION ENGINE.
    
    Capabilities:
    1. Steady State Analysis (Understeer Gradient).
    2. Frequency Domain Analysis (Control Bandwidth).
    3. Transient Response (Time Delays).
    """
    def __init__(self, parquet_storage_path: str):
        self.storage_path = parquet_storage_path
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
        
    def process_results(self, run_id: str, erg_file_path: str) -> Dict[str, float]:
        """
        Ingests simulation output, converts to optimized Parquet, 
        and calculates Engineering KPIs.
        """
        # Default "Fail" KPIs
        fail_kpis = {
            "cost": float('inf'), 
            "max_roll": 99.0, 
            "stability_index": 0.0, 
            "understeer_grad": 0.0, 
            "response_lag": 100.0, 
            "yaw_bandwidth": 0.0, # Gen 5.0 Metric
            "steering_rms": 0.0
        }

        if not os.path.exists(erg_file_path):
            return fail_kpis

        try:
            # 1. READ DATA (Robust handling for CarMaker ASCII)
            try:
                # Skip the first few header lines usually found in ERG files
                df = pd.read_csv(erg_file_path, encoding='iso-8859-1', delim_whitespace=True, skiprows=[1])
            except Exception as e:
                logger.error(f"Could not parse ERG file {erg_file_path}: {e}")
                return fail_kpis

            # 2. SAVE AS PARQUET (Fast access for Dashboard)
            parquet_path = os.path.join(self.storage_path, f"{run_id}.parquet")
            df.to_parquet(parquet_path)

            # 3. EXTRACT CHANNELS (Standard CarMaker Naming)
            # Ensure these match your specific CarMaker OutputQuantities!
            time = df['Time'].values
            steer = df['Car.Steer.WhlAngle'].values # rad (at wheel)
            speed = df['Car.v'].values # m/s
            yaw_rate = df['Car.YawRate'].values # rad/s
            lat_acc = df['Car.Fr1.Ay'].values # m/s^2 (Frame 1 ~ CG)
            roll = df['Car.Roll'].values # rad
            
            # 4. BASIC CHECKS
            lap_time = time[-1] if speed[-1] > 1.0 else 999.0 # Did we finish?
            max_roll = np.max(np.abs(roll))

            # =========================================================
            # GEN 5.0: THE PHYSICS ENGINE
            # =========================================================
            
            # --- A. STEADY STATE METRICS (The "Skidpad" Check) ---
            # Mask: Speed > 10m/s AND LatAcc > 0.5G (Loaded cornering)
            mask_cornering = (speed > 10.0) & (np.abs(lat_acc) > 5.0)
            
            understeer_gradient = 0.0
            if np.sum(mask_cornering) > 50:
                # Bundorf Analysis: Steer = L/R + K_us * Ay
                # We regress Steer (deg) vs LatAcc (g)
                x = lat_acc[mask_cornering] / 9.81 # g
                y = steer[mask_cornering] * 57.296 # deg
                if len(x) > 10:
                    slope, _, _, _, _ = linregress(x, y)
                    understeer_gradient = slope # deg/g

            # --- B. TRANSIENT RESPONSE (The "Agility" Check) ---
            # Calculate lag between Steering Input and Yaw Output
            lag_ms = 50.0
            try:
                # Normalize signals to -1..1 for correlation
                s_norm = (steer - np.mean(steer)) / (np.std(steer) + 1e-6)
                y_norm = (yaw_rate - np.mean(yaw_rate)) / (np.std(yaw_rate) + 1e-6)
                
                # Cross-Correlation
                correlation = np.correlate(s_norm, y_norm, mode='full')
                lags = np.arange(-len(s_norm) + 1, len(s_norm))
                lag_idx = lags[np.argmax(correlation)]
                
                dt = time[1] - time[0]
                lag_ms = max(0, lag_idx * dt * 1000) # ms
            except: pass

            # --- C. FREQUENCY DOMAIN (The "Titan" Check) ---
            # Calculate System Bandwidth via FFT
            yaw_bandwidth = self._calculate_frequency_response(time, steer, yaw_rate)

            # --- D. STABILITY INDEX ---
            # Penalize high Sideslip Rate (Beta_dot)
            stability_score = 1.0
            if 'Car.SideSlip' in df.columns:
                beta = df['Car.SideSlip'].values
                # Derivative of Beta
                beta_rate = np.gradient(beta, time)
                # Mean Absolute Beta Rate during cornering
                mean_beta_rate = np.mean(np.abs(beta_rate[mask_cornering])) if np.sum(mask_cornering) > 0 else 0.0
                # Heuristic: > 10 deg/s is scary
                stability_score = max(0.0, 1.0 - (mean_beta_rate * 5.0))

            # 5. PACKAGING
            kpis = {
                "cost": float(lap_time),
                "max_roll": float(max_roll),
                "understeer_grad": float(understeer_gradient), 
                "stability_index": float(stability_score),
                "response_lag": float(lag_ms),
                "yaw_bandwidth": float(yaw_bandwidth),
                "steering_rms": float(np.std(steer))
            }
            
            return kpis

        except Exception as e:
            logger.error(f"KPI Calc Failed for {run_id}: {e}")
            return fail_kpis

    def _calculate_frequency_response(self, time, steer, yaw_rate):
        """
        GEN 5.0 EXCLUSIVE: BODE PLOT GENERATOR.
        Calculates the -3dB Bandwidth of the Yaw Response.
        
        Judge Defense:
        "We optimized for a 3.0Hz bandwidth to ensure the driver can 
        counter-steer effectively in the slalom."
        """
        try:
            # Sampling frequency
            dt = np.mean(np.diff(time))
            if dt <= 0: return 0.0
            fs = 1.0 / dt
            
            # Welch's Method for Power Spectral Density (PSD)
            # nperseg=256 gives decent frequency resolution
            f, Pxx_steer = welch(steer, fs, nperseg=256)
            f, Pxx_yaw = welch(yaw_rate, fs, nperseg=256)
            
            # Transfer Function Magnitude Estimate |H(f)|
            # H(f) = Output / Input
            # Add epsilon to prevent divide by zero
            magnitude = np.sqrt(Pxx_yaw) / (np.sqrt(Pxx_steer) + 1e-9)
            
            # Normalize DC Gain (Low frequency gain) to 1.0
            # We assume the first 5 bins represent "Steady State"
            dc_gain = np.mean(magnitude[:5])
            if dc_gain < 1e-6: return 0.0 # No response?
            
            normalized_mag = magnitude / dc_gain
            
            # Find -3dB point (0.707 magnitude)
            # This is the standard definition of "Bandwidth"
            cutoff_indices = np.where(normalized_mag < 0.707)[0]
            
            if len(cutoff_indices) > 0:
                bandwidth_hz = f[cutoff_indices[0]]
            else:
                bandwidth_hz = f[-1] # Bandwidth exceeds Nyquist (unlikely)
                
            return float(bandwidth_hz)
            
        except Exception as e:
            logger.warning(f"Bandwidth Calc Failed: {e}")
            return 0.0