
# Open debug log
set log_fd [open "C:/Users/eracing/Desktop/CAR_MAKER/FS_race/debug_tcl.txt" w]
puts $log_fd "=== CarMaker Simulation Log ==="
puts $log_fd "TestRun: Run_0"
puts $log_fd "Trial: 0"
puts $log_fd "Timestamp: [clock format [clock seconds]]"
flush $log_fd

# Load TestRun
puts $log_fd "\nLoading TestRun: Run_0"
if { [catch {LoadTestRun "Run_0"} err] } {
    puts $log_fd "FATAL: LoadTestRun Failed: $err"
    close $log_fd
    Exit
}
puts $log_fd "TestRun loaded successfully"
flush $log_fd

# CRITICAL: Enable output explicitly via Tcl
puts $log_fd "\nConfiguring output..."
if { [catch {
    SaveCfgSet Write Enabled 1
    SaveCfgSet Enabled 1
} err] } {
    puts $log_fd "WARNING: Could not enable output: $err"
}

# Start Simulation
puts $log_fd "\nStarting Simulation..."
if { [catch {StartSim} err] } {
    puts $log_fd "FATAL: StartSim Failed: $err"
    close $log_fd
    Exit
}
flush $log_fd

# Wait for running state
puts $log_fd "Waiting for simulation to start..."
if { [catch {WaitForStatus running 20000} err] } {
    puts $log_fd "FATAL: Sim never reached 'running' state: $err"
    close $log_fd
    Exit
}
puts $log_fd "Simulation is now running"
flush $log_fd

# Wait for completion
puts $log_fd "\nWaiting for simulation to complete (max 90s)..."
set wait_result [catch {WaitForStatus idle 90000} err]
if { $wait_result != 0 } {
    puts $log_fd "WARNING: WaitForStatus returned error: $err"
}

# Get simulation results
set final_status [SimStatus]
puts $log_fd "Final SimStatus: $final_status"

# Get simulation time
if { [catch {
    set simtime [erg::get Time]
    puts $log_fd "Simulation Time: $simtime s"
} err] } {
    puts $log_fd "Could not get simulation time: $err"
}

# Get simulation directory
if { [catch {
    set simdir [erg::get SimDir]
    puts $log_fd "SimDir: $simdir"
} err] } {
    puts $log_fd "Could not get SimDir: $err"
}

# Save results explicitly
puts $log_fd "\nSaving results..."
if { [catch {SaveResults} err] } {
    puts $log_fd "WARNING: SaveResults failed: $err"
}

puts $log_fd "\n=== Simulation Complete ==="
close $log_fd
Exit
