
            set log_fd [open "C:/Users/eracing/Desktop/CAR_MAKER/FS_race/debug_tcl.txt" w]
            puts $log_fd "Step 1: Init"
            flush $log_fd

            after 2000
            
            # Discard any current testrun to ensure clean load
            catch {Project::Discard}
            
            puts $log_fd "Step 2: Loading Run_1"
            flush $log_fd
            
            # CarMaker adds the extension automatically
            if { [catch {LoadTestRun "Run_1"} err] } {
                puts $log_fd "FATAL: LoadTestRun Failed: $err"
                close $log_fd; Exit
            }
            
            puts $log_fd "Step 3: StartSim"
            flush $log_fd
            StartSim
            
            puts $log_fd "Step 4: Running..."
            flush $log_fd
            
            WaitForStatus idle 60000
            
            puts $log_fd "Step 5: Done."
            close $log_fd
            Exit
            