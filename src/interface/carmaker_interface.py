import os
import shutil
import subprocess
import pandas as pd
import logging
import time
import glob

class CarMakerInterface:
    def __init__(self):
        self.logger = logging.getLogger("CM_Interface")
        
        # --- CONFIGURATION ---
        self.CM_EXEC = r"C:\IPG\carmaker\win64-14.1\bin\CM_Office.exe"
        self.CM_CONVERT = r"C:\IPG\carmaker\win64-14.1\bin\cmconvert.exe"
        self.PROJECT_DIR = r"C:\Users\eracing\Desktop\CAR_MAKER\FS_race"
        
        self.TESTRUN_NAME = "Competition/FS_SkidPad" 

    def get_lap_time_from_log(self):
        """
        Aggressively scans ALL log files to find the most recent completed simulation.
        """
        # 1. Get all log files in SimOutput
        search_path = os.path.join(self.PROJECT_DIR, "SimOutput", "**", "*.log")
        files = glob.glob(search_path, recursive=True)
        
        if not files:
            return None
            
        # 2. Sort files by modification time (Newest first)
        files.sort(key=os.path.getmtime, reverse=True)
        
        # 3. Check the first 5 newest files (to avoid reading thousands of old logs)
        for log_file in files[:5]:
            try:
                # Skip the config files or weird logs
                if "config" in log_file: continue

                with open(log_file, 'r') as f:
                    lines = f.readlines()
                
                # Read backwards to find the last "SIM" entry
                for line in reversed(lines):
                    if line.startswith("SIM"):
                        parts = line.split()
                        # Expected format: SIM <ID> <User> <Group> <TestRun> <ExitCode> <LapTime> <TotalTime>
                        # We need at least 7 parts
                        if len(parts) >= 7:
                            try:
                                # Lap Time is 2nd to last
                                lap_time = float(parts[-2])
                                
                                # Timestamps or ID check could be added here
                                # But for now, valid physics range is enough check
                                if 4.0 < lap_time < 200.0:
                                    self.logger.info(f"   -> Found Valid Time {lap_time}s in {os.path.basename(log_file)}")
                                    return lap_time
                            except:
                                continue
            except:
                continue
                
        return None

    def run_test(self, vehicle_path, output_folder, trial_id):
        target_vehicle_name = f"Optimized_Car_{trial_id}"
        
        try:
            # 1. Install Vehicle
            cm_vehicle_path = os.path.join(self.PROJECT_DIR, "Data", "Vehicle", target_vehicle_name)
            shutil.copy(vehicle_path, cm_vehicle_path)

            safe_testrun = self.TESTRUN_NAME.replace("\\", "/")
            safe_vehicle = target_vehicle_name 
            
            # 2. GENERATE TCL SCRIPT
            tcl_file_path = os.path.join(self.PROJECT_DIR, "launch_sim.tcl")
            
            tcl_content = f"""
            # CarMaker Automation Script for Trial {trial_id}
            
            Log "PYTHON: Waiting for GUI..."
            after 3000
            
            Log "PYTHON: Loading TestRun {safe_testrun}..."
            if {{ [catch {{LoadTestRun "{safe_testrun}"}} err] }} {{
                Log "PYTHON: Load Error $err"
            }}
            after 1000
            
            Log "PYTHON: Swapping Vehicle to {safe_vehicle}..."
            if {{ [catch {{TestRun:Set Vehicle "{safe_vehicle}"}} err] }} {{
                 Log "PYTHON: Vehicle Set Error: $err"
            }}
            
            Log "PYTHON: Starting Sim..."
            StartSim
            
            # Wait 45s for the ~27s lap.
            # We rely on the log file being written upon completion.
            WaitForStatus idle 45000
            """
            
            with open(tcl_file_path, "w") as f:
                f.write(tcl_content)

            # 3. LAUNCH PROCESS
            cmd = [
                self.CM_EXEC,
                ".", "-iconic", "-cmd", "source launch_sim.tcl" 
            ]
            
            self.logger.info(f"   -> Launching Sim Trial {trial_id} (Max 55s)...")
            
            process = subprocess.Popen(
                cmd, 
                cwd=self.PROJECT_DIR, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )

            # 4. WAIT AND KILL
            try:
                # Wait 55 seconds
                process.wait(timeout=55)
            except subprocess.TimeoutExpired:
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])

            # 5. RETRIEVE RESULTS
            # Give CarMaker 1s to flush logs to disk
            time.sleep(1)
            
            # A. Try Log File (Best Method)
            lap_time = self.get_lap_time_from_log()
            
            if lap_time:
                return {'status': 'Complete', 'lap_time': lap_time, 'cones_hit': 0}

            # B. Try ERG File (Fallback)
            search_path = os.path.join(self.PROJECT_DIR, "SimOutput", "**", "*.erg")
            erg_files = glob.glob(search_path, recursive=True)
            
            if erg_files:
                erg_file = max(erg_files, key=os.path.getmtime)
                
                # Check age (must be recent)
                if (time.time() - os.path.getmtime(erg_file)) < 120:
                    csv_file = os.path.join(output_folder, "telemetry.csv")
                    subprocess.run([self.CM_CONVERT, "-to", "csv", "-out", csv_file, erg_file], capture_output=True)
                    try:
                        df = pd.read_csv(csv_file, skiprows=[1])
                        lap_time = df['Time'].iloc[-1]
                        return {'status': 'Complete', 'lap_time': lap_time, 'cones_hit': 0}
                    except:
                        pass

            self.logger.error("❌ No Data Found in Logs or ERG files.")
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

        except Exception as e:
            self.logger.error(f"Interface Error: {e}")
            try:
                subprocess.call(['taskkill', '/F', '/IM', 'CM_Office.exe'])
            except:
                pass
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}