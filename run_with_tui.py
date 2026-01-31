import threading
import os
import sys
import logging
import time

# Ensure imports work from Root
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.core.orchestrator import OptimizationOrchestrator
from src.dashboard.terminal_ui import TerminalDashboard
from tests.mocks import MockCarMakerInterface, MockResultHandler

STUDY_NAME = "Rich_Visuals_Mock_v1"
DB_URL = "sqlite:///optimization.db"
N_TRIALS = 100
N_WORKERS = 8 

# --- BULLETPROOF LOGGING SETUP ---
# 1. Determine the absolute path to the script's folder
script_dir = os.path.dirname(os.path.abspath(__file__))
log_file_path = os.path.join(script_dir, "system.log")

print(f"📄 LOG FILE IS HERE: {log_file_path}")
time.sleep(2) # Pause so you can read the path before TUI starts

# 2. Configure logging with absolute path
logging.basicConfig(
    filename=log_file_path, 
    level=logging.INFO, 
    filemode='w',
    format='%(asctime)s - %(message)s',
    force=True # Force overwrite of any previous configs
)
# --- The Patch (Injecting the Mocks) ---
class MockOrchestrator(OptimizationOrchestrator):
    """
    Same as the real orchestrator, but swaps the 'Engine' 
    for the Mock version that simulates physics.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 1. Swap the Interface (Simulates CarMaker.exe)
        self.interface = MockCarMakerInterface("dummy/path", self.project_root)
        
        # 2. Swap the Data Handler (Simulates reading .erg files)
        self.data_handler = MockResultHandler(os.path.join(self.project_root, "data", "parquet_store"))

# --- Worker Thread ---
def run_optimization_thread(stop_event):
    """
    Runs the optimization loop in the background.
    """
    # Initialize the MOCKED Orchestrator
    orchestrator = MockOrchestrator(
        project_root=os.path.abspath("."),
        cm_exe_path="dummy", 
        study_name=STUDY_NAME,
        storage_url=DB_URL,
        n_workers=N_WORKERS 
    )
    
    # Ensure template exists (Critical for ParameterManager)
    template_path = os.path.join(orchestrator.project_root, "templates", "TestRuns", "Master_ISO_LaneChange")
    if not os.path.exists(template_path):
        os.makedirs(os.path.dirname(template_path), exist_ok=True)
        with open(template_path, "w") as f:
            f.write("Spring.Front = <k_spring_f>\nSpring.Rear = <k_spring_r>\nDamp.Ratio = <damp_ratio>\nMass.Scale = <mass_scale>")

    try:
        # Run the loop!
        orchestrator.run(n_trials=N_TRIALS, n_jobs=N_WORKERS)
    except Exception as e:
        logging.error(f"Optimization Thread Crashed: {e}")
    finally:
        stop_event.set() # Trigger the UI to close when done

# --- Main Entry Point ---
if __name__ == "__main__":
    print("🚀 Initializing TUI...")
    
    # Signal to control the threads
    stop_event = threading.Event()
    
    # 1. Start Optimization (Background)
    opt_thread = threading.Thread(target=run_optimization_thread, args=(stop_event,))
    opt_thread.start()
    
    # 2. Start Dashboard (Foreground)
    # This will take over your terminal window
    dashboard = TerminalDashboard(STUDY_NAME, N_TRIALS, DB_URL)
    
    try:
        dashboard.run_monitor(stop_event)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_event.set()
        
    opt_thread.join()
    print("\n✅ Optimization and Monitoring Finished.")
    print("   Check 'system.log' for detailed debugging info.")