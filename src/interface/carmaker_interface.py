import os
import time
import shutil
import subprocess
import pandas as pd
import logging

class CarMakerInterface:
    """
    Production Interface for IPG CarMaker.
    Runs simulations via the 'CM.exe' command line interface.
    """
    def __init__(self):
        self.logger = logging.getLogger("CM_Interface")
        
        # --- CONFIGURATION (UPDATE THESE PATHS!) ---
        # Path to your CarMaker executable
        # Example: "C:/IPG/carmaker/win64-11.0/bin/CM.exe"
        self.CM_EXEC = r"C:\IPG\carmaker\win64-11.0\bin\CM.exe"
        
        # Path to your CarMaker Project Directory
        self.PROJECT_DIR = r"C:\CarMaker_Projects\FSAE_2026"
        
        self.MAX_RETRIES = 2

    def run_test(self, vehicle_path, output_folder, trial_id):
        """
        1. Copies the 'vehicle_path' to the CarMaker Data directory.
        2. Runs the TestRun using CM.exe -batch.
        3. Moves the results (.erg/.csv) to 'output_folder'.
        """
        try:
            # 1. Install the Vehicle File
            # We copy the optimized vehicle file to the CarMaker 'Data/Vehicle' folder
            # so the TestRun can find it.
            target_vehicle_name = f"Optimized_Car_{trial_id}"
            cm_vehicle_path = os.path.join(self.PROJECT_DIR, "Data", "Vehicle", target_vehicle_name)
            
            # Ensure the vehicle file has no extension or correct extension based on your usage
            shutil.copy(vehicle_path, cm_vehicle_path)

            # 2. Run Simulation
            # We assume you have a Master TestRun that points to "Optimized_Car_XXX"
            # OR we modify the TestRun on the fly.
            # For simplicity, let's assume we modify the TestRun here or use a Tcl script.
            
            # Simple Approach: Pass parameters via Tcl args to a generic script
            cmd = [
                self.CM_EXEC,
                self.PROJECT_DIR,
                "-batch",
                "-tcl", 
                f"LoadTestRun MySkidpad; ParamSet Vehicle {target_vehicle_name}; StartSim; WaitForStatus running; WaitForStatus idle; Exit"
            ]
            
            self.logger.info(f"   -> Launching Sim Trial {trial_id}...")
            
            # Run the command (Timeout after 60s to prevent hangs)
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if process.returncode != 0:
                self.logger.warning(f"CM.exe exited with code {process.returncode}")
                # return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

            # 3. Harvest Results
            # CarMaker saves to SimOutput/<User>/<TestRunName>.erg usually.
            # We need to export that to CSV or read it directly.
            
            # NOTE: You need a tool to convert ERG to CSV (cmconvert) or use the ASCII output format.
            # Let's assume we configured CarMaker to output a .csv file in SimOutput.
            result_file = os.path.join(self.PROJECT_DIR, "SimOutput", os.getlogin(), "MySkidpad.csv")
            
            if not os.path.exists(result_file):
                self.logger.error("Simulation Output missing.")
                return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}
                
            # Move result to our trial folder
            shutil.move(result_file, os.path.join(output_folder, "telemetry.csv"))
            
            # 4. Parse CSV for Lap Time
            df = pd.read_csv(os.path.join(output_folder, "telemetry.csv"))
            
            # Example: Get the last value of 'Time' or a specific 'LapTime' channel
            # This depends entirely on your UAQ (User Accessible Quantities) setup
            lap_time = df['Time'].iloc[-1] 
            
            # Basic Validity Check
            if lap_time < 10.0: # Too short to be real
                 return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

            return {'status': 'Complete', 'lap_time': lap_time, 'cones_hit': 0}

        except subprocess.TimeoutExpired:
            self.logger.error("Simulation Timed Out!")
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}
        except Exception as e:
            self.logger.error(f"Sim Driver Failed: {e}")
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}