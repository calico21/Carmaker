"""
CarMaker Output Detective - Find where results are being saved
"""
import os
import glob
import time
from datetime import datetime

PROJECT_DIR = r"C:\Users\eracing\Desktop\CAR_MAKER\FS_race"

print("=" * 70)
print("CARMAKER OUTPUT DETECTIVE")
print("=" * 70)

# 1. Check if SimOutput folder exists
simoutput_path = os.path.join(PROJECT_DIR, "SimOutput")
print(f"\n1. Checking SimOutput folder: {simoutput_path}")
if os.path.exists(simoutput_path):
    print("   ✅ Folder exists")
    
    # List all subdirectories
    subdirs = [d for d in os.listdir(simoutput_path) if os.path.isdir(os.path.join(simoutput_path, d))]
    print(f"   📁 Found {len(subdirs)} subdirectories:")
    for subdir in subdirs[:10]:  # Show first 10
        print(f"      - {subdir}")
else:
    print("   ❌ Folder does NOT exist!")

# 2. Search for ALL log files created in last 10 minutes
print("\n2. Searching for recent .log files (last 10 min)...")
search_patterns = [
    os.path.join(PROJECT_DIR, "SimOutput", "**", "*.log"),
    os.path.join(PROJECT_DIR, "**", "*.log"),
]

recent_files = []
ten_min_ago = time.time() - 600

for pattern in search_patterns:
    files = glob.glob(pattern, recursive=True)
    for f in files:
        if os.path.getmtime(f) > ten_min_ago:
            recent_files.append(f)

if recent_files:
    print(f"   ✅ Found {len(recent_files)} recent log files:")
    for f in recent_files[:5]:  # Show first 5
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        size = os.path.getsize(f)
        print(f"      - {f}")
        print(f"        Modified: {mtime}, Size: {size} bytes")
else:
    print("   ❌ No recent .log files found!")

# 3. Search for ANY recent files (txt, dat, erg, etc.)
print("\n3. Searching for ANY recent output files...")
extensions = ['*.txt', '*.dat', '*.erg', '*.csv', '*.mat']
all_recent = []

for ext in extensions:
    pattern = os.path.join(PROJECT_DIR, "SimOutput", "**", ext)
    files = glob.glob(pattern, recursive=True)
    for f in files:
        if os.path.getmtime(f) > ten_min_ago:
            all_recent.append((f, ext))

if all_recent:
    print(f"   ✅ Found {len(all_recent)} recent files:")
    for f, ext in all_recent[:10]:
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        size = os.path.getsize(f)
        rel_path = os.path.relpath(f, PROJECT_DIR)
        print(f"      - {rel_path}")
        print(f"        Type: {ext}, Modified: {mtime}, Size: {size} bytes")
else:
    print("   ❌ No recent output files found!")

# 4. Check if there's a TestRun-specific folder
print("\n4. Checking for TestRun folders...")
testrun_patterns = [
    os.path.join(PROJECT_DIR, "SimOutput", "Run_0*"),
    os.path.join(PROJECT_DIR, "SimOutput", "Optimized_Car_0*"),
]

for pattern in testrun_patterns:
    matches = glob.glob(pattern)
    if matches:
        print(f"   ✅ Found matching folders: {pattern}")
        for m in matches[:3]:
            print(f"      - {m}")

# 5. Show a sample log file if found
print("\n5. Sample log file content:")
if recent_files:
    sample_file = recent_files[0]
    print(f"   Reading: {sample_file}")
    print("   " + "-" * 60)
    try:
        with open(sample_file, 'r', errors='ignore') as f:
            lines = f.readlines()
            # Show first 20 lines
            for line in lines[:20]:
                print(f"   {line.rstrip()}")
            if len(lines) > 20:
                print(f"   ... ({len(lines) - 20} more lines)")
    except Exception as e:
        print(f"   ❌ Error reading file: {e}")

# 6. Check debug_tcl.txt
print("\n6. Checking debug_tcl.txt...")
debug_tcl = os.path.join(PROJECT_DIR, "debug_tcl.txt")
if os.path.exists(debug_tcl):
    print(f"   ✅ Found: {debug_tcl}")
    with open(debug_tcl, 'r') as f:
        print("   " + "-" * 60)
        print(f.read())
else:
    print("   ❌ Not found")

print("\n" + "=" * 70)
print("DETECTIVE WORK COMPLETE")
print("=" * 70)
print("\n📋 NEXT STEPS:")
print("1. Run your optimizer once: python run_real_optimization.py --trials 1")
print("2. Then run: python find_outputs.py")
print("3. Look for the pattern of where files are saved")
print("4. Update check_result_file() accordingly")
