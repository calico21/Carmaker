import os
import pandas as pd
import numpy as np
import logging
from typing import Dict

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
        """Reads ERG, saves Parquet, extracts Multi-Objective KPIs."""
        if not os.path.exists(erg_file_path):
            logger.error(f"[{run_id}] ERG file not found.")
            return {"cost": float('inf'), "max_roll": float('inf')}

        try:
            # 1. Parse ERG
            if cmerg:
                erg_data = cmerg.ERG(erg_file_path)
                df = erg_data.to_pd()
            else:
                # Fallback or error if no library
                return {"cost": float('inf'), "max_roll": float('inf')}

            # 2. Save Time-Series (Optimized Float32)
            cols = df.select_dtypes(include=[np.float64]).columns
            df[cols] = df[cols].astype(np.float32)
            
            parquet_filename = os.path.join(self.storage_path, f"{run_id}.parquet")
            df.to_parquet(parquet_filename, engine='pyarrow', compression='snappy')
            
            # 3. Calculate KPIs
            kpis = self._calculate_kpis(df)
            return kpis

        except Exception as e:
            logger.error(f"[{run_id}] Processing Failed: {e}")
            return {"cost": float('inf'), "max_roll": float('inf')}

    def _calculate_kpis(self, df: pd.DataFrame) -> Dict[str, float]:
        kpis = {}
        
        # --- OBJECTIVE 1: LAP TIME ---
        if 'User.lapTime' in df.columns:
            lap_time = float(df['User.lapTime'].max())
            if lap_time < 1.0: # Crash/DNF detection
                kpis['cost'] = 999.0
            else:
                kpis['cost'] = lap_time
        else:
            kpis['cost'] = 999.0

        # --- OBJECTIVE 2: MAX BODY ROLL (Stability) ---
        # We use absolute maximum roll angle (radians or degrees)
        if 'Car.Roll' in df.columns:
            # Convert to degrees if your analysis prefers it, usually keeps in radians
            max_roll = float(df['Car.Roll'].abs().max())
            kpis['max_roll'] = max_roll
        else:
            # If signal missing, apply "High Roll" penalty so optimizer avoids it
            kpis['max_roll'] = 99.0 

        return kpis