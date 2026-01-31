import os
import pandas as pd
import numpy as np
import logging
import json
from typing import Dict

# Try importing cmerg, handle failure gracefully
try:
    import cmerg
except ImportError:
    cmerg = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [DATA] - %(message)s')
logger = logging.getLogger(__name__)

class ResultHandler:
    """
    Responsibilities:
    1. Parse binary .erg files from CarMaker.
    2. Extract specific KPIs (like User.lapTime).
    3. Compress full time-series data into Parquet for the Dashboard.
    """

    def __init__(self, parquet_storage_path: str):
        self.storage_path = parquet_storage_path
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
        
        if cmerg is None:
            logger.warning("Library 'cmerg' not found. .erg files cannot be parsed.")

    def process_results(self, run_id: str, erg_file_path: str) -> Dict[str, float]:
        """
        Main pipeline: ERG -> Pandas -> Parquet + KPIs
        """
        if not os.path.exists(erg_file_path):
            logger.error(f"[{run_id}] ERG file not found at: {erg_file_path}")
            return {"cost": float('inf')}

        try:
            # 1. Read the proprietary ERG file
            erg_data = cmerg.ERG(erg_file_path)
            
            # Convert to Pandas DataFrame
            # We explicitly load only what we need to save memory if files are huge
            # But for standard runs, loading everything is fine.
            df = erg_data.to_pd()

            # 2. Optimization: Downcast to float32 to reduce storage by ~50%
            cols = df.select_dtypes(include=[np.float64]).columns
            df[cols] = df[cols].astype(np.float32)

            # 3. Save to Parquet (The "Time-Series Store")
            parquet_filename = os.path.join(self.storage_path, f"{run_id}.parquet")
            df.to_parquet(parquet_filename, engine='pyarrow', compression='snappy')
            
            # 4. Calculate KPIs (The "Scalar Metadata")
            kpis = self._calculate_kpis(df)
            
            return kpis

        except Exception as e:
            logger.error(f"[{run_id}] Failed to process results: {e}")
            return {"cost": float('inf')}

    def _calculate_kpis(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Compute scalar metrics from the time-series data.
        """
        kpis = {}
        
        # --- 1. PRIMARY OBJECTIVE: LAP TIME ---
        # In your TestRun, you defined "Qu::lapTime".
        # CarMaker exports this as "User.lapTime" in the ERG file.
        if 'User.lapTime' in df.columns:
            # The signal updates at the end of the lap. We take the max value.
            lap_time = float(df['User.lapTime'].max())
            
            # Sanity Check: If lap time is near 0, the car crashed or didn't start.
            if lap_time < 1.0:
                kpis['cost'] = 999.0 # Penalty for DNF (Did Not Finish)
                kpis['status'] = "DNF"
            else:
                kpis['cost'] = lap_time
                kpis['lap_time'] = lap_time
                kpis['status'] = "FINISHED"
        else:
            # Signal missing? Maybe the TestRun didn't compile correctly.
            logger.warning("Signal 'User.lapTime' missing in results.")
            kpis['cost'] = 999.0
            kpis['status'] = "ERROR_MISSING_SIGNAL"

        # --- 2. SECONDARY METRICS (For Analysis) ---
        # Max Speed
        if 'Car.v' in df.columns:
            kpis['max_speed'] = float(df['Car.v'].max() * 3.6) # m/s -> km/h
        
        # Lateral Acceleration Max (G-Force)
        if 'Car.ay' in df.columns:
            kpis['max_lat_g'] = float(df['Car.ay'].abs().max() / 9.81)

        return kpis