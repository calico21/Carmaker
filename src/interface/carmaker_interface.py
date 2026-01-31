import subprocess
import threading
import time
import os
import logging
import signal
from typing import Optional, Dict, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [INTERFACE] - %(message)s')
logger = logging.getLogger(__name__)

class SimulationWatchdog:
    """
    Responsibilities:
    1. Monitor stdout/stderr in real-time.
    2. Detect failure keywords (License, Crash).
    3. Detect Pruning keywords (Sector Times) for Optuna.
    4. Enforce timeouts.
    """
    def __init__(self, process: subprocess.Popen, timeout: int, trial=None):
        self.process = process
        self.timeout = timeout
        self.trial = trial # <--- Added for Pruning
        self.start_time = time.time()
        self.error_detected = False
        self.error_message = ""
        self.pruned = False # <--- Added for Pruning
        self.timed_out = False
        self._stop_event = threading.Event()

        # Failure keywords
        self.FAILURE_KEYWORDS = [
            "License error", "Checkout failed", "Segmentation fault",
            "aborted", "FATAL ERROR", "Exception"
        ]

    def monitor(self):
        """
        Real-time Log Parsing.
        Kills the sim if:
        1. It crashes (License/Fatal Error).
        2. It is too slow (Sector Pruning).
        """
        self.process.stdout.reconfigure(line_buffering=True)
        
        # --- PRUNING THRESHOLDS (Customize these for your track) ---
        # If Sector 1 takes > 28 seconds, the run is trash. Kill it.
        SECTOR_1_LIMIT = 28.0 
        
        while not self._stop_event.is_set():
            if self.process.poll() is not None:
                break

            # Read line-by-line
            line = self.process.stdout.readline()
            if not line:
                break
            
            # A. CRASH DETECTION
            for kw in self.FAILURE_KEYWORDS:
                if kw in line:
                    self.error_detected = True
                    self.error_message = kw
                    self.process.terminate()
                    return

            # B. EFFICIENCY: SECTOR PRUNING
            # CarMaker logs usually look like: "Sector 1: 24.5s" or similar
            # You might need to add a printf in your CarMaker TestRun to output this!
            if "Sector 1" in line and self.trial:
                try:
                    # Parse time from log line (e.g., "End of Sector 1: 29.5 s")
                    # This is a robust fallback: look for floating point numbers
                    words = line.split()
                    for w in words:
                        try:
                            time_val = float(w)
                            if 0 < time_val < 1000: # Sanity check
                                if time_val > SECTOR_1_LIMIT:
                                    logger.warning(f"✂️ PRUNED: Sector 1 Slow ({time_val}s > {SECTOR_1_LIMIT}s)")
                                    self.pruned = True
                                    self.trial.report(time_val, step=1) # Report to Optuna
                                    self.process.terminate()
                                    return
                        except: pass
                except: pass

            # C. TIMEOUT CHECK
            if time.time() - self.start_time > self.timeout:
                self.timed_out = True
                self.process.terminate()
                return

    def _handle_pruning(self, line):
        """Parses log line and asks Optuna if we should stop."""
        try:
            # Expected: "[PRUNE] Step=1 Value=12.5"
            parts = line.split() 
            step = int(parts[1].split('=')[1])
            value = float(parts[2].split('=')[1])
            
            self.trial.report(value, step=step)
            
            if self.trial.should_prune():
                logger.warning(f"Optimization Pruned at Step {step}")
                self.pruned = True
                self.kill_process("Optuna Early Stopping")
        except:
            pass

    def kill_process(self, reason: str):
        """Safely terminates the external binary."""
        logger.info(f"Terminating Simulation. Reason: {reason}")
        try:
            # Windows: Kill the whole process tree
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
        except Exception as e:
            logger.error(f"Failed to kill process: {e}")

    def stop(self):
        self._stop_event.set()


class CarMakerInterface:
    def __init__(self, executable_path: str, project_folder: str):
        self.exe_path = executable_path
        self.project_folder = project_folder
    
    def _find_result_file(self, sim_output_dir: str) -> Optional[str]:
        """
        Your robust file finder.
        """
        current_time = time.time()
        best_file = None
        
        if not os.path.exists(sim_output_dir):
            return None

        for filename in os.listdir(sim_output_dir):
            filepath = os.path.join(sim_output_dir, filename)
            
            if not os.path.isfile(filepath): continue
            if filename.endswith(".log"): continue 
            
            # Time & Size Check
            mtime = os.path.getmtime(filepath)
            if current_time - mtime > 180: continue # 3 mins max age
            if os.path.getsize(filepath) < 1000: continue
                
            best_file = filepath
            break
            
        return best_file

    def run_simulation(self, test_run_name: str, tcp_port: int, timeout_sec: int, trial=None) -> Dict:
        
        cmd = [
            self.exe_path,
            "-batch",
            "-cmdport", str(tcp_port),
            "-d", self.project_folder,
            "-run", test_run_name
        ]

        logger.info(f"Starting: {test_run_name} (Port {tcp_port})")

        try:
            # Use CREATE_NEW_PROCESS_GROUP for Windows safety
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding='utf-8',
                errors='ignore',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP 
            )

            # Attach the Enhanced Watchdog
            watchdog = SimulationWatchdog(process, timeout_sec, trial)
            monitor_thread = threading.Thread(target=watchdog.monitor)
            monitor_thread.start()

            process.wait() 
            watchdog.stop()
            monitor_thread.join()

            # Result Logic
            if watchdog.pruned:
                return {"status": "PRUNED", "reason": "Early Stopping"}

            if watchdog.timed_out:
                return {"status": "FAILED", "reason": "Timeout"}
            
            if watchdog.error_detected:
                return {"status": "FAILED", "reason": watchdog.error_message}

            if process.returncode != 0:
                return {"status": "FAILED", "reason": f"Exit Code {process.returncode}"}

            return {"status": "SUCCESS", "run_id": test_run_name}

        except Exception as e:
            logger.error(f"Interface Error: {e}")
            return {"status": "ERROR", "reason": str(e)}