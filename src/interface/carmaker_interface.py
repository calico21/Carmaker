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
        print("\n   [INFO] Loaded EXTENSION FIX Interface (Adds .ts)\n")
        
        # --- CONFIGURATION ---
        self.CM_EXEC = r"C:\IPG\carmaker\win64-14.1\bin\CM_Office.exe"
        self.CM_CONVERT = r"C:\IPG\carmaker\win64-14.1\bin\cmconvert.exe"
        self.PROJECT_DIR = r"C:\Users\eracing\Desktop\CAR_MAKER\FS_race"
        self.TEMPLATE_TESTRUN = "Competition/FS_SkidPad" 

    def kill_carmaker(self):
        """Forcefully kills CarMaker."""
        try:
            subprocess.call(['taskkill', '/F', '/IM', 'CM_Office.exe', '/T'], 
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)
        except: pass

    def cleanup_logs(self):
        debug_log = os.path.join(self.PROJECT_DIR, "debug_tcl.txt")
        if os.path.exists(debug_log):
            try: os.remove(debug_log)
            except: pass

    def create_trial_testrun(self, trial_id, vehicle_name):
        template_path = os.path.join(self.PROJECT_DIR, "Data", "TestRun", self.TEMPLATE_TESTRUN)
        
        # Handle missing extension in template path lookup
        if not os.path.exists(template_path):
            if os.path.exists(template_path + ".ts"): template_path += ".ts"
            elif os.path.exists(template_path + ".testrun"): template_path += ".testrun"
            else:
                self.logger.error(f"❌ Template not found: {template_path}")
                return None

        with open(template_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        new_lines = []
        vehicle_set = False
        for line in lines:
            if line.strip().startswith("Vehicle ="):
                new_lines.append(f"Vehicle = {vehicle_name}\n")
                vehicle_set = True
            else:
                new_lines.append(line)
        
        if not vehicle_set: new_lines.append(f"Vehicle = {vehicle_name}\n")

        # --- FIX: ADD .ts EXTENSION ---
        # We save as "Run_XX.ts" so CarMaker recognizes it
        testrun_name = f"Run_{trial_id}"
        filename_on_disk = f"{testrun_name}.ts"
        
        new_path = os.path.join(self.PROJECT_DIR, "Data", "TestRun", filename_on_disk)
        
        with open(new_path, 'w', encoding='utf-8', newline='\r\n') as f:
            f.writelines(new_lines)
            
        return testrun_name # Return name WITHOUT extension for the Tcl command

    def check_for_result(self, trial_start_time):
        search_path = os.path.join(self.PROJECT_DIR, "SimOutput", "**", "*.log")
        files = glob.glob(search_path, recursive=True)
        if not files: return None
        
        files.sort(key=os.path.getmtime, reverse=True)
        
        for log_file in files[:5]: 
            if os.path.getmtime(log_file) < trial_start_time: continue

            try:
                if "config" in log_file: continue
                with open(log_file, 'r', errors='ignore') as f:
                    lines = f.readlines()
                
                for line in reversed(lines):
                    if line.startswith("SIM"):
                        parts = line.split()
                        if len(parts) >= 7:
                            try:
                                lap_time = float(parts[-2])
                                if 4.0 < lap_time < 200.0:
                                    return lap_time
                            except: continue
            except: continue
        return None

    def run_test(self, vehicle_path, output_folder, trial_id):
        target_vehicle_name = f"Optimized_Car_{trial_id}"
        
        # 1. Clean Start
        self.kill_carmaker() 
        self.cleanup_logs()
        
        try:
            # 2. Setup Files
            cm_vehicle_path = os.path.join(self.PROJECT_DIR, "Data", "Vehicle", target_vehicle_name)
            shutil.copy(vehicle_path, cm_vehicle_path)

            testrun_name = self.create_trial_testrun(trial_id, target_vehicle_name)
            if not testrun_name: return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

            trial_start_time = time.time()

            # 3. Create Tcl Script
            tcl_file_path = os.path.join(self.PROJECT_DIR, "launch_sim.tcl")
            debug_log = os.path.join(self.PROJECT_DIR, "debug_tcl.txt").replace("\\", "/")
            
            tcl_content = f"""
            set log_fd [open "{debug_log}" w]
            puts $log_fd "Step 1: Init"
            flush $log_fd

            after 2000
            
            # Discard any current testrun to ensure clean load
            catch {{Project::Discard}}
            
            puts $log_fd "Step 2: Loading {testrun_name}"
            flush $log_fd
            
            # CarMaker adds the extension automatically
            if {{ [catch {{LoadTestRun "{testrun_name}"}} err] }} {{
                puts $log_fd "FATAL: LoadTestRun Failed: $err"
                close $log_fd; Exit
            }}
            
            puts $log_fd "Step 3: StartSim"
            flush $log_fd
            StartSim
            
            puts $log_fd "Step 4: Running..."
            flush $log_fd
            
            WaitForStatus idle 60000
            
            puts $log_fd "Step 5: Done."
            close $log_fd
            Exit
            """
            
            with open(tcl_file_path, "w") as f:
                f.write(tcl_content)

            # 4. Launch CarMaker (Non-Blocking)
            safe_tcl_path = tcl_file_path.replace("\\", "/")
            cmd = [
                self.CM_EXEC,
                self.PROJECT_DIR, 
                "-cmd", 
                f"source {{{safe_tcl_path}}}" 
            ]
            
            self.logger.info(f"   -> Launching Sim Trial {trial_id}...")
            
            process = subprocess.Popen(
                cmd, 
                cwd=self.PROJECT_DIR, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )

            # 5. ACTIVE HUNTER LOOP
            timeout = 60 
            start_wait = time.time()
            result_found = None
            
            while (time.time() - start_wait) < timeout:
                if process.poll() is not None: break 
                
                lap_time = self.check_for_result(trial_start_time)
                if lap_time:
                    result_found = lap_time
                    self.logger.info(f"   -> ✅ Results found ({lap_time}s). Terminating CarMaker...")
                    break
                
                if (time.time() - start_wait) > 5 and os.path.exists("debug_tcl.txt"):
                     with open("debug_tcl.txt", 'r') as f:
                         content = f.read()
                         if "FATAL" in content:
                             self.logger.error("   -> Tcl Script reported FATAL error.")
                             break

                time.sleep(1) 

            # 6. Cleanup & Return
            self.kill_carmaker() 
            
            if result_found:
                return {'status': 'Complete', 'lap_time': result_found, 'cones_hit': 0}

            self.logger.error("❌ Timed out or Crashed without results.")
            if os.path.exists("debug_tcl.txt"):
                with open("debug_tcl.txt", "r") as f:
                    print(f"   [Debug Trace]:\n{f.read().strip()}")

            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

        except Exception as e:
            self.logger.error(f"Interface Error: {e}")
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}
        
        finally:
            self.kill_carmaker()

            