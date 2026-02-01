import os
import shutil
import logging
import re
from typing import Dict

logger = logging.getLogger(__name__)

class ParameterManager:
    """
    Responsibilities:
    1. Read the 'Master' TestRun/InfoFile template.
    2. Inject optimization parameters (Vector x) into the text.
    3. Generate a unique, temporary TestRun file for the simulation.
    4. [Gen 2.0] Inject Driver Limitations (Delay/Filtering).
    """
    def __init__(self, template_dir: str, work_dir: str):
        self.template_dir = template_dir
        self.work_dir = work_dir

    def create_run_configuration(self, run_id: str, params: Dict[str, float], template_name: str) -> str:
        """
        Creates a new TestRun file with specific parameters.
        Returns: The name of the new TestRun file (without extension).
        """
        template_path = os.path.join(self.template_dir, template_name)
        new_run_name = f"{run_id}"
        new_run_path = os.path.join(self.work_dir, "Data", "TestRun", new_run_name) # CM standard path

        try:
            with open(template_path, 'r') as f:
                content = f.read()

            # --- GEN 2.0: DRIVER DEGRADATION INJECTION ---
            # If we want to simulate a "Human" driver, we can inject specific 
            # Manuever parameters here if they aren't in the optim params.
            # For now, we assume the 'params' dict might contain 'Driver.Delay' etc.
            
            # --- HYBRID INJECTION LOGIC ---
            # 1. Bracket Method (<k_spring_f>): Good for custom templates.
            # 2. Key-Value Method (Spring.Front = X): Good for raw CM exports.
            
            for key, value in params.items():
                # Method 1: Explicit Placeholder (<key>)
                placeholder = f"<{key}>" 
                if placeholder in content:
                    content = content.replace(placeholder, str(value))
                
                # Method 2: Direct Infofile Replacement
                # Regex looks for "Key = Number" or "Key = [Number]"
                # This allows you to use a RAW export from CarMaker as a template!
                else:
                    # Pattern: Start of line or whitespace + Key + whitespace + = + whitespace + number
                    # We utilize regex to safely find and replace the value
                    # Example: "Spring.Front = 50000" -> "Spring.Front = 65000"
                    pattern = rf"({re.escape(key)}\s*=\s*)([\d\.\-eE]+)"
                    if re.search(pattern, content):
                        content = re.sub(pattern, f"\\g<1>{value}", content)
                    else:
                        # Only warn if we really expected it (usually we just use what matches)
                        # logger.debug(f"Parameter {key} not found via Regex or Placeholder.")
                        pass

            # Write the new physical file
            # Ensure the directory exists
            os.makedirs(os.path.dirname(new_run_path), exist_ok=True)
            
            with open(new_run_path, 'w') as f:
                f.write(content)
            
            # logger.debug(f"Generated configuration for {run_id}")
            return new_run_name

        except Exception as e:
            logger.error(f"Failed to create run configuration: {e}")
            raise e