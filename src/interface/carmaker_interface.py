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
        print("\n   [INFO] Loaded DIAGNOSTIC Interface (v7.4 - Output Config Fix)\n")
        
        # --- CONFIGURATION: DOUBLE CHECK THESE! ---
        self.CM_EXEC = r"C:\IPG\carmaker\win64-14.1\bin\CM_Office.exe"
        self.PROJECT_DIR = r"C:\Users\eracing\Desktop\CAR_MAKER\FS_race"
        self.TEMPLATE_TESTRUN = "Competition/FS_SkidPad"
        self.USER_FOLDER = "u2000873"

        if not os.path.exists(self.CM_EXEC):
            print(f"❌ [ERROR] CarMaker not found at: {self.CM_EXEC}")
        if not os.path.exists(self.PROJECT_DIR):
            print(f"❌ [ERROR] Project not found at: {self.PROJECT_DIR}")

    def kill_carmaker(self):
        """Aggressive kill to remove ghost processes."""
        targets = ['CM_Office.exe', 'Movie.exe', 'ipg-movie.exe', 'wish86.exe']
        for target in targets:
            try:
                subprocess.call(['taskkill', '/F', '/IM', target, '/T'], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass
        time.sleep(2.0)

    def run_test(self, vehicle_path, output_folder, trial_id):
        self.kill_carmaker() 
        
        target_vehicle = f"Optimized_Car_{trial_id}"
        testrun_name = f"Run_{trial_id}"
        
        # Copy Vehicle
        try:
            vehicle_dir = os.path.join(self.PROJECT_DIR, "Data/Vehicle")
            os.makedirs(vehicle_dir, exist_ok=True)
            target_path = os.path.join(vehicle_dir, target_vehicle)
            shutil.copy(vehicle_path, target_path)
            self.logger.info(f"   -> Copied vehicle")
        except Exception as e:
            self.logger.error(f"Failed to copy vehicle: {e}")
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

        # Create TestRun with OUTPUT CONFIGURATION
        template_file = os.path.join(self.PROJECT_DIR, "Data/TestRun", self.TEMPLATE_TESTRUN)
        if not os.path.exists(template_file) and os.path.exists(template_file + ".ts"):
            template_file += ".ts"
            
        if not os.path.exists(template_file):
            self.logger.error(f"Template not found: {template_file}")
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

        # Read template and modify
        testrun_dir = os.path.join(self.PROJECT_DIR, "Data/TestRun")
        os.makedirs(testrun_dir, exist_ok=True)
        testrun_path = os.path.join(testrun_dir, f"{testrun_name}.ts")
        
        with open(template_file, 'r', encoding='utf-8', errors='ignore') as f: 
            lines = f.readlines()
        
        # Ensure output is enabled
        modified_lines = []
        found_saveconfig = False
        
        for line in lines:
            # Replace vehicle
            if line.strip().startswith("Vehicle ="):
                modified_lines.append(f"Vehicle = {target_vehicle}\n")
            # Ensure log output is enabled
            elif "SaveConfig" in line and "Write" in line:
                modified_lines.append("SaveConfig.Write.Enabled = 1\n")
                found_saveconfig = True
            elif "SaveConfig" in line and "Enabled" in line:
                modified_lines.append("SaveConfig.Enabled = 1\n")
                found_saveconfig = True
            else:
                modified_lines.append(line)
        
        # If no SaveConfig found, add it
        if not found_saveconfig:
            modified_lines.append("\n## Output Configuration (Added by Optimizer)\n")
            modified_lines.append("SaveConfig.Enabled = 1\n")
            modified_lines.append("SaveConfig.Write.Enabled = 1\n")
        
        with open(testrun_path, 'w', encoding='utf-8') as f:
            f.writelines(modified_lines)
        
        self.logger.info(f"   -> Created TestRun with output enabled")
                    
        # Generate enhanced Tcl Script
        tcl_path = os.path.join(self.PROJECT_DIR, "launch_sim.tcl")
        debug_log = os.path.join(self.PROJECT_DIR, "debug_tcl.txt").replace("\\", "/")
        
        tcl_content = f"""
# Open debug log
set log_fd [open "{debug_log}" w]
puts $log_fd "=== CarMaker Simulation Log ==="
puts $log_fd "TestRun: {testrun_name}"
puts $log_fd "Trial: {trial_id}"
puts $log_fd "Timestamp: [clock format [clock seconds]]"
flush $log_fd

# Load TestRun
puts $log_fd "\\nLoading TestRun: {testrun_name}"
if {{ [catch {{LoadTestRun "{testrun_name}"}} err] }} {{
    puts $log_fd "FATAL: LoadTestRun Failed: $err"
    close $log_fd
    Exit
}}
puts $log_fd "TestRun loaded successfully"
flush $log_fd

# CRITICAL: Enable output explicitly via Tcl
puts $log_fd "\\nConfiguring output..."
if {{ [catch {{
    SaveCfgSet Write Enabled 1
    SaveCfgSet Enabled 1
}} err] }} {{
    puts $log_fd "WARNING: Could not enable output: $err"
}}

# Start Simulation
puts $log_fd "\\nStarting Simulation..."
if {{ [catch {{StartSim}} err] }} {{
    puts $log_fd "FATAL: StartSim Failed: $err"
    close $log_fd
    Exit
}}
flush $log_fd

# Wait for running state
puts $log_fd "Waiting for simulation to start..."
if {{ [catch {{WaitForStatus running 20000}} err] }} {{
    puts $log_fd "FATAL: Sim never reached 'running' state: $err"
    close $log_fd
    Exit
}}
puts $log_fd "Simulation is now running"
flush $log_fd

# Wait for completion
puts $log_fd "\\nWaiting for simulation to complete (max 90s)..."
set wait_result [catch {{WaitForStatus idle 90000}} err]
if {{ $wait_result != 0 }} {{
    puts $log_fd "WARNING: WaitForStatus returned error: $err"
}}

# Get simulation results
set final_status [SimStatus]
puts $log_fd "Final SimStatus: $final_status"

# Get simulation time
if {{ [catch {{
    set simtime [erg::get Time]
    puts $log_fd "Simulation Time: $simtime s"
}} err] }} {{
    puts $log_fd "Could not get simulation time: $err"
}}

# Get simulation directory
if {{ [catch {{
    set simdir [erg::get SimDir]
    puts $log_fd "SimDir: $simdir"
}} err] }} {{
    puts $log_fd "Could not get SimDir: $err"
}}

# Save results explicitly
puts $log_fd "\\nSaving results..."
if {{ [catch {{SaveResults}} err] }} {{
    puts $log_fd "WARNING: SaveResults failed: $err"
}}

puts $log_fd "\\n=== Simulation Complete ==="
close $log_fd
Exit
"""
        with open(tcl_path, "w", encoding='utf-8') as f: 
            f.write(tcl_content)
        
        self.logger.info(f"   -> Created TCL script")

        # Launch CarMaker
        cmd = [self.CM_EXEC, self.PROJECT_DIR, "-cmd", f"source {{{tcl_path.replace(os.sep, '/')}}}"]
        
        self.logger.info(f"   -> Launching Trial {trial_id}...")
        
        stdout_log = os.path.join(self.PROJECT_DIR, f"stdout_{trial_id}.txt")
        stderr_log = os.path.join(self.PROJECT_DIR, f"stderr_{trial_id}.txt")
        
        try:
            sim_start_time = time.time()
            
            with open(stdout_log, 'w') as out_f, open(stderr_log, 'w') as err_f:
                process = subprocess.Popen(
                    cmd, 
                    cwd=self.PROJECT_DIR,
                    stdout=out_f,
                    stderr=err_f,
                    text=True
                )
            
            last_progress = sim_start_time
            timeout = 100
            
            while (time.time() - sim_start_time) < timeout:
                poll_result = process.poll()
                if poll_result is not None:
                    self.logger.info(f"   -> Process exited with code {poll_result}")
                    time.sleep(2)
                    break
                
                # Check for results
                res = self.check_result_in_user_folder(sim_start_time)
                if res: 
                    self.logger.info(f"   -> ✅ Result found: {res:.3f}s")
                    self.kill_carmaker()
                    return {'status': 'Complete', 'lap_time': res, 'cones_hit': 0}
                
                # Also check debug log for simulation time
                debug_result = self.extract_time_from_debug_log()
                if debug_result:
                    self.logger.info(f"   -> ✅ Result from debug log: {debug_result:.3f}s")
                    self.kill_carmaker()
                    return {'status': 'Complete', 'lap_time': debug_result, 'cones_hit': 0}
                
                current_time = time.time()
                if current_time - last_progress > 10:
                    elapsed = int(current_time - sim_start_time)
                    self.logger.info(f"   -> ⏳ Running... ({elapsed}s elapsed)")
                    last_progress = current_time
                
                time.sleep(1)

            # Final checks
            self.logger.info(f"   -> Performing final result scan...")
            time.sleep(2)
            
            res = self.check_result_in_user_folder(sim_start_time)
            if res:
                self.logger.info(f"   -> ✅ Result found: {res:.3f}s")
                self.kill_carmaker()
                return {'status': 'Complete', 'lap_time': res, 'cones_hit': 0}
            
            # Try debug log
            debug_result = self.extract_time_from_debug_log()
            if debug_result:
                self.logger.info(f"   -> ✅ Result from debug log: {debug_result:.3f}s")
                self.kill_carmaker()
                return {'status': 'Complete', 'lap_time': debug_result, 'cones_hit': 0}
            
            # No results - diagnostics
            self._print_diagnostics(sim_start_time, stderr_log)
            
            self.kill_carmaker()
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}

        except Exception as e:
            self.logger.error(f"Execution Error: {e}")
            import traceback
            traceback.print_exc()
            return {'status': 'Crash', 'lap_time': 999, 'cones_hit': 0}
        finally:
            try:
                if os.path.exists(stdout_log): os.remove(stdout_log)
                if os.path.exists(stderr_log): os.remove(stderr_log)
            except: pass

    def extract_time_from_debug_log(self):
        """Extract simulation time directly from debug log"""
        debug_log = os.path.join(self.PROJECT_DIR, "debug_tcl.txt")
        if not os.path.exists(debug_log):
            return None
        
        try:
            with open(debug_log, 'r') as f:
                content = f.read()
                # Look for "Simulation Time: XX.XX s"
                match = re.search(r'Simulation Time:\s*(\d+\.?\d*)', content)
                if match:
                    t = float(match.group(1))
                    if 3.0 < t < 100.0:
                        return t
        except:
            pass
        return None

    def check_result_in_user_folder(self, start_time):
        """Check for results in user folder"""
        # User folder log files
        log_pattern = os.path.join(self.PROJECT_DIR, "SimOutput", self.USER_FOLDER, "Log", "*.log")
        log_files = glob.glob(log_pattern)
        
        for log_file in sorted(log_files, key=os.path.getmtime, reverse=True):
            if os.path.getmtime(log_file) > start_time:
                result = self._parse_carmaker_log(log_file)
                if result:
                    return result
        
        # Main user log
        main_log = os.path.join(self.PROJECT_DIR, "SimOutput", f"{self.USER_FOLDER}.log")
        if os.path.exists(main_log) and os.path.getmtime(main_log) > start_time:
            result = self._parse_carmaker_log(main_log)
            if result:
                return result
        
        return None

    def _parse_carmaker_log(self, filepath):
        """Parse CarMaker log files for lap time"""
        try:
            with open(filepath, 'r', errors='ignore') as f:
                lines = f.readlines()
                
            # Look for SIM lines
            for line in reversed(lines[-100:]):
                if line.strip().startswith('SIM'):
                    parts = line.split()
                    if len(parts) >= 6:
                        try:
                            lap_time = float(parts[-2])
                            if 3.0 < lap_time < 100.0:
                                return lap_time
                        except (ValueError, IndexError):
                            continue
                
                # Alternative patterns
                if 'Time' in line or 'Lap' in line:
                    numbers = re.findall(r'\d+\.\d+', line)
                    for num_str in numbers:
                        try:
                            t = float(num_str)
                            if 3.0 < t < 100.0:
                                return t
                        except:
                            continue
        except Exception as e:
            self.logger.debug(f"Error parsing {filepath}: {e}")
        
        return None

    def _print_diagnostics(self, start_time, stderr_log):
        """Enhanced diagnostics"""
        print("\n" + "="*70)
        print("❌ SIMULATION DIAGNOSTICS")
        print("="*70)
        
        # Check stderr
        if os.path.exists(stderr_log):
            with open(stderr_log, 'r') as f:
                stderr_content = f.read().strip()
                if stderr_content:
                    print(f"\n[System Error]:")
                    print(stderr_content)
        
        # Check TCL debug log
        debug_log = os.path.join(self.PROJECT_DIR, "debug_tcl.txt")
        if os.path.exists(debug_log):
            print(f"\n[TCL Debug Log]:")
            with open(debug_log, 'r') as f:
                content = f.read()
                print(content)
                
                # Highlight if SimDir is wrong
                if "SimDir: 0.0" in content:
                    print("\n⚠️  CRITICAL: SimDir returned 0.0 instead of a path!")
                    print("   This means ERG data is not being saved properly.")
                    print("   Possible causes:")
                    print("   - TestRun has no Road/Track defined")
                    print("   - SimOutput folder permissions issue")
                    print("   - CarMaker configuration error")
        
        # Show recent log files
        print(f"\n[Recent Log Files in User Folder]:")
        log_pattern = os.path.join(self.PROJECT_DIR, "SimOutput", self.USER_FOLDER, "Log", "*.log")
        log_files = glob.glob(log_pattern)
        
        recent_logs = [f for f in log_files if os.path.getmtime(f) > start_time]
        
        if recent_logs:
            print(f"Found {len(recent_logs)} log files created during simulation:")
            for log_file in sorted(recent_logs, key=os.path.getmtime, reverse=True)[:5]:
                size = os.path.getsize(log_file)
                mtime = time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(log_file)))
                print(f"  - {os.path.basename(log_file)} ({size} bytes, {mtime})")
                
                with open(log_file, 'r', errors='ignore') as f:
                    lines = f.readlines()[:10]
                    if lines:
                        print("    Content preview:")
                        for line in lines:
                            print(f"      {line.rstrip()}")
        else:
            print("  No new log files created!")
            print("  ⚠️  This suggests the simulation didn't actually run or crashed immediately.")
        
        # Check main log
        print(f"\n[Main Log File]:")
        main_log = os.path.join(self.PROJECT_DIR, "SimOutput", f"{self.USER_FOLDER}.log")
        if os.path.exists(main_log):
            mtime = os.path.getmtime(main_log)
            if mtime > start_time:
                print(f"  ✅ {self.USER_FOLDER}.log was updated")
                with open(main_log, 'r', errors='ignore') as f:
                    lines = f.readlines()
                    print(f"  Last 10 lines:")
                    for line in lines[-10:]:
                        print(f"    {line.rstrip()}")
            else:
                print(f"  ⚠️  {self.USER_FOLDER}.log was NOT updated during simulation")
        
        print("="*70)
        print("\n💡 RECOMMENDATION:")
        print("   Try running the TestRun manually in CarMaker GUI to see if it works.")
        print("   Load: Data/TestRun/Run_0.ts")
        print("   Vehicle: Data/Vehicle/Optimized_Car_0")
