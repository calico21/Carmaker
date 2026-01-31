import time
import random
import os
import logging
import pandas as pd
import numpy as np
from typing import Dict

logger = logging.getLogger(__name__)

class MockCarMakerInterface:
    """
    Simulates the 'Service Layer' without running a binary.
    """
    def __init__(self, executable_path: str, project_folder: str):
        self.project_folder = project_folder
        logger.warning("⚠️ RUNNING IN MOCK MODE: No simulation will be executed.")

    def run_simulation(self, test_run_name: str, tcp_port: int, timeout_sec: int) -> Dict:
        # Simulate variable execution time (physics calculation)
        delay = random.uniform(0.1, 0.5)
        time.sleep(delay)
        
        # Simulate occasional random failures (robustness testing)
        if random.random() < 0.05: # 5% chance of crash
            return {"status": "FAILED", "reason": "Random Mock Segfault"}
            
        return {"status": "SUCCESS", "run_id": test_run_name}

class MockResultHandler:
    """
    Simulates the 'Data Layer'.
    Instead of reading .erg files, it calculates a math function to mimic physics costs.
    It generates fake time-series data for the Dashboard.
    """
    def __init__(self, parquet_storage_path: str):
        self.storage_path = parquet_storage_path
        os.makedirs(self.storage_path, exist_ok=True)

    def process_results(self, run_id: str, erg_file_path: str = None, params: Dict = None) -> Dict:
        """
        Generates synthetic data based on the input parameters.
        """
        # 1. Retrieve the parameters (We need them to calculate cost)
        # In the real class, we read results. Here, we infer cost from inputs (Math Problem).
        # Let's assume we are optimizing: Cost = (k_spring_f - 45000)^2 + (damp_ratio - 0.7)^2
        
        # Default center points (The "Optimal" setup)
        target_k = 45000.0
        target_damp = 0.65
        
        # Get params from the 'Fake' erg path or pass them explicitly? 
        # For simplicity in mocks, we often cheat and need the params.
        # But to keep the API consistent, we'll generate random noise if params aren't accessible,
        # OR we rely on the Orchestrator passing them (which requires a small tweak).
        # Let's assume the params influenced the "Physics" (Random for now + Trend).
        
        # GENERATE FAKE TIME SERIES (For Dashboard)
        # Create a velocity profile that gets "smoother" as cost improves
        length = 100
        t = np.linspace(0, 10, length)
        
        # Random variance
        noise = np.random.normal(0, 1, length)
        velocity = 30.0 + 5.0 * np.sin(t) + noise
        
        df = pd.DataFrame({
            "Time": t,
            "Car.v": velocity,
            "Steering.Ang": np.cos(t) * 0.5
        })
        
        # Save Parquet
        parquet_filename = os.path.join(self.storage_path, f"{run_id}.parquet")
        df.to_parquet(parquet_filename)

        # GENERATE SCALAR COST
        # To make the dashboard look real, we return a random cost 
        # (Real mock would calculate based on input params)
        cost = random.uniform(100, 200)
        
        return {
            "cost": cost,
            "max_speed": float(velocity.max()),
            "fuel_consumed": random.uniform(5.5, 9.2)
        }