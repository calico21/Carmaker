
            # CarMaker Automation Script for Trial 2
            
            Log "PYTHON: Waiting for GUI..."
            after 3000
            
            Log "PYTHON: Loading TestRun Competition/FS_SkidPad..."
            if { [catch {LoadTestRun "Competition/FS_SkidPad"} err] } {
                Log "PYTHON: Load Error $err"
            }
            after 1000
            
            Log "PYTHON: Swapping Vehicle to Optimized_Car_2..."
            if { [catch {TestRun:Set Vehicle "Optimized_Car_2"} err] } {
                 Log "PYTHON: Vehicle Set Error: $err"
            }
            
            Log "PYTHON: Starting Sim..."
            StartSim
            
            # Wait 45s for the 27s lap.
            WaitForStatus idle 45000
            