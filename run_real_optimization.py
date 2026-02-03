from src.core.orchestrator import Orchestrator
from src.core.system_id import SystemIdentifier
import logging

# --- CONFIGURATION ---
CALIBRATE_FIRST = False  # Set to True once you have "real_log.csv"
STUDY_NAME = "FSAE_Spain_2026_Attack"
REAL_LOG_PATH = "data/real_world_log.csv"

def main():
    logging.basicConfig(level=logging.INFO, 
                       format='[%(name)s] %(levelname)s: %(message)s')
    
    # 1. Initialize Resources
    orchestrator = Orchestrator(STUDY_NAME)
    
    # 2. Phase 5: Digital Twin Calibration (Optional but Recommended)
    if CALIBRATE_FIRST:
        sys_id = SystemIdentifier(REAL_LOG_PATH, orchestrator.storage_url)
        print("\n🔍 PHASE 5: SYSTEM IDENTIFICATION (DIGITAL TWIN)...")
        real_physics = sys_id.calibrate(n_trials=30)
        
        if real_physics:
            # Apply these calibrated physics to the base vehicle model
            orchestrator.param_manager.update_base_physics(real_physics)
    
    # 3. Phase 1-4: Dynamic Optimization
    print(f"\n🚀 STARTING OPTIMIZATION CAMPAIGN: {STUDY_NAME}")
    best_setup = orchestrator.optimize(n_trials=100)
    
    print("\n🏆 FINAL OPTIMIZED SETUP:")
    for k, v in best_setup.items():
        print(f"  {k}: {v:.4f}")

if __name__ == "__main__":
    main()