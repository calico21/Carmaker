import os
import shutil
import subprocess
import pandas as pd
import logging
import time
import glob
import re

class CarMakerInterface:
    def __init__(self):
        self.logger = logging.getLogger("CM_Interface")
        
        # --- CONFIGURATION ---
        self.CM_EXEC = r"C:\IPG\carmaker\win64-14.1\bin\CM_Office.exe"
        self.CM_CONVERT = r"C:\IPG\carmaker\win64-14.1\bin\cmconvert.exe"
        self.PROJECT_DIR = r"C:\Users\eracing\Desktop\CAR_MAKER\FS_race"
        
        # Exact Name
        self.TESTRUN_NAME = "Competition/FS_SkidPad" 

    def find_latest_erg(self):
        """Scans for the newest .erg file in SimOutput."""
        # We try strict search first, then broad search
        search_path = os.path.join(self.PROJECT_DIR, "SimOutput", "**", "*.erg")
        files = glob.glob(search_path, recursive=True)
        if not files: return None
        return max(files, key=os.path.getmtime)

    def get_lap_time_from_log(self):
        """FALLBACK: Reads the text logs in Data/Log if the .erg file is missing."""
        log_dir = os.path.join(self.PROJECT_DIR, "Data", "Log")
        if not os.path.exists(log_dir): return None

        # Find newest log file (e.g., u2000873.log)
        log_files = glob.glob(os.path.join(log_dir, "*.log"))
        if not log_files: return None
        
        latest_log = max(log_files, key=os.path.getmtime)
        
        # Read the last few lines to find the 'SIM' entry
        try:
            with open(latest_log, 'r') as f:
                lines = f.readlines()
                
            # Read backwards
            for line in reversed(lines):
                # Format: SIM <ID> <User> <Project> <TestRun> <ExitCode> <LapTime> <TotalTime>
                # Example: SIM 1770118862 u2000873 eracing Competition/FS_Skidpad 0 27.018 253.199
                if line.startswith("SIM") and "Competition/FS_Skid" in line:
                    parts = line.split()
                    # We expect at least 8 columns. LapTime is usually 2nd from end.
                    if len(parts) >= 7:
                        try:
                            lap_time = float(parts[-2]) # Second to last is Lap Time
                            # Sanity check
                            if 4.0 < lap_time < 200.0:
                                self.logger.info(f"   -> Recovered Lap Time {lap_time}s from Log File!")
                                return lap_time
                        except:
                            continue
        except Exception as e:
            self.logger.warning(f"Could not parse log file: {e}")
            return None
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
            
            # Wait 45s for the 27s lap.
            WaitForStatus idle 45000
            """
            
            with open(tcl_file_path, "w") as f:
                f.write(tcl_content)

            # 3. LAUNCH PROCESS
            cmd = [
                self.CM_EXEC,
                ".", "-iconic", "-cmd", "source launch_sim.tcl" 
            ]
            
            self.logger.info(f"   -> Launching Sim Trial {trial_id} (Max 50s)...")
            
            process = subprocess.Popen(
                cmd, 
                cwd=self.PROJECT_DIR, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )

            # 4. WAIT AND KILL
            try:
                process.wait(timeout=50)
            except subprocess.TimeoutExpired:
                # Force kill if it's still open
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])

            # 5. RETRIEVE RESULTS (Dual Strategy)
            
            # Strategy A: The Log File (Fast & Reliable for LapTime)
            lap_time = self.get_lap_time_from_log()
            
            if lap_time:
                # We found the time in the logs! Success!
                return {'status': 'Complete', 'lap_time': lap_time, 'cones_hit': 0}

            # Strategy B: The .erg File (Fallback if log parsing fails)
            erg_file = self.find_latest_erg()
            
            if not erg_file:
                # Debugging: List what IS in the folder so we know for next time
                sim_out = os.path.join(self.PROJECT_DIR, "SimOutput")
                self.logger.error(f"❌ No .erg found. Contents of {sim_out}:")
                try:
                    for root, dirs, files in os.walk(sim_out):
                        for file in files:
                            self.logger.error(f"   - {os.path.join(root, file)}")
                except: pass
                
                return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

            # Check if file is fresh
            file_age = time.time() - os.path.getmtime(erg_file)
            if file_age > 120:
                self.logger.warning(f"⚠️ File is old ({int(file_age)}s).")
                return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

            # Convert
            csv_file = os.path.join(output_folder, "telemetry.csv")
            subprocess.run([self.CM_CONVERT, "-to", "csv", "-out", csv_file, erg_file], capture_output=True)

            if not os.path.exists(csv_file): 
                return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

            try:
                df = pd.read_csv(csv_file, skiprows=[1])
                lap_time = df['Time'].iloc[-1]
            except:
                try:
                    df = pd.read_csv(csv_file)
                    lap_time = df['Time'].iloc[-1]
                except:
                    return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

            if lap_time < 4.0: return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

            return {'status': 'Complete', 'lap_time': lap_time, 'cones_hit': 0}

        except Exception as e:
            self.logger.error(f"Interface Error: {e}")
            try:
                subprocess.call(['taskkill', '/F', '/IM', 'CM_Office.exe'])
            except:
                pass
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}