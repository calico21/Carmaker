import subprocess
import threading
import time
import os
import logging
from typing import Dict, Optional

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
    def __init__(self, process: subprocess.Popen, timeout: int, trial=None, sector_limits: Dict[str, float] = None):
        self.process = process
        self.timeout = timeout
        self.trial = trial
        self.sector_limits = sector_limits or {}  # e.g., {"Sector 1": 28.0}
        
        self.start_time = time.time()
        self.error_detected = False
        self.error_message = ""
        self.pruned = False 
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
        """
        # Ensure we can read line-by-line
        if self.process.stdout:
            self.process.stdout.reconfigure(line_buffering=True)
        
        while not self._stop_event.is_set():
            # Check if process is dead
            if self.process.poll() is not None:
                break

            # Non-blocking read loop is hard in Python without select() on Windows.
            # We rely on readline() with line buffering.
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
            except Exception:
                break
            
            # A. CRASH DETECTION
            for kw in self.FAILURE_KEYWORDS:
                if kw in line:
                    self.error_detected = True
                    self.error_message = kw
                    self.kill_process(f"Crash Detected: {kw}")
                    return

            # B. EFFICIENCY: DYNAMIC SECTOR PRUNING
            # We check if any defined sector limit is violated
            # Log format expected: "End of Sector 1: 29.5 s"
            if self.trial and self.sector_limits:
                for sector_name, limit in self.sector_limits.items():
                    if sector_name in line:
                        self._check_sector_time(line, limit)
                        if self.pruned: return

            # C. TIMEOUT CHECK
            if time.time() - self.start_time > self.timeout:
                self.timed_out = True
                self.kill_process("Timeout Reached")
                return

    def _check_sector_time(self, line: str, limit: float):
        """Parses the log line for time values."""
        try:
            words = line.split()
            for w in words:
                try:
                    time_val = float(w)
                    # Sanity check: Times are usually 0-1000s
                    if 0 < time_val < 1000:
                        if time_val > limit:
                            logger.warning(f"✂️ PRUNED: {line.strip()} (> {limit}s)")
                            self.pruned = True
                            # We report to Optuna so it knows the run was bad
                            self.trial.report(time_val, step=1) 
                            self.kill_process("Sector Time Limit Exceeded")
                            return
                except ValueError:
                    continue
        except Exception:
            pass

    def kill_process(self, reason: str):
        """Safely terminates the external binary."""
        logger.info(f"Terminating Simulation. Reason: {reason}")
        try:
            # Windows: Kill the whole process tree to catch child processes
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
        except Exception as e:
            logger.error(f"Failed to kill process: {e}")

    def stop(self):
        self._stop_event.set()


class CarMakerInterface:
    def __init__(self, executable_path: str, project_folder: str):
        self.exe_path = executable_path
        self.project_folder = project_folder
    
    def run_simulation(self, test_run_name: str, tcp_port: int, timeout_sec: int, trial=None, sector_limits: Dict[str, float] = None) -> Dict:
        """
        Launches CarMaker in headless mode.
        """
        cmd = [
            self.exe_path,
            "-batch",
            "-cmdport", str(tcp_port),
            "-d", self.project_folder,
            "-run", test_run_name
        ]

        logger.info(f"Starting: {test_run_name} (Port {tcp_port})")

        watchdog = None
        process = None

        try:
            # Use CREATE_NEW_PROCESS_GROUP for Windows safety (allows clean kills)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding='utf-8',
                errors='ignore',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP 
            )

            # Attach the Watchdog
            watchdog = SimulationWatchdog(process, timeout_sec, trial, sector_limits)
            monitor_thread = threading.Thread(target=watchdog.monitor)
            monitor_thread.start()

            # Wait for finish
            process.wait() 
            
            # Cleanup
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
                # CM sometimes returns non-zero on forced kill, check if we caused it
                if not (watchdog.pruned or watchdog.timed_out):
                    return {"status": "FAILED", "reason": f"Exit Code {process.returncode}"}

            return {"status": "SUCCESS", "run_id": test_run_name}

        except Exception as e:
            logger.error(f"Interface Error: {e}")
            if process:
                try: process.kill()
                except: pass
            return {"status": "ERROR", "reason": str(e)}