import subprocess
import threading
import time
import os
import signal
import logging
from typing import Optional, Dict, List

# Configure logging to track the "Black Box" behavior
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [INTERFACE] - %(message)s')
logger = logging.getLogger(__name__)

class SimulationWatchdog:
    """
    Responsibilities:
    1. Monitor stdout/stderr in real-time without blocking the main thread.
    2. Detect failure keywords (e.g., 'License Denied', 'Segfault').
    3. Enforce hard timeouts to prevent zombie processes.
    """
    def __init__(self, process: subprocess.Popen, timeout: int):
        self.process = process
        self.timeout = timeout
        self.start_time = time.time()
        self.error_detected = False
        self.error_message = ""
        self.timed_out = False
        self._stop_event = threading.Event()

        # Failure keywords derived from historical crash logs (as per design doc)
        self.FAILURE_KEYWORDS = [
            "License error",
            "Checkout failed",
            "Segmentation fault",
            "aborted",
            "FATAL ERROR"
        ]

    def monitor(self):
        """Runs in a background thread to intercept stream data."""
        while not self._stop_event.is_set():
            # Check for timeout
            elapsed = time.time() - self.start_time
            if elapsed > self.timeout:
                self.timed_out = True
                self.kill_process(reason="Hard Timeout Exceeded")
                break

            # Check if process is still running
            if self.process.poll() is not None:
                break

            # Read a line from stdout (non-blocking logic usually required here, 
            # but for simplicity we use readline in a thread)
            line = self.process.stdout.readline()
            if line:
                decoded_line = line.decode('utf-8', errors='ignore').strip()
                if decoded_line:
                    # Log specific simulation steps if needed
                    # logger.debug(f"Sim Output: {decoded_line}")
                    pass
                
                # Scan for failure keywords
                for keyword in self.FAILURE_KEYWORDS:
                    if keyword in decoded_line:
                        self.error_detected = True
                        self.error_message = decoded_line
                        self.kill_process(reason=f"Keyword Detected: {keyword}")
                        return
            time.sleep(0.1)

    def kill_process(self, reason: str):
        """Safely terminates the external binary."""
        logger.error(f"Terminating Simulation. Reason: {reason}")
        try:
            # Send SIGTERM first
            self.process.terminate()
            time.sleep(1)
            # Force SIGKILL if still alive
            if self.process.poll() is None:
                self.process.kill()
        except Exception as e:
            logger.error(f"Failed to kill process: {e}")

    def stop(self):
        """Stops the monitoring thread."""
        self._stop_event.set()


class CarMakerInterface:
    """
    The 'Service Layer' Interface.
    Encapsulates the complexity of CLI arguments, port management, 
    and the 'Ask-and-Tell' file handling.
    """
    def __init__(self, executable_path: str, project_folder: str):
        self.exe_path = executable_path
        self.project_folder = project_folder
    
    def _find_result_file(self, sim_output_dir: str) -> Optional[str]:
        """
        Robust file finder inspired by your previous code.
        Ignores .log files and finds the most recent binary result.
        """
        current_time = time.time()
        best_file = None
        
        if not os.path.exists(sim_output_dir):
            return None

        for filename in os.listdir(sim_output_dir):
            filepath = os.path.join(sim_output_dir, filename)
            
            # 1. Skip directories and .log files (Text logs are not results!)
            if not os.path.isfile(filepath): continue
            if filename.endswith(".log"): continue 
            if filename.endswith(".erg"): # We specifically want .erg or binary
                pass
            else:
                # Some CM versions produce files without extensions, check size
                pass

            # 2. Time Check (Must be recent)
            mtime = os.path.getmtime(filepath)
            if current_time - mtime > 60: # Older than 1 min = stale
                continue
                
            # 3. Size Check (Ignore empty placeholders)
            if os.path.getsize(filepath) < 1000: # < 1KB is suspicious
                continue
                
            best_file = filepath
            # We break on the first valid match, or you could sort by time
            break
            
        return best_file

    def run_simulation(self, 
                       test_run_name: str, 
                       tcp_port: int = 16660, 
                       timeout_sec: int = 300) -> Dict:
        """
        Executes a single simulation run in 'Batch Mode'.
        """
        
        # 1. Command Construction (The 'Black Box' Input)
        # -batch: Suppresses GUI (Headless)
        # -cmdport: Assigns unique port to avoid parallel collisions
        # -apphost: Start locally
        cmd = [
            self.exe_path,
            "-batch",
            "-cmdport", str(tcp_port),
            "-d", self.project_folder, # Set working directory
            "-run", test_run_name
        ]

        logger.info(f"Starting Simulation: {test_run_name} on Port {tcp_port}")

        try:
            # 2. Subprocess Execution
            # stderr is redirected to stdout to catch all logs in one stream
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP # Windows specific: isolate process
            )

            # 3. Attach Watchdog
            watchdog = SimulationWatchdog(process, timeout_sec)
            monitor_thread = threading.Thread(target=watchdog.monitor)
            monitor_thread.start()

            # 4. Wait for completion
            process.wait() 
            watchdog.stop()
            monitor_thread.join()

            # 5. Determine Result Status
            if watchdog.timed_out:
                return {"status": "FAILED", "reason": "Timeout", "cost": float('inf')}
            
            if watchdog.error_detected:
                return {"status": "FAILED", "reason": watchdog.error_message, "cost": float('inf')}

            if process.returncode != 0:
                return {"status": "FAILED", "reason": f"Non-zero exit code: {process.returncode}", "cost": float('inf')}

            logger.info("Simulation finished successfully.")
            return {"status": "SUCCESS", "run_id": test_run_name}

        except Exception as e:
            logger.error(f"Critical Interface Error: {e}")
            return {"status": "ERROR", "reason": str(e)}

# --- Usage Example (Mock) ---
if __name__ == "__main__":
    # Mocking paths for demonstration
    cm_interface = CarMakerInterface(
        executable_path=r"C:\IPG\CarMaker_win64.exe",
        project_folder=r"C:\CM_Projects\Optimization_v1"
    )
    
    # This would be called by the 'Core' orchestrator
    result = cm_interface.run_simulation("TestRun_001_Optimized", tcp_port=16665)
    print(result)