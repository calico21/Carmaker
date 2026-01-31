import os
import pandas as pd
import numpy as np
import logging
from typing import Dict

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
        
        # --- 1. PERFORMANCE: Lap Time ---
        if 'User.lapTime' in df.columns:
            lap_time = float(df['User.lapTime'].max())
            kpis['cost'] = 999.0 if lap_time < 1.0 else lap_time
        else:
            kpis['cost'] = 999.0

        # --- 2. STABILITY: Max Roll ---
        if 'Car.Roll' in df.columns:
            kpis['max_roll'] = float(df['Car.Roll'].abs().max())
        else:
            kpis['max_roll'] = 99.0

        # --- 3. DRIVER FEEL: Understeer Gradient ---
        # Goal: Calculate slope of Steering Angle vs Lateral G
        if 'Car.ay' in df.columns and 'Car.Steer.WhlAng' in df.columns:
            try:
                # Get absolute values (treat left/right turns the same)
                # Convert ay to G-force (m/s^2 -> g)
                ay_g = df['Car.ay'].abs() / 9.81
                steer_deg = df['Car.Steer.WhlAng'].abs() * (180/np.pi) # Ensure degrees
                
                # FILTER: Only look at the "Linear Range" of the tires
                # We ignore low speed (<0.2G) and extreme sliding (>1.2G)
                mask = (ay_g > 0.2) & (ay_g < 1.2)
                
                if mask.sum() > 10: # Ensure we have enough data points
                    # Linear Regression (Polyfit Order 1)
                    # y = mx + c  ->  Steer = (Gradient * G) + Offset
                    slope, intercept = np.polyfit(ay_g[mask], steer_deg[mask], 1)
                    
                    kpis['understeer_grad'] = float(slope) # Units: deg/g
                else:
                    kpis['understeer_grad'] = 0.0
                    
            except Exception as e:
                logger.warning(f"Failed to calc Understeer Gradient: {e}")
                kpis['understeer_grad'] = 0.0
        else:
            kpis['understeer_grad'] = 0.0

        return kpis