import os
import shutil
import subprocess
import logging
import time
import glob
import re

class CarMakerInterface:
    def __init__(self):
        self.logger = logging.getLogger("CM_Interface")
        print("\n   [INFO] Loaded DIAGNOSTIC Interface (v8.0 - Humanized Driver & Soft Penalties)\n")
        
        self.CM_EXEC = r"C:\IPG\carmaker\win64-14.1\bin\CM_Office.exe"
        self.PROJECT_DIR = r"C:\Users\eracing\Desktop\CAR_MAKER\FS_race"
        self.TEMPLATE_TESTRUN = "Competition/FS_SkidPad"
        self.USER_FOLDER = "u2000873"

        if not os.path.exists(self.CM_EXEC):
            print(f"❌ [ERROR] CarMaker not found at: {self.CM_EXEC}")

    def kill_carmaker(self):
        targets = ['CM_Office.exe', 'Movie.exe', 'ipg-movie.exe', 'wish86.exe']
        for target in targets:
            try:
                subprocess.call(['taskkill', '/F', '/IM', target, '/T'], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass
        time.sleep(1.0)

    def run_test(self, vehicle_path, output_folder, trial_id):
        self.kill_carmaker() 
        
        target_vehicle = f"Optimized_Car_{trial_id}"
        testrun_name = f"Run_{trial_id}"
        
        # 1. Copy Vehicle
        try:
            vehicle_dir = os.path.join(self.PROJECT_DIR, "Data/Vehicle")
            os.makedirs(vehicle_dir, exist_ok=True)
            target_path = os.path.join(vehicle_dir, target_vehicle)
            shutil.copy(vehicle_path, target_path)
        except Exception as e:
            self.logger.error(f"Failed to copy vehicle: {e}")
            return {'status': 'Crash', 'lap_time': 999, 'distance': 0}

        # 2. Create TestRun with HUMANIZED DRIVER (Fix #3)
        #  "Humanización del Modelo de Conductor"
        template_file = os.path.join(self.PROJECT_DIR, "Data/TestRun", self.TEMPLATE_TESTRUN)
        if not os.path.exists(template_file) and os.path.exists(template_file + ".ts"):
            template_file += ".ts"
            
        testrun_path = os.path.join(self.PROJECT_DIR, "Data/TestRun", f"{testrun_name}.ts")
        
        with open(template_file, 'r', encoding='utf-8', errors='ignore') as f: 
            lines = f.readlines()
        
        modified_lines = []
        for line in lines:
            if line.strip().startswith("Vehicle ="):
                modified_lines.append(f"Vehicle = {target_vehicle}\n")
            elif "SaveConfig" in line:
                pass # Remove old save configs to overwrite below
            else:
                modified_lines.append(line)
        
        # Inject Driver Degradation & Output Config
        modified_lines.append("\n# --- OPTIMIZER INJECTIONS ---\n")
        modified_lines.append("SaveConfig.Enabled = 1\n")
        modified_lines.append("SaveConfig.Write.Enabled = 1\n")
        
        #  Transport Delay 150-200ms
        modified_lines.append("Driver.ReactTime = 0.18\n") 
        # [cite: 535] Neuromuscular Filter (approximate via steering damping/filter)
        modified_lines.append("DrivMan.Steer.Filter.G = 4.0\n") 
        
        with open(testrun_path, 'w', encoding='utf-8') as f:
            f.writelines(modified_lines)
                    
        # 3. Generate TCL Script (Headless Execution)
        tcl_path = os.path.join(self.PROJECT_DIR, "launch_sim.tcl")
        debug_log = os.path.join(self.PROJECT_DIR, "debug_tcl.txt").replace("\\", "/")
        
        tcl_content = f"""
set log_fd [open "{debug_log}" w]
puts $log_fd "Starting Trial {trial_id}"
LoadTestRun "{testrun_name}"
StartSim
WaitForStatus running 20000
WaitForStatus idle 90000
set simtime [erg::get Time]
set dist [erg::get Distance]
puts $log_fd "Simulation Time: $simtime"
puts $log_fd "Simulation Dist: $dist"
SaveResults
close $log_fd
Exit
"""
        with open(tcl_path, "w", encoding='utf-8') as f: 
            f.write(tcl_content)

        # 4. Launch CarMaker
        cmd = [self.CM_EXEC, self.PROJECT_DIR, "-cmd", f"source {{{tcl_path.replace(os.sep, '/')}}}"]
        
        try:
            sim_start_time = time.time()
            process = subprocess.Popen(cmd, cwd=self.PROJECT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Wait for result loop (simplified)
            timeout = 100
            while (time.time() - sim_start_time) < timeout:
                if process.poll() is not None: break
                
                # Check debug log for "Simulation Time" AND "Distance"
                res = self.extract_metrics_from_debug_log()
                if res:
                    self.kill_carmaker()
                    return res
                time.sleep(1)
            
            self.kill_carmaker()
            return {'status': 'Crash', 'lap_time': 999, 'distance': 0.0}

        except Exception:
            self.kill_carmaker()
            return {'status': 'Crash', 'lap_time': 999, 'distance': 0.0}

    def extract_metrics_from_debug_log(self):
        """Extract time AND distance for Soft Penalties"""
        debug_log = os.path.join(self.PROJECT_DIR, "debug_tcl.txt")
        if not os.path.exists(debug_log): return None
        
        time_val = None
        dist_val = None
        
        try:
            with open(debug_log, 'r') as f:
                content = f.read()
                
            m_time = re.search(r'Simulation Time:\s*(\d+\.?\d*)', content)
            m_dist = re.search(r'Simulation Dist:\s*(\d+\.?\d*)', content)
            
            if m_time: time_val = float(m_time.group(1))
            if m_dist: dist_val = float(m_dist.group(1))
            
            if time_val is not None and time_val > 1.0:
                # If distance is missing, assume 0
                return {'status': 'Complete', 'lap_time': time_val, 'distance': dist_val or 0.0}
        except: pass
        return None