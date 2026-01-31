import os
import sys
import logging
import time
import numpy as np

# Patch for library compatibility
np.bool = np.bool_

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(PROJECT_ROOT)

from src.core.orchestrator import OptimizationOrchestrator

# --- CONFIGURATION ---
STUDY_NAME = "FSAE_Championship_Run_v1"
N_TRIALS = 100
N_WORKERS = 4  # Set this to the number of CarMaker licenses you have available
CM_EXE_PATH = r"C:\IPG\carmaker\win64-13.0\bin\CM.exe" # <--- VERIFY YOUR VERSION (13.0 vs 14.1)

# Paths
DB_PATH = os.path.join(PROJECT_ROOT, "data", "optimization.db")
DB_URL = f"sqlite:///{DB_PATH}"
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "production.log")

# Setup Directories
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# --- LOGGING SETUP ---
# We log to BOTH file and console so you can see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)

if __name__ == "__main__":
    print(f"\n🚀 FSAE DESIGN OPTIMIZATION SYSTEM STARTING")
    print(f"-------------------------------------------")
    print(f"📂 Project Root: {PROJECT_ROOT}")
    print(f"📂 Database:     {DB_PATH}")
    print(f"🏎️  CarMaker:     {CM_EXE_PATH}")
    print(f"🧵 Workers:      {N_WORKERS}")
    print(f"-------------------------------------------\n")

    # Check if CarMaker exists before starting
    if not os.path.exists(CM_EXE_PATH):
        logging.critical(f"❌ CRITICAL: CarMaker executable not found at {CM_EXE_PATH}")
        sys.exit(1)

    try:
        # Initialize the Brain
        orchestrator = OptimizationOrchestrator(
            project_root=PROJECT_ROOT,
            cm_exe_path=CM_EXE_PATH,
            study_name=STUDY_NAME,
            storage_url=DB_URL,
            n_workers=N_WORKERS
        )

        logging.info("✅ Orchestrator Initialized. Starting Optimization Loop...")
        
        # Run the Optimization
        # Note: We use n_jobs=1 here because the Orchestrator handles threading internally via ResourceManager
        orchestrator.run(n_trials=N_TRIALS, n_jobs=1) 
        
        logging.info("🏁 Optimization Finished Successfully.")
        
    except KeyboardInterrupt:
        logging.warning("⚠️ Process Interrupted by User.")
    except Exception as e:
        logging.critical(f"❌ FATAL ERROR: {e}", exc_info=True)