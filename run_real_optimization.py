import threading
import os
import sys
import logging
import time

# Ensure imports work from Root
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.core.orchestrator import OptimizationOrchestrator
from src.dashboard.terminal_ui import TerminalDashboard

# --- PATH CONFIGURATION ---
script_dir = os.path.dirname(os.path.abspath(__file__))

# 1. Database Path (Moved to /data)
DB_PATH = os.path.join(script_dir, "data", "optimization.db")
DB_URL = f"sqlite:///{DB_PATH}"

# 2. Log Path (Moved to /logs)
LOG_DIR = os.path.join(script_dir, "logs")
LOG_FILE = os.path.join(LOG_DIR, "production.log")

# Ensure directories exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# --- LOGGING SETUP ---
logging.basicConfig(
    filename=LOG_FILE, 
    level=logging.INFO, 
    filemode='w', # 'w' overwrites log each run. Change to 'a' to append history.
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)

# --- RUN CONFIGURATION ---
STUDY_NAME = "Production_Run_v1"
N_TRIALS = 50 
N_WORKERS = 1  # Start conservative!

def run_optimization_thread(stop_event):
    """The Real Worker Thread"""
    
    # UPDATE THIS PATH to match your installation
    cm_exe_path = r"C:\IPG\carmaker\win64-14.1\bin\CM.exe"
    
    if not os.path.exists(cm_exe_path):
        logging.critical(f"CarMaker Executable not found at: {cm_exe_path}")
        stop_event.set()
        return

    orchestrator = OptimizationOrchestrator(
        project_root=script_dir,
        cm_exe_path=cm_exe_path, 
        study_name=STUDY_NAME,
        storage_url=DB_URL, # <--- Passing the new data path
        n_workers=N_WORKERS 
    )
    
    # Validation
    template_path = os.path.join(script_dir, "templates", "TestRuns", "Master_Skidpad")
    if not os.path.exists(template_path):
        logging.critical(f"Template not found: {template_path}")
        stop_event.set()
        return

    try:
        logging.info("Starting Production Optimization Loop...")
        orchestrator.run(n_trials=N_TRIALS, n_jobs=N_WORKERS)
    except Exception as e:
        logging.error(f"Optimization Thread Crashed: {e}", exc_info=True)
    finally:
        stop_event.set()

if __name__ == "__main__":
    print(f"🚀 Starting PRODUCTION Run...")
    print(f"📂 Database: data/optimization.db")
    print(f"📄 Logging to: logs/production.log")
    print(f"⚠️  Workers: {N_WORKERS}")
    time.sleep(3) 
    
    stop_event = threading.Event()
    
    opt_thread = threading.Thread(target=run_optimization_thread, args=(stop_event,))
    opt_thread.start()
    
    dashboard = TerminalDashboard(STUDY_NAME, N_TRIALS, DB_URL)
    
    try:
        dashboard.run_monitor(stop_event)
    except KeyboardInterrupt:
        stop_event.set()
        
    opt_thread.join()
    print("\n✅ Run Finished.")