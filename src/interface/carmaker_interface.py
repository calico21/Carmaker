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
        """Runs in a background thread to intercept stream data."""
        while not self._stop_event.is_set():
            # 1. Timeout Check
            elapsed = time.time() - self.start_time
            if elapsed > self.timeout:
                self.timed_out = True
                self.kill_process("Hard Timeout Exceeded")
                break

            # 2. Process Check
            if self.process.poll() is not None:
                break

            # 3. Read Stream (Non-blocking-ish)
            try:
                line = self.process.stdout.readline()
                if line:
                    decoded_line = line.strip()
                    if decoded_line:
                        # --- A. PRUNING CHECK (From our Optimization discussion) ---
                        if self.trial and "[PRUNE]" in decoded_line:
                            self._handle_pruning(decoded_line)
                            if self.pruned: 
                                break

                        # --- B. ERROR CHECK (From your original code) ---
                        for keyword in self.FAILURE_KEYWORDS:
                            if keyword in decoded_line:
                                self.error_detected = True
                                self.error_message = decoded_line
                                self.kill_process(f"Keyword Detected: {keyword}")
                                return
            except Exception as e:
                pass # Stream might be closed

            time.sleep(0.01)

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