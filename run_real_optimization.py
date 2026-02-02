import logging
import argparse
import sys
import os

# --- CRITICAL FIX: Force UTF-8 Output on Windows ---
# This prevents the UnicodeEncodeError when printing emojis like 🚀 or 📂
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.orchestrator import Orchestrator

def setup_logging():
    """
    Configures a clean, table-like log format.
    """
    # Remove default handlers to reset format
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)
            
    logging.basicConfig(
        level=logging.INFO,
        # We remove timestamps/names for a cleaner 'Dashboard' look
        format='%(message)s', 
        handlers=[
            logging.FileHandler("optimization.log", encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    setup_logging()
    logger = logging.getLogger("Main")

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='dynamics', choices=['dynamics', 'kinematics'])
    parser.add_argument('--trials', type=int, default=50)
    parser.add_argument('--study_name', type=str, default='Titan_Campaign_001')
    args = parser.parse_args()

    # ASCII Art Header
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║                  FSAE SUSPENSION OPTIMIZER v6.0                    ║")
    print("╠════════════════════════════════════════════════════════════════════╣")
    print(f"║  CAMPAIGN: {args.study_name:<47} ║")
    print(f"║  MODE:     {args.mode.upper():<47} ║")
    print(f"║  TRIALS:   {args.trials:<47} ║")
    print("╚════════════════════════════════════════════════════════════════════╝\n")

    try:
        orchestrator = Orchestrator(study_name=args.study_name)
        orchestrator.set_mode(args.mode)
        
        # Run
        orchestrator.optimize(n_trials=args.trials)
        
    except KeyboardInterrupt:
        print("\n\n🛑 Optimization Aborted by User.")
    except Exception as e:
        logger.exception(f"Fatal Error: {e}")

if __name__ == "__main__":
    main()