"""
Test script to verify parameter injection is working correctly
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.parameter_manager import ParameterManager

# Test parameters from orchestrator
test_params = {
    "Spring_F": 35000,
    "Spring_R": 45000,
    "Damp_Bump_F": 2500,
    "Damp_Reb_F": 4000,
    "Damp_Bump_R": 2500,
    "Damp_Reb_R": 4000,
    "Stabilizer_F": 20000,
    "Stabilizer_R": 15000,
}

print("="*70)
print("PARAMETER INJECTION TEST")
print("="*70)

# Initialize parameter manager
pm = ParameterManager(template_path="templates/FSE_AllWheelDrive")

# Create test output
output_path = "test_vehicle_output.txt"

print(f"\nTemplate: templates/FSE_AllWheelDrive")
print(f"Output: {output_path}")
print(f"\nParameters to inject:")
for k, v in test_params.items():
    print(f"  {k}: {v}")

# Inject
success = pm.inject_parameters(output_path, test_params)

if success:
    print(f"\n✅ Injection successful!")
    print(f"\nChecking output file...")
    
    # Read and verify
    with open(output_path, 'r') as f:
        lines = f.readlines()
    
    # Look for our parameters
    found_params = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("SuspF.Spring"):
            found_params["Spring_F"] = line.strip()
        elif stripped.startswith("SuspR.Spring"):
            found_params["Spring_R"] = line.strip()
        elif stripped.startswith("SuspF.Stabi"):
            found_params["Stabilizer_F"] = line.strip()
        elif stripped.startswith("SuspR.Stabi"):
            found_params["Stabilizer_R"] = line.strip()
        elif stripped.startswith("SuspF.Damp_Push.Amplify"):
            found_params["Damp_Bump_F"] = line.strip()
        elif stripped.startswith("SuspF.Damp_Pull.Amplify"):
            found_params["Damp_Reb_F"] = line.strip()
    
    print("\nFound in output:")
    for k, v in found_params.items():
        print(f"  {k}: {v}")
    
    # Check for errors/invalid syntax
    print("\nChecking for common errors...")
    errors = []
    for i, line in enumerate(lines, 1):
        # Check for double = signs
        if "= =" in line:
            errors.append(f"Line {i}: Double equals sign: {line.strip()}")
        # Check for parameters without values
        if line.strip().endswith("="):
            errors.append(f"Line {i}: Missing value: {line.strip()}")
    
    if errors:
        print("⚠️  Found potential issues:")
        for err in errors:
            print(f"  {err}")
    else:
        print("✅ No syntax errors found")
    
    # Show last 20 lines (where appended params would be)
    print("\nLast 20 lines of file (checking for appended params):")
    for line in lines[-20:]:
        print(f"  {line.rstrip()}")
    
else:
    print("\n❌ Injection failed!")

print("\n" + "="*70)
print("TEST COMPLETE")
print("="*70)
print("\nNEXT STEPS:")
print("1. Review the output file: test_vehicle_output.txt")
print("2. Try loading it in CarMaker GUI to check for errors")
print("3. If it works in GUI, the problem is elsewhere")
