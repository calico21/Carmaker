# Auto-generated script for Trial 30
Log "=== OPTIMIZER: Starting Trial 30 ==="

set errorCode [catch {
    # Load test configuration
    LoadTestRun "output/Trial_30.testrun"
    
    # Set output file name
    SetResultFName "Trial_30"
    
    # Start simulation
    Log "Starting simulation..."
    StartSim
    
    # Wait for simulation to start (max 10s)
    if {[WaitForStatus running 10000] != 0} {
        error "Simulation failed to start"
    }
    
    # Wait for completion (max 120s)
    Log "Simulation running..."
    if {[WaitForStatus idle 120000] != 0} {
        error "Simulation timeout"
    }
    
    Log "Simulation completed successfully"
} errorMsg]

if {$errorCode != 0} {
    Log "ERROR: $errorMsg"
    Exit 1
}

Log "=== OPTIMIZER: Trial 30 finished ==="
Exit 0